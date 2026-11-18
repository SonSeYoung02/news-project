"""수집기 공용 SSRF 방어 및 스트리밍 응답 크기·시간 제한 HTTP 유틸리티."""

from __future__ import annotations

import contextlib
import contextvars
import ipaddress
import socket
import ssl
import threading
import time
import typing
import zlib
from collections.abc import Mapping
from urllib.parse import urlsplit

import httpcore
import httpx
from httpcore._backends.sync import SyncStream
from httpcore._exceptions import ConnectError, ConnectTimeout, ReadTimeout, WriteTimeout, map_exceptions
from httpx._config import DEFAULT_LIMITS, create_ssl_context

from config import (
    CRAWL_ALLOWED_PORTS,
    CRAWL_HEADERS,
    CRAWL_MAX_DNS_WORKERS,
    CRAWL_MAX_RAW_BYTES,
    CRAWL_MAX_REDIRECTS,
    CRAWL_MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
)

_MAX_ENCODING_LAYERS = 2
_ACTIVE_REQUEST_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "crawl_request_deadline",
    default=None,
)
_DEFAULT_DNS_SEMAPHORE = threading.BoundedSemaphore(CRAWL_MAX_DNS_WORKERS)

_DISALLOWED_HOSTNAMES = frozenset({"localhost", "ip6-localhost", "ip6-loopback"})
_DISALLOWED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".arpa")

_DISALLOWED_IPV4_NETWORKS = (
    ipaddress.IPv4Network("0.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.0.0.0/24"),
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("192.88.99.0/24"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("198.18.0.0/15"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
    ipaddress.IPv4Network("224.0.0.0/4"),
    ipaddress.IPv4Network("240.0.0.0/4"),
)

_DISALLOWED_IPV6_NETWORKS = (
    ipaddress.IPv6Network("::/128"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("::/96"),
    ipaddress.IPv6Network("64:ff9b::/96"),
    ipaddress.IPv6Network("64:ff9b:1::/48"),
    ipaddress.IPv6Network("100::/64"),
    ipaddress.IPv6Network("2001::/32"),
    ipaddress.IPv6Network("2001:2::/48"),
    ipaddress.IPv6Network("2001:db8::/32"),
    ipaddress.IPv6Network("2002::/16"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
    ipaddress.IPv6Network("fec0::/10"),
    ipaddress.IPv6Network("ff00::/8"),
)

_ALLOWED_MIME_BY_KIND: dict[str, frozenset[str]] = {
    "html": frozenset({"text/html", "application/xhtml+xml", "text/plain"}),
    "xml": frozenset({
        "application/rss+xml",
        "application/atom+xml",
        "application/rdf+xml",
        "application/xml",
        "text/xml",
        "text/html",
        "text/plain",
    }),
    "json": frozenset({"application/json", "text/json", "text/plain"}),
    "any": frozenset({
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "application/rss+xml",
        "application/atom+xml",
        "application/rdf+xml",
        "application/xml",
        "text/xml",
        "application/json",
        "text/json",
    }),
}


class UnsafeURLError(ValueError):
    """SSRF 정책에 위배되는 URL, 포트, 호스트 또는 IP 주소."""


class ResponseTooLargeError(ValueError):
    """응답 바이트 상한 초과."""


class UnsupportedContentTypeError(ValueError):
    """허용되지 않은 응답 MIME 또는 Content-Encoding."""


class RequestBudgetExceededError(httpx.TimeoutException):
    """리다이렉트와 스트리밍을 포함한 전체 요청 시간 예산 초과."""


IPAddress = typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]


def _check_ip_object(ip: IPAddress) -> None:
    if (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise UnsafeURLError(f"허용되지 않는 IP 주소입니다: {ip}")

    if isinstance(ip, ipaddress.IPv4Address):
        if any(ip in net for net in _DISALLOWED_IPV4_NETWORKS):
            raise UnsafeURLError(f"허용되지 않는 IPv4 대역입니다: {ip}")
        return

    if ip.is_site_local or any(ip in net for net in _DISALLOWED_IPV6_NETWORKS):
        raise UnsafeURLError(f"허용되지 않는 IPv6 대역입니다: {ip}")

    if ip.ipv4_mapped is not None:
        _check_ip_object(ip.ipv4_mapped)
    if ip.sixtofour is not None:
        _check_ip_object(ip.sixtofour)
    if ip.teredo is not None:
        _check_ip_object(ip.teredo[0])
        _check_ip_object(ip.teredo[1])


def validate_ip_address(ip_str: str) -> IPAddress:
    """문자열 IP 주소를 파싱해 공인 전역 라우팅 가능 주소인지 검증한다."""
    cleaned = ip_str.strip()
    if not cleaned or "%" in cleaned:
        raise UnsafeURLError(f"유효하지 않은 IP 주소 형식입니다: {ip_str!r}")
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError as exc:
        raise UnsafeURLError(f"IP 주소 파싱 실패: {ip_str!r}") from exc
    _check_ip_object(ip)
    return ip


def validate_host(host: str) -> str:
    """호스트명이 로컬·내부 도메인이나 비정규 IP 리터럴이 아닌지 검증한다."""
    if not host or "%" in host or "\\" in host or any(ord(c) < 32 or ord(c) == 127 or c.isspace() for c in host):
        raise UnsafeURLError(f"유효하지 않은 호스트입니다: {host!r}")

    normalized = host.rstrip(".").lower()
    if (
        not normalized
        or normalized in _DISALLOWED_HOSTNAMES
        or any(normalized.endswith(suffix) for suffix in _DISALLOWED_HOST_SUFFIXES)
    ):
        raise UnsafeURLError(f"로컬 또는 내부 호스트 접근이 차단되었습니다: {host!r}")

    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            socket.inet_aton(normalized)
        except OSError:
            return host
        raise UnsafeURLError(f"비정규 IPv4 주소 표기는 허용되지 않습니다: {host!r}")

    _check_ip_object(ip)
    return host


def validate_url(
    url: str | httpx.URL,
    *,
    allowed_ports: frozenset[int] = CRAWL_ALLOWED_PORTS,
) -> httpx.URL:
    """요청 URL의 스킴, userinfo, 포트, 호스트 및 리터럴 IP를 검증한다."""
    raw_url = str(url).strip()
    if not raw_url or any(ord(c) < 32 or ord(c) == 127 for c in raw_url):
        raise UnsafeURLError("비어 있거나 제어 문자를 포함한 URL은 허용되지 않습니다.")

    try:
        split = urlsplit(raw_url)
        explicit_port = split.port
    except ValueError as exc:
        raise UnsafeURLError(f"유효하지 않은 URL 포트입니다: {raw_url!r}") from exc

    if split.scheme.lower() not in ("http", "https"):
        raise UnsafeURLError(f"허용되지 않는 URL 스킴입니다: {split.scheme!r}")
    if split.username is not None or split.password is not None or "@" in split.netloc:
        raise UnsafeURLError("사용자정보(userinfo)가 포함된 URL은 허용되지 않습니다.")

    try:
        hx_url = httpx.URL(raw_url)
    except httpx.InvalidURL as exc:
        raise UnsafeURLError(f"유효하지 않은 URL입니다: {raw_url!r}") from exc

    if hx_url.scheme not in ("http", "https"):
        raise UnsafeURLError(f"허용되지 않는 URL 스킴입니다: {hx_url.scheme!r}")
    if hx_url.userinfo:
        raise UnsafeURLError("사용자정보(userinfo)가 포함된 URL은 허용되지 않습니다.")

    effective_port = explicit_port if explicit_port is not None else (443 if hx_url.scheme == "https" else 80)
    if effective_port not in allowed_ports:
        raise UnsafeURLError(f"허용되지 않는 포트입니다: {effective_port}")

    validate_host(hx_url.host)
    return hx_url


@contextlib.contextmanager
def _request_deadline_scope(deadline: float) -> typing.Iterator[None]:
    token = _ACTIVE_REQUEST_DEADLINE.set(deadline)
    try:
        yield
    finally:
        _ACTIVE_REQUEST_DEADLINE.reset(token)


class _DeadlineNetworkStream(httpcore.NetworkStream):
    """요청 전체 deadline의 남은 시간만 각 소켓 I/O 타임아웃으로 전달하는 스트림 래퍼."""

    def __init__(self, inner: httpcore.NetworkStream) -> None:
        self._inner = inner

    def _effective_timeout(self, timeout: float | None) -> tuple[float | None, float | None]:
        req_deadline = _ACTIVE_REQUEST_DEADLINE.get()
        if req_deadline is None:
            return timeout, None
        remaining = req_deadline - time.monotonic()
        if remaining <= 0:
            raise RequestBudgetExceededError("요청 시간 예산을 초과했습니다.")
        if timeout is None:
            return remaining, req_deadline
        return min(timeout, remaining), req_deadline

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        effective, req_deadline = self._effective_timeout(timeout)
        try:
            return self._inner.read(max_bytes, effective)
        except ReadTimeout as exc:
            if req_deadline is not None and time.monotonic() >= req_deadline:
                raise RequestBudgetExceededError("응답 수신 중 전체 시간 예산을 초과했습니다.") from exc
            raise

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        effective, req_deadline = self._effective_timeout(timeout)
        try:
            self._inner.write(buffer, effective)
        except WriteTimeout as exc:
            if req_deadline is not None and time.monotonic() >= req_deadline:
                raise RequestBudgetExceededError("요청 전송 중 전체 시간 예산을 초과했습니다.") from exc
            raise

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        effective, req_deadline = self._effective_timeout(timeout)
        try:
            tls_stream = self._inner.start_tls(
                ssl_context=ssl_context,
                server_hostname=server_hostname,
                timeout=effective,
            )
        except ConnectTimeout as exc:
            if req_deadline is not None and time.monotonic() >= req_deadline:
                raise RequestBudgetExceededError("TLS 핸드셰이크 중 전체 시간 예산을 초과했습니다.") from exc
            raise
        return _DeadlineNetworkStream(tls_stream)

    def close(self) -> None:
        self._inner.close()

    def get_extra_info(self, info: str) -> typing.Any:
        return self._inner.get_extra_info(info)


class SafeNetworkBackend(httpcore.SyncBackend):
    """제한된 DNS 조회와 검증된 IP 직접 연결로 DNS 재바인딩·시간 초과를 차단하는 백엔드."""

    def __init__(
        self,
        *,
        allowed_ports: frozenset[int] = CRAWL_ALLOWED_PORTS,
        max_dns_workers: int | None = None,
    ) -> None:
        self._allowed_ports = allowed_ports
        self._dns_semaphore = (
            threading.BoundedSemaphore(max_dns_workers)
            if max_dns_workers is not None
            else _DEFAULT_DNS_SEMAPHORE
        )

    @staticmethod
    def _raise_timeout(req_deadline: float | None, message: str) -> typing.NoReturn:
        if req_deadline is not None and time.monotonic() >= req_deadline:
            raise RequestBudgetExceededError(message)
        raise ConnectTimeout(message)

    def _resolve_addresses(
        self,
        host: str,
        port: int,
        deadline: float | None,
        req_deadline: float | None,
    ) -> list[typing.Any]:
        if deadline is None:
            try:
                return socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            except OSError as exc:
                raise ConnectError(str(exc)) from exc

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            self._raise_timeout(req_deadline, f"DNS 조회 시간 예산을 초과했습니다: {host}")

        if not self._dns_semaphore.acquire(timeout=remaining):
            self._raise_timeout(req_deadline, f"DNS 작업 슬롯 대기 시간을 초과했습니다: {host}")

        done = threading.Event()
        result: list[list[typing.Any]] = []
        error: list[BaseException] = []

        def _worker() -> None:
            try:
                result.append(
                    socket.getaddrinfo(host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                )
            except BaseException as exc:
                error.append(exc)
            finally:
                done.set()
                self._dns_semaphore.release()

        thread = threading.Thread(target=_worker, name="crawler-dns", daemon=True)
        try:
            thread.start()
        except BaseException:
            self._dns_semaphore.release()
            raise

        wait_remaining = deadline - time.monotonic()
        if wait_remaining <= 0 or not done.wait(timeout=wait_remaining):
            self._raise_timeout(req_deadline, f"DNS 조회 시간이 초과되었습니다: {host}")

        if error:
            exc = error[0]
            if isinstance(exc, OSError):
                raise ConnectError(str(exc)) from exc
            raise exc
        return result[0]

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[typing.Any] | None = None,
    ) -> httpcore.NetworkStream:
        if port not in self._allowed_ports:
            raise UnsafeURLError(f"허용되지 않는 TCP 포트입니다: {port}")
        validate_host(host)

        req_deadline = _ACTIVE_REQUEST_DEADLINE.get()
        local_deadline = (time.monotonic() + timeout) if timeout is not None else None
        if req_deadline is not None and local_deadline is not None:
            deadline: float | None = min(req_deadline, local_deadline)
        else:
            deadline = req_deadline if req_deadline is not None else local_deadline

        infos = self._resolve_addresses(host, port, deadline, req_deadline)
        if not infos:
            raise ConnectError(f"DNS 조회 결과가 없습니다: {host}")

        # 모든 반환 주소를 먼저 검증(fail-closed)해 공인+사설 혼합 DNS 레코드 악용을 차단한다.
        validated_targets: list[tuple[int, int, int, tuple[typing.Any, ...]]] = []
        for family, socktype, proto, _, sockaddr in infos:
            if family not in (socket.AF_INET, socket.AF_INET6) or not sockaddr:
                raise UnsafeURLError(f"허용되지 않는 주소 패밀리입니다: {family}")
            if family == socket.AF_INET6 and len(sockaddr) >= 4 and sockaddr[3] != 0:
                raise UnsafeURLError(f"IPv6 scope_id가 포함된 주소는 허용되지 않습니다: {sockaddr[0]}")
            validate_ip_address(sockaddr[0])
            validated_targets.append((family, socktype, proto, sockaddr))

        if socket_options is None:
            socket_options = ()

        exc_map = {socket.timeout: ConnectTimeout, OSError: ConnectError}
        last_exc: Exception | None = None
        with map_exceptions(exc_map):
            for family, socktype, proto, sockaddr in validated_targets:
                attempt_timeout: float | None = None
                if deadline is not None:
                    attempt_timeout = deadline - time.monotonic()
                    if attempt_timeout <= 0:
                        self._raise_timeout(req_deadline, f"TCP 연결 시간 예산을 초과했습니다: {host}")

                sock: socket.socket | None = None
                try:
                    sock = socket.socket(family, socktype, proto)
                    sock.settimeout(attempt_timeout)
                    if local_address is not None:
                        sock.bind((local_address, 0))
                    # 호스트명이 아니라 검증 완료된 sockaddr IP 튜플로 직접 연결해 2차 DNS 조회를 제거한다.
                    sock.connect(sockaddr)
                    for option in socket_options:
                        sock.setsockopt(*option)
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    return _DeadlineNetworkStream(SyncStream(sock))
                except OSError as exc:
                    last_exc = exc
                    if sock is not None:
                        with contextlib.suppress(OSError):
                            sock.close()
                    if deadline is not None and time.monotonic() >= deadline:
                        self._raise_timeout(req_deadline, f"TCP 연결 시간 예산을 초과했습니다: {host}")
            if last_exc is not None:
                raise last_exc
            raise ConnectError(f"연결 대상 주소가 없습니다: {host}")

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[typing.Any] | None = None,
    ) -> httpcore.NetworkStream:
        raise UnsafeURLError("Unix 도메인 소켓 연결은 허용되지 않습니다.")


class SafeHTTPTransport(httpx.HTTPTransport):
    """환경 프록시·안전하지 않은 DNS 연결을 차단하고 TLS/SNI를 유지하는 HTTPTransport."""

    def __init__(
        self,
        *,
        allowed_ports: frozenset[int] = CRAWL_ALLOWED_PORTS,
        verify: ssl.SSLContext | bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits = DEFAULT_LIMITS,
        retries: int = 0,
        socket_options: typing.Iterable[typing.Any] | None = None,
    ) -> None:
        super().__init__(
            verify=verify,
            trust_env=False,
            http1=http1,
            http2=http2,
            limits=limits,
            retries=retries,
            socket_options=socket_options,
        )
        ssl_context = create_ssl_context(verify=verify, trust_env=False)
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_context,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=http1,
            http2=http2,
            retries=retries,
            socket_options=socket_options,
            network_backend=SafeNetworkBackend(allowed_ports=allowed_ports),
        )


def create_safe_client(
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = REQUEST_TIMEOUT,
    max_redirects: int = CRAWL_MAX_REDIRECTS,
    allowed_ports: frozenset[int] = CRAWL_ALLOWED_PORTS,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """SSRF 방어·프록시 우회 차단이 적용된 수집용 httpx.Client를 생성한다."""
    merged_headers = {
        **CRAWL_HEADERS,
        "Accept-Encoding": "gzip, deflate",
    }
    if headers:
        merged_headers.update(headers)

    def _validate_request(request: httpx.Request) -> None:
        validate_url(request.url, allowed_ports=allowed_ports)

    return httpx.Client(
        headers=merged_headers,
        timeout=timeout,
        follow_redirects=False,
        max_redirects=max_redirects,
        trust_env=False,
        transport=transport if transport is not None else SafeHTTPTransport(allowed_ports=allowed_ports),
        event_hooks={"request": [_validate_request]},
    )


def _validate_content_type(content_type: str | None, expected_kind: str) -> None:
    if not content_type:
        return
    mime = content_type.split(";", 1)[0].strip().lower()
    if not mime:
        return

    allowed = _ALLOWED_MIME_BY_KIND.get(expected_kind, _ALLOWED_MIME_BY_KIND["any"])
    if mime in allowed:
        return
    if expected_kind == "xml" and mime.endswith("+xml"):
        return
    if expected_kind == "json" and mime.endswith("+json"):
        return
    if expected_kind == "any" and (mime.startswith("text/") or mime.endswith("+xml") or mime.endswith("+json")):
        return

    raise UnsupportedContentTypeError(f"허용되지 않는 MIME 타입입니다({expected_kind}): {mime}")


class _BoundedZlibDecoder:
    """max_length를 강제해 gzip/deflate 압축 폭탄을 조기 차단하는 스트리밍 디코더."""

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        self._raw_deflate_fallback = False
        self._first_chunk = True
        if encoding in ("gzip", "x-gzip"):
            self._decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)
        elif encoding == "deflate":
            self._decompressor = zlib.decompressobj(zlib.MAX_WBITS)
        else:
            raise UnsupportedContentTypeError(f"지원하지 않는 Content-Encoding입니다: {encoding}")

    def decode(self, data: bytes, remaining_budget: int) -> bytes:
        if not data:
            return b""
        if remaining_budget < 0:
            raise ResponseTooLargeError("해제된 응답 크기가 상한을 초과했습니다.")

        was_first = self._first_chunk
        self._first_chunk = False
        try:
            out = self._decompressor.decompress(data, max_length=remaining_budget + 1)
        except zlib.error as exc:
            if self.encoding == "deflate" and was_first and not self._raw_deflate_fallback:
                self._raw_deflate_fallback = True
                self._decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
                try:
                    out = self._decompressor.decompress(data, max_length=remaining_budget + 1)
                except zlib.error as inner_exc:
                    raise httpx.DecodingError(str(inner_exc)) from inner_exc
            else:
                raise httpx.DecodingError(str(exc)) from exc

        if len(out) > remaining_budget or self._decompressor.unconsumed_tail:
            raise ResponseTooLargeError("압축 해제된 응답 크기가 허용 상한을 초과했습니다.")
        return out

    def flush(self, remaining_budget: int) -> bytes:
        try:
            tail = self._decompressor.flush()
        except zlib.error as exc:
            raise httpx.DecodingError(str(exc)) from exc
        if len(tail) > remaining_budget:
            raise ResponseTooLargeError("압축 해제된 응답 크기가 허용 상한을 초과했습니다.")
        return tail


def _build_decoders(resp: httpx.Response) -> list[_BoundedZlibDecoder]:
    encodings = [
        value.strip().lower()
        for value in resp.headers.get_list("content-encoding", split_commas=True)
        if value.strip() and value.strip().lower() != "identity"
    ]
    if len(encodings) > _MAX_ENCODING_LAYERS:
        raise UnsupportedContentTypeError(f"중첩 Content-Encoding이 너무 많습니다: {len(encodings)}")
    # HTTP Content-Encoding은 적용 순서대로 나열되므로 디코딩은 역순으로 수행한다.
    return [_BoundedZlibDecoder(enc) for enc in reversed(encodings)]


def _check_content_length_header(resp: httpx.Response, max_raw_bytes: int) -> None:
    raw_len = resp.headers.get("content-length")
    if not raw_len:
        return
    try:
        declared = int(raw_len.strip())
    except ValueError:
        return
    if declared > max_raw_bytes:
        raise ResponseTooLargeError(
            f"Content-Length({declared})가 허용 상한({max_raw_bytes})을 초과했습니다."
        )


def _read_bounded_body(
    resp: httpx.Response,
    *,
    max_bytes: int,
    max_raw_bytes: int,
    deadline: float,
) -> bytes:
    if hasattr(resp, "_content"):
        if time.monotonic() > deadline:
            raise RequestBudgetExceededError("요청 시간 예산을 초과했습니다.")
        body = resp._content
        if len(body) > max_bytes:
            raise ResponseTooLargeError(
                f"응답 크기({len(body)})가 허용 상한({max_bytes})을 초과했습니다."
            )
        return body

    decoders = _build_decoders(resp)
    raw_total = 0
    decoded_total = 0
    chunks: list[bytes] = []

    for raw_chunk in resp.iter_raw(chunk_size=None):
        if time.monotonic() > deadline:
            raise RequestBudgetExceededError("응답 스트리밍 중 전체 시간 예산을 초과했습니다.")

        raw_total += len(raw_chunk)
        if raw_total > max_raw_bytes:
            raise ResponseTooLargeError(
                f"원시 응답 크기({raw_total})가 허용 상한({max_raw_bytes})을 초과했습니다."
            )

        data = raw_chunk
        if not decoders:
            decoded_total += len(data)
            if decoded_total > max_bytes:
                raise ResponseTooLargeError(
                    f"응답 크기({decoded_total})가 허용 상한({max_bytes})을 초과했습니다."
                )
        else:
            for idx, decoder in enumerate(decoders):
                # 마지막 디코더는 최종 출력 바이트 예산, 중간 디코더도 동일 상한으로 폭탄 증폭을 제한한다.
                budget = (max_bytes - decoded_total) if idx == len(decoders) - 1 else max_bytes
                data = decoder.decode(data, budget)
            decoded_total += len(data)
            if decoded_total > max_bytes:
                raise ResponseTooLargeError(
                    f"압축 해제된 응답 크기({decoded_total})가 허용 상한({max_bytes})을 초과했습니다."
                )

        if data:
            chunks.append(data)

    if decoders:
        for idx, decoder in enumerate(decoders):
            budget = (max_bytes - decoded_total) if idx == len(decoders) - 1 else max_bytes
            tail = decoder.flush(budget)
            for next_decoder in decoders[idx + 1 :]:
                tail = next_decoder.decode(tail, max_bytes - decoded_total)
            decoded_total += len(tail)
            if decoded_total > max_bytes:
                raise ResponseTooLargeError(
                    f"압축 해제된 응답 크기({decoded_total})가 허용 상한({max_bytes})을 초과했습니다."
                )
            if tail:
                chunks.append(tail)

    if time.monotonic() > deadline:
        raise RequestBudgetExceededError("요청 시간 예산을 초과했습니다.")

    return b"".join(chunks)


def safe_get(
    client: httpx.Client,
    url: str | httpx.URL,
    *,
    params: typing.Any = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = REQUEST_TIMEOUT,
    max_bytes: int = CRAWL_MAX_RESPONSE_BYTES,
    max_raw_bytes: int | None = None,
    max_redirects: int = CRAWL_MAX_REDIRECTS,
    expected_kind: str = "any",
    allowed_ports: frozenset[int] = CRAWL_ALLOWED_PORTS,
    raise_for_status: bool = True,
) -> httpx.Response:
    """URL·리다이렉트·MIME·압축해제 바이트 상한·시간 예산을 강제하여 GET 요청을 수행한다."""
    total_budget = float(timeout)
    deadline = time.monotonic() + total_budget
    effective_max_raw = (
        max_raw_bytes
        if max_raw_bytes is not None
        else min(CRAWL_MAX_RAW_BYTES, max_bytes + 1024)
    )
    target = httpx.URL(url, params=params) if params is not None else url
    current_url = validate_url(target, allowed_ports=allowed_ports)
    history: list[httpx.Response] = []

    with _request_deadline_scope(deadline):
        for hop in range(max_redirects + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RequestBudgetExceededError("요청 시간 예산을 초과했습니다.")

            hop_timeout = httpx.Timeout(
                remaining,
                connect=min(10.0, remaining),
                read=remaining,
                write=remaining,
                pool=remaining,
            )

            with client.stream(
                "GET",
                str(current_url),
                headers=dict(headers) if headers else None,
                timeout=hop_timeout,
                follow_redirects=False,
            ) as resp:
                if resp.has_redirect_location:
                    if hop >= max_redirects:
                        raise UnsafeURLError(f"리다이렉트 허용 횟수({max_redirects})를 초과했습니다.")
                    if resp.next_request is None:
                        raise UnsafeURLError("리다이렉트 대상 URL을 확인할 수 없습니다.")
                    next_url = validate_url(resp.next_request.url, allowed_ports=allowed_ports)
                    history.append(resp)
                    current_url = next_url
                    continue

                if raise_for_status:
                    resp.raise_for_status()

                if resp.status_code < 400:
                    _validate_content_type(resp.headers.get("content-type"), expected_kind)
                _check_content_length_header(resp, effective_max_raw)
                body = _read_bounded_body(
                    resp,
                    max_bytes=max_bytes,
                    max_raw_bytes=effective_max_raw,
                    deadline=deadline,
                )
                resp.history = history
                resp._content = body
                return resp

    raise UnsafeURLError(f"리다이렉트 허용 횟수({max_redirects})를 초과했습니다.")

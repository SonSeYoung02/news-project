import gzip
import http.server
import os
import socket
import ssl
import threading
import unittest
import zlib
from unittest.mock import patch

import httpx

from crawlers import _rss, arxiv, devto, geeknews, github_trending, google_news, huggingface, naver, reddit_ai
from crawlers._http import (
    RequestBudgetExceededError,
    ResponseTooLargeError,
    SafeHTTPTransport,
    SafeNetworkBackend,
    UnsafeURLError,
    UnsupportedContentTypeError,
    create_safe_client,
    safe_get,
    validate_ip_address,
    validate_url,
)


class CountingStream(httpx.SyncByteStream):
    def __init__(self, block_size: int = 65536, blocks: int = 32, payload_byte: bytes = b"A") -> None:
        self.block_size = block_size
        self.blocks = blocks
        self.payload_byte = payload_byte
        self.bytes_read = 0
        self.closed = False

    def __iter__(self):
        for _ in range(self.blocks):
            block = self.payload_byte * self.block_size
            self.bytes_read += len(block)
            yield block

    def close(self) -> None:
        self.closed = True


class ChunkedBytesStream(httpx.SyncByteStream):
    def __init__(self, data: bytes, chunk_size: int = 1024) -> None:
        self.data = data
        self.chunk_size = chunk_size
        self.bytes_read = 0
        self.closed = False

    def __iter__(self):
        for i in range(0, len(self.data), self.chunk_size):
            chunk = self.data[i : i + self.chunk_size]
            self.bytes_read += len(chunk)
            yield chunk

    def close(self) -> None:
        self.closed = True


class TestUrlAndIpValidation(unittest.TestCase):
    def test_blocks_disallowed_schemes_userinfo_ports_and_local_hosts(self):
        bad_urls = [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "gopher://127.0.0.1:6379/_INFO",
            "javascript:alert(1)",
            "https://user:pass@example.com/article",
            "https://news.google.com@127.0.0.1/admin",
            "http://example.com:22/",
            "https://example.com:6379/",
            "http://example.com:8080/internal",
            "http://example.com:99999/",
            "http://localhost/admin",
            "http://localhost./admin",
            "http://sub.localhost/admin",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://service.internal/metrics",
            "http://printer.local/",
            "http://2130706433/",
            "http://0177.0.0.1/",
            "http://0x7f.0.0.1/",
            "http://127.1/",
            "http://[fe80::1%25eth0]/",
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsafeURLError):
                    validate_url(url)

    def test_blocks_private_loopback_link_local_reserved_ipv4_and_ipv6(self):
        bad_ips = [
            "127.0.0.1",
            "127.0.0.2",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "0.1.2.3",
            "224.0.0.1",
            "255.255.255.255",
            "192.0.2.1",
            "198.18.0.1",
            "::1",
            "::",
            "fe80::1",
            "fc00::1",
            "fd12:3456:789a::1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "64:ff9b::127.0.0.1",
            "2002:7f00:1::",
        ]
        for ip_str in bad_ips:
            with self.subTest(ip=ip_str):
                with self.assertRaises(UnsafeURLError):
                    validate_ip_address(ip_str)
                host = f"[{ip_str}]" if ":" in ip_str else ip_str
                with self.assertRaises(UnsafeURLError):
                    validate_url(f"http://{host}/")

    def test_allows_valid_public_urls(self):
        good_urls = [
            "https://news.google.com/rss/search?q=AI",
            "http://example.com/news",
            "http://example.com:80/news",
            "https://example.com:443/news",
            "https://[2606:2800:220:1:248:1893:25c8:1946]/article",
        ]
        for url in good_urls:
            with self.subTest(url=url):
                parsed = validate_url(url)
                self.assertIn(parsed.scheme, ("http", "https"))


class TestRedirectAndDnsSecurity(unittest.TestCase):
    def test_safe_get_blocks_ssrf_redirect_and_does_not_read_redirect_body(self):
        redirect_body = CountingStream(block_size=65536, blocks=32)
        requested = []

        def respond(req: httpx.Request) -> httpx.Response:
            requested.append(str(req.url))
            if req.url.host == "publisher.example":
                return httpx.Response(
                    302,
                    headers={"Location": "http://169.254.169.254/latest/meta-data/"},
                    stream=redirect_body,
                )
            return httpx.Response(200, text="SECRET")

        with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
            with self.assertRaises(UnsafeURLError):
                safe_get(client, "https://publisher.example/article")

        self.assertEqual(requested, ["https://publisher.example/article"])
        self.assertEqual(redirect_body.bytes_read, 0)

    def test_safe_get_allows_safe_redirects_and_caps_redirect_hops(self):
        def respond(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/start":
                return httpx.Response(302, headers={"Location": "/hop1"})
            if req.url.path == "/hop1":
                return httpx.Response(302, headers={"Location": "https://cdn.example/final"})
            if req.url.host == "cdn.example" and req.url.path == "/final":
                return httpx.Response(200, text="OK BODY", headers={"Content-Type": "text/html"})
            return httpx.Response(302, headers={"Location": "/loop"})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            resp = safe_get(client, "https://publisher.example/start", expected_kind="html")
            self.assertEqual(resp.text, "OK BODY")

            with self.assertRaises(UnsafeURLError):
                safe_get(client, "https://publisher.example/loop", max_redirects=3)

    def test_safe_network_backend_blocks_private_and_mixed_dns_before_connect(self):
        backend = SafeNetworkBackend()
        mixed_records = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ]
        with patch("socket.getaddrinfo", return_value=mixed_records), patch("socket.socket") as mock_sock:
            with self.assertRaises(UnsafeURLError):
                backend.connect_tcp("dual.example", 443, timeout=5.0)
            mock_sock.assert_not_called()

        for v6_ip in ("::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1"):
            v6_records = [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (v6_ip, 443, 0, 0))]
            with patch("socket.getaddrinfo", return_value=v6_records), patch("socket.socket") as mock_sock:
                with self.assertRaises(UnsafeURLError):
                    backend.connect_tcp("v6.example", 443, timeout=5.0)
                mock_sock.assert_not_called()

        with self.assertRaises(UnsafeURLError):
            backend.connect_unix_socket("/tmp/docker.sock")

    def test_safe_network_backend_prevents_dns_rebinding_and_preserves_sni(self):
        backend = SafeNetworkBackend()
        public_record = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        rebound_record = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]

        connect_calls = []

        class FakeSocket:
            def settimeout(self, t):
                pass

            def setsockopt(self, *args):
                pass

            def connect(self, addr):
                connect_calls.append(addr)

            def close(self):
                pass

        # Even if a second DNS lookup WOULD return 127.0.0.1, connect_tcp uses only the first lookup's IP.
        with patch("socket.getaddrinfo", side_effect=[public_record, rebound_record]) as mock_gai:
            with patch("socket.socket", return_value=FakeSocket()):
                stream = backend.connect_tcp("rebind.example", 443, timeout=5.0)
                stream.close()
                self.assertEqual(mock_gai.call_count, 1)
                self.assertEqual(connect_calls, [("93.184.216.34", 443)])

        # A subsequent TCP connection after DNS rebound to 127.0.0.1 must be blocked.
        with patch("socket.getaddrinfo", return_value=rebound_record):
            with patch("socket.socket") as mock_sock:
                with self.assertRaises(UnsafeURLError):
                    backend.connect_tcp("rebind.example", 443, timeout=5.0)
                mock_sock.assert_not_called()

    def test_tls_sni_and_host_header_use_original_hostname_over_pinned_ip(self):
        public_record = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        captured = {}

        class FakeConnectedStream:
            def __init__(self):
                self._closed = False
                self._chunks = [
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello",
                    b"",
                ]

            def start_tls(self, ssl_context, server_hostname=None, timeout=None):
                captured["sni_hostname"] = server_hostname
                captured["check_hostname"] = ssl_context.check_hostname
                captured["verify_mode"] = ssl_context.verify_mode
                return self

            def write(self, data, timeout=None):
                captured["raw_request"] = captured.get("raw_request", b"") + data

            def read(self, max_bytes, timeout=None):
                return self._chunks.pop(0) if self._chunks else b""

            def close(self):
                self._closed = True

            def get_extra_info(self, info):
                return None

        backend = SafeNetworkBackend()

        def fake_connect_tcp(host, port, timeout=None, local_address=None, socket_options=None):
            # Run real resolution + validation inside SafeNetworkBackend without real external TCP.
            with patch("socket.getaddrinfo", return_value=public_record):
                class RecordingSock:
                    def settimeout(self, t):
                        pass
                    def setsockopt(self, *args):
                        pass
                    def connect(self, addr):
                        captured["connected_addr"] = addr
                    def close(self):
                        pass
                with patch("socket.socket", return_value=RecordingSock()):
                    SafeNetworkBackend.connect_tcp(
                        backend, host, port, timeout=timeout, local_address=local_address, socket_options=socket_options
                    ).close()
            return FakeConnectedStream()

        transport = SafeHTTPTransport()
        transport._pool._network_backend.connect_tcp = fake_connect_tcp

        with create_safe_client(transport=transport) as client:
            resp = safe_get(client, "https://publisher.example/article", expected_kind="html")

        self.assertEqual(resp.text, "hello")
        self.assertEqual(captured["connected_addr"], ("93.184.216.34", 443))
        self.assertEqual(captured["sni_hostname"], "publisher.example")
        self.assertTrue(captured["check_hostname"])
        self.assertEqual(captured["verify_mode"], ssl.CERT_REQUIRED)
        self.assertIn(b"Host: publisher.example\r\n", captured["raw_request"])

    def test_ignores_environment_proxy_settings(self):
        with patch.dict(
            os.environ,
            {
                "HTTP_PROXY": "http://127.0.0.1:8888",
                "HTTPS_PROXY": "http://127.0.0.1:8888",
                "ALL_PROXY": "http://127.0.0.1:8888",
            },
        ):
            with create_safe_client() as client:
                self.assertFalse(client._trust_env)
                self.assertEqual(client._mounts, {})

    def test_real_loopback_server_never_receives_request(self):
        hits = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append(self.path)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"secret")

            def log_message(self, format, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with create_safe_client(allowed_ports=frozenset({80, 443, port})) as client:
                with self.assertRaises(UnsafeURLError):
                    safe_get(client, f"http://127.0.0.1:{port}/internal", allowed_ports=frozenset({80, 443, port}))
            self.assertEqual(hits, [])
        finally:
            server.shutdown()
            server.server_close()


class TestStreamingSizeBudgetAndMime(unittest.TestCase):
    def test_stream_byte_limit_stops_early(self):
        stream = CountingStream(block_size=65536, blocks=32)  # 2 MiB total

        def respond(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream, headers={"Content-Type": "text/html"})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ResponseTooLargeError):
                safe_get(client, "https://publisher.example/large", max_bytes=262144, max_raw_bytes=262144)

        self.assertLess(stream.bytes_read, 2_097_152)
        self.assertLessEqual(stream.bytes_read, 327680)
        self.assertTrue(stream.closed)

    def test_gzip_decompression_bomb_stops_at_max_bytes(self):
        bomb = gzip.compress(b"A" * 5_000_000)  # ~5 KB compressed -> 5 MB uncompressed
        self.assertLess(len(bomb), 50_000)
        stream = ChunkedBytesStream(bomb, chunk_size=1024)

        def respond(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=stream,
                headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ResponseTooLargeError):
                safe_get(client, "https://publisher.example/bomb", max_bytes=65536, max_raw_bytes=1_048_576)

        self.assertTrue(stream.closed)

    def test_oversized_content_length_rejects_before_reading_stream(self):
        stream = CountingStream(block_size=1024, blocks=10)

        def respond(req: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                stream=stream,
                headers={"Content-Type": "text/html", "Content-Length": "50000000"},
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ResponseTooLargeError):
                safe_get(client, "https://publisher.example/huge")

        self.assertEqual(stream.bytes_read, 0)

    def test_time_budget_exceeded_aborts_slow_stream(self):
        stream = CountingStream(block_size=1024, blocks=10)

        def respond(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream, headers={"Content-Type": "text/html"})

        ticks = iter([0.0, 0.5, 2.0, 2.5])
        with patch("crawlers._http.time.monotonic", side_effect=lambda: next(ticks)):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(RequestBudgetExceededError):
                    safe_get(client, "https://publisher.example/slow", timeout=1.0)

    def test_disallowed_mime_type_aborts_before_reading_body(self):
        stream = CountingStream(block_size=1024, blocks=5)

        def respond(req: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=stream, headers={"Content-Type": "application/pdf"})

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(UnsupportedContentTypeError):
                safe_get(client, "https://publisher.example/doc.pdf", expected_kind="html")

        self.assertEqual(stream.bytes_read, 0)

    def test_deflate_and_chained_content_encoding_decode_and_bomb_protection(self):
        raw_comp = zlib.compressobj(level=9, wbits=-zlib.MAX_WBITS)
        raw_deflate_bytes = raw_comp.compress(b"hello raw deflate") + raw_comp.flush()
        chained_bytes = zlib.compress(gzip.compress(b"hello chained gzip+deflate"))

        def respond(req: httpx.Request) -> httpx.Response:
            if req.url.path == "/raw-deflate":
                return httpx.Response(
                    200,
                    stream=ChunkedBytesStream(raw_deflate_bytes, chunk_size=8),
                    headers={"Content-Type": "text/plain", "Content-Encoding": "deflate"},
                )
            if req.url.path == "/chained":
                return httpx.Response(
                    200,
                    stream=ChunkedBytesStream(chained_bytes, chunk_size=8),
                    headers={"Content-Type": "text/plain", "Content-Encoding": "gzip, deflate"},
                )
            bomb = zlib.compress(b"Z" * 2_000_000)
            return httpx.Response(
                200,
                stream=ChunkedBytesStream(bomb, chunk_size=512),
                headers={"Content-Type": "text/plain", "Content-Encoding": "deflate"},
            )

        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            self.assertEqual(safe_get(client, "https://publisher.example/raw-deflate").text, "hello raw deflate")
            self.assertEqual(safe_get(client, "https://publisher.example/chained").text, "hello chained gzip+deflate")
            with self.assertRaises(ResponseTooLargeError):
                safe_get(client, "https://publisher.example/deflate-bomb", max_bytes=32768)


class TestAllCrawlersSecurityAndRegression(unittest.TestCase):
    def test_google_news_blocks_redirect_ssrf_and_oversize_while_preserving_normal_and_fallback(self):
        for destination in (
            "http://127.0.0.1/internal",
            "http://192.168.0.1/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/internal",
            "http://[::ffff:127.0.0.1]/internal",
            "file:///etc/passwd",
        ):
            requested = []
            sentinel = "INTERNAL_SECRET_BODY " * 30

            def respond(req: httpx.Request, dest=destination) -> httpx.Response:
                requested.append(str(req.url))
                if req.url.host == "news.google.com":
                    return httpx.Response(
                        200,
                        text=(
                            "<rss><channel><item>"
                            "<title>AI News</title>"
                            "<link>https://publisher.example/article</link>"
                            "<description>RSS fallback text</description>"
                            "</item></channel></rss>"
                        ),
                    )
                if req.url.host == "publisher.example":
                    return httpx.Response(302, headers={"Location": dest})
                return httpx.Response(200, text=f"<article>{sentinel}</article>")

            with httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=True) as client:
                with patch.object(google_news.trafilatura, "extract", return_value=sentinel):
                    articles = google_news._fetch_query(client, "test", "AI", set())

            self.assertNotIn(destination, requested)
            self.assertEqual(len(articles), 1)
            self.assertEqual(articles[0]["content"], "RSS fallback text")

        # Oversized stream triggers early stop and returns fallback
        stream = CountingStream(block_size=65536, blocks=32)
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=stream))) as client:
            with patch.object(google_news.trafilatura, "extract", return_value="A" * 9000):
                content = google_news._fetch_article_content(client, "https://publisher.example/large", "fallback")
        self.assertEqual(content, "fallback")
        self.assertLess(stream.bytes_read, 2_097_152)

        # Normal article extraction capped at 8000 chars
        normal_body = "Normal English AI article body. " * 400
        gn_transport = httpx.MockTransport(
            lambda r: (
                httpx.Response(
                    200,
                    text=(
                        "<rss><channel><item><title>Good</title>"
                        "<link>https://publisher.example/good</link>"
                        "<description>desc</description></item></channel></rss>"
                    ),
                )
                if r.url.host == "news.google.com"
                else httpx.Response(
                    200,
                    text=f"<html><body><article>{normal_body}</article></body></html>",
                    headers={"Content-Type": "text/html"},
                )
            )
        )
        with patch(
            "crawlers.google_news.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=gn_transport, **kw),
        ):
            with patch.object(google_news.trafilatura, "extract", return_value=normal_body):
                articles = google_news.fetch()
        self.assertEqual(len(articles), 1)
        self.assertEqual(len(articles[0]["content"]), 8000)

    def test_naver_blocks_unsafe_href_and_redirect_and_preserves_normal_crawl(self):
        requested = []
        long_korean = "국내 인공지능 산업이 빠르게 성장하고 있습니다. " * 5

        def respond(req: httpx.Request) -> httpx.Response:
            requested.append(str(req.url))
            if "main.naver" in req.url.path:
                return httpx.Response(
                    200,
                    text=(
                        '<html><body>'
                        '<a href="//127.0.0.1/article?id=1">로컬 내부 기사 제목입니다</a>'
                        '<a href="/article/good1">정상 네이버 기사 제목입니다</a>'
                        '<a href="https://evil.example/article/redir">리다이렉트 기사 제목입니다</a>'
                        "</body></html>"
                    ),
                    headers={"Content-Type": "text/html"},
                )
            if req.url.host == "news.naver.com" and req.url.path == "/article/good1":
                return httpx.Response(
                    200,
                    text=f'<html><body><div id="dic_area">{long_korean}</div></body></html>',
                    headers={"Content-Type": "text/html"},
                )
            if req.url.host == "evil.example":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
            return httpx.Response(200, text='<div id="dic_area">INTERNAL SECRET</div>')

        with patch(
            "crawlers.naver.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(respond), **kw),
        ):
            articles = naver.fetch()

        self.assertFalse(any("127.0.0.1" in u for u in requested))
        self.assertTrue(len(articles) >= 1)
        self.assertEqual(articles[0]["url"], "https://news.naver.com/article/good1")
        self.assertIn("국내 인공지능 산업", articles[0]["content"])

    def test_geeknews_falls_back_when_primary_redirects_to_internal_ip(self):
        requested = []

        def respond(req: httpx.Request) -> httpx.Response:
            requested.append(str(req.url))
            if req.url.host == "feeds.feedburner.com":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/admin"})
            return httpx.Response(
                200,
                text=(
                    '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
                    "<title>GeekNews 정상 글</title>"
                    '<link href="https://news.hada.io/topic?id=1"/>'
                    "<content type='text'>정상 본문 내용입니다</content>"
                    "</entry></feed>"
                ),
                headers={"Content-Type": "application/atom+xml"},
            )

        with patch(
            "crawlers.geeknews.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(respond), **kw),
        ):
            articles = geeknews.fetch()

        self.assertNotIn("http://127.0.0.1/admin", requested)
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "GeekNews 정상 글")

    def test_reddit_github_huggingface_arxiv_devto_and_rss(self):
        # Reddit AI: normal & blocked redirect
        reddit_xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>Local LLM benchmark</title>"
            '<link href="https://www.reddit.com/r/LocalLLaMA/comments/1"/>'
            "<content type='text'>Detailed benchmark results for open-weight models.</content>"
            "</entry></feed>"
        )
        reddit_headers_seen = []

        def reddit_ok(req: httpx.Request) -> httpx.Response:
            reddit_headers_seen.append(req.headers.get("user-agent"))
            return httpx.Response(200, text=reddit_xml, headers={"Content-Type": "application/atom+xml"})

        with patch(
            "crawlers.reddit_ai.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(reddit_ok), **kw),
        ):
            self.assertEqual(len(reddit_ai.fetch()), 2)
        self.assertTrue(all("news-crawling-project/1.0" in (ua or "") for ua in reddit_headers_seen))

        # GitHub Trending: normal & blocks redirect to internal IP
        gh_html = (
            '<html><body><article class="Box-row">'
            '<h2><a href="/org/ai-repo">org / ai-repo</a></h2>'
            "<p>Open source AI agent toolkit</p>"
            '<span itemprop="programmingLanguage">Python</span>'
            "</article></body></html>"
        )
        with patch(
            "crawlers.github_trending.create_safe_client",
            side_effect=lambda **kw: create_safe_client(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, text=gh_html, headers={"Content-Type": "text/html"})
                ),
                **kw,
            ),
        ):
            gh_items = github_trending.fetch()
        self.assertEqual(len(gh_items), 1)
        self.assertEqual(gh_items[0]["source"], "GitHub Trending")

        with patch(
            "crawlers.github_trending.create_safe_client",
            side_effect=lambda **kw: create_safe_client(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
                    if r.url.host == "github.com"
                    else httpx.Response(200, text="SECRET")
                ),
                **kw,
            ),
        ):
            self.assertEqual(github_trending.fetch(), [])

        # Hugging Face: blog redirect SSRF falls back to papers
        hf_papers_html = '<html><body><a href="/papers/2601.00001"><h3>New Transformer Paper</h3></a></body></html>'
        hf_requested = []

        def hf_respond(req: httpx.Request) -> httpx.Response:
            hf_requested.append(str(req.url))
            if "feed.xml" in req.url.path:
                return httpx.Response(302, headers={"Location": "http://192.168.0.1/"})
            return httpx.Response(200, text=hf_papers_html, headers={"Content-Type": "text/html"})

        with patch(
            "crawlers.huggingface.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(hf_respond), **kw),
        ):
            hf_items = huggingface.fetch()
        self.assertNotIn("http://192.168.0.1/", hf_requested)
        self.assertEqual(len(hf_items), 1)
        self.assertEqual(hf_items[0]["title"], "New Transformer Paper")

        # arXiv: 429 retry works & normal parse works
        arxiv_xml = (
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>Paper Title</title>"
            "<summary>Paper summary text.</summary>"
            '<link rel="alternate" href="https://arxiv.org/abs/2601.00001"/>'
            "</entry></feed>"
        )
        attempts = {"count": 0}

        def arxiv_respond(req: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, text=arxiv_xml, headers={"Content-Type": "application/atom+xml"})

        with patch(
            "crawlers.arxiv.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(arxiv_respond), **kw),
        ), patch("crawlers.arxiv.time.sleep"):
            arxiv_items = arxiv.fetch()
        self.assertEqual(attempts["count"], 2)
        self.assertEqual(len(arxiv_items), 1)

        # dev.to: valid id fetches body_markdown, invalid/redirect detail falls back to description, bad id ignored
        devto_requested = []

        def devto_respond(req: httpx.Request) -> httpx.Response:
            devto_requested.append(str(req.url))
            if req.url.path == "/api/articles":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 101,
                            "title": "Good Post",
                            "url": "https://dev.to/u/good",
                            "description": "Short desc 1",
                            "tag_list": ["ai"],
                        },
                        {
                            "id": 202,
                            "title": "Redirect Detail Post",
                            "url": "https://dev.to/u/redir",
                            "description": "Fallback desc 2",
                            "tag_list": ["llm"],
                        },
                        {
                            "id": "999/../../admin",
                            "title": "Bad ID Post",
                            "url": "https://dev.to/u/badid",
                            "description": "Fallback bad id",
                            "tag_list": [],
                        },
                    ],
                )
            if req.url.path == "/api/articles/101":
                return httpx.Response(200, json={"body_markdown": "Full markdown body " * 20})
            if req.url.path == "/api/articles/202":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
            return httpx.Response(200, json={"body_markdown": "LEAKED"})

        with patch(
            "crawlers.devto.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(devto_respond), **kw),
        ):
            devto_items = devto.fetch()

        self.assertFalse(any("127.0.0.1" in u for u in devto_requested))
        self.assertFalse(any("admin" in u for u in devto_requested))
        self.assertEqual(len(devto_items), 3)
        self.assertTrue(devto_items[0]["content"].startswith("Full markdown body"))
        self.assertEqual(devto_items[1]["content"], "Fallback desc 2\nTags: llm")
        self.assertEqual(devto_items[2]["content"], "Fallback bad id")

        # _rss helper: blocks internal redirect and falls back to RSS description
        rss_requested = []

        def rss_respond(req: httpx.Request) -> httpx.Response:
            rss_requested.append(str(req.url))
            if req.url.path == "/feed.xml":
                return httpx.Response(
                    200,
                    text=(
                        "<rss><channel><item>"
                        "<title>RSS Item</title>"
                        "<link>https://publisher.example/post</link>"
                        "<description>RSS Safe Description</description>"
                        "</item></channel></rss>"
                    ),
                )
            if req.url.host == "publisher.example":
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
            return httpx.Response(200, text="<article>INTERNAL</article>")

        with patch(
            "crawlers._rss.create_safe_client",
            side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(rss_respond), **kw),
        ):
            rss_items = _rss.fetch_rss("https://feed.example/feed.xml", "TestRSS")

        self.assertNotIn("http://127.0.0.1/secret", rss_requested)
        self.assertEqual(len(rss_items), 1)
        self.assertEqual(rss_items[0]["content"], "RSS Safe Description")


if __name__ == "__main__":
    unittest.main()

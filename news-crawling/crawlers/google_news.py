import base64
import binascii
import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

from ._http import create_safe_client, safe_get, safe_post

logger = logging.getLogger(__name__)

_BASE_URL = "https://news.google.com/rss/search"
_BATCHEXECUTE_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je"
_GOOGLE_ARTICLE_PREFIXES = ("/rss/articles/", "/articles/", "/read/")
_DEFAULT_GARTURL_CONTEXT = [
    ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None, None, 0, 1],
    "X",
    "X",
    1,
    [1, 1, 1],
    1,
    1,
    None,
    0,
    0,
    None,
    0,
]
_MIN_BODY_LENGTH = 200
_MAX_BODY_LENGTH = 8000
_QUERIES = [
    ("global economy OR markets OR business", "경제"),
    ("artificial intelligence OR LLM OR generative AI", "AI"),
]


def fetch() -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    try:
        with create_safe_client() as client:
            for query, category in _QUERIES:
                articles.extend(_fetch_query(client, query, category, seen_urls))
    except Exception as e:
        logger.error("Google News 외국 뉴스 크롤링 실패: %s", e)
        return []
    return articles


def _fetch_query(
    client: httpx.Client,
    query: str,
    category: str,
    seen_urls: set[str],
) -> list[dict[str, Any]]:
    params = urlencode(
        {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
    )
    resp = safe_get(client, f"{_BASE_URL}?{params}", timeout=REQUEST_TIMEOUT, expected_kind="xml")

    soup = BeautifulSoup(resp.text, "lxml-xml")
    articles = []
    for item in soup.find_all("item")[:10]:
        title = item.find("title")
        link = item.find("link")
        if not title or not link:
            continue

        url = link.get_text(strip=True)
        if not url.lower().startswith(("http://", "https://")):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        pub_date = item.find("pubDate")
        description = item.find("description")
        fallback = BeautifulSoup(
            description.get_text(" ", strip=True) if description else "",
            "html.parser",
        ).get_text(" ", strip=True)

        content = _fetch_article_content(client, url, fallback)

        articles.append(
            {
                "url": url,
                "source": "Google News",
                "title": title.get_text(strip=True),
                "content": content,
                "published_at": pub_date.get_text(strip=True) if pub_date else datetime.now().isoformat(),
                "crawled_at": datetime.now().isoformat(),
                "major_category": category,
                "translate_to_korean": True,
            }
        )
    return articles


def _is_google_news_article_url(url: str) -> bool:
    """Google News 중간 기사 링크인지 판별한다."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if host != "news.google.com":
        return False
    return _extract_article_id(url) is not None


def _extract_article_id(url: str) -> str | None:
    """Google News 기사 URL 경로에서 base64 토큰(article_id)을 추출한다."""
    path = urlsplit(url).path.rstrip("/")
    for prefix in _GOOGLE_ARTICLE_PREFIXES:
        if path.startswith(prefix):
            article_id = path[len(prefix) :].split("/", 1)[0].strip()
            return article_id or None
    return None


def _decode_legacy_article_url(article_id: str) -> str | None:
    """구형 비암호화 Google News article ID(base64 protobuf)에서 원문 URL을 추출한다."""
    padded = article_id + "=" * (-len(article_id) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except (ValueError, binascii.Error):
        return None

    pos = 0
    if pos >= len(raw) or raw[pos] != 0x08:
        return None
    pos += 1
    while pos < len(raw) and (raw[pos] & 0x80):
        pos += 1
    pos += 1
    if pos >= len(raw) or raw[pos] != 0x22:
        return None
    pos += 1

    length = 0
    shift = 0
    while pos < len(raw):
        byte = raw[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
        if shift > 28:
            return None
    else:
        return None

    if length <= 0 or pos + length > len(raw):
        return None

    try:
        candidate = raw[pos : pos + length].decode("utf-8").strip()
    except UnicodeDecodeError:
        return None

    if candidate.startswith("AU_yqL"):
        return None
    if not candidate.lower().startswith(("http://", "https://")):
        return None
    if any(ch.isspace() or ord(ch) < 32 for ch in candidate):
        return None
    if _is_google_news_article_url(candidate):
        return None
    return candidate


def _parse_intermediate_params(html: str, fallback_article_id: str) -> tuple[str, int, str, list[Any]] | None:
    """Google News 중간 페이지 HTML에서 batchexecute 요청용 ID·타임스탬프·서명·컨텍스트를 추출한다."""
    soup = BeautifulSoup(html, "lxml")
    aid = fallback_article_id
    ts_str = ""
    sg = ""
    context = _DEFAULT_GARTURL_CONTEXT

    params_tag = soup.find(attrs={"data-n-a-ts": True, "data-n-a-sg": True})
    if params_tag is not None:
        ts_str = str(params_tag.get("data-n-a-ts") or "").strip()
        sg = str(params_tag.get("data-n-a-sg") or "").strip()
        tag_aid = str(params_tag.get("data-n-a-id") or "").strip()
        if tag_aid:
            aid = tag_aid

    cwiz_tag = soup.find("c-wiz", attrs={"data-p": True}) or soup.find(attrs={"data-p": True})
    if cwiz_tag is not None:
        raw_data_p = str(cwiz_tag.get("data-p") or "").strip()
        if raw_data_p.startswith("%.@."):
            try:
                parsed_p = json.loads("[" + raw_data_p[4:])
            except json.JSONDecodeError:
                parsed_p = None
            if isinstance(parsed_p, list) and parsed_p:
                if isinstance(parsed_p[0], list):
                    context = parsed_p[0]
                if (not ts_str or not sg) and len(parsed_p) >= 8:
                    p_aid = str(parsed_p[1] or "").strip()
                    if p_aid and (not aid or params_tag is None):
                        aid = p_aid
                    if not ts_str and parsed_p[-2] is not None:
                        ts_str = str(parsed_p[-2]).strip()
                    if not sg and parsed_p[-1] is not None:
                        sg = str(parsed_p[-1]).strip()

    if not aid or not ts_str or not sg:
        return None
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    return aid, ts, sg, context


def _parse_batchexecute_response(body: str) -> str | None:
    """Google batchexecute(Fbv4je) 응답에서 변환된 원문 URL을 추출한다."""
    cleaned = body.lstrip()
    if cleaned.startswith(")]}'"):
        cleaned = cleaned[4:].lstrip()
    if not cleaned:
        return None

    chunks: list[Any] = []
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            chunks.append(parsed)
    except json.JSONDecodeError:
        for line in cleaned.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                parsed_line = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed_line, list):
                chunks.append(parsed_line)

    for chunk in chunks:
        for item in chunk:
            if not (isinstance(item, list) and len(item) >= 3 and item[0] == "wrb.fr" and item[1] == "Fbv4je"):
                continue
            raw_inner = item[2]
            if not isinstance(raw_inner, str):
                continue
            try:
                inner = json.loads(raw_inner)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(inner, list)
                and len(inner) >= 2
                and inner[0] == "garturlres"
                and isinstance(inner[1], str)
                and inner[1].strip()
            ):
                return inner[1].strip()
    return None


def _extract_article_body(html_text: str, source_url: str, target_url: str, fallback: str) -> str:
    """HTML 응답에서 trafilatura로 본문을 추출하고 실패·단문 시 fallback을 반환한다."""
    try:
        content = trafilatura.extract(
            html_text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
    except Exception as e:
        logger.warning("Google News 원문 본문 추출 실패 (%s -> %s): %s", source_url[:60], target_url[:60], e)
        return fallback
    if content and len(content) > _MIN_BODY_LENGTH:
        return content[:_MAX_BODY_LENGTH]
    logger.warning(
        "Google News 원문 본문 추출 부족 (%s -> %s, length=%d)",
        source_url[:60],
        target_url[:60],
        len(content) if content else 0,
    )
    return fallback


def _fetch_and_extract_publisher(client: httpx.Client, source_url: str, target_url: str, fallback: str) -> str:
    """변환된 원문 URL을 안전하게 조회해 본문을 추출한다."""
    try:
        resp = safe_get(client, target_url, timeout=REQUEST_TIMEOUT, expected_kind="html")
    except Exception as e:
        logger.warning("Google News 원문 페이지 조회 실패 (%s -> %s): %s", source_url[:60], target_url[:60], e)
        return fallback
    return _extract_article_body(resp.text, source_url, target_url, fallback)


def _fetch_article_content(client: httpx.Client, url: str, fallback: str) -> str:
    if not _is_google_news_article_url(url):
        return _fetch_and_extract_publisher(client, url, url, fallback)

    article_id = _extract_article_id(url)
    if article_id:
        legacy_url = _decode_legacy_article_url(article_id)
        if legacy_url:
            return _fetch_and_extract_publisher(client, url, legacy_url, fallback)

    try:
        inter_resp = safe_get(client, url, timeout=REQUEST_TIMEOUT, expected_kind="html")
    except Exception as e:
        logger.warning("Google News 중간 페이지 조회 실패 (%s): %s", url[:80], e)
        return fallback

    final_host = (inter_resp.url.host or "").rstrip(".").lower()
    if final_host and final_host != "google.com" and not final_host.endswith(".google.com"):
        return _extract_article_body(inter_resp.text, url, str(inter_resp.url), fallback)

    params = _parse_intermediate_params(inter_resp.text, article_id or "")
    if params is None:
        logger.warning("Google News 원문 URL 변환 토큰 파싱 실패 (%s)", url[:80])
        return fallback

    aid, ts, sg, context = params
    inner_req = json.dumps(["garturlreq", context, aid, ts, sg], separators=(",", ":"))
    f_req = json.dumps([[["Fbv4je", inner_req, None, "generic"]]], separators=(",", ":"))

    try:
        rpc_resp = safe_post(
            client,
            _BATCHEXECUTE_URL,
            data={"f.req": f_req},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Referer": "https://news.google.com/",
            },
            timeout=REQUEST_TIMEOUT,
            max_redirects=0,
            expected_kind="json",
        )
    except Exception as e:
        logger.warning("Google News 원문 URL 변환 요청 실패 (%s): %s", url[:80], e)
        return fallback

    resolved_url = _parse_batchexecute_response(rpc_resp.text)
    if (
        not resolved_url
        or not resolved_url.lower().startswith(("http://", "https://"))
        or _is_google_news_article_url(resolved_url)
    ):
        logger.warning("Google News 원문 URL 변환 응답 파싱 실패 (%s)", url[:80])
        return fallback

    return _fetch_and_extract_publisher(client, url, resolved_url, fallback)

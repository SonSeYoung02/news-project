import base64
import json
import logging
from unittest.mock import patch
from urllib.parse import parse_qs

import httpx

from crawlers import google_news
from crawlers._http import create_safe_client

_ARTICLE_ID = (
    "CBMiigFBVV95cUxOV1NfLUZucXFvUGZrZE9PeVBvcEdiLV82LTRsLTRuTm9fejRKLXJfRUVHalNidTRNMFk0VVMt"
    "Z01qejBwSkZhcHFCakpDdzg3SV9nb21USGlCU2VJeGFVZk9lcTdkQmNUUXlQbTQ1M21FTnhtYUpuWnBZUWtjdXVK"
    "LVkyUnI2U043a3c"
)
_GOOGLE_ARTICLE_URL = f"https://news.google.com/rss/articles/{_ARTICLE_ID}?oc=5"
_GOOGLE_REDIRECTED_URL = f"{_GOOGLE_ARTICLE_URL}&hl=en-US&gl=US&ceid=US:en"
_FALLBACK_TEXT = "Helping American Farmers Compete in Global Markets Union Pacific"

_SAMPLE_RSS_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News Sample</title>
    <item>
      <title>Helping American Farmers Compete in Global Markets - Union Pacific</title>
      <link>{_GOOGLE_ARTICLE_URL}</link>
      <pubDate>Wed, 18 Nov 2026 01:28:27 GMT</pubDate>
      <description>&lt;a href="{_GOOGLE_ARTICLE_URL}" target="_blank"&gt;Helping American Farmers Compete in Global Markets&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Union Pacific&lt;/font&gt;</description>
      <source url="https://www.up.com">Union Pacific</source>
    </item>
  </channel>
</rss>
"""

_DATA_P_JSON = (
    '%.@.[["en-US","US",["FINANCE_TOP_INDICES","GENESIS_PUBLISHER_SECTION","WEB_TEST_1_0_0"],'
    'null,null,1,1,"US:en",null,null,null,null,null,null,null,false,5],"en-US","US",true,'
    '[3,5,9,18],1,true,"1022455856",false,false,null,false],'
    f'"{_ARTICLE_ID}",1,2,null,false,1795014895,"AdwtSYOtFclwIg9dLAWQw0CFAJLf"]'
).replace('"', "&quot;")

_INTERMEDIATE_HTML = f"""<!doctype html>
<html lang="en-US">
<head><title>Google News</title></head>
<body class="y0K44d EA71Tc"></body>
<c-wiz jsrenderer="lW1Lhc" data-p="{_DATA_P_JSON}" jscontroller="he6YWd" view c-wiz>
  <div jscontroller="aLI87"
       data-n-a-id="{_ARTICLE_ID}"
       data-n-a-ts="1795014895"
       data-n-a-sg="AdwtSYOtFclwIg9dLAWQw0CFAJLf"
       data-n-dnlg="false"></div>
  <c-data id="i1"></c-data>
</c-wiz>
</html>
"""

_INTERMEDIATE_DATA_P_ONLY_HTML = f"""<!doctype html>
<html lang="en-US">
<head><title>Google News</title></head>
<body>
  <c-wiz jsrenderer="lW1Lhc" data-p="{_DATA_P_JSON}" jscontroller="he6YWd"></c-wiz>
</body>
</html>
"""

_PUBLISHER_HTML = """<!doctype html>
<html lang="en">
<head><title>Helping American Farmers Compete in Global Markets</title></head>
<body>
  <article>
    <h1>Helping American Farmers Compete in Global Markets</h1>
    <p>Rail freight investment across the Midwest is expanding grain export capacity for agricultural producers.</p>
    <p>New shuttle train corridors connect regional elevators directly to Pacific Northwest ports, reducing transit times
    and lowering logistics costs during peak harvest seasons across multiple states.</p>
    <p>Industry analysts note that reliable bulk rail service allows domestic growers to remain competitive in global
    commodity markets even when ocean shipping schedules fluctuate sharply throughout the year.</p>
  </article>
</body>
</html>
"""


def _batchexecute_response(target_url: str | None) -> str:
    inner = json.dumps(["garturlres", target_url, 1] if target_url is not None else ["garturlres", None, 2])
    outer = [
        ["wrb.fr", "Fbv4je", inner, None, None, None, "generic"],
        ["di", 14],
        ["af.httprm", 14, "-1833428009519316998", 35],
    ]
    return ")]}'\n\n" + json.dumps(outer)


def _encode_legacy_cbmi_token(target_url: str) -> str:
    url_bytes = target_url.encode("utf-8")
    # Protobuf: field 1 (varint 19 = 0x08 0x13), field 4 (length-delimited = 0x22 + varint len)
    length = len(url_bytes)
    varint = bytearray()
    while True:
        byte = length & 0x7F
        length >>= 7
        if length:
            varint.append(byte | 0x80)
        else:
            varint.append(byte)
            break
    payload = b"\x08\x13\x22" + bytes(varint) + url_bytes
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def test_resolves_google_news_intermediate_page_and_extracts_body():
    """Google News 중간 페이지의 토큰·서명을 batchexecute로 변환한 뒤 실제 원문 본문을 추출한다."""
    requested: list[tuple[str, str]] = []
    batchexecute_payloads: list[str] = []

    def respond(req: httpx.Request) -> httpx.Response:
        requested.append((req.method, str(req.url)))
        if req.url.host == "news.google.com" and req.url.path == "/rss/search":
            return httpx.Response(200, text=_SAMPLE_RSS_XML, headers={"Content-Type": "application/xml; charset=utf-8"})
        if req.url.host == "news.google.com" and req.url.path == f"/rss/articles/{_ARTICLE_ID}":
            if "hl=en-US" not in str(req.url):
                return httpx.Response(302, headers={"Location": _GOOGLE_REDIRECTED_URL})
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html; charset=utf-8"})
        if req.url.host == "news.google.com" and req.url.path == "/_/DotsSplashUi/data/batchexecute":
            form = parse_qs(req.content.decode("utf-8"))
            batchexecute_payloads.append(form["f.req"][0])
            return httpx.Response(
                200,
                text=_batchexecute_response("https://publisher.example/news/helping-farmers"),
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        if req.url.host == "publisher.example" and req.url.path == "/news/helping-farmers":
            return httpx.Response(200, text=_PUBLISHER_HTML, headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(respond)
    with patch(
        "crawlers.google_news.create_safe_client",
        side_effect=lambda **kw: create_safe_client(transport=transport, **kw),
    ):
        articles = google_news.fetch()

    assert len(articles) == 1
    assert len(batchexecute_payloads) == 1
    req_outer = json.loads(batchexecute_payloads[0])
    assert req_outer[0][0][0] == "Fbv4je"
    inner = json.loads(req_outer[0][0][1])
    assert inner[0] == "garturlreq"
    assert inner[2] == _ARTICLE_ID
    assert inner[3] == 1795014895
    assert inner[4] == "AdwtSYOtFclwIg9dLAWQw0CFAJLf"

    assert len(articles[0]["content"]) > 300
    assert "Rail freight investment" in articles[0]["content"]
    assert articles[0]["content"] != _FALLBACK_TEXT


def test_resolves_using_data_p_when_data_n_a_attributes_absent():
    """div[data-n-a-*] 속성이 없어도 c-wiz[data-p] 속성에서 토큰과 서명을 파싱해 원문 본문을 추출한다."""

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.host == "news.google.com" and req.url.path.startswith("/rss/articles/"):
            return httpx.Response(
                200, text=_INTERMEDIATE_DATA_P_ONLY_HTML, headers={"Content-Type": "text/html; charset=utf-8"}
            )
        if req.url.host == "news.google.com" and req.url.path == "/_/DotsSplashUi/data/batchexecute":
            return httpx.Response(
                200,
                text=_batchexecute_response("https://publisher.example/news/helping-farmers"),
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        if req.url.host == "publisher.example":
            return httpx.Response(200, text=_PUBLISHER_HTML, headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404, text="not found")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert len(content) > 300
    assert "Rail freight investment" in content


def test_resolves_legacy_unencrypted_cbmi_token_without_intermediate_fetch():
    """구형 비암호화 CBMi 토큰은 중간 페이지나 batchexecute 호출 없이 원문 URL을 직접 디코딩해 추출한다."""
    legacy_target = "https://publisher.example/news/legacy-farmers"
    legacy_token = _encode_legacy_cbmi_token(legacy_target)
    legacy_google_url = f"https://news.google.com/rss/articles/{legacy_token}?oc=5"
    requested: list[str] = []

    def respond(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        if str(req.url) == legacy_target:
            return httpx.Response(200, text=_PUBLISHER_HTML, headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(500, text="unexpected request")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        content = google_news._fetch_article_content(client, legacy_google_url, _FALLBACK_TEXT)

    assert requested == [legacy_target]
    assert len(content) > 300
    assert "Rail freight investment" in content


def test_falls_back_with_conversion_warning_when_intermediate_tokens_missing(caplog):
    """중간 페이지에서 서명·타임스탬프를 찾지 못하면 변환 실패 경고를 남기고 RSS 요약으로 대체한다."""
    batchexecute_called = False

    def respond(req: httpx.Request) -> httpx.Response:
        nonlocal batchexecute_called
        if req.url.path == "/_/DotsSplashUi/data/batchexecute":
            batchexecute_called = True
        return httpx.Response(
            200,
            text="<html><body><p>Before you continue to Google News</p></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert content == _FALLBACK_TEXT
    assert not batchexecute_called
    assert any("변환" in rec.message or "토큰" in rec.message for rec in caplog.records)


def test_falls_back_with_conversion_warning_when_batchexecute_fails(caplog):
    """batchexecute 요청이 429를 반환하거나 빈 URL을 응답하면 변환 실패 경고를 남기고 RSS 요약으로 대체한다."""

    def respond_429(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/rss/articles/"):
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html"})
        return httpx.Response(429, text="Too Many Requests", headers={"Content-Type": "text/plain"})

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond_429)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert content == _FALLBACK_TEXT
    assert any("변환" in rec.message for rec in caplog.records)

    caplog.clear()

    def respond_null(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/rss/articles/"):
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html"})
        return httpx.Response(200, text=_batchexecute_response(None), headers={"Content-Type": "application/json"})

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond_null)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert content == _FALLBACK_TEXT
    assert any("변환" in rec.message for rec in caplog.records)


def test_blocks_ssrf_url_returned_by_batchexecute_and_falls_back(caplog):
    """batchexecute가 내부 IP 주소를 반환해도 SSRF 검증으로 차단하고 RSS 요약으로 대체한다."""
    requested: list[str] = []
    batchexecute_called = False

    def respond(req: httpx.Request) -> httpx.Response:
        nonlocal batchexecute_called
        requested.append(str(req.url))
        if req.url.path.startswith("/rss/articles/"):
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html"})
        if req.url.path == "/_/DotsSplashUi/data/batchexecute":
            batchexecute_called = True
            return httpx.Response(
                200,
                text=_batchexecute_response("http://169.254.169.254/latest/meta-data/"),
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(200, text="LEAKED_METADATA")

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert batchexecute_called
    assert "http://169.254.169.254/latest/meta-data/" not in requested
    assert content == _FALLBACK_TEXT
    assert any("원문" in rec.message for rec in caplog.records)


def test_falls_back_with_extraction_warning_when_publisher_blocked_or_short(caplog):
    """변환된 원문 페이지가 403 차단이거나 페이월 단문이면 추출 실패 경고를 남기고 RSS 요약으로 대체한다."""

    def respond_403(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/rss/articles/"):
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html"})
        if req.url.path == "/_/DotsSplashUi/data/batchexecute":
            return httpx.Response(
                200,
                text=_batchexecute_response("https://publisher.example/blocked"),
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(403, text="Forbidden", headers={"Content-Type": "text/html"})

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond_403)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert content == _FALLBACK_TEXT
    assert any("원문" in rec.message and ("조회" in rec.message or "추출" in rec.message) for rec in caplog.records)

    caplog.clear()

    def respond_paywall(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/rss/articles/"):
            return httpx.Response(200, text=_INTERMEDIATE_HTML, headers={"Content-Type": "text/html"})
        if req.url.path == "/_/DotsSplashUi/data/batchexecute":
            return httpx.Response(
                200,
                text=_batchexecute_response("https://publisher.example/paywall"),
                headers={"Content-Type": "application/json"},
            )
        return httpx.Response(
            200,
            text="<html><body><article><p>Subscribe to continue reading this article.</p></article></body></html>",
            headers={"Content-Type": "text/html"},
        )

    with caplog.at_level(logging.WARNING, logger="crawlers.google_news"):
        with httpx.Client(transport=httpx.MockTransport(respond_paywall)) as client:
            content = google_news._fetch_article_content(client, _GOOGLE_ARTICLE_URL, _FALLBACK_TEXT)

    assert content == _FALLBACK_TEXT
    assert any("추출" in rec.message or "부족" in rec.message for rec in caplog.records)

"""Hugging Face 블로그 및 Daily Papers 본문 추출 재현 테스트."""

import html as html_lib
import json
from unittest.mock import patch

import httpx

from crawlers import huggingface
from crawlers._http import create_safe_client

_BLOG_URL_1 = "https://huggingface.co/blog/ibm-research/time-series-powered-streamhouse"
_BLOG_URL_2 = "https://huggingface.co/blog/reson8/rumble-2-flash"

_FEED_XML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Hugging Face Blog</title>
    <link>https://huggingface.co/blog</link>
    {items}
  </channel>
</rss>
"""

_BLOG_HTML_1 = """<!DOCTYPE html>
<html lang="en">
<head><title>Time-Series Models in the Streamhouse: A New Frontier and Use Cases</title></head>
<body>
<header><nav><a href="/models">Models</a><a href="/datasets">Datasets</a><a href="/blog">Blog</a></nav></header>
<main class="flex flex-1 flex-col">
  <div class="container relative flex flex-row justify-center gap-12">
    <div class="max-w-full pb-16 pt-6 lg:max-w-3xl lg:flex-1">
      <div class="blog-content copiable-code-container prose mx-auto mb-8">
        <div class="mb-4"><a href="/blog">Back to Articles</a></div>
        <h1>Time-Series Models in the Streamhouse: A New Frontier and Use Cases</h1>
        <p>Real-time forecasting, anomaly detection, and optimization, powered by open time-series foundation models running efficiently on CPUs and GPUs in streaming pipelines.</p>
        <p>Every business generates a continuous record of change: a machine reading, a payment, a sale, an order, or a telemetry metric emitted every millisecond across distributed systems.</p>
        <h2>Architecture and Streaming Integration</h2>
        <p>By embedding zero-shot inference directly inside stream processing stages, organizations can detect anomalies immediately without waiting for batch ETL jobs or manual feature engineering pipelines.</p>
      </div>
    </div>
  </div>
</main>
<footer><p>Hugging Face Terms Privacy</p></footer>
</body>
</html>"""

_BLOG_HTML_WITH_CARD = """<!DOCTYPE html>
<html lang="en">
<head><title>Rumble-2-Flash: an open 0.5B speech model for 40+ languages</title></head>
<body>
<main class="flex flex-1 flex-col">
  <div class="blog-content prose mx-auto mb-8">
    <h1>Rumble-2-Flash: an open 0.5B speech model for 40+ languages</h1>
    <p>Today we open source Rumble-2-Flash under the Apache 2.0 license. It is a 0.5B-parameter speech recognition model for 40+ languages that competes with models many times its size.</p>
    <article class="overview-card-wrapper group/repo">
      <a href="/Reson8/Rumble-2-Flash"><h4>Reson8/Rumble-2-Flash</h4><span>Updated 2 days ago</span></a>
    </article>
    <p>Across standard multilingual speech benchmarks, the model achieves strong accuracy while running with low latency on edge hardware and consumer GPUs without custom kernels.</p>
  </div>
</main>
</body>
</html>"""


def _mock_client_factory(handler):
    transport = httpx.MockTransport(handler)
    return lambda **kw: create_safe_client(transport=transport, **kw)


def test_fetch_blog_extracts_full_article_body_from_post_html():
    """RSS에 본문이 없는 Hugging Face 블로그 글은 글 URL HTML에서 실제 본문을 추출한다."""
    feed_xml = _FEED_XML_TEMPLATE.format(
        items=f"""
        <item>
          <title>Time-Series Models in the Streamhouse: A New Frontier and Use Cases</title>
          <pubDate>Wed, 18 Nov 2026 15:00:23 GMT</pubDate>
          <link>{_BLOG_URL_1}</link>
          <guid isPermaLink="false">{_BLOG_URL_1}</guid>
        </item>
        <item>
          <title>Rumble-2-Flash: an open 0.5B speech model for 40+ languages</title>
          <pubDate>Tue, 17 Nov 2026 12:00:00 GMT</pubDate>
          <link>{_BLOG_URL_2}</link>
          <guid isPermaLink="false">{_BLOG_URL_2}</guid>
        </item>
        """
    )
    requested: list[str] = []

    def respond(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(200, text=feed_xml, headers={"Content-Type": "application/rss+xml; charset=utf-8"})
        if str(req.url) == _BLOG_URL_1:
            return httpx.Response(200, text=_BLOG_HTML_1, headers={"Content-Type": "text/html; charset=utf-8"})
        if str(req.url) == _BLOG_URL_2:
            return httpx.Response(200, text=_BLOG_HTML_WITH_CARD, headers={"Content-Type": "text/html; charset=utf-8"})
        return httpx.Response(404)

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface.fetch()

    assert _BLOG_URL_1 in requested
    assert _BLOG_URL_2 in requested
    assert len(articles) == 2

    assert articles[0]["source"] == "Hugging Face"
    assert len(articles[0]["content"]) > 300
    assert "Real-time forecasting, anomaly detection, and optimization" in articles[0]["content"]
    assert "organizations can detect anomalies immediately" in articles[0]["content"]
    assert "Hugging Face Terms Privacy" not in articles[0]["content"]

    assert len(articles[1]["content"]) > 300
    assert "Today we open source Rumble-2-Flash under the Apache 2.0 license." in articles[1]["content"]
    assert "running with low latency on edge hardware" in articles[1]["content"]


def test_fetch_blog_truncates_extracted_body_to_8000_chars():
    """추출된 블로그 본문이 8,000자를 초과하면 최대 8,000자로 잘라 저장한다."""
    long_paragraphs = "".join(
        f"<p>Paragraph {i}: Efficient open-weight foundation model training and distributed inference telemetry across clusters.</p>"
        for i in range(120)
    )
    long_html = f"""<!DOCTYPE html>
    <html><body><main><div class="blog-content prose">
      <h1>Very Long Technical Deep Dive</h1>
      {long_paragraphs}
    </div></main></body></html>"""

    feed_xml = _FEED_XML_TEMPLATE.format(
        items=f"""
        <item>
          <title>Very Long Technical Deep Dive</title>
          <pubDate>Wed, 18 Nov 2026 15:00:23 GMT</pubDate>
          <link>{_BLOG_URL_1}</link>
        </item>
        """
    )

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(200, text=feed_xml, headers={"Content-Type": "application/rss+xml"})
        return httpx.Response(200, text=long_html, headers={"Content-Type": "text/html"})

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface.fetch()

    assert len(articles) == 1
    assert len(articles[0]["content"]) == 8000


def test_fetch_blog_falls_back_to_feed_content_or_title_on_error_ssrf_and_short_body():
    """본문 요청 실패·SSRF 차단·짧은 추출 결과는 피드 내용 또는 제목으로 대체한다."""
    url_fail = "https://huggingface.co/blog/fail-post"
    url_ssrf = "https://huggingface.co/blog/ssrf-post"
    url_short = "https://huggingface.co/blog/short-post"
    feed_xml = _FEED_XML_TEMPLATE.format(
        items=f"""
        <item>
          <title>Post With Feed Description</title>
          <link>{url_fail}</link>
          <description><![CDATA[<p>RSS 피드에 포함된 요약 본문입니다.</p>]]></description>
        </item>
        <item>
          <title>SSRF Redirect Post Title</title>
          <link>{url_ssrf}</link>
        </item>
        <item>
          <title>Short Extraction Post Title</title>
          <link>{url_short}</link>
        </item>
        """
    )
    requested: list[str] = []

    def respond(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(200, text=feed_xml, headers={"Content-Type": "application/rss+xml"})
        if str(req.url) == url_fail:
            return httpx.Response(500, text="Server Error", headers={"Content-Type": "text/html"})
        if str(req.url) == url_ssrf:
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
        if str(req.url) == url_short:
            return httpx.Response(
                200,
                text="<html><body><main><p>Coming soon.</p></main></body></html>",
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(200, text="SECRET")

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface.fetch()

    assert url_fail in requested
    assert url_ssrf in requested
    assert url_short in requested
    assert "http://127.0.0.1/secret" not in requested

    assert len(articles) == 3
    assert articles[0]["content"] == "RSS 피드에 포함된 요약 본문입니다."
    assert articles[1]["content"] == "SSRF Redirect Post Title"
    assert articles[2]["content"] == "Short Extraction Post Title"


def test_fetch_papers_enriches_abstract_from_daily_papers_props():
    """블로그 피드 실패 시 Daily Papers 대체 경로는 페이지 내 JSON 초록으로 본문을 보강한다."""
    abstract_text = (
        "We present Xing 4, a series of large language models that extends the TeleChat lineage "
        "through coordinated advances in model architecture and training infrastructure. "
        "This report details pre-training stability, long-context scaling, and agentic reasoning evaluations."
    )
    props = json.dumps(
        {
            "dailyPapers": [
                {
                    "paper": {
                        "id": "2611.22115",
                        "title": "TeleChat to Xing4: Advancing Frontier Agentic Models",
                        "summary": abstract_text,
                        "publishedAt": "2026-11-18T08:00:00.000Z",
                    },
                    "title": "TeleChat to Xing4: Advancing Frontier Agentic Models",
                    "summary": abstract_text,
                    "publishedAt": "2026-11-18T08:00:00.000Z",
                }
            ]
        }
    )
    escaped_props = html_lib.escape(props, quote=True)
    papers_html = f"""<!DOCTYPE html>
    <html><body>
      <a href="/papers/trending">Trending</a>
      <a href="/papers/date/2026-11-17">Yesterday</a>
      <div class="SVELTE_HYDRATER" data-target="DailyPapers" data-props="{escaped_props}"></div>
      <article>
        <a href="/papers/2611.22115"><h3>TeleChat to Xing4: Advancing Frontier Agentic Models</h3></a>
        <a href="/papers/2611.22115#community">2 comments</a>
      </article>
    </body></html>"""

    requested: list[str] = []

    def respond(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(503)
        if req.url.path == "/papers":
            return httpx.Response(200, text=papers_html, headers={"Content-Type": "text/html"})
        return httpx.Response(404)

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface.fetch()

    assert len(articles) == 1
    assert articles[0]["url"] == "https://huggingface.co/papers/2611.22115"
    assert articles[0]["title"] == "TeleChat to Xing4: Advancing Frontier Agentic Models"
    assert articles[0]["content"] == abstract_text
    assert articles[0]["published_at"] == "2026-11-18T08:00:00.000Z"
    assert "https://huggingface.co/papers/2611.22115" not in requested


def test_fetch_papers_falls_back_to_paper_detail_page_and_stub():
    """Daily Papers JSON 초록이 없으면 개별 논문 페이지에서 초록을 추출하고 실패 시 기본 문구로 대체한다."""
    papers_html = """<!DOCTYPE html>
    <html><body>
      <a href="/papers/2611.00001"><h3>Sparse Attention Routing at Scale</h3></a>
      <a href="/papers/2611.00002"><h3>Unavailable Paper Detail Page</h3></a>
    </body></html>"""

    paper_detail_html = """<!DOCTYPE html>
    <html><body><main>
      <section>
        <h1>Sparse Attention Routing at Scale</h1>
        <h2>Abstract</h2>
        <p>We propose a hardware-aware sparse attention routing mechanism that reduces memory bandwidth overhead during long-context decoding while preserving accuracy across reasoning and retrieval benchmarks.</p>
        <p>Extensive experiments on multi-node GPU clusters demonstrate significant throughput improvements without degrading downstream task quality.</p>
      </section>
    </main></body></html>"""

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(
                200, text="<rss><channel></channel></rss>", headers={"Content-Type": "application/rss+xml"}
            )
        if req.url.path == "/papers":
            return httpx.Response(200, text=papers_html, headers={"Content-Type": "text/html"})
        if req.url.path == "/papers/2611.00001":
            return httpx.Response(200, text=paper_detail_html, headers={"Content-Type": "text/html"})
        return httpx.Response(404)

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface.fetch()

    assert len(articles) == 2
    assert "hardware-aware sparse attention routing mechanism" in articles[0]["content"]
    assert articles[1]["content"] == (
        "Hugging Face Daily Paper: Unavailable Paper Detail Page\nURL: https://huggingface.co/papers/2611.00002"
    )


def test_fetch_blog_feed_direct_call_without_client_caps_at_10():
    """_fetch_blog_feed를 client 없이 직접 호출해도 글 본문을 모두 추출하고 최대 10건으로 제한한다."""
    items_xml = "\n".join(
        f"""
        <item>
          <title>Blog Post {i}</title>
          <pubDate>Wed, 18 Nov 2026 15:00:23 GMT</pubDate>
          <link>https://huggingface.co/blog/post-{i}</link>
        </item>
        """
        for i in range(12)
    )
    feed_xml = _FEED_XML_TEMPLATE.format(items=items_xml)

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(200, text=feed_xml, headers={"Content-Type": "application/rss+xml"})
        slug = req.url.path.rsplit("/", 1)[-1]
        html = f"""<!DOCTYPE html>
        <html><body><main><div class="blog-content prose">
          <h1>{slug}</h1>
          <p>Detailed engineering report for {slug} covering model architecture, dataset curation, evaluation benchmarks, quantization recipes, and deployment latency measurements in production environments.</p>
          <p>Additional ablation results and reproducible training configurations are shared for community practitioners building open-source systems.</p>
        </div></main></body></html>"""
        return httpx.Response(200, text=html, headers={"Content-Type": "text/html"})

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond)):
        articles = huggingface._fetch_blog_feed()

    assert len(articles) == 10
    assert "Detailed engineering report for post-0" in articles[0]["content"]
    assert "Detailed engineering report for post-9" in articles[9]["content"]


def test_huggingface_normalizes_trafilatura_paragraphs_to_double_newlines():
    """Hugging Face 블로그와 논문 상세 페이지의 trafilatura 추출 결과는 '\\n\\n' 문단 구분으로 정규화된다."""
    feed_xml = _FEED_XML_TEMPLATE.format(
        items=f"""
        <item>
          <title>Time-Series Models in the Streamhouse: A New Frontier and Use Cases</title>
          <pubDate>Wed, 18 Nov 2026 15:00:23 GMT</pubDate>
          <link>{_BLOG_URL_1}</link>
        </item>
        """
    )

    def respond_blog(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/blog/feed.xml":
            return httpx.Response(200, text=feed_xml, headers={"Content-Type": "application/rss+xml"})
        return httpx.Response(200, text=_BLOG_HTML_1, headers={"Content-Type": "text/html"})

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond_blog)):
        blog_articles = huggingface.fetch()

    assert len(blog_articles) == 1
    blog_paragraphs = blog_articles[0]["content"].split("\n\n")
    assert len(blog_paragraphs) >= 4
    assert "Real-time forecasting, anomaly detection, and optimization" in blog_paragraphs[1]

    papers_html = (
        '<html><body><a href="/papers/2611.00001"><h3>Sparse Attention Routing at Scale</h3></a></body></html>'
    )
    paper_detail_html = """<!DOCTYPE html>
    <html><body><main><section>
      <h1>Sparse Attention Routing at Scale</h1>
      <h2>Abstract</h2>
      <p>We propose a hardware-aware sparse attention routing mechanism that reduces memory bandwidth overhead during long-context decoding while preserving accuracy across reasoning and retrieval benchmarks.</p>
      <p>Extensive experiments on multi-node GPU clusters demonstrate significant throughput improvements without degrading downstream task quality.</p>
    </section></main></body></html>"""

    def respond_paper(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/papers":
            return httpx.Response(200, text=papers_html, headers={"Content-Type": "text/html"})
        return httpx.Response(200, text=paper_detail_html, headers={"Content-Type": "text/html"})

    with patch("crawlers.huggingface.create_safe_client", side_effect=_mock_client_factory(respond_paper)):
        paper_articles = huggingface._fetch_papers()

    assert len(paper_articles) == 1
    paper_paragraphs = paper_articles[0]["content"].split("\n\n")
    assert len(paper_paragraphs) >= 3
    assert "Extensive experiments on multi-node GPU clusters" in paper_paragraphs[-1]

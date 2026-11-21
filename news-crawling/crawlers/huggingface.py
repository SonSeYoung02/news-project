import json
import logging
from contextlib import nullcontext
from datetime import datetime
from typing import Any

import httpx
import trafilatura
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

from ._html_text import feed_content_to_text, normalize_paragraphs
from ._http import create_safe_client, safe_get

logger = logging.getLogger(__name__)

_BLOG_FEED_URL = "https://huggingface.co/blog/feed.xml"
_PAPERS_URL = "https://huggingface.co/papers"
_MAX_CONTENT_CHARS = 8000
_MIN_EXTRACTED_CHARS = 200
_MIN_SUMMARY_CHARS = 50


def fetch() -> list[dict[str, Any]]:
    try:
        with create_safe_client() as client:
            articles = _fetch_blog_feed(client)
            if articles:
                return articles[:10]
            return _fetch_papers(client)[:10]
    except Exception as e:
        logger.error("Hugging Face 크롤링 실패: %s", e)
        return []


def _fetch_blog_feed(client: httpx.Client | None = None) -> list[dict[str, Any]]:
    try:
        ctx = nullcontext(client) if client is not None else create_safe_client()
        with ctx as active_client:
            try:
                resp = safe_get(active_client, _BLOG_FEED_URL, timeout=REQUEST_TIMEOUT, expected_kind="xml")
            except Exception as e:
                logger.warning("Hugging Face 블로그 피드 요청 실패: %s", e)
                return []

            soup = BeautifulSoup(resp.text, "lxml-xml")
            elements = soup.find_all("item")
            if not elements:
                elements = soup.find_all("entry")

            articles: list[dict[str, Any]] = []
            for el in elements[:10]:
                title = _extract_tag_text(el, "title")
                url = _extract_url(el)
                if not title or not url:
                    continue

                published_at = (
                    _extract_tag_text(el, "pubDate")
                    or _extract_tag_text(el, "published")
                    or _extract_tag_text(el, "updated")
                    or datetime.now().isoformat()
                )

                cleaned_content = _extract_content_text(el)
                fallback = (cleaned_content or title)[:_MAX_CONTENT_CHARS]
                content = _fetch_article_content(active_client, url, fallback)

                articles.append(
                    {
                        "url": url,
                        "source": "Hugging Face",
                        "title": title,
                        "content": content,
                        "published_at": published_at,
                        "crawled_at": datetime.now().isoformat(),
                        "major_category": "AI",
                        "translate_to_korean": True,
                    }
                )

            return articles
    except Exception as e:
        logger.warning("Hugging Face 블로그 피드 처리 실패: %s", e)
        return []


def _fetch_papers(client: httpx.Client | None = None) -> list[dict[str, Any]]:
    try:
        ctx = nullcontext(client) if client is not None else create_safe_client()
        with ctx as active_client:
            try:
                resp = safe_get(active_client, _PAPERS_URL, timeout=REQUEST_TIMEOUT, expected_kind="html")
            except Exception as e:
                logger.warning("Hugging Face Papers 요청 실패: %s", e)
                return []

            soup = BeautifulSoup(resp.text, "lxml")
            paper_meta = _extract_daily_papers_metadata(soup)
            articles: list[dict[str, Any]] = []
            for link in soup.select("a[href^='/papers/']"):
                href = str(link.get("href", "")).strip()
                if (
                    not href
                    or href in ("/papers", "/papers/trending")
                    or href.startswith("/papers/date/")
                    or "#" in href
                ):
                    continue

                title_el = link.find(["h3", "h4", "p"]) or link
                title = title_el.get_text(strip=True)
                if not title or len(title) < 5:
                    continue

                url = f"https://huggingface.co{href}"
                if any(a["url"] == url for a in articles):
                    continue

                meta = paper_meta.get(url, {})
                summary = meta.get("summary", "")
                fallback = f"Hugging Face Daily Paper: {title}\nURL: {url}"
                if len(summary) > _MIN_SUMMARY_CHARS:
                    content = summary[:_MAX_CONTENT_CHARS]
                else:
                    content = _fetch_article_content(active_client, url, fallback)

                articles.append(
                    {
                        "url": url,
                        "source": "Hugging Face",
                        "title": title,
                        "content": content,
                        "published_at": meta.get("published_at") or datetime.now().isoformat(),
                        "crawled_at": datetime.now().isoformat(),
                        "major_category": "AI",
                        "translate_to_korean": True,
                    }
                )
                if len(articles) >= 10:
                    break

            return articles
    except Exception as e:
        logger.warning("Hugging Face Papers 처리 실패: %s", e)
        return []


def _fetch_article_content(client: httpx.Client, url: str, fallback: str) -> str:
    """글 URL에서 HTML을 안전하게 가져와 trafilatura로 본문을 추출하고 실패 시 fallback을 반환한다."""
    try:
        resp = safe_get(client, url, timeout=REQUEST_TIMEOUT, expected_kind="html")
        extracted = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        content = normalize_paragraphs(extracted)
        if len(content) > _MIN_EXTRACTED_CHARS:
            return content[:_MAX_CONTENT_CHARS]
    except Exception as e:
        logger.warning("Hugging Face 원문 추출 실패 (%s): %s", url[:80], e)
    return fallback


def _extract_daily_papers_metadata(soup: BeautifulSoup) -> dict[str, dict[str, str]]:
    """Daily Papers 페이지의 Svelte hydration JSON에서 논문별 초록과 발행 시각을 추출한다."""
    node = soup.select_one('[data-target="DailyPapers"][data-props]')
    if node is None:
        return {}
    raw_props = node.get("data-props")
    if not isinstance(raw_props, str) or not raw_props:
        return {}
    try:
        props = json.loads(raw_props)
    except (ValueError, TypeError):
        return {}
    if not isinstance(props, dict):
        return {}

    metadata: dict[str, dict[str, str]] = {}
    for entry in props.get("dailyPapers") or []:
        if not isinstance(entry, dict):
            continue
        paper = entry.get("paper") if isinstance(entry.get("paper"), dict) else {}
        paper_id = str(paper.get("id") or "").strip()
        if not paper_id:
            continue
        summary = str(entry.get("summary") or paper.get("summary") or "").strip()
        published_at = str(entry.get("publishedAt") or paper.get("publishedAt") or "").strip()
        metadata[f"https://huggingface.co/papers/{paper_id}"] = {
            "summary": summary,
            "published_at": published_at,
        }
    return metadata


def _extract_url(element: Any) -> str:
    link = element.find("link")
    if link:
        href = link.get("href")
        if href:
            return str(href).strip()
        text = link.get_text(strip=True)
        if text:
            return text
    id_tag = element.find("id")
    if id_tag:
        text = id_tag.get_text(strip=True)
        if text.startswith("http://") or text.startswith("https://"):
            return text
    return ""


def _extract_tag_text(element: Any, tag_name: str) -> str:
    tag = element.find(tag_name)
    return tag.get_text(strip=True) if tag else ""


def _extract_content_text(element: Any) -> str:
    for tag_name in ("description", "content", "summary"):
        tag = element.find(tag_name)
        if tag:
            text = feed_content_to_text(tag)
            if text:
                return text
    return ""

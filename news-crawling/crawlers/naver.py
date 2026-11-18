import logging
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT

from ._http import UnsafeURLError, create_safe_client, safe_get, validate_url

logger = logging.getLogger(__name__)

_MAX_ARTICLES_PER_SECTION = 5
_SECTION_URLS = [
    "https://news.naver.com/section/105",  # IT/과학
    "https://news.naver.com/section/101",  # 경제
    "https://news.naver.com/section/104",  # 세계
]
_BODY_SELECTORS = (
    "#dic_area",
    "#newsct_article",
    "#articleBodyContents",
    "#articeBody",
    ".article_body",
)


def _extract_section_links(soup: BeautifulSoup) -> list[Any]:
    """섹션 페이지에서 기사 제목 링크를 우선 추출하고, 단순 HTML은 일반 article 링크로 폴백한다."""
    title_links = soup.select("a.sa_text_title")
    if title_links:
        return title_links
    return soup.select("a[href*='article']")


def _fetch_article_content(client: httpx.Client, url: str) -> str:
    try:
        resp = safe_get(client, url, timeout=REQUEST_TIMEOUT, expected_kind="html")
        soup = BeautifulSoup(resp.text, "lxml")
        for selector in _BODY_SELECTORS:
            article_body = soup.select_one(selector)
            if article_body:
                for tag in article_body.select("script, style, noscript"):
                    tag.decompose()
                text = article_body.get_text(separator="\n", strip=True)
                if text:
                    return text
        return ""
    except Exception as e:
        logger.debug("기사 본문 수집 실패 url=%s: %s", url, e)
        return ""


def fetch() -> list[dict[str, Any]]:
    articles: list[dict] = []
    seen_urls: set[str] = set()

    try:
        with create_safe_client() as client:
            for section_url in _SECTION_URLS:
                try:
                    resp = safe_get(client, section_url, timeout=REQUEST_TIMEOUT, expected_kind="html")
                    soup = BeautifulSoup(resp.text, "lxml")

                    section_requests = 0
                    for link in _extract_section_links(soup):
                        if section_requests >= _MAX_ARTICLES_PER_SECTION:
                            break
                        raw_href = str(link.get("href", "") or "").strip()
                        if not raw_href:
                            continue
                        href = urljoin(section_url, raw_href)
                        try:
                            validate_url(href)
                        except UnsafeURLError as e:
                            logger.warning("네이버 기사 URL 검증 차단 (%s): %s", href[:80], e)
                            continue
                        if "article" not in href or "/article/comment/" in href or href in seen_urls:
                            continue

                        title = link.get_text(strip=True)
                        if len(title) < 5:
                            continue

                        seen_urls.add(href)
                        section_requests += 1
                        content = _fetch_article_content(client, href)
                        if not content:
                            continue

                        articles.append(
                            {
                                "url": href,
                                "source": "네이버뉴스",
                                "title": title,
                                "content": content,
                                "published_at": datetime.now().isoformat(),
                                "crawled_at": datetime.now().isoformat(),
                            }
                        )
                except Exception as e:
                    logger.error("네이버 섹션 수집 실패 url=%s: %s", section_url, e)
    except Exception as e:
        logger.error("네이버 크롤러 초기화 실패: %s", e)

    return articles

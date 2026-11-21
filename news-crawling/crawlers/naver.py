import logging
import re
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
_NOISE_SELECTORS = (
    "script",
    "style",
    "noscript",
    ".end_photo_org",
    ".img_desc",
    "em.img_desc",
    "figcaption",
    ".photo_desc",
    ".img_caption",
    ".media_end_copyright",
    ".copyright",
)
_INLINE_TAGS = ("strong", "b", "em", "i", "a", "span", "font", "u", "small", "mark", "sub", "sup", "code")
_WHITESPACE_RE = re.compile(r"[ \t\xa0\u200b]+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_LABEL_RE = re.compile(r"(?:기자\s*)?(?:이메일|메일|제보|문의)")
_REPORTER_ROLE_RE = re.compile(r"(?:기자|특파원|논설위원|에디터|리포터)")
_PHOTO_CAPTION_LINE_RE = re.compile(
    r"^[\[\(]?\s*(?:사진|이미지|자료사진|그래픽|영상)\s*(?:=|[:：]|출처\s*[=:]|제공\s*[=:]|\|)\s*[^.\n]{1,60}[\]\)]?$"
    r"|^[\[\(]\s*(?:자료사진|사진\s*제공)\s*[\]\)]$"
)
_COPYRIGHT_LINE_RE = re.compile(
    r"(?:<|\[)?\s*저작권자\s*(?:\([cC]\)|ⓒ|©)"
    r"|^[<\[]\s*저작권자\b"
    r"|^[<\[]?\s*[ⓒ©]"
    r"|무단\s*전재\s*(?:및|·|ㆍ|,|-|/|\s)*(?:재배포|복제|배포|AI|인공지능|학습).{0,30}금지"
    r"|(?:무단\s*전재|재배포)\s*금지"
    r"|^[<\[]\s*[^\n]{0,40}무단\s*전재"
    r"|copyright\s*(?:\([cC]\)|ⓒ|©|\d{4})"
    r"|all\s+rights\s+reserved\.?",
    re.IGNORECASE,
)


def _is_reporter_email_line(line: str) -> bool:
    if not _EMAIL_RE.search(line):
        return False
    without_email = _EMAIL_RE.sub("", line)
    without_label = _EMAIL_LABEL_RE.sub("", without_email)
    remainder = re.sub(r"[\s\[\]\(\)<>{}:：=·ㆍ•▶◆/|,-]+", "", without_label)
    if not remainder:
        return True
    return bool(_REPORTER_ROLE_RE.search(line) and len(line) <= 100 and "다." not in line)


def _is_noise_line(line: str) -> bool:
    if _PHOTO_CAPTION_LINE_RE.match(line):
        return True
    if _is_reporter_email_line(line):
        return True
    if _COPYRIGHT_LINE_RE.search(line) and len(line) <= 150:
        return True
    return False


def _clean_article_text(raw_text: str) -> str:
    """네이버 본문 줄에서 불필요한 공백, 기자 이메일, 사진 캡션, 저작권 문구를 제거한다."""
    cleaned_lines: list[str] = []
    for raw_line in raw_text.splitlines():
        line = _WHITESPACE_RE.sub(" ", raw_line).strip()
        if not line or _is_noise_line(line):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


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
        noise_selector = ", ".join(_NOISE_SELECTORS)
        for selector in _BODY_SELECTORS:
            article_body = soup.select_one(selector)
            if article_body:
                for tag in article_body.select(noise_selector):
                    if not getattr(tag, "decomposed", False):
                        tag.decompose()
                for tag in article_body.find_all(_INLINE_TAGS):
                    tag.unwrap()
                article_body.smooth()
                text = _clean_article_text(article_body.get_text(separator="\n", strip=True))
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

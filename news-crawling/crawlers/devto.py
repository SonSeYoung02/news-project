import logging
from datetime import datetime
from typing import Any

import httpx

from config import REQUEST_TIMEOUT

from ._http import create_safe_client, safe_get

logger = logging.getLogger(__name__)

_API_URL = "https://dev.to/api/articles"
_PARAMS = {
    "tag": "ai",
    "per_page": 10,
    "top": 7,
}


def fetch() -> list[dict[str, Any]]:
    try:
        with create_safe_client() as client:
            resp = safe_get(
                client,
                _API_URL,
                params=_PARAMS,
                timeout=REQUEST_TIMEOUT,
                expected_kind="json",
            )
            payload = resp.json()

            articles = []
            for item in payload:
                title = item.get("title", "")
                url = item.get("url") or item.get("canonical_url")
                if not title or not url:
                    continue

                fallback = _short_content(item)
                article_id = item.get("id")
                is_valid_id = isinstance(article_id, int) and not isinstance(article_id, bool) and article_id > 0
                content = _fetch_full_content(client, article_id, fallback) if is_valid_id else fallback

                articles.append(
                    {
                        "url": url,
                        "source": "dev.to",
                        "title": title,
                        "content": content,
                        "published_at": item.get("published_at") or datetime.now().isoformat(),
                        "crawled_at": datetime.now().isoformat(),
                        "major_category": "AI",
                        "sub_category": "개발",
                        "tags": item.get("tag_list", [])[:10],
                        "translate_to_korean": True,
                    }
                )
            return articles
    except Exception as e:
        logger.error("dev.to API 크롤링 실패: %s", e)
        return []


def _fetch_full_content(client: httpx.Client, article_id: int, fallback: str) -> str:
    try:
        resp = safe_get(
            client,
            f"https://dev.to/api/articles/{article_id}",
            timeout=REQUEST_TIMEOUT,
            expected_kind="json",
        )
        data = resp.json()
        body = data.get("body_markdown") or data.get("body_html") or ""
        if body and len(body) > 100:
            return body[:8000]
    except Exception as e:
        logger.warning("dev.to 전체 본문 가져오기 실패 (id=%s): %s", article_id, e)
    return fallback


def _short_content(item: dict[str, Any]) -> str:
    parts = [
        item.get("description", ""),
        item.get("readable_publish_date", ""),
    ]
    tags = item.get("tag_list") or []
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return "\n".join(part for part in parts if part)

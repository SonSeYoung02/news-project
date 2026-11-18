import importlib
import logging
from unittest.mock import MagicMock

import pytest

import config
import crawlers
from crawlers import (
    arxiv,
    devto,
    geeknews,
    github_trending,
    google_news,
    huggingface,
    naver,
    reddit_ai,
)

_SOURCE_MODULES = [
    ("네이버뉴스", naver),
    ("Google News", google_news),
    ("GeekNews", geeknews),
    ("Reddit AI", reddit_ai),
    ("GitHub Trending", github_trending),
    ("Hugging Face", huggingface),
    ("arXiv", arxiv),
    ("dev.to", devto),
]
_OTHER_SOURCES = [name for name, _ in _SOURCE_MODULES if name != "Reddit AI"]


@pytest.fixture
def crawler_env():
    """테스트마다 REDDIT_ENABLED 환경 변수와 크롤러 모듈 상태를 격리하고 종료 시 원복한다."""
    with pytest.MonkeyPatch.context() as mp:
        yield mp
    importlib.reload(config)
    importlib.reload(crawlers)


def _mock_source_fetches(mp: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    mocks: dict[str, MagicMock] = {}
    for source_name, module in _SOURCE_MODULES:
        mock_fetch = MagicMock(
            return_value=[
                {
                    "url": f"https://example.com/{source_name.lower().replace(' ', '-')}",
                    "source": source_name,
                    "title": f"{source_name} sample",
                    "content": "Sample article body",
                    "published_at": "2026-11-19T00:00:00Z",
                    "crawled_at": "2026-11-19T01:00:00",
                }
            ]
        )
        mp.setattr(module, "fetch", mock_fetch)
        mocks[source_name] = mock_fetch
    return mocks


def test_reddit_disabled_by_default_in_config(crawler_env):
    """REDDIT_ENABLED 환경 변수가 지정되지 않으면 기본값은 False다."""
    crawler_env.delenv("REDDIT_ENABLED", raising=False)
    importlib.reload(config)

    assert config.REDDIT_ENABLED is False


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("yes", True),
        ("YES", True),
        ("Yes", True),
        ("0", False),
        ("false", False),
        ("False", False),
        ("no", False),
        ("", False),
        ("enabled", False),
    ],
)
def test_reddit_enabled_parses_env_values(crawler_env, raw_value: str, expected: bool):
    """REDDIT_ENABLED는 1/true/yes(대소문자 무시)일 때만 True이고 그 외 값은 False다."""
    crawler_env.setenv("REDDIT_ENABLED", raw_value)
    importlib.reload(config)

    assert config.REDDIT_ENABLED is expected


def test_get_all_articles_skips_reddit_and_logs_reason_by_default(crawler_env, caplog):
    """기본 설정에서 get_all_articles()는 Reddit fetch를 호출하지 않고 비활성화 로그를 남기며 다른 출처는 모두 수집한다."""
    mocks = _mock_source_fetches(crawler_env)
    crawler_env.delenv("REDDIT_ENABLED", raising=False)
    importlib.reload(config)
    importlib.reload(crawlers)

    with caplog.at_level(logging.INFO, logger="crawlers"):
        articles = crawlers.get_all_articles()

    assert mocks["Reddit AI"].call_count == 0
    assert "Reddit AI" not in [name for name, _ in crawlers._SOURCES]
    for source_name in _OTHER_SOURCES:
        assert mocks[source_name].call_count == 1
    assert [article["source"] for article in articles] == _OTHER_SOURCES
    assert any(
        record.levelno == logging.INFO
        and "Reddit AI 수집 비활성화" in record.message
        and "REDDIT_ENABLED=false" in record.message
        for record in caplog.records
    )


def test_get_all_articles_calls_reddit_and_other_sources_when_enabled(crawler_env, caplog):
    """REDDIT_ENABLED=true면 get_all_articles()가 Reddit fetch와 다른 출처를 모두 호출해 수집한다."""
    mocks = _mock_source_fetches(crawler_env)
    crawler_env.setenv("REDDIT_ENABLED", "true")
    importlib.reload(config)
    importlib.reload(crawlers)

    assert "Reddit AI" in [name for name, _ in crawlers._SOURCES]

    with caplog.at_level(logging.INFO, logger="crawlers"):
        articles = crawlers.get_all_articles()

    assert mocks["Reddit AI"].call_count == 1
    for source_name in _OTHER_SOURCES:
        assert mocks[source_name].call_count == 1
    assert [article["source"] for article in articles] == [name for name, _ in _SOURCE_MODULES]
    assert "Reddit AI 수집 비활성화" not in caplog.text


def test_get_all_articles_isolates_failure_when_reddit_disabled(crawler_env, caplog):
    """Reddit이 비활성화된 상태에서도 한 출처가 실패하면 예외를 격리하고 나머지 출처 수집을 계속한다."""
    mocks = _mock_source_fetches(crawler_env)
    mocks["Google News"].side_effect = RuntimeError("수집 실패 시뮬레이션")
    crawler_env.delenv("REDDIT_ENABLED", raising=False)
    importlib.reload(config)
    importlib.reload(crawlers)

    with caplog.at_level(logging.INFO, logger="crawlers"):
        articles = crawlers.get_all_articles()

    assert mocks["Reddit AI"].call_count == 0
    for source_name in _OTHER_SOURCES:
        assert mocks[source_name].call_count == 1
    assert [article["source"] for article in articles] == [name for name in _OTHER_SOURCES if name != "Google News"]
    assert "Google News 크롤링 실패" in caplog.text

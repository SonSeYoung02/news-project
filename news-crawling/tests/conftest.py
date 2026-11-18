"""크롤러·번역 파이프라인 pytest 공용 픽스처 모듈."""

import json
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

import db

CRAWLER_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """각 테스트마다 격리된 임시 SQLite DB를 초기화하고 DB_PATH를 지정한다."""
    db_path = tmp_path / "test_news.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.delenv("CRAWL_LOCK_PATH", raising=False)
    db.init_db()
    yield db_path


@pytest.fixture
def temp_crawl_lock(
    temp_db: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    """임시 DB와 함께 격리된 공유 락 파일 경로를 CRAWL_LOCK_PATH로 지정한다."""
    lock_path = tmp_path / "locks" / "crawl.lock"
    monkeypatch.setenv("CRAWL_LOCK_PATH", str(lock_path))
    yield lock_path


@pytest.fixture
def fake_gemini_batch():
    """Gemini 묶음 번역 호출에 대한 표준 한국어 JSON 응답 생성기를 반환한다."""

    def _respond(batch, model=None):
        return json.dumps(
            [
                {
                    "id": job["article_id"],
                    "title": "한국어 제목",
                    "content": "한국어 번역 본문 " * 40,
                }
                for job in batch
            ],
            ensure_ascii=False,
        )

    return _respond


@pytest.fixture
def mock_call_gemini_batch(fake_gemini_batch) -> Iterator[MagicMock]:
    """translation.batch_translator.call_gemini_batch를 모킹해 실제 API 호출을 차단한다."""
    with patch(
        "translation.batch_translator.call_gemini_batch",
        side_effect=fake_gemini_batch,
    ) as mock_call:
        yield mock_call

"""백엔드 의도 기반 테스트용 공용 pytest 픽스처 모듈."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

import pytest
from fastapi.testclient import TestClient

import main


def _init_schema(db_path: Path, *, with_translations: bool = True) -> None:
    """article-storage 계약과 일치하는 임시 SQLite 스키마를 생성한다."""
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            """
            CREATE TABLE articles (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                url            TEXT UNIQUE NOT NULL,
                source         TEXT NOT NULL,
                title          TEXT NOT NULL,
                content        TEXT NOT NULL,
                published_at   TEXT,
                crawled_at     TEXT NOT NULL,
                summary        TEXT,
                major_category TEXT,
                sub_category   TEXT,
                tags           TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE article_analysis (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id     INTEGER NOT NULL REFERENCES articles(id),
                summary        TEXT,
                major_category TEXT,
                sub_category   TEXT,
                tags           TEXT,
                analyzed_at    TEXT NOT NULL,
                UNIQUE(article_id)
            )
            """
        )
        if with_translations:
            conn.execute(
                """
                CREATE TABLE article_translations (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id         INTEGER NOT NULL REFERENCES articles(id),
                    content_hash       TEXT NOT NULL,
                    translated_title   TEXT,
                    translated_content TEXT,
                    language           TEXT NOT NULL DEFAULT 'ko',
                    status             TEXT NOT NULL DEFAULT 'pending',
                    attempts           INTEGER NOT NULL DEFAULT 0,
                    completed_at       TEXT,
                    model              TEXT,
                    last_error         TEXT,
                    created_at         TEXT NOT NULL,
                    updated_at         TEXT NOT NULL,
                    UNIQUE(article_id, content_hash)
                )
                """
            )


class DbSeeder:
    """임시 SQLite DB에 기사·분석·번역 데이터를 삽입하는 테스트 헬퍼."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._seq = 0

    def article(
        self,
        *,
        article_id: Optional[int] = None,
        url: Optional[str] = None,
        source: str = "devto",
        title: str = "Sample Article Title",
        content: str = "Sample Article Content",
        published_at: Optional[str] = "2026-11-10T02:00:00Z",
        crawled_at: str = "2026-11-10T11:00:00",
        summary: Optional[str] = "기본 요약",
        major_category: Optional[str] = "AI",
        sub_category: Optional[str] = "LLM",
        tags: Optional[str] = '["AI"]',
    ) -> int:
        self._seq += 1
        actual_url = url if url is not None else f"https://example.com/articles/{self._seq}"
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            if article_id is not None:
                conn.execute(
                    """
                    INSERT INTO articles (
                        id, url, source, title, content, published_at, crawled_at,
                        summary, major_category, sub_category, tags
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article_id,
                        actual_url,
                        source,
                        title,
                        content,
                        published_at,
                        crawled_at,
                        summary,
                        major_category,
                        sub_category,
                        tags,
                    ),
                )
                return article_id

            cursor = conn.execute(
                """
                INSERT INTO articles (
                    url, source, title, content, published_at, crawled_at,
                    summary, major_category, sub_category, tags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    actual_url,
                    source,
                    title,
                    content,
                    published_at,
                    crawled_at,
                    summary,
                    major_category,
                    sub_category,
                    tags,
                ),
            )
            return int(cursor.lastrowid)

    def analysis(
        self,
        *,
        article_id: int,
        summary: Optional[str] = None,
        major_category: Optional[str] = None,
        sub_category: Optional[str] = None,
        tags: Optional[str] = None,
        analyzed_at: str = "2026-11-10T11:05:00",
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO article_analysis (
                    article_id, summary, major_category, sub_category, tags, analyzed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (article_id, summary, major_category, sub_category, tags, analyzed_at),
            )

    def translation(
        self,
        *,
        article_id: int,
        content_hash: str,
        translated_title: Optional[str] = "번역된 제목",
        translated_content: Optional[str] = "번역된 본문",
        status: str = "completed",
        language: str = "ko",
        created_at: str = "2026-11-10T11:05:00",
        updated_at: str = "2026-11-10T11:10:00",
    ) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO article_translations (
                    article_id, content_hash, translated_title, translated_content,
                    language, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id,
                    content_hash,
                    translated_title,
                    translated_content,
                    language,
                    status,
                    created_at,
                    updated_at,
                ),
            )

    def count_articles(self) -> int:
        with closing(sqlite3.connect(self.db_path)) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0])


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """실제 news.db와 격리된 임시 SQLite DB 경로를 구성한다."""
    db_path = tmp_path / "test_news.db"
    _init_schema(db_path, with_translations=True)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setattr(main, "DB_PATH", db_path)
    main._clear_briefing_cache()
    try:
        yield db_path
    finally:
        main._clear_briefing_cache()


@pytest.fixture
def temp_db_without_translations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """article_translations 테이블이 없는 구형 DB 환경을 구성한다."""
    db_path = tmp_path / "test_legacy_news.db"
    _init_schema(db_path, with_translations=False)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setattr(main, "DB_PATH", db_path)
    main._clear_briefing_cache()
    try:
        yield db_path
    finally:
        main._clear_briefing_cache()


@pytest.fixture
def seed_db(temp_db: Path) -> DbSeeder:
    """임시 DB에 테스트 데이터를 삽입하는 시더 객체를 반환한다."""
    return DbSeeder(temp_db)


@pytest.fixture
def seed_legacy_db(temp_db_without_translations: Path) -> DbSeeder:
    """번역 테이블이 없는 임시 DB용 시더 객체를 반환한다."""
    return DbSeeder(temp_db_without_translations)


@pytest.fixture
def client(temp_db: Path):
    """임시 DB가 바인딩된 FastAPI TestClient를 반환한다."""
    with TestClient(main.app) as test_client:
        yield test_client

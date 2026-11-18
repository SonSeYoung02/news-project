import os
import random
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import main

FIXED_NOW = datetime(2026, 11, 10, 3, 0, 0, tzinfo=timezone.utc)


def _create_schema(db_path: str, with_translations: bool = True) -> None:
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


def _reset_briefing_cache() -> None:
    if hasattr(main, "_clear_briefing_cache"):
        main._clear_briefing_cache()


class TestBriefingThroughputSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "news.db")
        _create_schema(self.db, with_translations=True)
        self.env_patch = patch.dict(os.environ, {"DB_PATH": self.db})
        self.db_patch = patch.object(main, "DB_PATH", main.Path(self.db))
        self.env_patch.start()
        self.db_patch.start()
        _reset_briefing_cache()
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        _reset_briefing_cache()
        self.db_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def _insert_articles(self, rows: list[tuple]) -> None:
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.executemany(
                """
                INSERT INTO articles
                    (id, url, source, title, content, published_at, crawled_at, summary, major_category, sub_category, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def test_old_ai_articles_do_not_load_bodies_or_compute_hashes(self):
        old_rows = [
            (
                i,
                f"https://example.com/old/{i}",
                "techcrunch",
                f"Old AI Article {i}",
                "B" * 2000,
                "2000-01-01T00:00:00Z",
                "2000-01-01T01:00:00",
                "old summary",
                "AI",
                "LLM",
                '["AI"]',
            )
            for i in range(1, 1201)
        ]
        self._insert_articles(old_rows)

        row_calls = 0
        hash_calls = 0
        orig_row_to_dict = main._row_to_dict
        orig_hash = main.compute_content_hash

        def spy_row_to_dict(row):
            nonlocal row_calls
            row_calls += 1
            return orig_row_to_dict(row)

        def spy_hash(title, content):
            nonlocal hash_calls
            hash_calls += 1
            return orig_hash(title, content)

        with patch.object(main, "_utc_now", return_value=FIXED_NOW), \
             patch.object(main, "_row_to_dict", side_effect=spy_row_to_dict), \
             patch.object(main, "compute_content_hash", side_effect=spy_hash):
            resp = self.client.get("/briefing")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["articles"], [])
        self.assertEqual(row_calls, 0)
        self.assertEqual(hash_calls, 0)

    def test_only_selected_five_articles_load_full_bodies_and_hashes(self):
        old_rows = [
            (
                i,
                f"https://example.com/old/{i}",
                "techcrunch",
                f"Old AI {i}",
                "X" * 1500,
                "2020-01-01T00:00:00Z",
                "2020-01-01T01:00:00",
                "summary",
                "AI",
                "LLM",
                '["AI"]',
            )
            for i in range(1, 801)
        ]
        recent_rows = []
        for idx in range(60):
            aid = 1000 + idx
            src = f"source_{idx % 6}"
            topic = f"topic_{idx % 6}"
            ts = (FIXED_NOW - timedelta(minutes=idx)).isoformat()
            recent_rows.append(
                (
                    aid,
                    f"https://example.com/recent/{aid}",
                    src,
                    f"Recent AI {aid}",
                    f"Body {aid} " + ("C" * 500),
                    ts,
                    ts,
                    f"Summary {aid}",
                    "AI",
                    topic,
                    '["AI"]',
                )
            )
        self._insert_articles(old_rows + recent_rows)

        # 최상위 후보 1000번 기사에 번역 추가
        h1000 = main.compute_content_hash("Recent AI 1000", "Body 1000 " + ("C" * 500))
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                """
                INSERT INTO article_translations
                    (article_id, content_hash, translated_title, translated_content, status, created_at, updated_at)
                VALUES (1000, ?, '번역 제목 1000', '번역 본문 1000', 'completed', '2026-11-10T03:00:00', '2026-11-10T03:00:00')
                """,
                (h1000,),
            )

        row_calls = 0
        hash_calls = 0
        orig_row_to_dict = main._row_to_dict
        orig_hash = main.compute_content_hash

        def spy_row_to_dict(row):
            nonlocal row_calls
            row_calls += 1
            return orig_row_to_dict(row)

        def spy_hash(title, content):
            nonlocal hash_calls
            hash_calls += 1
            return orig_hash(title, content)

        with patch.object(main, "_utc_now", return_value=FIXED_NOW), \
             patch.object(main, "_row_to_dict", side_effect=spy_row_to_dict), \
             patch.object(main, "compute_content_hash", side_effect=spy_hash):
            resp = self.client.get("/briefing")

        self.assertEqual(resp.status_code, 200)
        articles = resp.json()["articles"]
        self.assertEqual(len(articles), 5)
        self.assertEqual(len({a["source"] for a in articles}), 5)
        self.assertEqual(len({a["sub_category"] for a in articles}), 5)
        self.assertEqual(articles[0]["id"], 1000)
        self.assertEqual(articles[0]["title"], "번역 제목 1000")
        self.assertEqual(articles[0]["content"], "번역 본문 1000")
        self.assertEqual(row_calls, 5)
        self.assertEqual(hash_calls, 5)

    def test_streaming_compaction_matches_exact_full_selection_with_many_24h_candidates(self):
        # 500건 압축 임계값을 여러 번 넘기는 1,200건의 24시간 내 후보 생성
        rows = []
        raw_candidates = []
        for idx in range(1, 1201):
            # 뒤쪽에 더 최신 기사와 희귀 주제/출처를 섞어 DB 순회 순서에 의존하지 않게 구성
            if idx % 37 == 0:
                topic = f"rare_topic_{idx}"
            elif idx % 5 == 0:
                topic = ""
            else:
                topic = f"topic_{idx % 12}"
            src = f"src_{idx % 25}"
            if idx % 3 == 0:
                # RFC 2822 형식
                dt = FIXED_NOW - timedelta(seconds=(1200 - idx) * 30)
                published_at = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
                crawled_at = "2026-11-10T01:00:00"
                effective = dt
            elif idx % 3 == 1:
                # published_at 오류 → crawled_at fallback (naive KST)
                dt = FIXED_NOW - timedelta(seconds=(1200 - idx) * 25)
                published_at = "invalid-date"
                kst_dt = dt.astimezone(timezone(timedelta(hours=9))).replace(tzinfo=None)
                crawled_at = kst_dt.isoformat()
                effective = dt
            else:
                dt = FIXED_NOW - timedelta(seconds=(1200 - idx) * 20)
                published_at = dt.isoformat().replace("+00:00", "Z")
                crawled_at = published_at
                effective = dt

            rows.append(
                (
                    idx,
                    f"https://example.com/c/{idx}",
                    src,
                    f"Title {idx}",
                    "Body",
                    published_at,
                    crawled_at,
                    "Summary",
                    "AI",
                    topic,
                    "[]",
                )
            )
            raw_candidates.append((effective, idx, src, topic.strip()))

        self._insert_articles(rows)

        # 전체 후보 기준 참조 정답 계산
        expected_ids = []
        remaining = list(raw_candidates)
        used_sources, used_topics = set(), set()
        while remaining and len(expected_ids) < 5:
            chosen = max(
                remaining,
                key=lambda c: (
                    bool(c[3]) and c[3] not in used_topics,
                    c[2] not in used_sources,
                    c[0],
                    c[1],
                ),
            )
            remaining.remove(chosen)
            expected_ids.append(chosen[1])
            used_sources.add(chosen[2])
            used_topics.add(chosen[3])

        row_calls = 0
        orig_row_to_dict = main._row_to_dict

        def spy_row_to_dict(row):
            nonlocal row_calls
            row_calls += 1
            return orig_row_to_dict(row)

        with patch.object(main, "_utc_now", return_value=FIXED_NOW), \
             patch.object(main, "_row_to_dict", side_effect=spy_row_to_dict):
            resp = self.client.get("/briefing")

        self.assertEqual(resp.status_code, 200)
        actual_ids = [a["id"] for a in resp.json()["articles"]]
        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(row_calls, 5)

    def test_compact_briefing_candidates_property_equivalence(self):
        rng = random.Random(20261116)
        for seed_idx in range(50):
            topic_cardinality = rng.choice([1, 3, 6, 15, 40])
            source_cardinality = rng.choice([1, 3, 6, 15, 40])
            pool = []
            for aid in range(1, 601):
                published = FIXED_NOW - timedelta(seconds=rng.randint(0, 86400))
                source = f"s_{rng.randint(0, source_cardinality - 1)}"
                topic = "" if rng.random() < 0.2 else f"t_{rng.randint(0, topic_cardinality - 1)}"
                pool.append((published, aid, source, topic))

            expected = main._select_briefing_ids(pool)
            compacted = main._compact_briefing_candidates(pool)
            self.assertLessEqual(len(compacted), 56)
            actual = main._select_briefing_ids(compacted)
            self.assertEqual(actual, expected, f"mismatch at seed_idx={seed_idx}")

    def test_briefing_preserves_valid_articles_across_diverse_date_formats_without_recent_n_cutoff(self):
        # id=1(가장 오래된 PK)이 유효한 24h RFC 2822 기사, id=2..1501은 구버전 published_at + 최신 crawled_at
        rows = [
            (
                1,
                "https://example.com/valid-old-id",
                "arXiv",
                "Valid RFC Date Article",
                "Valid Body",
                "Tue, 10 Nov 2026 11:30:00 +0900",
                "2026-11-10T11:30:00",
                "Summary",
                "AI",
                "Agents",
                "[]",
            )
        ]
        for aid in range(2, 1502):
            rows.append(
                (
                    aid,
                    f"https://example.com/stale/{aid}",
                    "techcrunch",
                    f"Stale Article {aid}",
                    "Stale Body",
                    "2020-01-01T00:00:00Z",
                    "2026-11-10T11:45:00",
                    "Summary",
                    "AI",
                    "LLM",
                    "[]",
                )
            )
        rows.append(
            (
                1502,
                "https://example.com/fallback",
                "huggingface",
                "Fallback Crawled Date Article",
                "Fallback Body",
                "not-a-date",
                "2026-11-10T11:50:00",
                "Summary",
                "AI",
                "Vision",
                "[]",
            )
        )
        self._insert_articles(rows)

        with patch.object(main, "_utc_now", return_value=FIXED_NOW):
            resp = self.client.get("/briefing")

        self.assertEqual(resp.status_code, 200)
        ids = {a["id"] for a in resp.json()["articles"]}
        self.assertEqual(ids, {1, 1502})

    def test_briefing_ttl_cache_hit_and_invalidation_on_db_change_and_path_change(self):
        self._insert_articles(
            [
                (
                    1,
                    "https://example.com/1",
                    "arXiv",
                    "First AI",
                    "Body 1",
                    "2026-11-10T02:00:00Z",
                    "2026-11-10T11:00:00",
                    "Summary 1",
                    "AI",
                    "LLM",
                    '["AI"]',
                )
            ]
        )

        connect_calls = 0
        orig_connect = main._connect

        def spy_connect():
            nonlocal connect_calls
            connect_calls += 1
            return orig_connect()

        fake_mono = [100.0]
        fake_now = [FIXED_NOW]

        with patch.object(main, "_connect", side_effect=spy_connect), \
             patch.object(main, "_utc_now", side_effect=lambda: fake_now[0]), \
             patch("time.monotonic", side_effect=lambda: fake_mono[0]):
            first = self.client.get("/briefing")
            self.assertEqual(first.status_code, 200)
            self.assertEqual([a["id"] for a in first.json()["articles"]], [1])
            self.assertEqual(connect_calls, 1)

            # TTL 내 재요청 → 캐시 적중 (_connect 미호출) 및 호출자 변조 격리
            fake_mono[0] += 5.0
            fake_now[0] += timedelta(seconds=5)
            direct = main.get_briefing()
            direct["articles"][0]["tags"].append("mutated")
            direct["articles"].clear()
            second = self.client.get("/briefing")
            self.assertEqual(second.status_code, 200)
            self.assertEqual([a["id"] for a in second.json()["articles"]], [1])
            self.assertEqual(second.json()["articles"][0]["tags"], ["AI"])
            self.assertEqual(connect_calls, 1)

            # 동일 DB에 새 기사 추가 → TTL 내라도 즉시 캐시 무효화
            self._insert_articles(
                [
                    (
                        2,
                        "https://example.com/2",
                        "huggingface",
                        "Second AI",
                        "Body 2",
                        "2026-11-10T02:30:00Z",
                        "2026-11-10T11:30:00",
                        "Summary 2",
                        "AI",
                        "Vision",
                        '["AI"]',
                    )
                ]
            )
            fake_mono[0] += 1.0
            fake_now[0] += timedelta(seconds=1)
            third = self.client.get("/briefing")
            self.assertEqual(third.status_code, 200)
            self.assertEqual({a["id"] for a in third.json()["articles"]}, {1, 2})
            self.assertEqual(connect_calls, 2)

            # 동일 DB에 번역 완료 추가 → 즉시 캐시 무효화
            h2 = main.compute_content_hash("Second AI", "Body 2")
            with closing(sqlite3.connect(self.db)) as conn, conn:
                conn.execute(
                    """
                    INSERT INTO article_translations
                        (article_id, content_hash, translated_title, translated_content, status, created_at, updated_at)
                    VALUES (2, ?, '두 번째 번역', '번역 본문', 'completed', '2026-11-10T02:35:00', '2026-11-10T02:35:00')
                    """,
                    (h2,),
                )
            fourth = self.client.get("/briefing")
            self.assertEqual(fourth.status_code, 200)
            by_id = {a["id"]: a for a in fourth.json()["articles"]}
            self.assertEqual(by_id[2]["title"], "두 번째 번역")
            self.assertEqual(connect_calls, 3)

            # TTL 만료 시 재계산
            fake_mono[0] += main.BRIEFING_CACHE_TTL_SECONDS + 1.0
            fake_now[0] += timedelta(seconds=main.BRIEFING_CACHE_TTL_SECONDS + 1.0)
            fifth = self.client.get("/briefing")
            self.assertEqual(fifth.status_code, 200)
            self.assertEqual(connect_calls, 4)

            # DB 경로 변경 시 캐시 격리
            db2 = os.path.join(self.tmp.name, "news2.db")
            _create_schema(db2, with_translations=True)
            with closing(sqlite3.connect(db2)) as conn, conn:
                conn.execute(
                    """
                    INSERT INTO articles
                        (id, url, source, title, content, published_at, crawled_at, summary, major_category, sub_category, tags)
                    VALUES (99, 'https://example.com/99', 'devto', 'Other DB AI', 'Body 99',
                            '2026-11-10T02:00:00Z', '2026-11-10T11:00:00', 'Sum', 'AI', 'Agents', '[]')
                    """
                )
            with patch.dict(os.environ, {"DB_PATH": db2}):
                other = self.client.get("/briefing")
            self.assertEqual(other.status_code, 200)
            self.assertEqual([a["id"] for a in other.json()["articles"]], [99])
            self.assertEqual(connect_calls, 5)

    def test_briefing_wal_mode_db_change_invalidates_cache(self):
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                INSERT INTO articles
                    (id, url, source, title, content, published_at, crawled_at, summary, major_category, sub_category, tags)
                VALUES (1, 'https://example.com/1', 'arXiv', 'WAL AI 1', 'Body 1',
                        '2026-11-10T02:00:00Z', '2026-11-10T11:00:00', 'Sum', 'AI', 'LLM', '[]')
                """
            )
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        connect_calls = 0
        orig_connect = main._connect

        def spy_connect():
            nonlocal connect_calls
            connect_calls += 1
            return orig_connect()

        with patch.object(main, "_connect", side_effect=spy_connect), \
             patch.object(main, "_utc_now", return_value=FIXED_NOW):
            r1 = self.client.get("/briefing")
            self.assertEqual(r1.status_code, 200)
            self.assertEqual([a["id"] for a in r1.json()["articles"]], [1])
            self.assertEqual(connect_calls, 1)

            # TTL 내 캐시 적중 확인
            r1_cached = self.client.get("/briefing")
            self.assertEqual(r1_cached.status_code, 200)
            self.assertEqual(connect_calls, 1)

            # 체크포인트 없이 -wal에만 기록되는 변경 발생
            with closing(sqlite3.connect(self.db)) as conn:
                conn.execute(
                    """
                    INSERT INTO articles
                        (id, url, source, title, content, published_at, crawled_at, summary, major_category, sub_category, tags)
                    VALUES (2, 'https://example.com/2', 'huggingface', 'WAL AI 2', 'Body 2',
                            '2026-11-10T02:30:00Z', '2026-11-10T11:30:00', 'Sum', 'AI', 'Vision', '[]')
                    """
                )
                conn.commit()

            r2 = self.client.get("/briefing")
            self.assertEqual(r2.status_code, 200)
            self.assertEqual({a["id"] for a in r2.json()["articles"]}, {1, 2})
            self.assertEqual(connect_calls, 2)

    def test_briefing_single_flight_prevents_concurrent_duplicate_computation(self):
        self._insert_articles(
            [
                (
                    i,
                    f"https://example.com/{i}",
                    f"src_{i}",
                    f"Title {i}",
                    "Body",
                    "2026-11-10T02:00:00Z",
                    "2026-11-10T11:00:00",
                    "Summary",
                    "AI",
                    f"topic_{i}",
                    "[]",
                )
                for i in range(1, 6)
            ]
        )

        compute_count = 0
        count_lock = threading.Lock()
        orig_connect = main._connect

        def slow_connect():
            nonlocal compute_count
            with count_lock:
                compute_count += 1
            time.sleep(0.08)
            return orig_connect()

        with patch.object(main, "_connect", side_effect=slow_connect), \
             patch.object(main, "_utc_now", return_value=FIXED_NOW):
            barrier = threading.Barrier(8)

            def worker(_):
                barrier.wait(timeout=5)
                return self.client.get("/briefing")

            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(worker, range(8)))

        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertTrue(all(len(r.json()["articles"]) == 5 for r in responses))
        self.assertEqual(compute_count, 1)


class TestArticlesInputBoundsSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "news.db")
        _create_schema(self.db, with_translations=True)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                """
                INSERT INTO articles
                    (id, url, source, title, content, published_at, crawled_at, summary, major_category, sub_category, tags)
                VALUES
                    (1, 'https://example.com/1', 'devto', 'Discount 100% Guide', 'Model ai_v2\\release launch details',
                     '2026-11-10T02:00:00Z', '2026-11-10T11:00:00', 'Summary 1', 'AI', 'LLM', '["AI"]'),
                    (2, 'https://example.com/2', 'naver', 'Other News', 'Model aixv2 comparison',
                     '2026-11-10T01:00:00Z', '2026-11-10T10:00:00', 'Summary 2', 'IT', 'Cloud', '["IT"]')
                """
            )
        self.env_patch = patch.dict(os.environ, {"DB_PATH": self.db})
        self.db_patch = patch.object(main, "DB_PATH", main.Path(self.db))
        self.env_patch.start()
        self.db_patch.start()
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        self.db_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def test_page_sqlite_int64_overflow_returns_422_not_500(self):
        for page in (9223372036854775808, 9223372036854775807):
            resp = self.client.get("/articles", params={"page": page})
            self.assertEqual(resp.status_code, 422, f"page={page} returned {resp.status_code}")

    def test_page_and_calculated_offset_upper_bounds_return_422(self):
        self.assertEqual(self.client.get("/articles", params={"page": 10001, "size": 1}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"page": 2002, "size": 100}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"page": 0}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"page": -1}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"size": 0}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"size": 101}).status_code, 422)

    def test_article_detail_id_sqlite_int64_overflow_returns_422_and_missing_returns_404(self):
        self.assertEqual(self.client.get("/articles/9223372036854775808").status_code, 422)
        self.assertEqual(self.client.get("/articles/-9223372036854775809").status_code, 422)
        self.assertEqual(self.client.get("/articles/999999").status_code, 404)
        self.assertEqual(self.client.get("/articles/0").status_code, 404)

    def test_search_query_and_filter_length_and_nul_validation(self):
        self.assertEqual(self.client.get("/articles", params={"q": "a" * 201}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"category": "a" * 101}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"source": "a" * 101}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"q": "abc\x00def"}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"category": "AI\x00"}).status_code, 422)
        self.assertEqual(self.client.get("/articles", params={"source": "devto\x00"}).status_code, 422)

    def test_valid_queries_empty_q_and_like_wildcards_preserve_contract_without_auth(self):
        # 정상 경계와 무인증 공개 접근
        ok_resp = self.client.get("/articles", params={"page": 1, "size": 20})
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.json()["total"], 2)

        self.assertEqual(self.client.get("/articles", params={"page": 10000, "size": 20}).status_code, 200)
        self.assertEqual(self.client.get("/articles", params={"page": 2001, "size": 100}).status_code, 200)
        self.assertEqual(self.client.get("/articles", params={"q": ""}).json()["total"], 2)
        self.assertEqual(self.client.get("/articles", params={"q": "a" * 200}).status_code, 200)

        # LIKE 와일드카드 리터럴 일치 검증
        percent_resp = self.client.get("/articles", params={"q": "100%"})
        self.assertEqual(percent_resp.status_code, 200)
        self.assertEqual([a["id"] for a in percent_resp.json()["articles"]], [1])

        underscore_resp = self.client.get("/articles", params={"q": "ai_v2"})
        self.assertEqual(underscore_resp.status_code, 200)
        self.assertEqual([a["id"] for a in underscore_resp.json()["articles"]], [1])

        backslash_resp = self.client.get("/articles", params={"q": "ai_v2\\release"})
        self.assertEqual(backslash_resp.status_code, 200)
        self.assertEqual([a["id"] for a in backslash_resp.json()["articles"]], [1])


if __name__ == "__main__":
    unittest.main()

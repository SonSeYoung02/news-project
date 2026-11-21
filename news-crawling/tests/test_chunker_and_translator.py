from unittest.mock import patch

import db
from translation.chunker import chunk_text
from translation.translator import translate_article_job


class DummyRateLimiter:
    def __init__(self, allow=True):
        self.allow = allow

    def can_consume(self, requests=1):
        return self.allow

    def wait_and_consume(self, tokens=100, requests=1):
        return self.allow


class DummyCutoffController:
    def __init__(self, can_request=True):
        self._can_request = can_request

    def can_request(self, now_dt=None):
        return self._can_request


def test_chunk_text_small_and_large():
    """짧은 본문은 단일 조각으로 유지하고 긴 본문은 max_chars 기준으로 문단 분할한다."""
    short = "This is a short article."
    chunks = chunk_text(short, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0] == short

    p1 = "Paragraph 1: " + ("A" * 80)
    p2 = "Paragraph 2: " + ("B" * 80)
    p3 = "Paragraph 3: " + ("C" * 80)
    long_text = f"{p1}\n\n{p2}\n\n{p3}"
    chunks_long = chunk_text(long_text, max_chars=120)
    assert len(chunks_long) == 3
    assert chunks_long[0] == p1
    assert chunks_long[1] == p2
    assert chunks_long[2] == p3


def test_chunk_text_recognizes_single_newline_as_paragraph_boundary():
    """단일 줄바꿈('\\n')만 있는 본문도 문단 경계로 인식해 분할하고 재결합 시 문단 구조를 유지한다."""
    p1 = "Paragraph 1: " + ("A" * 80)
    p2 = "Paragraph 2: " + ("B" * 80)
    p3 = "Paragraph 3: " + ("C" * 80)
    single_newline_text = f"{p1}\n{p2}\n{p3}"

    chunks = chunk_text(single_newline_text, max_chars=120)
    assert chunks == [p1, p2, p3]
    assert "\n\n".join(chunks) == f"{p1}\n\n{p2}\n\n{p3}"

    chunks_packed = chunk_text(single_newline_text, max_chars=200)
    assert len(chunks_packed) == 2
    assert all(len(c) <= 200 for c in chunks_packed)
    assert "\n\n".join(chunks_packed) == f"{p1}\n\n{p2}\n\n{p3}"

    heading = "Section Heading Without Punctuation"
    line1 = "First line body without trailing period"
    line2 = "Second line body without trailing period"
    chunks_no_punct = chunk_text(f"{heading}\n{line1}\n{line2}", max_chars=50)
    assert chunks_no_punct == [heading, line1, line2]


def test_chunk_text_preserves_newlines_during_long_paragraph_sentence_splitting():
    """긴 문단을 문장 단위로 분할할 때도 원래 줄바꿈과 코드 블록을 보존한다."""
    s1 = ("First sentence discusses distributed training. " * 2).strip()
    s2 = ("Second sentence follows after a line break. " * 2).strip()
    s3 = ("Third sentence stays on the same paragraph line. " * 2).strip()
    mixed_text = f"Intro.\n\n{s1}\n{s2} {s3}"

    chunks = chunk_text(mixed_text, max_chars=200)
    rejoined = "\n\n".join(chunks)

    assert all(len(c) <= 200 for c in chunks)
    assert f"{s1} {s2}" not in rejoined
    assert [line.strip() for line in rejoined.splitlines() if line.strip()] == [
        "Intro.",
        s1,
        f"{s2} {s3}",
    ]

    code = "def hello():\n    return 1"
    doc_with_code = f"{'A' * 120}\n\n{code}\n\n{'B' * 120}"
    chunks_code = chunk_text(doc_with_code, max_chars=200)
    assert any(code in c for c in chunks_code)
    assert "\n\n".join(chunks_code) == doc_with_code

    long_single_line = "Sentence one about AI. Sentence two about ML. Sentence three about DL."
    assert chunk_text(long_single_line, max_chars=46) == [
        "Sentence one about AI. Sentence two about ML.",
        "Sentence three about DL.",
    ]


def test_translate_article_job_with_resume(temp_db):
    """마감 시간으로 중단된 조각 번역은 다음 실행에서 남은 조각만 이어서 번역해 완료한다."""
    with patch("translation.translator._call_gemini_api") as mock_gemini:
        mock_gemini.side_effect = lambda prompt, **kwargs: f"[번역] {prompt[:20]}"

        p1 = "First chunk of content. " + ("X" * 60)
        p2 = "Second chunk of content. " + ("Y" * 60)
        content = f"{p1}\n\n{p2}"

        article = {
            "url": "https://example.com/chunk-test",
            "source": "devto",
            "title": "Chunked Title",
            "content": content,
            "published_at": "2026-11-12T00:00:00Z",
            "crawled_at": "2026-11-12T01:00:00",
        }
        db.save_article(article)
        aid = db.get_article_id_by_url(article["url"])
        content_hash = db.compute_content_hash(article["title"], content)

        job = {
            "article_id": aid,
            "url": article["url"],
            "title": article["title"],
            "content": content,
            "content_hash": content_hash,
            "source": "devto",
        }

        rate_limiter = DummyRateLimiter(allow=True)
        call_count = [0]

        class SteppedCutoff:
            def can_request(self, now_dt=None):
                call_count[0] += 1
                return call_count[0] <= 2

        ok1 = translate_article_job(
            job=job,
            rate_limiter=rate_limiter,
            cutoff_controller=SteppedCutoff(),
            max_chars=90,
        )
        assert not ok1

        trans_mid = db.get_or_create_translation(aid, content_hash)
        assert trans_mid["status"] == "pending"
        chunks_mid = db.get_translation_chunks(aid, content_hash)
        assert len(chunks_mid) >= 1
        assert chunks_mid[0]["status"] == "completed"

        calls_phase1 = mock_gemini.call_count

        ok2 = translate_article_job(
            job=job,
            rate_limiter=DummyRateLimiter(allow=True),
            cutoff_controller=DummyCutoffController(can_request=True),
            max_chars=90,
        )
        assert ok2

        calls_phase2 = mock_gemini.call_count - calls_phase1
        assert calls_phase2 == 1

        trans_final = db.get_or_create_translation(aid, content_hash)
        assert trans_final["status"] == "completed"
        assert trans_final["translated_title"] is not None
        assert trans_final["translated_content"] is not None
        assert "[번역]" in trans_final["translated_content"]

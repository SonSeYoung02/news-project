import re

_BLANK_LINE_RE = re.compile(r"\r?\n[ \t]*\r?\n")
_NEWLINE_RE = re.compile(r"\r?\n")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(\s+)")


def _pack_units(units: list[str], max_chars: int, joiner: str) -> list[str]:
    """허용 길이(max_chars) 안에서 인접 단위를 joiner로 묶는다."""
    packed: list[str] = []
    current: list[str] = []
    current_len = 0

    for unit in units:
        sep_len = len(joiner) if current else 0
        if current and current_len + sep_len + len(unit) > max_chars:
            packed.append(joiner.join(current))
            current = [unit]
            current_len = len(unit)
        else:
            current.append(unit)
            current_len += sep_len + len(unit)

    if current:
        packed.append(joiner.join(current))
    return packed


def _split_by_sentences(paragraph: str, max_chars: int) -> list[str]:
    """문장 끝 부호 뒤 공백·줄바꿈 구분자를 보존한 채 max_chars 이하 조각으로 나눈다."""
    parts = _SENTENCE_SPLIT_RE.split(paragraph)
    if len(parts) == 1:
        return [paragraph]

    chunks: list[str] = []
    buf = parts[0]
    for i in range(1, len(parts), 2):
        sep = parts[i]
        sent = parts[i + 1] if i + 1 < len(parts) else ""
        if not sent:
            continue
        if buf and len(buf) + len(sep) + len(sent) > max_chars:
            chunks.append(buf)
            buf = sent
        else:
            buf += sep + sent
    if buf:
        chunks.append(buf)
    return chunks


def _split_long_block(block: str, max_chars: int) -> list[str]:
    """max_chars를 초과하는 블록을 줄바꿈 -> 문장 순으로 분할하며 줄바꿈을 보존한다."""
    lines = [line.strip() for line in _NEWLINE_RE.split(block) if line.strip()]
    if len(lines) > 1:
        expanded: list[str] = []
        for line in lines:
            if len(line) > max_chars:
                expanded.extend(_split_by_sentences(line, max_chars))
            else:
                expanded.append(line)
        return _pack_units(expanded, max_chars, joiner="\n")
    return _split_by_sentences(block, max_chars)


def chunk_text(text: str, max_chars: int = 2000) -> list[str]:
    """긴 기사 본문을 자연스러운 문단 또는 문장 단위로 분할한다.
    - max_chars 이하의 크기로 분할하며 문맥을 보존한다.
    - 코드 블록, 숫자, 링크, 고유명사를 훼손하지 않는다.
    - 재결합 시 원문의 문단 흐름을 그대로 복원할 수 있다.
    """
    if not text or not text.strip():
        return []
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    if _BLANK_LINE_RE.search(text):
        paragraphs = [p.strip() for p in _BLANK_LINE_RE.split(text) if p.strip()]
    else:
        paragraphs = [p.strip() for p in _NEWLINE_RE.split(text) if p.strip()]

    chunks: list[str] = []
    pending: list[str] = []

    for p_str in paragraphs:
        if len(p_str) > max_chars:
            if pending:
                chunks.extend(_pack_units(pending, max_chars, joiner="\n\n"))
                pending = []
            chunks.extend(_split_long_block(p_str, max_chars))
        else:
            pending.append(p_str)

    if pending:
        chunks.extend(_pack_units(pending, max_chars, joiner="\n\n"))

    return chunks

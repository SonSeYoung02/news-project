import re

from bs4 import BeautifulSoup

from crawlers._html_text import feed_content_to_text, html_to_text, looks_like_html, normalize_paragraphs
from crawlers.geeknews import _parse_feed

_TAG_RESIDUE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*[^<>]*>")

_ICEWM_ESCAPED = (
    "&lt;div&gt;&lt;ul&gt;&lt;li&gt;&lt;strong&gt;IceWM&lt;/strong&gt;은 빠르고 단순함&lt;/li&gt;"
    "&lt;li&gt;키보드만으로도 사용 가능&lt;/li&gt;&lt;/ul&gt;&lt;hr&gt;&lt;h2&gt;창 관리&lt;/h2&gt;&lt;/div&gt;"
)
_ICEWM_EXPECTED = "• IceWM은 빠르고 단순함\n• 키보드만으로도 사용 가능\n창 관리"


def _atom_content(inner: str, attrs: str) -> object:
    xml = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><content {attrs}>{inner}</content></entry></feed>'
    return BeautifulSoup(xml, "lxml-xml").find("content")


class TestFeedContentToText:
    def test_escaped_atom_html_content(self):
        """이스케이프된 Atom HTML 콘텐츠를 태그 잔여물 없이 읽기 좋은 텍스트로 변환한다."""
        tag = _atom_content(_ICEWM_ESCAPED, "type='html' xml:lang='ko'")
        result = feed_content_to_text(tag)
        assert result == _ICEWM_EXPECTED
        assert _TAG_RESIDUE.search(result) is None

    def test_xhtml_content_with_child_tags(self):
        """XHTML 콘텐츠의 자식 태그와 엔티티를 제거하고 링크 URL은 남기지 않는다."""
        inner = (
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            '<p>Hello <a href="https://example.com">링크</a> &amp; <em>world</em></p>'
            "<ul><li>항목</li></ul></div>"
        )
        tag = _atom_content(inner, 'type="xhtml"')
        result = feed_content_to_text(tag)
        assert result == "Hello 링크 & world\n• 항목"
        assert "https://example.com" not in result

    def test_double_escaped_text_is_unescaped_only_once(self):
        """이중 이스케이프된 태그 문자열은 HTML 타입에서 1회만 언이스케이프한다."""
        # 본문에 문자 그대로의 "&lt;div&gt;"가 있으면 html 타입에서 escape는 한 번만 풀린다.
        tag = _atom_content("&amp;lt;div&amp;gt; 태그 설명", "type='html'")
        assert feed_content_to_text(tag) == "&lt;div&gt; 태그 설명"

    def test_rss_description_cdata(self):
        """RSS description의 CDATA HTML을 문단 단위 텍스트로 변환한다."""
        xml = "<rss><channel><item><description><![CDATA[<p>첫 문단</p><p>둘째 문단</p>]]></description></item></channel></rss>"
        tag = BeautifulSoup(xml, "lxml-xml").find("description")
        assert feed_content_to_text(tag) == "첫 문단\n둘째 문단"

    def test_plain_text_unchanged(self):
        """일반 텍스트 타입 피드는 HTML 파싱 없이 원문 문자를 보존한다."""
        tag = _atom_content("그냥 일반 텍스트 List&lt;String&gt; 포함", "type='text'")
        assert feed_content_to_text(tag) == "그냥 일반 텍스트 List<String> 포함"

    def test_none_tag(self):
        """태그가 None이면 빈 문자열을 반환한다."""
        assert feed_content_to_text(None) == ""


class TestHtmlToText:
    def test_nested_list_indentation(self):
        """중첩 목록은 단계별 들여쓰기와 불릿으로 변환한다."""
        html = "<ul><li>상위<ul><li>하위<ul><li>최하위</li></ul></li></ul></li><li>다음</li></ul>"
        assert html_to_text(html) == "• 상위\n  • 하위\n    • 최하위\n• 다음"

    def test_ordered_list_uses_bullet(self):
        """순서 있는 목록도 불릿 기호 목록으로 변환한다."""
        assert html_to_text("<ol><li>하나</li><li>둘</li></ol>") == "• 하나\n• 둘"

    def test_br_and_paragraphs(self):
        """br과 p 태그는 줄바꿈으로 바꾸고 연속 빈 줄은 최대 하나로 정규화한다."""
        html = "<p>첫 줄<br>둘째 줄</p><p>문단 둘</p>a<br><br><br><br>b"
        assert html_to_text(html) == "첫 줄\n둘째 줄\n문단 둘\na\n\nb"

    def test_link_text_only(self):
        """앵커 태그는 href를 버리고 링크 텍스트만 본문에 유지한다."""
        html = '<p>자세한 내용은 <a href="https://example.com/x">여기</a>를 참고</p>'
        assert html_to_text(html) == "자세한 내용은 여기를 참고"

    def test_inline_tags_stay_on_same_line(self):
        """strong, em, code 등 인라인 태그는 줄바꿈 없이 같은 줄에 이어진다."""
        html = "<li><strong>굵게</strong>와 <em>기울임</em>, <code>code()</code> 연결</li>"
        assert html_to_text(html) == "• 굵게와 기울임, code() 연결"

    def test_script_and_style_removed(self):
        """script와 style 태그 내용은 추출 텍스트에서 완전히 제거한다."""
        html = "<style>p{color:red}</style><p>본문</p><script>alert(1)</script>"
        assert html_to_text(html) == "본문"

    def test_list_item_with_paragraph_keeps_bullet_line(self):
        """li 내부의 p 태그는 불릿과 같은 줄에 유지한다."""
        assert html_to_text("<ul><li><p>문단 항목</p></li></ul>") == "• 문단 항목"

    def test_empty_input(self):
        """빈 문자열과 공백만 있는 입력은 빈 문자열을 반환한다."""
        assert html_to_text("") == ""
        assert html_to_text("   ") == ""

    def test_no_tag_residue(self):
        """언이스케이프된 HTML 조각 변환 결과에 태그 잔여물이 남지 않는다."""
        html = BeautifulSoup(f"<x>{_ICEWM_ESCAPED}</x>", "html.parser").get_text()
        result = html_to_text(html)
        assert result == _ICEWM_EXPECTED
        assert _TAG_RESIDUE.search(result) is None

    def test_looks_like_html(self):
        """실제 HTML 태그와 제네릭·비교 연산자의 꺾쇠 기호를 구분해 판별한다."""
        assert looks_like_html("<div>본문</div>")
        assert looks_like_html("줄<br/>바꿈")
        assert not looks_like_html("List<String> 과 a < b")
        assert not looks_like_html("")


class TestGeekNewsParse:
    def test_parse_feed_strips_escaped_html(self):
        """GeekNews 피드 파싱 시 이스케이프된 HTML 본문을 정제된 텍스트로 추출한다."""
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>IceWM 소개</title>"
            '<link rel="alternate" href="https://news.hada.io/topic?id=1"/>'
            "<published>2026-11-13T00:00:00+09:00</published>"
            f"<content type='html' xml:lang='ko'>{_ICEWM_ESCAPED}</content>"
            "</entry></feed>"
        )
        articles = _parse_feed(xml)
        assert len(articles) == 1
        assert articles[0]["content"] == _ICEWM_EXPECTED


class TestNormalizeParagraphs:
    def test_single_newlines_become_double_newline_paragraphs(self):
        """단일 줄바꿈으로 구분된 추출 본문은 '\\n\\n' 문단 구분으로 정규화된다."""
        raw = "  First paragraph.  \r\nSecond paragraph.\n\n\n   \nThird paragraph.  "
        assert normalize_paragraphs(raw) == "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    def test_whitespace_only_returns_empty_string(self):
        """빈 문자열이나 공백·줄바꿈만 있는 입력은 빈 문자열을 반환한다."""
        assert normalize_paragraphs("") == ""
        assert normalize_paragraphs("  \n \r\n\t ") == ""

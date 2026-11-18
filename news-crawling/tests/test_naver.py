"""네이버뉴스 크롤러 섹션 주소·기사 링크·본문 추출 회귀 테스트."""

from unittest.mock import patch

import httpx

from crawlers import naver
from crawlers._http import create_safe_client


def _make_section_item(
    oid: str,
    aid: str,
    title: str,
    *,
    video_badge: bool = False,
) -> str:
    thumb_inner = '<span class="sa_thumb_icon">동영상뉴스</span>' if video_badge else '<img alt="" />'
    return (
        '<li class="sa_item _SECTION_HEADLINE">'
        '  <div class="sa_item_inner">'
        '    <div class="sa_thumb _LAZY_LOADING_ERROR_HIDE">'
        '      <div class="sa_thumb_inner">'
        f'        <a href="https://n.news.naver.com/mnews/article/{oid}/{aid}" class="sa_thumb_link _NLOG_IMPRESSION">'
        f"          {thumb_inner}"
        "        </a>"
        "      </div>"
        "    </div>"
        '    <div class="sa_text">'
        f'      <a href="https://n.news.naver.com/mnews/article/{oid}/{aid}" class="sa_text_title _NLOG_IMPRESSION">'
        f'        <strong class="sa_text_strong">{title}</strong>'
        "      </a>"
        '      <div class="sa_text_info">'
        '        <div class="sa_text_info_left">'
        f'          <a href="https://n.news.naver.com/mnews/article/comment/{oid}/{aid}" '
        '             class="sa_text_cmt _COMMENT_COUNT_LIST"></a>'
        "        </div>"
        "      </div>"
        f'      <a href="/cluster/c_20261118_0001/section/105?oid={oid}&aid={aid}" '
        '         class="sa_text_cluster">10개의 관련뉴스 더보기</a>'
        "    </div>"
        "  </div>"
        "</li>"
    )


def _make_section_html(section_title: str, items: list[tuple[str, str, str, bool]]) -> str:
    li_html = "\n".join(_make_section_item(oid, aid, title, video_badge=video) for oid, aid, title, video in items)
    return (
        "<!doctype html>"
        f"<html><head><title>{section_title} : 네이버 뉴스</title></head>"
        f'<body><div class="section_article"><ul>{li_html}</ul></div></body></html>'
    )


def _make_article_html(title: str, body_paragraphs: list[str], *, container: str = "dic_area") -> str:
    body_html = "<br/><br/>".join(body_paragraphs)
    if container == "dic_area":
        content_block = (
            '<div id="newsct_article" class="newsct_article _article_body">'
            f'<article id="dic_area" class="go_trans _article_content">{body_html}</article>'
            "</div>"
        )
    elif container == "newsct_article":
        content_block = f'<div id="newsct_article" class="newsct_article _article_body">{body_html}</div>'
    elif container == "articleBodyContents":
        content_block = f'<div id="articleBodyContents">{body_html}</div>'
    else:
        content_block = f'<div class="article_body">{body_html}</div>'

    return (
        "<!doctype html>"
        f"<html><head><title>{title}</title></head>"
        "<body>"
        f'<h2 id="title_area" class="media_end_head_headline"><span>{title}</span></h2>'
        f"{content_block}"
        "</body></html>"
    )


SECTION_105_HTML = _make_section_html(
    "IT/과학",
    [
        ("422", "0000927599", "인공지능 보안 점검 확대 발표", True),
        ("028", "0002832847", "공공 전산망 자바 취약점 긴급 대응", False),
        ("025", "0003566198", "국가 슈퍼컴퓨터 6호기 구축 완료", False),
        ("138", "0002249122", "국내 클라우드 기업 해외 인증 획득", False),
        ("277", "0005844643", "차세대 반도체 패키징 기술 공개", False),
        ("030", "0003487228", "여섯 번째 IT 기사 제목은 상한 초과", False),
    ],
)

SECTION_101_HTML = _make_section_html(
    "경제",
    [
        ("138", "0002249121", "바이오 생산 공장 증설 계획 확정", False),
        ("018", "0006412041", "국내 증시 외국인 순매수 전환", False),
        ("022", "0004176330", "한국은행 기준금리 동결 결정 배경", False),
        ("056", "0012296501", "수출 기업 환율 변동성 대응 강화", False),
        ("001", "0016449872", "코스피 주요 종목 정기 변경 발표", False),
        ("009", "0005111111", "여섯 번째 경제 기사 제목은 상한 초과", False),
    ],
)

SECTION_104_HTML = _make_section_html(
    "세계",
    [
        ("022", "0004176131", "유럽연합 인공지능 규제법 시행 준비", False),
        ("421", "0009295825", "글로벌 반도체 공급망 재편 가속화", False),
        ("001", "0016450170", "APEC 정상회의 다자 무역 논의 개막", False),
        ("001", "0016447784", "미 연준 통화정책 회의 의사록 공개", False),
        ("028", "0002832796", "국제 에너지 시장 원유 수요 전망", False),
        ("003", "0013000001", "여섯 번째 세계 기사 제목은 상한 초과", False),
    ],
)


def test_fetch_uses_updated_section_urls_and_skips_thumb_and_comment_links():
    """변경된 /section/105·101·104 주소로 섹션당 최대 5건의 실제 기사 제목과 본문을 수집한다."""
    requested_urls: list[str] = []
    long_body = [
        "국내외 산업 전반에서 인공지능 전환과 보안 강화 움직임이 빠르게 확산하고 있다. " * 4,
        "관계 기관은 표준 지침을 정비하고 현장 적용 점검을 단계적으로 추진할 계획이다. " * 4,
    ]

    def respond(req: httpx.Request) -> httpx.Response:
        requested_urls.append(str(req.url))
        if req.url.host == "news.naver.com" and req.url.path == "/main/main.naver":
            sid1 = req.url.params.get("sid1", "")
            return httpx.Response(302, headers={"Location": f"/section/{sid1}"})
        if req.url.host == "news.naver.com" and req.url.path == "/section/001":
            return httpx.Response(500, text="Internal Server Error", headers={"Content-Type": "text/html"})
        if req.url.host == "news.naver.com" and req.url.path == "/section/105":
            return httpx.Response(200, text=SECTION_105_HTML, headers={"Content-Type": "text/html"})
        if req.url.host == "news.naver.com" and req.url.path == "/section/101":
            return httpx.Response(200, text=SECTION_101_HTML, headers={"Content-Type": "text/html"})
        if req.url.host == "news.naver.com" and req.url.path == "/section/104":
            return httpx.Response(200, text=SECTION_104_HTML, headers={"Content-Type": "text/html"})
        if req.url.host == "n.news.naver.com" and req.url.path.startswith("/mnews/article/comment/"):
            return httpx.Response(200, text="<html><body>comment</body></html>", headers={"Content-Type": "text/html"})
        if req.url.host == "n.news.naver.com" and req.url.path.startswith("/mnews/article/"):
            return httpx.Response(
                200,
                text=_make_article_html("상세 기사 제목", long_body),
                headers={"Content-Type": "text/html"},
            )
        return httpx.Response(404, text="Not Found", headers={"Content-Type": "text/html"})

    with patch(
        "crawlers.naver.create_safe_client",
        side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(respond), **kw),
    ):
        articles = naver.fetch()

    assert "https://news.naver.com/section/105" in requested_urls
    assert "https://news.naver.com/section/101" in requested_urls
    assert "https://news.naver.com/section/104" in requested_urls
    assert not any("main.naver" in u or "/section/001" in u for u in requested_urls)
    assert not any("/article/comment/" in u for u in requested_urls)

    article_requests = [u for u in requested_urls if "n.news.naver.com/mnews/article/" in u]
    assert len(article_requests) == 15

    assert len(articles) == 15
    titles = [a["title"] for a in articles]
    assert "동영상뉴스" not in titles
    assert "인공지능 보안 점검 확대 발표" in titles
    assert "바이오 생산 공장 증설 계획 확정" in titles
    assert "유럽연합 인공지능 규제법 시행 준비" in titles
    assert "여섯 번째 IT 기사 제목은 상한 초과" not in titles
    assert all(a["source"] == "네이버뉴스" for a in articles)
    assert all("인공지능 전환과 보안 강화" in a["content"] for a in articles)


def test_fetch_continues_remaining_sections_when_one_section_fails():
    """한 섹션이 500 오류로 실패해도 나머지 유효 섹션 기사는 정상 수집한다."""
    section_html = _make_section_html(
        "경제",
        [("138", "0002249121", "한 섹션 장애에도 나머지 섹션 정상 수집", False)],
    )
    world_html = _make_section_html(
        "세계",
        [("022", "0004176131", "세계 섹션 정상 수집 확인 기사", False)],
    )

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/section/105":
            return httpx.Response(500, text="Server Error", headers={"Content-Type": "text/html"})
        if req.url.path == "/section/101":
            return httpx.Response(200, text=section_html, headers={"Content-Type": "text/html"})
        if req.url.path == "/section/104":
            return httpx.Response(200, text=world_html, headers={"Content-Type": "text/html"})
        return httpx.Response(
            200,
            text=_make_article_html("테스트 제목", ["충분한 길이의 정상 본문 문단입니다. " * 5]),
            headers={"Content-Type": "text/html"},
        )

    with patch(
        "crawlers.naver.create_safe_client",
        side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(respond), **kw),
    ):
        articles = naver.fetch()

    assert [a["title"] for a in articles] == [
        "한 섹션 장애에도 나머지 섹션 정상 수집",
        "세계 섹션 정상 수집 확인 기사",
    ]


def test_fetch_article_content_extracts_body_and_handles_fallbacks():
    """기사 본문 추출은 #dic_area 및 대체 컨테이너를 파싱하고 실패 시 빈 문자열을 반환한다."""

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/mnews/article/001/1":
            return httpx.Response(
                200,
                text=_make_article_html(
                    "기사1", ["첫째 문단 본문입니다.", "둘째 문단 본문입니다."], container="dic_area"
                ),
                headers={"Content-Type": "text/html"},
            )
        if req.url.path == "/mnews/article/001/2":
            return httpx.Response(
                200,
                text=_make_article_html("기사2", ["newsct_article 대체 본문입니다."], container="newsct_article"),
                headers={"Content-Type": "text/html"},
            )
        if req.url.path == "/mnews/article/001/3":
            return httpx.Response(
                200,
                text=_make_article_html(
                    "기사3", ["articleBodyContents 구형 본문입니다."], container="articleBodyContents"
                ),
                headers={"Content-Type": "text/html"},
            )
        if req.url.path == "/mnews/article/001/4":
            return httpx.Response(
                200, text="<html><body><div>본문 없음</div></body></html>", headers={"Content-Type": "text/html"}
            )
        return httpx.Response(500, text="error", headers={"Content-Type": "text/html"})

    with create_safe_client(transport=httpx.MockTransport(respond)) as client:
        assert "첫째 문단 본문입니다.\n둘째 문단 본문입니다." == naver._fetch_article_content(
            client, "https://n.news.naver.com/mnews/article/001/1"
        )
        assert "newsct_article 대체 본문입니다." == naver._fetch_article_content(
            client, "https://n.news.naver.com/mnews/article/001/2"
        )
        assert "articleBodyContents 구형 본문입니다." == naver._fetch_article_content(
            client, "https://n.news.naver.com/mnews/article/001/3"
        )
        assert naver._fetch_article_content(client, "https://n.news.naver.com/mnews/article/001/4") == ""
        assert naver._fetch_article_content(client, "https://n.news.naver.com/mnews/article/001/500") == ""


def test_fetch_respects_max_five_requests_per_section_and_deduplicates_across_sections():
    """한 섹션에 6건 이상이 있고 섹션 간 중복 URL이 있어도 섹션당 요청 5건 상한과 중복 제거를 유지한다."""
    requested_articles: list[str] = []
    dup_item = ("999", "0000000001", "섹션 간 중복 노출되는 주요 기사 제목", False)
    items_7 = [dup_item] + [
        ("100", f"000000000{i}", f"유효 기사 제목 번호 {i} 테스트입니다", False) for i in range(2, 8)
    ]
    html_7 = _make_section_html("IT/과학", items_7)

    def respond(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/section/"):
            return httpx.Response(200, text=html_7, headers={"Content-Type": "text/html"})
        requested_articles.append(str(req.url))
        return httpx.Response(
            200,
            text=_make_article_html("기사", ["정상 기사 본문 내용입니다. " * 6]),
            headers={"Content-Type": "text/html"},
        )

    with patch(
        "crawlers.naver.create_safe_client",
        side_effect=lambda **kw: create_safe_client(transport=httpx.MockTransport(respond), **kw),
    ):
        articles = naver.fetch()

    # 섹션 1: 5건 요청 (999/1 + 100/2..5)
    # 섹션 2, 3: 999/1, 100/2..5는 이미 seen_urls에 있어 요청 없이 스킵되고 100/6, 100/7만 추가 요청됨 -> 총 7건
    assert len(articles) == 7
    assert len(requested_articles) == 7
    assert len({a["url"] for a in articles}) == 7

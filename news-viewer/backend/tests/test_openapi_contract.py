"""커밋된 OpenAPI 명세(openapi.json)가 현재 코드와 어긋나지 않음을 보장하는 의도 기반 테스트."""

import json
from pathlib import Path

from app import create_app

OPENAPI_PATH = Path(__file__).resolve().parent.parent / "openapi.json"


def test_커밋된_openapi_명세가_현재_코드에서_생성한_명세와_같다():
    """API를 바꾸고 명세를 갱신하지 않으면 실패한다. 갱신: python scripts/export_openapi.py"""
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    generated = create_app().openapi()

    assert committed == generated, "openapi.json이 현재 코드와 다릅니다. python scripts/export_openapi.py로 갱신하세요."


def test_openapi_명세는_모든_데이터_엔드포인트를_GET으로만_노출한다():
    """읽기 전용 API 계약: 명세에 GET 외 메서드가 나타나면 안 된다."""
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))

    assert set(spec["paths"]) >= {"/articles", "/articles/{article_id}", "/briefing", "/categories", "/sources"}
    for path, operations in spec["paths"].items():
        assert set(operations) == {"get"}, f"{path}에 GET 이외의 메서드가 있습니다: {sorted(operations)}"


def test_기사_상세_명세는_404_오류_응답_형식을_문서화한다():
    """프론트엔드가 상세 직접 진입 404를 처리하므로 404 응답 형식이 명세에 있어야 한다."""
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))

    not_found = spec["paths"]["/articles/{article_id}"]["get"]["responses"]["404"]
    schema_ref = not_found["content"]["application/json"]["schema"]["$ref"]
    assert schema_ref == "#/components/schemas/ErrorResponse"
    assert "detail" in spec["components"]["schemas"]["ErrorResponse"]["properties"]

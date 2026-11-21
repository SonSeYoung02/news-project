"""FastAPI 앱의 OpenAPI 명세를 backend/openapi.json으로 내보낸다.

사용법 (news-viewer/backend에서 실행):
    python scripts/export_openapi.py          # openapi.json 갱신
    python scripts/export_openapi.py --check  # 커밋된 파일이 현재 코드와 같은지만 검사 (다르면 종료 코드 1)
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
OPENAPI_PATH = BACKEND_DIR / "openapi.json"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import create_app  # noqa: E402


def build_openapi() -> dict:
    """현재 코드 기준 OpenAPI 명세를 생성한다."""
    return create_app().openapi()


def render_openapi(spec: dict) -> str:
    """사람과 도구가 모두 읽기 쉽고 diff가 안정적인 형태로 직렬화한다."""
    return json.dumps(spec, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="파일을 쓰지 않고 현재 코드와 일치하는지만 검사")
    args = parser.parse_args()

    spec = build_openapi()

    if args.check:
        # 체크아웃 환경의 줄바꿈(CRLF/LF) 차이에 흔들리지 않도록 텍스트가 아닌 JSON 내용으로 비교한다.
        current = json.loads(OPENAPI_PATH.read_text(encoding="utf-8")) if OPENAPI_PATH.exists() else None
        if current != spec:
            print(f"{OPENAPI_PATH.name}가 현재 코드와 다릅니다. python scripts/export_openapi.py로 갱신하세요.")
            return 1
        print(f"{OPENAPI_PATH.name}가 현재 코드와 일치합니다.")
        return 0

    OPENAPI_PATH.write_text(render_openapi(spec), encoding="utf-8", newline="\n")
    print(f"{OPENAPI_PATH}를 갱신했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

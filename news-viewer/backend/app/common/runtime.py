import sys
from typing import TypeVar

T = TypeVar("T")


def resolve_main_attr(name: str, default: T) -> T:
    """루트 main 모듈의 속성이 테스트 등에서 패치된 경우 해당 값을 우선 반환한다."""
    main_mod = sys.modules.get("main")
    if main_mod is not None and hasattr(main_mod, name):
        return getattr(main_mod, name)
    return default

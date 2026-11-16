from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.article import router as article_router
from app.briefing import router as briefing_router
from app.meta import router as meta_router
from app.status import router as status_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="News Viewer API",
        description="뉴스 크롤링 데이터를 조회하는 REST API. 기사 목록·상세·카테고리·출처·오늘의 AI 브리핑 엔드포인트를 제공합니다.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(status_router.router)
    app.include_router(article_router.router)
    app.include_router(briefing_router.router)
    app.include_router(meta_router.router)

    return app

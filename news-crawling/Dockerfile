# 뉴스 수집·번역 파이프라인. 공식 multi-arch 이미지라 라즈베리파이(ARM64)에서도 그대로 빌드된다.
# lxml은 linux/arm64(manylinux aarch64) wheel이 배포되어 별도 빌드 도구 없이 설치된다.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul \
    DB_PATH=/data/news.db

# APScheduler·datetime이 Asia/Seoul을 해석하도록 tzdata를 설치한다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# main.py는 작업 디렉터리에 pipeline.log를 남긴다. 같은 내용이 stdout으로도 나가므로
# 컨테이너 안에서 파일이 끝없이 커지지 않게 /dev/null로 연결하고, 로그는 docker logs로 본다.
LABEL news.crawler.shared-lock="1"
RUN chmod 755 /usr/local/bin/entrypoint.sh \
    && ln -sf /dev/null /app/pipeline.log \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home app \
    && mkdir -p /data /run/crawler-lock && chown app:app /data /run/crawler-lock
USER app

# 공유 볼륨의 news.db에 스키마가 준비되었는지 확인한다(백엔드가 이 상태를 기다린다).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sqlite3,sys; c=sqlite3.connect('file:'+os.environ['DB_PATH']+'?mode=ro', uri=True); sys.exit(0 if c.execute(\"SELECT 1 FROM sqlite_master WHERE type='table' AND name='articles'\").fetchone() else 1)" || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "main.py", "--schedule"]

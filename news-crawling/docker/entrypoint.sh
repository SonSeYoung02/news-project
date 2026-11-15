#!/bin/sh
# 컨테이너 시작 시 news.db 스키마를 먼저 만든다.
# --schedule 모드는 첫 수집 시각 전까지 init_db()를 호출하지 않아, 빈 볼륨에서는
# 백엔드가 테이블 없음 오류를 낸다. CREATE TABLE IF NOT EXISTS라 반복 실행해도 안전하다.
set -e
python -c "from db import init_db; init_db()"
exec "$@"

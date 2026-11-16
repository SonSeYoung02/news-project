#!/usr/bin/env bash
# 예약된 크롤러 업데이트를 유휴 시 자동 반영하는 스크립트(systemd timer 및 수동 실행용).
#
#   bash scripts/crawler-apply.sh [apply]  대기 중인 크롤러 예약이 있고 유휴이면 적용
#   bash scripts/crawler-apply.sh status   크롤러 잠금·예약·실패 상태 출력
#
# 환경 변수:
#   WAIT_TIMEOUT              헬스체크 대기 최대 초(기본 300)
#   FORCE_APPLY=1             수집 시작 임박·백오프·레거시 시간대 보호를 무시(공유 잠금은 항상 준수)
#   DEPLOY_NOW_KST=HH:MM      현재 한국 시각 주입(테스트용)
#   CRAWLER_RETRY_BACKOFF_SECONDS 실패 후 재시도 기본 백오프 초(기본 300, 0이면 비활성)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { echo "[crawler-apply] $*"; }
warn() {
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "::warning::$*"
  else
    echo "[crawler-apply] 경고: $*" >&2
  fi
}
err() {
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "::error::$*"
  else
    echo "[crawler-apply] 오류: $*" >&2
  fi
}
die() {
  err "$*"
  exit 1
}

# shellcheck source=lib/crawler.sh
source "$ROOT/scripts/lib/crawler.sh"

cmd_apply() {
  apply_reserved_crawler
}

cmd_status() {
  if in_crawler_window; then
    echo "crawler 시간대: 보류 시간대 ($CRAWLER_WINDOW_DESC)"
  else
    echo "crawler 시간대: 허용 ($CRAWLER_WINDOW_DESC)"
  fi
  print_crawler_status
}

main() {
  if [ -n "${DEPLOY_NOW_KST:-}" ] && ! [[ "$DEPLOY_NOW_KST" =~ ^[0-9]{1,2}:[0-9]{2}$ ]]; then
    die "DEPLOY_NOW_KST는 HH:MM 형식이어야 합니다."
  fi
  case "${1:-apply}" in
    apply) cmd_apply ;;
    status) cmd_status ;;
    *)
      echo "사용법: $0 [apply|status]" >&2
      exit 2
      ;;
  esac
}

main "$@"

#!/usr/bin/env bash
# 블루-그린 무중단 배포 스크립트.
#
#   bash scripts/deploy.sh [deploy]      비활성 색으로 배포 후 전환(기본 동작)
#   bash scripts/deploy.sh status        활성 색, 크롤러 예약·잠금·실패 상태, 서비스 상태 출력
#   bash scripts/deploy.sh crawler-window  수집 시간대 판정 결과 출력
#
# 구성: core 스택(docker-compose.yml, 프로젝트 news-project: proxy·crawler·볼륨·news-edge 네트워크)과
#       색상별 앱 스택(docker-compose.app.yml, 프로젝트 news-blue / news-green: web·backend).
# 활성 색의 유일한 원천은 proxy가 읽는 .deploy/proxy/active.conf다(없으면 blue로 간주).
#
# 환경 변수
#   WEB_BIND_ADDRESS          proxy 호스트 바인딩 주소(기본 127.0.0.1, 루트 .env도 읽음)
#   WEB_PORT                  proxy 호스트 포트(기본 80, 루트 .env도 읽음)
#   WAIT_TIMEOUT              헬스체크 대기 최대 초(기본 300)
#   DRAIN_SECONDS             전환 후 이전 색을 내리기 전 대기 초(기본 15)
#   PROXY_RELOAD_WAIT         proxy reload 후 대기 초(기본 2)
#   FORCE_CRAWLER=1           수집 시간대여도 crawler 교체를 강제(공유 잠금은 항상 준수)
#   CRAWLER_WINDOW_MARGIN_MIN 수집 시작 몇 분 전부터 보류할지(기본 10)
#   DEPLOY_SHA                빌드·예약에 사용할 커밋 SHA(기본 git rev-parse HEAD)
#   DEPLOY_NOW_KST=HH:MM      현재 한국 시각 주입(테스트용)
#   DEPLOY_LOG_DIR            실패 시 컨테이너 로그 저장 폴더(기본 ~/deploy-logs)
#
# 보안: 공개 Actions 로그에서 실행되므로 컨테이너 로그, .env 내용, docker compose config 출력은
#       표준 출력에 남기지 않는다. 실패 로그는 DEPLOY_LOG_DIR(700/600)에만 저장한다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_PROJECT="news-project"
APP_PROJECT_PREFIX="news"
CORE_FILE="$ROOT/docker-compose.yml"
APP_FILE="$ROOT/docker-compose.app.yml"
STATE_DIR="$ROOT/.deploy"
PROXY_STATE_DIR="$STATE_DIR/proxy"
ACTIVE_CONF="$PROXY_STATE_DIR/active.conf"
# 블루-그린 이전 구조에서 쓰던 이미지 태그. 전환 후 정리한다.
LEGACY_IMAGES=(news-nginx:latest news-backend:latest news-frontend:latest)

WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"
DRAIN_SECONDS="${DRAIN_SECONDS:-15}"
PROXY_RELOAD_WAIT="${PROXY_RELOAD_WAIT:-2}"
FORCE_CRAWLER="${FORCE_CRAWLER:-0}"
CRAWLER_WINDOW_MARGIN_MIN="${CRAWLER_WINDOW_MARGIN_MIN:-10}"
LOG_DIR="${DEPLOY_LOG_DIR:-${HOME:-/tmp}/deploy-logs}"

# ---------------------------------------------------------------- 출력

log() { echo "[deploy] $*"; }

warn() {
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "::warning::$*"
  else
    echo "[deploy] 경고: $*" >&2
  fi
}

err() {
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "::error::$*"
  else
    echo "[deploy] 오류: $*" >&2
  fi
}

die() {
  err "$*"
  exit 1
}

# shellcheck source=lib/crawler.sh
source "$ROOT/scripts/lib/crawler.sh"

other_color() {
  if [ "$1" = "blue" ]; then echo green; else echo blue; fi
}

# ---------------------------------------------------------------- 활성 색 상태(active.conf)

# active.conf의 web 업스트림에서 활성 색을 읽는다. 파일이 없거나 해석할 수 없으면 빈 문자열.
read_active() {
  [ -f "$ACTIVE_CONF" ] || return 0
  # shellcheck disable=SC2016 # $web_upstream은 nginx 변수 이름(셸 확장 아님)
  sed -n 's/^[[:space:]]*set[[:space:]]*\$web_upstream[[:space:]]*web-\(blue\|green\):80;.*$/\1/p' \
    "$ACTIVE_CONF" | head -n 1
}

write_active() {
  local color="$1" tmp
  mkdir -p "$PROXY_STATE_DIR"
  tmp="$ACTIVE_CONF.tmp.$$"
  {
    echo "# scripts/deploy.sh가 관리하는 활성 색 설정입니다. 직접 수정하지 마세요."
    echo "set \$web_upstream web-$color:80;"
    echo "set \$backend_upstream backend-$color:8000;"
  } >"$tmp"
  chmod 644 "$tmp"
  # 같은 폴더 안 rename이라 proxy는 항상 완전한 파일만 본다.
  mv -f "$tmp" "$ACTIVE_CONF"
}

# 전환 전 상태로 되돌린다. 이전에 파일이 없었으면 삭제한다(proxy 기본값 blue).
restore_active() {
  local prev_color="$1"
  if [ -n "$prev_color" ]; then
    write_active "$prev_color"
  else
    rm -f "$ACTIVE_CONF"
  fi
}

# ---------------------------------------------------------------- 잠금

acquire_deploy_lock() {
  mkdir -p "$STATE_DIR"
  acquire_fd_lock 9 "$DEPLOY_LOCK_PATH" 1 644 \
    || die "다른 배포가 진행 중입니다(잠금: $DEPLOY_LOCK_PATH)."
  if ! command -v flock >/dev/null 2>&1; then
    trap 'release_fd_lock 9' EXIT
  fi
}

# ---------------------------------------------------------------- 검증

# http_ok <container> <url>: 컨테이너 안에서 GET이 2xx인지 확인한다(최대 5회 재시도).
http_ok() {
  local cid="$1" url="$2" _
  for _ in 1 2 3 4 5; do
    if docker_cmd exec "$cid" wget -q -T 5 -O - "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

# 공유 네트워크 안에서 대상 색의 web·backend를 alias 이름으로 직접 확인한다.
verify_direct() {
  local color="$1" cid url
  cid="$(compose_app "$color" ps -q web | head -n 1)"
  if [ -z "$cid" ]; then
    err "web-$color 컨테이너를 찾을 수 없습니다."
    return 1
  fi
  for url in "http://web-$color/" "http://backend-$color:8000/" "http://backend-$color:8000/articles?page=1&size=1"; do
    if ! http_ok "$cid" "$url"; then
      err "직접 검증 실패: $url"
      return 1
    fi
    log "직접 검증 통과: $url"
  done
}

# proxy 경유로 화면과 API를 확인한다.
verify_proxy() {
  local cid url
  cid="$(compose_core ps -q proxy | head -n 1)"
  if [ -z "$cid" ]; then
    err "proxy 컨테이너를 찾을 수 없습니다."
    return 1
  fi
  for url in "http://127.0.0.1/" "http://127.0.0.1/api/articles?page=1&size=1"; do
    if ! http_ok "$cid" "$url"; then
      err "proxy 경유 검증 실패: $url"
      return 1
    fi
    log "proxy 경유 검증 통과: $url"
  done
}

# 설정 문법을 확인한 뒤 graceful reload한다. 문법 오류면 reload하지 않아 기존 설정이 유지된다.
proxy_reload() {
  if ! compose_core exec -T proxy nginx -t -q; then
    err "proxy 설정 검사(nginx -t)에 실패했습니다."
    return 1
  fi
  compose_core exec -T proxy nginx -s reload || return 1
  # reload 신호는 비동기라 새 worker가 뜰 시간을 잠시 준다.
  [ "$PROXY_RELOAD_WAIT" -gt 0 ] 2>/dev/null && sleep "$PROXY_RELOAD_WAIT" || true
}

# ---------------------------------------------------------------- 배포

legacy_containers() {
  {
    docker_cmd ps -aq --filter "label=com.docker.compose.project=$CORE_PROJECT" \
      --filter "label=com.docker.compose.service=nginx"
    docker_cmd ps -aq --filter "label=com.docker.compose.project=$CORE_PROJECT" \
      --filter "label=com.docker.compose.service=backend"
  } | sort -u
}

ACTIVE=""
TARGET=""
MIGRATION=0
SWITCHED=0

# 3~6단계 실패 시: 업스트림을 이전 색으로 되돌리고 새 색 스택을 내린 뒤 실패로 끝낸다.
rollback() {
  err "$1"
  save_logs
  if [ "$MIGRATION" = "1" ]; then
    if [ "$SWITCHED" = "1" ]; then
      # 이전 구조(nginx·backend)는 이미 정리되어 되돌릴 대상이 없다. 새 색을 유지한다.
      err "1회 전환 중 이전 구조가 이미 정리되어 자동 롤백할 수 없습니다. 새 색($TARGET) 스택을 유지합니다. README의 수동 복구 절차를 확인하세요."
      exit 1
    fi
    # 이전 구조가 계속 서비스 중이다. 만들어 둔(시작 전) proxy 컨테이너와 활성 색 파일을 정리한다.
    compose_core rm -f proxy >/dev/null 2>&1 || true
    restore_active ""
  elif [ "$SWITCHED" = "1" ]; then
    log "업스트림을 이전 색(${ACTIVE:-기본값 blue})으로 되돌립니다."
    restore_active "$ACTIVE"
    proxy_reload || err "롤백 reload에 실패했습니다. proxy 상태를 확인하세요."
  fi
  log "새 색($TARGET) 스택을 내립니다."
  compose_app "$TARGET" down --remove-orphans || true
  print_ps
  exit 1
}

warn_if_timer_inactive() {
  if command -v systemctl >/dev/null 2>&1; then
    if ! run_unlocked_fds systemctl is-active --quiet news-crawler-apply.timer 2>/dev/null; then
      warn "news-crawler-apply.timer가 비활성 상태입니다. 보류된 예약을 자동 반영하려면 README의 systemd 타이머 설치 안내를 확인하세요."
    fi
  fi
}

handle_crawler_update_after_app_deploy() {
  local sha="$1" target_image="$2" target_fp target_cfg state
  target_fp="$(image_fingerprint "$target_image")"
  target_cfg="$(canonical_crawler_config_hash)"
  state="$(crawler_state_for_image "$target_image")"

  case "$state" in
    same)
      log "crawler 변경 없음: 재생성하지 않습니다."
      clear_obsolete_reservation_if_same "$target_image"
      cleanup_crawler_images "$target_image"
      ;;
    missing | stopped | changed)
      save_crawler_reservation "$sha" "$target_image" "$target_fp" "$target_cfg" "$FORCE_CRAWLER"
      log "crawler 교체 예약을 저장했습니다: sha=${sha:0:12} ($target_image)"
      if in_crawler_window && [ "$FORCE_CRAWLER" != "1" ]; then
        warn "수집 시간대라 crawler 교체를 보류하고 예약을 저장했습니다($CRAWLER_WINDOW_DESC). 유휴 시 타이머가 자동 적용하며, 즉시 적용하려면 FORCE_CRAWLER=1로 실행하세요."
        warn_if_timer_inactive
        cleanup_crawler_images "$target_image"
        return 0
      fi
      [ "$FORCE_CRAWLER" = "1" ] && log "FORCE_CRAWLER=1: 수집 시간대 판정과 무관하게 crawler 교체를 시도합니다."
      if ! apply_reserved_crawler; then
        die "crawler 기동 또는 헬스체크에 실패했습니다. 앱은 $TARGET(으)로 서비스 중이며 이전 crawler 복구와 예약/실패 상태 기록을 완료했습니다."
      fi
      ;;
  esac
}

cmd_deploy() {
  local legacy old deploy_sha crawler_sha_image
  acquire_deploy_lock
  mkdir -p "$PROXY_STATE_DIR"
  ensure_lock_file_inode "$CRAWL_LOCK_PATH" 666

  ACTIVE="$(read_active)"
  legacy="$(legacy_containers)"
  if [ -n "$legacy" ]; then
    MIGRATION=1
    ACTIVE=""
    log "블루-그린 이전 구조(news-project의 nginx·backend)를 감지했습니다. 1회 전환을 진행합니다."
  elif [ -z "$ACTIVE" ] && [ -n "$(compose_app blue ps -q)" ]; then
    # active.conf가 없으면 proxy는 기본값 blue로 서비스한다. 실행 중인 blue를 덮어쓰지 않도록 활성으로 본다.
    ACTIVE=blue
    warn "활성 색 파일($ACTIVE_CONF)이 없어 proxy 기본값인 blue를 활성 색으로 간주합니다."
  fi
  if [ "$ACTIVE" = "blue" ]; then TARGET=green; else TARGET=blue; fi
  log "활성 색: ${ACTIVE:-없음} → 배포 대상: $TARGET"

  deploy_sha="$(resolve_commit_sha)"
  crawler_sha_image="$(crawler_sha_image_tag "$deploy_sha")"

  seed_crawler_state

  # 1) 이미지 빌드(서비스 영향 없음; 크롤러는 커밋 SHA 태그로 준비해 실행 중 :latest를 덮어쓰지 않음)
  log "이미지를 빌드합니다(crawler=$crawler_sha_image, $TARGET 앱 스택)."
  CRAWLER_IMAGE="$crawler_sha_image" compose_core build crawler
  compose_app "$TARGET" build

  # 2) core 보장
  if [ "$MIGRATION" = "1" ]; then
    # 이전 nginx가 포트를 쓰고 있으므로 proxy는 만들기만 하고(네트워크·볼륨 준비) 시작은 전환 시점에 한다.
    compose_core create --no-recreate proxy
  else
    log "core 스택(proxy)을 보장합니다."
    compose_core up -d --no-deps --wait --wait-timeout "$WAIT_TIMEOUT" proxy
    # nginx/proxy/conf.d 변경은 재생성 없이 reload로 반영한다.
    proxy_reload || die "proxy 설정 반영에 실패했습니다. 앱 전환 전이라 서비스는 그대로입니다."
    ensure_crawler_running "$crawler_sha_image" "$deploy_sha"
  fi

  # 3) 대상 색 기동
  log "$TARGET 앱 스택을 기동합니다."
  # 비활성 색은 서비스 중이 아니므로, 남아 있던 컨테이너가 있어도 새 이미지로 강제 재생성한다.
  if ! compose_app "$TARGET" up -d --no-build --force-recreate --wait --wait-timeout "$WAIT_TIMEOUT"; then
    rollback "$TARGET 앱 스택 기동 또는 헬스체크에 실패했습니다."
  fi

  # 4) 직접 검증
  verify_direct "$TARGET" || rollback "$TARGET 앱 스택 직접 검증에 실패했습니다."

  # 5) 전환
  log "업스트림을 $TARGET(으)로 전환합니다."
  write_active "$TARGET"
  SWITCHED=1
  if [ "$MIGRATION" = "1" ]; then
    log "이전 nginx·backend를 정리하고 proxy를 시작합니다(이 순간 짧은 중단이 있습니다)."
    if ! compose_core up -d --no-deps --wait --wait-timeout "$WAIT_TIMEOUT" --remove-orphans proxy; then
      rollback "proxy 시작에 실패했습니다."
    fi
  else
    proxy_reload || rollback "proxy reload에 실패했습니다."
  fi

  # 6) proxy 경유 검증
  verify_proxy || rollback "proxy 경유 검증에 실패했습니다."
  log "배포 성공: 활성 색은 $TARGET입니다."

  # 7) 이전 색 정리
  old="$(other_color "$TARGET")"
  if [ -n "$(compose_app "$old" ps -a -q)" ]; then
    log "진행 중인 요청을 위해 ${DRAIN_SECONDS}초 기다린 뒤 이전 색($old) 스택을 내립니다."
    [ "$DRAIN_SECONDS" -gt 0 ] 2>/dev/null && sleep "$DRAIN_SECONDS" || true
    compose_app "$old" down --remove-orphans
  fi

  # 8) crawler 예약/교체(앱 전환과 독립적으로 마지막에 처리; 실패해도 앱은 새 색으로 서비스된다)
  handle_crawler_update_after_app_deploy "$deploy_sha" "$crawler_sha_image"

  # 9) 이전 구조 이미지 정리(미사용 SHA 태그와 dangling 정리도 위 단계의 cleanup_crawler_images에서 수행)
  local image
  for image in "${LEGACY_IMAGES[@]}"; do
    if docker_cmd image inspect "$image" >/dev/null 2>&1 \
        && docker_cmd image rm "$image" >/dev/null 2>&1; then
      log "이전 구조 이미지 정리: $image"
    fi
  done
}

cmd_status() {
  local active
  active="$(read_active)"
  echo "활성 색: ${active:-없음(proxy 기본값 blue)}"
  if in_crawler_window; then
    echo "crawler 교체: 보류 시간대 ($CRAWLER_WINDOW_DESC)"
  else
    echo "crawler 교체: 허용 ($CRAWLER_WINDOW_DESC)"
  fi
  print_crawler_status
  print_ps
}

cmd_crawler_window() {
  if in_crawler_window; then
    echo "in_window=yes ($CRAWLER_WINDOW_DESC)"
  else
    echo "in_window=no ($CRAWLER_WINDOW_DESC)"
  fi
}

main() {
  # 시간 주입 값은 함수 내부(서브셸)에서 검사하면 실패가 전달되지 않으므로 시작 시 검사한다.
  if [ -n "${DEPLOY_NOW_KST:-}" ] && ! [[ "$DEPLOY_NOW_KST" =~ ^[0-9]{1,2}:[0-9]{2}$ ]]; then
    die "DEPLOY_NOW_KST는 HH:MM 형식이어야 합니다."
  fi
  case "${1:-deploy}" in
    deploy) cmd_deploy ;;
    status) cmd_status ;;
    crawler-window) cmd_crawler_window ;;
    *)
      echo "사용법: $0 [deploy|status|crawler-window]" >&2
      exit 2
      ;;
  esac
}

main "$@"

#!/usr/bin/env bash
# 크롤러 예약 배포·공유 잠금·상태 관리·실패 복구 공통 라이브러리.
# scripts/deploy.sh와 scripts/crawler-apply.sh가 함께 source한다.

CORE_PROJECT="${CORE_PROJECT:-news-project}"
APP_PROJECT_PREFIX="${APP_PROJECT_PREFIX:-news}"
CORE_FILE="${CORE_FILE:-$ROOT/docker-compose.yml}"
APP_FILE="${APP_FILE:-$ROOT/docker-compose.app.yml}"
STATE_DIR="${STATE_DIR:-$ROOT/.deploy}"
PROXY_STATE_DIR="${PROXY_STATE_DIR:-$STATE_DIR/proxy}"
ACTIVE_CONF="${ACTIVE_CONF:-$PROXY_STATE_DIR/active.conf}"

DEPLOY_LOCK_PATH="${DEPLOY_LOCK_PATH:-$STATE_DIR/deploy.lock}"
CRAWLER_LOCK_DIR="${CRAWLER_LOCK_DIR:-$STATE_DIR/locks}"
CRAWL_LOCK_PATH="${CRAWL_LOCK_PATH:-$CRAWLER_LOCK_DIR/crawl.lock}"
CRAWLER_APPLY_LOCK_PATH="${CRAWLER_APPLY_LOCK_PATH:-$STATE_DIR/crawler-apply.lock}"
CRAWLER_RESERVATION_LOCK_PATH="${CRAWLER_RESERVATION_LOCK_PATH:-$STATE_DIR/crawler-reservation.lock}"

CRAWLER_STATE="${CRAWLER_STATE:-$STATE_DIR/crawler.image}"
CRAWLER_ACTIVE_FILE="${CRAWLER_ACTIVE_FILE:-$STATE_DIR/crawler-active.env}"
CRAWLER_RESERVATION_FILE="${CRAWLER_RESERVATION_FILE:-$STATE_DIR/crawler-reservation.env}"
CRAWLER_FAILURE_FILE="${CRAWLER_FAILURE_FILE:-$STATE_DIR/crawler-failure.env}"
CRAWLER_ENV="${CRAWLER_ENV:-$ROOT/news-crawling/.env}"
CRAWLER_DEFAULT_IMAGE="${CRAWLER_DEFAULT_IMAGE:-news-crawler:latest}"

WAIT_TIMEOUT="${WAIT_TIMEOUT:-300}"
FORCE_CRAWLER="${FORCE_CRAWLER:-0}"
FORCE_APPLY="${FORCE_APPLY:-0}"
CRAWLER_WINDOW_MARGIN_MIN="${CRAWLER_WINDOW_MARGIN_MIN:-10}"
CRAWLER_PRE_GUARD_AFTER_MIN="${CRAWLER_PRE_GUARD_AFTER_MIN:-2}"
CRAWLER_RETRY_BACKOFF_SECONDS="${CRAWLER_RETRY_BACKOFF_SECONDS:-300}"
LOG_DIR="${DEPLOY_LOG_DIR:-${HOME:-/tmp}/deploy-logs}"

HOLDING_APPLY_LOCK=0
_LOCK_FALLBACK_6=""
_LOCK_FALLBACK_7=""
_LOCK_FALLBACK_8=""
_LOCK_FALLBACK_9=""

# ---------------------------------------------------------------- 출력(미정의 시 기본 제공)

if ! declare -F log >/dev/null 2>&1; then
  log() { echo "[crawler] $*"; }
fi
if ! declare -F warn >/dev/null 2>&1; then
  warn() {
    if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
      echo "::warning::$*"
    else
      echo "[crawler] 경고: $*" >&2
    fi
  }
fi
if ! declare -F err >/dev/null 2>&1; then
  err() {
    if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
      echo "::error::$*"
    else
      echo "[crawler] 오류: $*" >&2
    fi
  }
fi
if ! declare -F die >/dev/null 2>&1; then
  die() {
    err "$*"
    exit 1
  }
fi

# ---------------------------------------------------------------- FD 상속 차단 및 잠금

# 잠금 FD(6, 7, 8, 9)를 자식 프로세스에 상속하지 않고 명령을 실행한다.
run_unlocked_fds() {
  "$@" 6>&- 7>&- 8>&- 9>&-
}

docker_cmd() {
  run_unlocked_fds docker "$@"
}

compose_core() {
  run_unlocked_fds docker compose -p "$CORE_PROJECT" -f "$CORE_FILE" "$@"
}

compose_app() {
  local color="$1"
  shift
  DEPLOY_COLOR="$color" run_unlocked_fds docker compose -p "$APP_PROJECT_PREFIX-$color" -f "$APP_FILE" "$@"
}

# 잠금 파일은 최초 1회만 생성하고 기존 파일의 inode를 절대 삭제·교체·절단하지 않는다.
ensure_lock_file_inode() {
  local path="$1" mode="${2:-644}"
  mkdir -p "$(dirname "$path")"
  if [ ! -e "$path" ]; then
    : >>"$path"
    chmod "$mode" "$path" 2>/dev/null || true
  fi
}

_set_fallback_dir() {
  local fd="$1" val="$2"
  case "$fd" in
    6) _LOCK_FALLBACK_6="$val" ;;
    7) _LOCK_FALLBACK_7="$val" ;;
    8) _LOCK_FALLBACK_8="$val" ;;
    9) _LOCK_FALLBACK_9="$val" ;;
  esac
}

_get_fallback_dir() {
  case "$1" in
    6) printf '%s' "$_LOCK_FALLBACK_6" ;;
    7) printf '%s' "$_LOCK_FALLBACK_7" ;;
    8) printf '%s' "$_LOCK_FALLBACK_8" ;;
    9) printf '%s' "$_LOCK_FALLBACK_9" ;;
  esac
}

# acquire_fd_lock <fd> <path> <nonblock:1|0> [file_mode]
acquire_fd_lock() {
  local fd="$1" path="$2" nonblock="${3:-1}" mode="${4:-644}"
  ensure_lock_file_inode "$path" "$mode"
  if command -v flock >/dev/null 2>&1; then
    # '>' 절단 대신 '>>' 또는 읽기 전용 '<'로 열어 inode·내용을 보존한다.
    if ! eval "exec ${fd}>>\"\$path\"" 2>/dev/null; then
      eval "exec ${fd}<\"\$path\"" || return 1
    fi
    if [ "$nonblock" = "1" ]; then
      if ! flock -n "$fd"; then
        eval "exec ${fd}>&-" 2>/dev/null || true
        return 1
      fi
    else
      if ! flock "$fd"; then
        eval "exec ${fd}>&-" 2>/dev/null || true
        return 1
      fi
    fi
    return 0
  fi

  # flock이 없는 환경(Windows Git Bash 등)용 대체 잠금.
  local lock_dir="${path}.d" tries=0
  if [ "$nonblock" = "1" ]; then
    mkdir "$lock_dir" 2>/dev/null || return 1
    _set_fallback_dir "$fd" "$lock_dir"
    return 0
  fi
  while ! mkdir "$lock_dir" 2>/dev/null; do
    tries=$((tries + 1))
    [ "$tries" -ge 50 ] && return 1
    sleep 0.1
  done
  _set_fallback_dir "$fd" "$lock_dir"
  return 0
}

release_fd_lock() {
  local fd="$1"
  if command -v flock >/dev/null 2>&1; then
    flock -u "$fd" 2>/dev/null || true
    eval "exec ${fd}>&-" 2>/dev/null || true
  else
    local lock_dir
    lock_dir="$(_get_fallback_dir "$fd")"
    if [ -n "$lock_dir" ]; then
      rmdir "$lock_dir" 2>/dev/null || true
      _set_fallback_dir "$fd" ""
    fi
  fi
}

# 공유 수집 잠금이 현재 점유 중이면 0(busy), 유휴이면 1(free)을 반환한다.
probe_crawl_lock_busy() {
  if command -v flock >/dev/null 2>&1; then
    [ -e "$CRAWL_LOCK_PATH" ] || return 1
    if ( exec 7<"$CRAWL_LOCK_PATH" 2>/dev/null && flock -n 7 ); then
      return 1
    fi
    return 0
  fi
  [ -d "${CRAWL_LOCK_PATH}.d" ]
}

# 예약·상태 파일 메타데이터 수정용 짧은 직렬화 잠금(리프 락).
with_reservation_lock() {
  local rc=0
  acquire_fd_lock 6 "$CRAWLER_RESERVATION_LOCK_PATH" 0 644 \
    || die "예약 메타데이터 잠금을 획득할 수 없습니다($CRAWLER_RESERVATION_LOCK_PATH)."
  if "$@"; then
    rc=0
  else
    rc=$?
  fi
  release_fd_lock 6
  return "$rc"
}

# ---------------------------------------------------------------- 상태 파일 원자적 읽기·쓰기

kv_get() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 0
  awk -F= -v k="$key" '$1 == k { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

sanitize_kv() {
  printf '%s' "$1" | tr '\r\n' '  '
}

write_kv_atomic() {
  local dest="$1" tmp line
  shift
  mkdir -p "$(dirname "$dest")"
  tmp="$dest.tmp.$$"
  : >"$tmp"
  for line in "$@"; do
    printf '%s\n' "$line" >>"$tmp"
  done
  chmod 644 "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$dest"
}

# ---------------------------------------------------------------- 수집 시간대

crawler_env_int() {
  local key="$1" default="$2" value=""
  if [ -f "$CRAWLER_ENV" ]; then
    value="$(sed -n "s/^[[:space:]]*${key}[[:space:]]*=[[:space:]]*[\"']\{0,1\}\([0-9]\{1,2\}\)[\"']\{0,1\}[[:space:]]*\$/\1/p" \
      "$CRAWLER_ENV" | tail -n 1)"
  fi
  echo "${value:-$default}"
}

now_kst_minutes() {
  local hh mm
  if [ -n "${DEPLOY_NOW_KST:-}" ]; then
    [[ "$DEPLOY_NOW_KST" =~ ^([0-9]{1,2}):([0-9]{2})$ ]]
    echo $(((10#${BASH_REMATCH[1]} * 60 + 10#${BASH_REMATCH[2]}) % 1440))
    return
  fi
  IFS=: read -r hh mm < <(date -u +%H:%M)
  echo $(((10#$hh * 60 + 10#$mm + 540) % 1440))
}

fmt_minutes() {
  printf '%02d:%02d' $(($1 / 60)) $(($1 % 60))
}

minutes_in_range() {
  local now="$1" start="$2" end="$3"
  if [ "$start" -le "$end" ]; then
    [ "$now" -ge "$start" ] && [ "$now" -lt "$end" ]
  else
    [ "$now" -ge "$start" ] || [ "$now" -lt "$end" ]
  fi
}

CRAWLER_WINDOW_DESC=""
in_crawler_window() {
  local start end now
  start=$((10#$(crawler_env_int SCHEDULE_HOUR 1) * 60 + 10#$(crawler_env_int SCHEDULE_MINUTE 0)))
  end=$((10#$(crawler_env_int DEADLINE_HOUR 6) * 60 + 10#$(crawler_env_int DEADLINE_MINUTE 0)))
  start=$(((start - CRAWLER_WINDOW_MARGIN_MIN + 1440) % 1440))
  now="$(now_kst_minutes)"
  CRAWLER_WINDOW_DESC="수집 시간대 $(fmt_minutes "$start")~$(fmt_minutes "$end") KST(시작 ${CRAWLER_WINDOW_MARGIN_MIN}분 전 포함), 현재 $(fmt_minutes "$now") KST"
  minutes_in_range "$now" "$start" "$end"
}

PRE_CRAWL_WINDOW_DESC=""
in_pre_crawl_window() {
  local sched start end now
  sched=$((10#$(crawler_env_int SCHEDULE_HOUR 1) * 60 + 10#$(crawler_env_int SCHEDULE_MINUTE 0)))
  start=$(((sched - CRAWLER_WINDOW_MARGIN_MIN + 1440) % 1440))
  end=$(((sched + CRAWLER_PRE_GUARD_AFTER_MIN) % 1440))
  now="$(now_kst_minutes)"
  PRE_CRAWL_WINDOW_DESC="수집 시작 임박 구간 $(fmt_minutes "$start")~$(fmt_minutes "$end") KST, 현재 $(fmt_minutes "$now") KST"
  minutes_in_range "$now" "$start" "$end"
}

# ---------------------------------------------------------------- 실패 로그

print_ps() {
  local color
  echo "--- core ($CORE_PROJECT)"
  compose_core ps -a || true
  for color in blue green; do
    echo "--- app ($APP_PROJECT_PREFIX-$color)"
    compose_app "$color" ps -a || true
  done
}

save_logs() {
  local log_file color rev
  rev="$(run_unlocked_fds git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  log_file="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-$rev.log"
  print_ps
  if (umask 077 && mkdir -p "$LOG_DIR" && chmod 700 "$LOG_DIR" \
      && touch "$log_file" && chmod 600 "$log_file"); then
    {
      print_ps
      echo
      echo "=== core logs"
      compose_core logs --no-color --timestamps --tail 500
      for color in blue green; do
        echo
        echo "=== app $color logs"
        compose_app "$color" logs --no-color --timestamps --tail 500
      done
    } >>"$log_file" 2>&1 || true
    log "컨테이너 로그는 공개 로그에 출력하지 않고 러너 호스트에 저장했습니다: $log_file"
  else
    warn "컨테이너 로그 파일 저장에 실패했습니다. 호스트에서 'docker compose logs'로 확인하세요."
  fi
  find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' 2>/dev/null \
    | sort -r | tail -n +21 | xargs -r rm -f -- || true
}

# ---------------------------------------------------------------- 이미지·컨테이너 조회

resolve_commit_sha() {
  local sha
  sha="${DEPLOY_SHA:-}"
  if [ -z "$sha" ]; then
    sha="$(run_unlocked_fds git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  fi
  if ! [[ "$sha" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    sha="unknown"
  fi
  printf '%s' "$sha"
}

crawler_sha_image_tag() {
  local sha="$1"
  if [ -z "$sha" ] || [ "$sha" = "unknown" ]; then
    printf '%s' "news-crawler:sha-unknown"
    return
  fi
  printf 'news-crawler:sha-%s' "${sha:0:12}"
}

image_fingerprint() {
  local meta
  meta="$(docker_cmd image inspect -f '{{json .RootFS.Layers}}{{json .Config}}' "$1" 2>/dev/null)" || return 0
  [ -n "$meta" ] || return 0
  printf '%s' "$meta" | sha256sum | cut -c1-64
}

canonical_crawler_config_hash() {
  CRAWLER_IMAGE="$CRAWLER_DEFAULT_IMAGE" compose_core config --hash crawler | awk '{print $2}'
}

crawler_container_id() {
  compose_core ps -a -q crawler | head -n 1
}

container_is_healthy_or_running() {
  local cid="$1" running health
  [ -n "$cid" ] || return 1
  running="$(docker_cmd inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)"
  [ "$running" = "true" ] || return 1
  health="$(docker_cmd inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)"
  if [ -n "$health" ] && [ "$health" != "healthy" ]; then
    return 1
  fi
  return 0
}

# 실행 중 컨테이너가 이미지 라벨(shared-lock)과 /run/crawler-lock 마운트를 모두 갖추었는지 확인한다.
container_supports_shared_lock() {
  local cid="$1" label img_id mounts
  [ -n "$cid" ] || return 1
  label="$(docker_cmd inspect -f '{{index .Config.Labels "news.crawler.shared-lock"}}' "$cid" 2>/dev/null || true)"
  if [ "$label" != "1" ]; then
    img_id="$(docker_cmd inspect -f '{{.Image}}' "$cid" 2>/dev/null || true)"
    [ -n "$img_id" ] && label="$(docker_cmd image inspect -f '{{index .Config.Labels "news.crawler.shared-lock"}}' "$img_id" 2>/dev/null || true)"
  fi
  [ "$label" = "1" ] || return 1
  mounts="$(docker_cmd inspect -f '{{range .Mounts}}{{.Destination}}{{"\n"}}{{end}}' "$cid" 2>/dev/null || true)"
  printf '%s\n' "$mounts" | grep -Fxq "/run/crawler-lock"
}

# crawler_state_for_image <target_image>: missing | stopped | changed | same
crawler_state_for_image() {
  local target_image="${1:-$CRAWLER_DEFAULT_IMAGE}"
  local cid running cur_fp="" cur_cfg="" new_fp new_cfg active_cid="" img_id

  cid="$(crawler_container_id)"
  [ -n "$cid" ] || { echo missing; return; }
  running="$(docker_cmd inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)"
  [ "$running" = "true" ] || { echo stopped; return; }

  if [ -f "$CRAWLER_ACTIVE_FILE" ]; then
    active_cid="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_CONTAINER_ID")"
    if [ "$active_cid" = "$cid" ]; then
      cur_fp="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_FINGERPRINT")"
      cur_cfg="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_CONFIG_HASH")"
    fi
  fi

  if [ -z "$cur_fp" ]; then
    if [ -f "$CRAWLER_STATE" ]; then
      cur_fp="$(cat "$CRAWLER_STATE" 2>/dev/null || true)"
    else
      img_id="$(docker_cmd inspect -f '{{.Image}}' "$cid" 2>/dev/null || true)"
      if [ -n "$img_id" ] && docker_cmd image inspect "$img_id" >/dev/null 2>&1; then
        cur_fp="$(image_fingerprint "$img_id")"
      fi
    fi
  fi

  if [ -z "$cur_cfg" ]; then
    cur_cfg="$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$cid" 2>/dev/null || true)"
  fi

  new_fp="$(image_fingerprint "$target_image")"
  new_cfg="$(canonical_crawler_config_hash)"
  if [ -z "$cur_fp" ] || [ -z "$new_fp" ] || [ "$cur_fp" != "$new_fp" ] || [ "$cur_cfg" != "$new_cfg" ]; then
    echo changed
  else
    echo same
  fi
}

_seed_crawler_state_locked() {
  local cid img_id img_ref fp cfg prev_img=""
  cid="$(crawler_container_id)"
  [ -n "$cid" ] || return 0

  local recorded_cid=""
  [ -f "$CRAWLER_ACTIVE_FILE" ] && recorded_cid="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_CONTAINER_ID")"
  if [ -f "$CRAWLER_ACTIVE_FILE" ] && [ "$recorded_cid" = "$cid" ] && [ -f "$CRAWLER_STATE" ]; then
    return 0
  fi

  img_ref="$(docker_cmd inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
  img_id="$(docker_cmd inspect -f '{{.Image}}' "$cid" 2>/dev/null || true)"
  if [ -f "$CRAWLER_STATE" ] && [ -z "$recorded_cid" ]; then
    fp="$(cat "$CRAWLER_STATE" 2>/dev/null || true)"
  elif [ -n "$img_id" ] && docker_cmd image inspect "$img_id" >/dev/null 2>&1; then
    fp="$(image_fingerprint "$img_id")"
  elif [ -n "$img_ref" ] && docker_cmd image inspect "$img_ref" >/dev/null 2>&1; then
    fp="$(image_fingerprint "$img_ref")"
  else
    fp=""
  fi
  cfg="$(docker_cmd inspect -f '{{index .Config.Labels "com.docker.compose.config-hash"}}' "$cid" 2>/dev/null || true)"
  [ -f "$CRAWLER_ACTIVE_FILE" ] && prev_img="$(kv_get "$CRAWLER_ACTIVE_FILE" "PREVIOUS_IMAGE")"

  if [ -n "$fp" ]; then
    mkdir -p "$STATE_DIR"
    printf '%s\n' "$fp" >"$CRAWLER_STATE"
  fi
  write_kv_atomic "$CRAWLER_ACTIVE_FILE" \
    "ACTIVE_CONTAINER_ID=$(sanitize_kv "$cid")" \
    "ACTIVE_IMAGE=$(sanitize_kv "${img_ref:-$CRAWLER_DEFAULT_IMAGE}")" \
    "ACTIVE_SHA=$(sanitize_kv "$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_SHA")")" \
    "ACTIVE_FINGERPRINT=$(sanitize_kv "$fp")" \
    "ACTIVE_CONFIG_HASH=$(sanitize_kv "$cfg")" \
    "PREVIOUS_IMAGE=$(sanitize_kv "$prev_img")" \
    "UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

seed_crawler_state() {
  with_reservation_lock _seed_crawler_state_locked
}

_record_active_crawler_locked() {
  local cid="$1" img="$2" sha="$3" fp="$4" cfg="$5" prev_img="${6:-}" prev_sha="${7:-}" prev_fp="${8:-}" prev_cfg="${9:-}"
  mkdir -p "$STATE_DIR"
  printf '%s\n' "$fp" >"$CRAWLER_STATE"
  write_kv_atomic "$CRAWLER_ACTIVE_FILE" \
    "ACTIVE_CONTAINER_ID=$(sanitize_kv "$cid")" \
    "ACTIVE_IMAGE=$(sanitize_kv "$img")" \
    "ACTIVE_SHA=$(sanitize_kv "$sha")" \
    "ACTIVE_FINGERPRINT=$(sanitize_kv "$fp")" \
    "ACTIVE_CONFIG_HASH=$(sanitize_kv "$cfg")" \
    "PREVIOUS_IMAGE=$(sanitize_kv "$prev_img")" \
    "PREVIOUS_SHA=$(sanitize_kv "$prev_sha")" \
    "PREVIOUS_FINGERPRINT=$(sanitize_kv "$prev_fp")" \
    "PREVIOUS_CONFIG_HASH=$(sanitize_kv "$prev_cfg")" \
    "UPDATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

# crawler를 지정 이미지로 기동하고 활성 상태를 기록한다(호출자가 필요 시 잠금을 보유).
_crawler_up_with_image() {
  local target_image="$1" target_sha="${2:-}" target_fp="${3:-}" target_cfg="${4:-}"
  local prev_img="${5:-}" prev_sha="${6:-}" prev_fp="${7:-}" prev_cfg="${8:-}"
  ensure_lock_file_inode "$CRAWL_LOCK_PATH" 666
  CRAWLER_IMAGE="$target_image" compose_core up -d --no-deps --no-build --force-recreate --wait --wait-timeout "$WAIT_TIMEOUT" crawler \
    || return 1

  local cid
  cid="$(crawler_container_id)"
  container_is_healthy_or_running "$cid" || return 1

  [ -n "$target_fp" ] || target_fp="$(image_fingerprint "$target_image")"
  [ -n "$target_cfg" ] || target_cfg="$(canonical_crawler_config_hash)"
  if [ "$target_image" != "$CRAWLER_DEFAULT_IMAGE" ]; then
    docker_cmd tag "$target_image" "$CRAWLER_DEFAULT_IMAGE" >/dev/null 2>&1 || true
  fi
  with_reservation_lock _record_active_crawler_locked \
    "$cid" "$target_image" "$target_sha" "$target_fp" "$target_cfg" \
    "$prev_img" "$prev_sha" "$prev_fp" "$prev_cfg"
}

ensure_crawler_running() {
  local target_image="${1:-$CRAWLER_DEFAULT_IMAGE}" target_sha="${2:-}" state cid
  state="$(crawler_state_for_image "$target_image")"
  case "$state" in
    missing)
      log "crawler가 없어($state) 기동합니다($target_image)."
      _crawler_up_with_image "$target_image" "$target_sha"
      ;;
    stopped)
      log "crawler가 중지 상태여(stopped) 기동합니다."
      ensure_lock_file_inode "$CRAWL_LOCK_PATH" 666
      cid="$(crawler_container_id)"
      if ! compose_core start crawler >/dev/null 2>&1 || ! container_is_healthy_or_running "$cid"; then
        _crawler_up_with_image "$target_image" "$target_sha"
      fi
      ;;
  esac
}

# ---------------------------------------------------------------- 예약 저장·비교 삭제·실패 보존

_save_reservation_locked() {
  local res_id="$1" sha="$2" img="$3" fp="$4" cfg="$5" force="$6"
  write_kv_atomic "$CRAWLER_RESERVATION_FILE" \
    "RESERVATION_ID=$(sanitize_kv "$res_id")" \
    "TARGET_SHA=$(sanitize_kv "$sha")" \
    "TARGET_IMAGE=$(sanitize_kv "$img")" \
    "TARGET_FINGERPRINT=$(sanitize_kv "$fp")" \
    "TARGET_CONFIG_HASH=$(sanitize_kv "$cfg")" \
    "CREATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "FORCE_CRAWLER=$(sanitize_kv "$force")" \
    "ATTEMPTS=0" \
    "NEXT_RETRY_EPOCH=0"
}

save_crawler_reservation() {
  local sha="$1" img="$2" fp="$3" cfg="$4" force="${5:-0}" res_id
  res_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM:-0}"
  with_reservation_lock _save_reservation_locked "$res_id" "$sha" "$img" "$fp" "$cfg" "$force"
}

_clear_obsolete_reservation_locked() {
  if [ -f "$CRAWLER_RESERVATION_FILE" ]; then
    rm -f "$CRAWLER_RESERVATION_FILE"
    log "최신 성공 배포가 현재 실행 중인 crawler와 동일해 대기 예약을 정리했습니다."
  fi
  if [ -f "$CRAWLER_FAILURE_FILE" ]; then
    rm -f "$CRAWLER_FAILURE_FILE"
  fi
}

clear_obsolete_reservation_if_same() {
  with_reservation_lock _clear_obsolete_reservation_locked
}

_compare_and_delete_reservation_locked() {
  local expected_id="$1" cur_id
  [ -f "$CRAWLER_RESERVATION_FILE" ] || return 0
  cur_id="$(kv_get "$CRAWLER_RESERVATION_FILE" "RESERVATION_ID")"
  if [ "$cur_id" = "$expected_id" ]; then
    rm -f "$CRAWLER_RESERVATION_FILE"
    return 0
  fi
  log "교체 도중 새 예약(${cur_id:-unknown})이 등록되어 기존 예약($expected_id)만 완료 처리하고 새 예약은 유지합니다."
  return 0
}

_clear_failure_locked() {
  rm -f "$CRAWLER_FAILURE_FILE"
}

_record_failure_and_preserve_reservation_locked() {
  local res_id="$1" sha="$2" img="$3" reason="$4" recovery_status="$5" recovery_img="$6" attempts="$7" next_retry="$8"
  write_kv_atomic "$CRAWLER_FAILURE_FILE" \
    "FAILED_RESERVATION_ID=$(sanitize_kv "$res_id")" \
    "FAILED_SHA=$(sanitize_kv "$sha")" \
    "FAILED_IMAGE=$(sanitize_kv "$img")" \
    "FAILED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "FAILED_REASON=$(sanitize_kv "$reason")" \
    "RECOVERY_STATUS=$(sanitize_kv "$recovery_status")" \
    "RECOVERY_IMAGE=$(sanitize_kv "$recovery_img")" \
    "ATTEMPTS=$(sanitize_kv "$attempts")"

  if [ -f "$CRAWLER_RESERVATION_FILE" ]; then
    local cur_id cur_sha cur_img cur_fp cur_cfg cur_created cur_force
    cur_id="$(kv_get "$CRAWLER_RESERVATION_FILE" "RESERVATION_ID")"
    if [ "$cur_id" = "$res_id" ]; then
      cur_sha="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_SHA")"
      cur_img="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_IMAGE")"
      cur_fp="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_FINGERPRINT")"
      cur_cfg="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_CONFIG_HASH")"
      cur_created="$(kv_get "$CRAWLER_RESERVATION_FILE" "CREATED_AT")"
      cur_force="$(kv_get "$CRAWLER_RESERVATION_FILE" "FORCE_CRAWLER")"
      write_kv_atomic "$CRAWLER_RESERVATION_FILE" \
        "RESERVATION_ID=$(sanitize_kv "$cur_id")" \
        "TARGET_SHA=$(sanitize_kv "$cur_sha")" \
        "TARGET_IMAGE=$(sanitize_kv "$cur_img")" \
        "TARGET_FINGERPRINT=$(sanitize_kv "$cur_fp")" \
        "TARGET_CONFIG_HASH=$(sanitize_kv "$cur_cfg")" \
        "CREATED_AT=$(sanitize_kv "$cur_created")" \
        "FORCE_CRAWLER=$(sanitize_kv "$cur_force")" \
        "ATTEMPTS=$(sanitize_kv "$attempts")" \
        "NEXT_RETRY_EPOCH=$(sanitize_kv "$next_retry")"
    fi
  fi
}

_read_reservation_vars() {
  [ -f "$CRAWLER_RESERVATION_FILE" ] || return 1
  RES_ID="$(kv_get "$CRAWLER_RESERVATION_FILE" "RESERVATION_ID")"
  RES_SHA="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_SHA")"
  RES_IMG="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_IMAGE")"
  RES_FP="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_FINGERPRINT")"
  RES_CFG="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_CONFIG_HASH")"
  RES_FORCE="$(kv_get "$CRAWLER_RESERVATION_FILE" "FORCE_CRAWLER")"
  RES_ATTEMPTS="$(kv_get "$CRAWLER_RESERVATION_FILE" "ATTEMPTS")"
  RES_NEXT_RETRY="$(kv_get "$CRAWLER_RESERVATION_FILE" "NEXT_RETRY_EPOCH")"
  [ -n "$RES_ID" ] && [ -n "$RES_IMG" ]
}

_collect_protected_images_locked() {
  PROTECTED_IMAGES=("$CRAWLER_DEFAULT_IMAGE")
  local val cid cur_img
  for val in \
    "$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_IMAGE")" \
    "$(kv_get "$CRAWLER_ACTIVE_FILE" "PREVIOUS_IMAGE")" \
    "$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_IMAGE")" \
    "$(kv_get "$CRAWLER_FAILURE_FILE" "FAILED_IMAGE")" \
    "$(kv_get "$CRAWLER_FAILURE_FILE" "RECOVERY_IMAGE")"
  do
    [ -n "$val" ] && PROTECTED_IMAGES+=("$val")
  done
  cid="$(crawler_container_id)"
  if [ -n "$cid" ]; then
    cur_img="$(docker_cmd inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
    [ -n "$cur_img" ] && PROTECTED_IMAGES+=("$cur_img")
  fi
}

_is_protected_image() {
  local needle="$1" p
  for p in "${PROTECTED_IMAGES[@]}"; do
    [ "$p" = "$needle" ] && return 0
  done
  return 1
}

cleanup_crawler_images_locked() {
  local extra
  local PROTECTED_IMAGES=()
  with_reservation_lock _collect_protected_images_locked
  for extra in "$@"; do
    [ -n "$extra" ] && PROTECTED_IMAGES+=("$extra")
  done

  local tag
  while IFS= read -r tag; do
    [ -n "$tag" ] || continue
    case "$tag" in
      news-crawler:sha-*)
        if ! _is_protected_image "$tag"; then
          if docker_cmd image rm "$tag" >/dev/null 2>&1; then
            log "미사용 크롤러 SHA 태그 정리: $tag"
          fi
        fi
        ;;
    esac
  done < <(docker_cmd image ls --format '{{.Repository}}:{{.Tag}}' news-crawler 2>/dev/null || true)

  docker_cmd image prune -f >/dev/null 2>&1 || docker_cmd image prune -f || true
}

cleanup_crawler_images() {
  if [ "$HOLDING_APPLY_LOCK" = "1" ]; then
    cleanup_crawler_images_locked "$@"
    return $?
  fi
  if ! acquire_fd_lock 8 "$CRAWLER_APPLY_LOCK_PATH" 1 644; then
    log "crawler 반영 작업이 진행 중이라 이미지 정리를 건너뜁니다."
    return 0
  fi
  HOLDING_APPLY_LOCK=1
  cleanup_crawler_images_locked "$@" || true
  HOLDING_APPLY_LOCK=0
  release_fd_lock 8
}

_compute_next_retry_epoch() {
  local attempts="$1" now_epoch="$2" base="$CRAWLER_RETRY_BACKOFF_SECONDS" delay=0 i=1
  if [ "$base" -le 0 ] 2>/dev/null; then
    echo 0
    return
  fi
  delay="$base"
  while [ "$i" -lt "$attempts" ]; do
    delay=$((delay * 2))
    if [ "$delay" -ge 3600 ]; then
      delay=3600
      break
    fi
    i=$((i + 1))
  done
  echo $((now_epoch + delay))
}

RECOVERY_STATUS=""

_attempt_previous_recovery() {
  local prev_img="$1"
  if [ -z "$prev_img" ]; then
    RECOVERY_STATUS="no_previous_image"
    return 1
  fi
  if ! docker_cmd image inspect "$prev_img" >/dev/null 2>&1; then
    RECOVERY_STATUS="no_previous_image"
    return 1
  fi
  log "이전 정상 이미지($prev_img)로 crawler 복구를 시도합니다."
  ensure_lock_file_inode "$CRAWL_LOCK_PATH" 666
  if CRAWLER_IMAGE="$prev_img" compose_core up -d --no-deps --no-build --force-recreate --wait --wait-timeout "$WAIT_TIMEOUT" crawler; then
    local restored_cid
    restored_cid="$(crawler_container_id)"
    if container_is_healthy_or_running "$restored_cid"; then
      RECOVERY_STATUS="restored_previous"
      return 0
    fi
  fi
  RECOVERY_STATUS="rollback_failed"
  return 1
}

# 예약된 crawler 버전이 있으면 유휴 시 적용한다.
# 반환 코드: 0=성공/예약없음/정상보류(실행중·시간대·백오프), 1=교체 또는 이미지 검증 실패
apply_reserved_crawler() {
  [ -f "$CRAWLER_RESERVATION_FILE" ] || return 0

  if ! acquire_fd_lock 8 "$CRAWLER_APPLY_LOCK_PATH" 1 644; then
    log "이미 다른 crawler 반영 작업이 실행 중입니다."
    return 0
  fi
  HOLDING_APPLY_LOCK=1

  local RES_ID="" RES_SHA="" RES_IMG="" RES_FP="" RES_CFG="" RES_FORCE="0" RES_ATTEMPTS="0" RES_NEXT_RETRY="0"
  if ! with_reservation_lock _read_reservation_vars; then
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 0
  fi

  local force_flag=0
  if [ "$FORCE_APPLY" = "1" ] || [ "$FORCE_CRAWLER" = "1" ] || [ "${RES_FORCE:-0}" = "1" ]; then
    force_flag=1
  fi

  local now_epoch
  now_epoch="$(date -u +%s)"
  if [ "$force_flag" != "1" ] && [ "${RES_NEXT_RETRY:-0}" -gt "$now_epoch" ] 2>/dev/null; then
    log "이전 실패 백오프 대기 중입니다(sha=${RES_SHA:0:12}, 재시도 epoch=${RES_NEXT_RETRY}). FORCE_APPLY=1로 즉시 재시도할 수 있습니다."
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 0
  fi

  if ! docker_cmd image inspect "$RES_IMG" >/dev/null 2>&1; then
    local attempts=$(( ${RES_ATTEMPTS:-0} + 1 ))
    local next_retry
    next_retry="$(_compute_next_retry_epoch "$attempts" "$now_epoch")"
    err "예약된 크롤러 이미지를 찾을 수 없습니다: $RES_IMG"
    with_reservation_lock _record_failure_and_preserve_reservation_locked \
      "$RES_ID" "$RES_SHA" "$RES_IMG" "target image missing: $RES_IMG" "no_action_needed" "" "$attempts" "$next_retry"
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 1
  fi

  local state cid running
  state="$(crawler_state_for_image "$RES_IMG")"
  if [ "$state" = "same" ]; then
    log "실행 중인 crawler가 이미 예약 버전(${RES_SHA:0:12})과 일치합니다. 예약을 정리합니다."
    with_reservation_lock _compare_and_delete_reservation_locked "$RES_ID"
    with_reservation_lock _clear_failure_locked
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 0
  fi

  cid="$(crawler_container_id)"
  running=""
  [ -n "$cid" ] && running="$(docker_cmd inspect -f '{{.State.Running}}' "$cid" 2>/dev/null || true)"
  if [ "$running" = "true" ] && [ "$force_flag" != "1" ]; then
    if container_supports_shared_lock "$cid"; then
      if in_pre_crawl_window; then
        log "수집 시작 임박 시간대라 교체를 대기합니다($PRE_CRAWL_WINDOW_DESC)."
        HOLDING_APPLY_LOCK=0
        release_fd_lock 8
        return 0
      fi
    else
      if in_crawler_window; then
        log "기존 컨테이너가 공유 잠금을 지원하지 않아 수집 시간대 종료까지 대기합니다($CRAWLER_WINDOW_DESC)."
        HOLDING_APPLY_LOCK=0
        release_fd_lock 8
        return 0
      fi
    fi
  fi

  # Python 수집·번역·DB 저장 전체 구간과 공유하는 OS 파일 잠금을 논블로킹으로 획득한다.
  if ! acquire_fd_lock 7 "$CRAWL_LOCK_PATH" 1 666; then
    log "수집 또는 번역 파이프라인이 실행 중이어서 이번 주기는 교체를 보류합니다(예약 유지: ${RES_SHA:0:12})."
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 0
  fi

  # 잠금 획득 직후 최신 예약을 한 번 더 읽어 직전 도착한 새 예약을 반영한다.
  if ! with_reservation_lock _read_reservation_vars; then
    release_fd_lock 7
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    return 0
  fi

  local prev_cid prev_img="" prev_sha="" prev_fp="" prev_cfg=""
  prev_cid="$(crawler_container_id)"
  if [ -n "$prev_cid" ]; then
    prev_img="$(docker_cmd inspect -f '{{.Config.Image}}' "$prev_cid" 2>/dev/null || true)"
    if [ -f "$CRAWLER_ACTIVE_FILE" ] && [ "$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_CONTAINER_ID")" = "$prev_cid" ]; then
      prev_sha="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_SHA")"
      prev_fp="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_FINGERPRINT")"
      prev_cfg="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_CONFIG_HASH")"
      [ -n "$prev_img" ] || prev_img="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_IMAGE")"
    fi
    if [ -z "$prev_fp" ] && [ -n "$prev_img" ] && docker_cmd image inspect "$prev_img" >/dev/null 2>&1; then
      prev_fp="$(image_fingerprint "$prev_img")"
    fi
  fi
  if [ -z "$prev_img" ] && [ -f "$CRAWLER_ACTIVE_FILE" ]; then
    prev_img="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_IMAGE")"
  fi

  log "예약된 crawler를 적용합니다: sha=${RES_SHA:0:12} ($RES_IMG)"
  if _crawler_up_with_image "$RES_IMG" "$RES_SHA" "$RES_FP" "$RES_CFG" "$prev_img" "$prev_sha" "$prev_fp" "$prev_cfg"; then
    with_reservation_lock _compare_and_delete_reservation_locked "$RES_ID"
    with_reservation_lock _clear_failure_locked
    release_fd_lock 7
    cleanup_crawler_images_locked "$RES_IMG" "$prev_img"
    HOLDING_APPLY_LOCK=0
    release_fd_lock 8
    log "crawler 교체 및 헬스체크가 완료되었습니다: sha=${RES_SHA:0:12}"
    return 0
  fi

  err "새 crawler($RES_IMG) 기동 또는 헬스체크에 실패했습니다."
  save_logs
  RECOVERY_STATUS=""
  _attempt_previous_recovery "$prev_img" || true
  local recovery_status="$RECOVERY_STATUS"
  if [ "$recovery_status" = "restored_previous" ]; then
    local restored_cid
    restored_cid="$(crawler_container_id)"
    with_reservation_lock _record_active_crawler_locked \
      "$restored_cid" "$prev_img" "$prev_sha" "$prev_fp" "$prev_cfg" "" "" "" ""
    log "이전 이미지($prev_img)로 crawler 복구에 성공했습니다."
  else
    err "이전 이미지(${prev_img:-없음}) 복구에 실패했습니다(상태: $recovery_status)."
  fi

  local fail_attempts=$(( ${RES_ATTEMPTS:-0} + 1 ))
  local next_retry
  next_retry="$(_compute_next_retry_epoch "$fail_attempts" "$(date -u +%s)")"
  with_reservation_lock _record_failure_and_preserve_reservation_locked \
    "$RES_ID" "$RES_SHA" "$RES_IMG" "container startup or healthcheck failed" \
    "$recovery_status" "$prev_img" "$fail_attempts" "$next_retry"

  release_fd_lock 7
  HOLDING_APPLY_LOCK=0
  release_fd_lock 8
  return 1
}

# ---------------------------------------------------------------- 상태 표시

print_crawler_status() {
  local cid active_img="" active_sha="" shared_lock_txt="컨테이너 없음" lock_state_txt="유휴"

  if probe_crawl_lock_busy; then
    lock_state_txt="수집/번역 실행 중 (잠금 사용 중)"
  elif ! command -v flock >/dev/null 2>&1; then
    lock_state_txt="유휴 (flock 미지원 환경)"
  fi
  echo "crawler 잠금 상태: $lock_state_txt"

  cid="$(crawler_container_id)"
  if [ -n "$cid" ]; then
    if container_supports_shared_lock "$cid"; then
      shared_lock_txt="지원"
    else
      shared_lock_txt="미지원(레거시 컨테이너)"
    fi
    active_img="$(docker_cmd inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true)"
  fi
  echo "crawler 공유 잠금 지원: $shared_lock_txt"

  if [ -f "$CRAWLER_ACTIVE_FILE" ]; then
    [ -n "$active_img" ] || active_img="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_IMAGE")"
    active_sha="$(kv_get "$CRAWLER_ACTIVE_FILE" "ACTIVE_SHA")"
  fi
  echo "crawler 활성 버전: ${active_sha:-미기록} (${active_img:-없음})"

  if [ -f "$CRAWLER_RESERVATION_FILE" ]; then
    local r_sha r_img r_at r_att r_next
    r_sha="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_SHA")"
    r_img="$(kv_get "$CRAWLER_RESERVATION_FILE" "TARGET_IMAGE")"
    r_at="$(kv_get "$CRAWLER_RESERVATION_FILE" "CREATED_AT")"
    r_att="$(kv_get "$CRAWLER_RESERVATION_FILE" "ATTEMPTS")"
    r_next="$(kv_get "$CRAWLER_RESERVATION_FILE" "NEXT_RETRY_EPOCH")"
    echo "crawler 예약 대기: ${r_sha:-unknown} (${r_img:-unknown}, 예약: ${r_at:-unknown}, 시도: ${r_att:-0}, 다음 재시도 epoch: ${r_next:-0})"
  else
    echo "crawler 예약 대기: 없음"
  fi

  if [ -f "$CRAWLER_FAILURE_FILE" ]; then
    local f_sha f_at f_reason f_rec f_rec_img
    f_sha="$(kv_get "$CRAWLER_FAILURE_FILE" "FAILED_SHA")"
    f_at="$(kv_get "$CRAWLER_FAILURE_FILE" "FAILED_AT")"
    f_reason="$(kv_get "$CRAWLER_FAILURE_FILE" "FAILED_REASON")"
    f_rec="$(kv_get "$CRAWLER_FAILURE_FILE" "RECOVERY_STATUS")"
    f_rec_img="$(kv_get "$CRAWLER_FAILURE_FILE" "RECOVERY_IMAGE")"
    echo "crawler 최근 실패: ${f_sha:-unknown} (${f_at:-unknown}, 사유: ${f_reason:-unknown}, 복구: ${f_rec:-unknown} ${f_rec_img:-})"
  else
    echo "crawler 최근 실패: 없음"
  fi
}

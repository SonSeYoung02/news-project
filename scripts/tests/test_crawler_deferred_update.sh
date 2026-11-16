#!/usr/bin/env bash
# 크롤러 예약 배포·잠금·실패 복구·이미지 보호·레거시 전환 회귀 테스트(외부 Docker/Gemini 불필요).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS_COUNT=0
FAIL_COUNT=0
TMP_WORKSPACES=()

cleanup() {
  local ws
  for ws in "${TMP_WORKSPACES[@]:-}"; do
    rm -rf "$ws" 2>/dev/null || true
  done
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  return 1
}

assert_eq() {
  local actual="$1" expected="$2" msg="${3:-}"
  if [ "$actual" != "$expected" ]; then
    fail "${msg:+$msg: }expected='$expected' actual='$actual'"
  fi
}

assert_file_exists() {
  local path="$1" msg="${2:-file should exist: $1}"
  [ -f "$path" ] || fail "$msg"
}

assert_file_missing() {
  local path="$1" msg="${2:-file should not exist: $1}"
  [ ! -e "$path" ] || fail "$msg"
}

assert_contains() {
  local haystack="$1" needle="$2" msg="${3:-}"
  if [[ "$haystack" != *"$needle"* ]]; then
    fail "${msg:+$msg: }missing '$needle' in output"
  fi
}

read_kv() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 0
  awk -F= -v k="$key" '$1 == k { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

setup_mock_workspace() {
  local ws
  ws="$(mktemp -d)"
  TMP_WORKSPACES+=("$ws")
  mkdir -p "$ws/repo/scripts/lib" "$ws/repo/scripts/systemd" "$ws/repo/news-crawling" \
           "$ws/repo/nginx/proxy/conf.d" "$ws/bin" "$ws/mock_docker" "$ws/logs"

  cp "$REPO_ROOT/scripts/deploy.sh" "$ws/repo/scripts/deploy.sh"
  if [ -f "$REPO_ROOT/scripts/crawler-apply.sh" ]; then
    cp "$REPO_ROOT/scripts/crawler-apply.sh" "$ws/repo/scripts/crawler-apply.sh"
  fi
  if [ -d "$REPO_ROOT/scripts/lib" ]; then
    cp -r "$REPO_ROOT/scripts/lib/." "$ws/repo/scripts/lib/" 2>/dev/null || true
  fi
  cp "$REPO_ROOT/docker-compose.yml" "$ws/repo/docker-compose.yml"
  cp "$REPO_ROOT/docker-compose.app.yml" "$ws/repo/docker-compose.app.yml"

  cat >"$ws/repo/news-crawling/.env" <<'EOF'
SCHEDULE_HOUR=1
SCHEDULE_MINUTE=0
DEADLINE_HOUR=6
DEADLINE_MINUTE=0
GEMINI_API_KEY=dummy-not-printed
EOF

  # mock state defaults
  echo "0c4c0b71a4ab950152fcf58b5af6184876f1a1d2" >"$ws/mock_docker/git_head"
  : >"$ws/mock_docker/docker_calls.log"
  : >"$ws/mock_docker/images.db"
  : >"$ws/mock_docker/containers.db"
  echo "CFG_HASH_V2" >"$ws/mock_docker/compose_crawler_hash"

  # mock git
  cat >"$ws/bin/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
MOCK_DIR="${MOCK_DOCKER_DIR:?}"
if [ "${1:-}" = "-C" ]; then
  shift 2
fi
if [ "${1:-}" = "rev-parse" ]; then
  if [ "${2:-}" = "--short" ]; then
    head -c 7 "$MOCK_DIR/git_head"
    echo
  else
    cat "$MOCK_DIR/git_head"
  fi
  exit 0
fi
exit 0
EOF
  chmod +x "$ws/bin/git"

  # mock systemctl (inert)
  cat >"$ws/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
  chmod +x "$ws/bin/systemctl"

  # mock docker + compose
  cat >"$ws/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
MOCK_DIR="${MOCK_DOCKER_DIR:?}"
echo "docker $*" >>"$MOCK_DIR/docker_calls.log"
for fd in 6 7 8 9; do
  if eval "(: <&$fd)" 2>/dev/null; then
    echo "LEAKED_LOCK_FD_$fd" >>"$MOCK_DIR/docker_calls.log"
  fi
done

find_image_field() {
  local ref="$1" col="$2"
  awk -F'|' -v r="$ref" -v c="$col" '$1 == r { print $c; exit }' "$MOCK_DIR/images.db"
}

upsert_image() {
  local ref="$1" fp="$2" lock_label="$3"
  local tmp="$MOCK_DIR/images.db.tmp.$$"
  awk -F'|' -v r="$ref" '$1 != r' "$MOCK_DIR/images.db" >"$tmp"
  printf '%s|%s|%s\n' "$ref" "$fp" "$lock_label" >>"$tmp"
  mv -f "$tmp" "$MOCK_DIR/images.db"
}

remove_image() {
  local ref="$1"
  local tmp="$MOCK_DIR/images.db.tmp.$$"
  awk -F'|' -v r="$ref" '$1 != r' "$MOCK_DIR/images.db" >"$tmp"
  mv -f "$tmp" "$MOCK_DIR/images.db"
}

find_container() {
  local proj="$1" svc="$2"
  awk -F'|' -v p="$proj" -v s="$svc" '$1 == p && $2 == s { print; exit }' "$MOCK_DIR/containers.db"
}

find_container_by_id() {
  local cid="$1"
  awk -F'|' -v id="$cid" '$3 == id { print; exit }' "$MOCK_DIR/containers.db"
}

upsert_container() {
  # project|service|cid|running|image_ref|fp|cfg_hash|lock_label|has_mount|health
  local proj="$1" svc="$2" cid="$3" running="$4" img="$5" fp="$6" cfg="$7" lbl="$8" mnt="$9" health="${10}"
  local tmp="$MOCK_DIR/containers.db.tmp.$$"
  awk -F'|' -v p="$proj" -v s="$svc" '!($1 == p && $2 == s)' "$MOCK_DIR/containers.db" >"$tmp"
  printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
    "$proj" "$svc" "$cid" "$running" "$img" "$fp" "$cfg" "$lbl" "$mnt" "$health" >>"$tmp"
  mv -f "$tmp" "$MOCK_DIR/containers.db"
}

remove_container_proj() {
  local proj="$1"
  local tmp="$MOCK_DIR/containers.db.tmp.$$"
  awk -F'|' -v p="$proj" '$1 != p' "$MOCK_DIR/containers.db" >"$tmp"
  mv -f "$tmp" "$MOCK_DIR/containers.db"
}

if [ "${1:-}" = "compose" ]; then
  shift
  proj=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -p) proj="$2"; shift 2 ;;
      -f) shift 2 ;;
      *) break ;;
    esac
  done
  sub="${1:-}"
  shift || true
  case "$sub" in
    build)
      svc="${1:-}"
      if [ "$proj" = "news-project" ] && [ "$svc" = "crawler" ]; then
        img="${CRAWLER_IMAGE:-news-crawler:latest}"
        fp="${MOCK_BUILD_FP:-FP_${img}}"
        lbl="${MOCK_BUILD_LOCK_LABEL:-1}"
        upsert_image "$img" "$fp" "$lbl"
      fi
      exit 0
      ;;
    config)
      if [ "${1:-}" = "--hash" ] && [ "${2:-}" = "crawler" ]; then
        if [ "${CRAWLER_IMAGE:-news-crawler:latest}" = "news-crawler:latest" ]; then
          printf 'crawler %s\n' "$(cat "$MOCK_DIR/compose_crawler_hash")"
        else
          printf 'crawler %s_%s\n' "$(cat "$MOCK_DIR/compose_crawler_hash")" "${CRAWLER_IMAGE}"
        fi
        exit 0
      fi
      exit 0
      ;;
    ps)
      quiet=0
      svc=""
      for arg in "$@"; do
        case "$arg" in
          -q) quiet=1 ;;
          -a) ;;
          *) svc="$arg" ;;
        esac
      done
      if [ "$quiet" = "1" ]; then
        if [ -n "$svc" ]; then
          line="$(find_container "$proj" "$svc")"
          [ -n "$line" ] && printf '%s\n' "$(printf '%s' "$line" | cut -d'|' -f3)"
        else
          awk -F'|' -v p="$proj" '$1 == p { print $3 }' "$MOCK_DIR/containers.db"
        fi
      else
        awk -F'|' -v p="$proj" '$1 == p { printf "%s %s (%s)\n", $2, $5, $10 }' "$MOCK_DIR/containers.db"
      fi
      exit 0
      ;;
    exec)
      exit 0
      ;;
    up)
      svc=""
      for arg in "$@"; do
        case "$arg" in
          -d|--no-deps|--no-build|--force-recreate|--wait|--remove-orphans) ;;
          --wait-timeout) ;;
          *) svc="$arg" ;;
        esac
      done
      # grab last non-flag token if numeric wait-timeout preceded it
      last="${!#:-}"
      if [ "$proj" = "news-project" ] && [ "$last" = "crawler" ]; then
        img="${CRAWLER_IMAGE:-news-crawler:latest}"
        if [ -x "$MOCK_DIR/on_crawler_up_hook" ]; then
          "$MOCK_DIR/on_crawler_up_hook" "$img"
        fi
        if [ -f "$MOCK_DIR/fail_images" ] && grep -Fxq "$img" "$MOCK_DIR/fail_images"; then
          fp="$(find_image_field "$img" 2)"
          lbl="$(find_image_field "$img" 3)"
          upsert_container "news-project" "crawler" "cid-crawler-${img//[:\/]/_}" "false" "$img" "${fp:-FP}" "$(cat "$MOCK_DIR/compose_crawler_hash")" "${lbl:-1}" "1" "unhealthy"
          exit 1
        fi
        fp="$(find_image_field "$img" 2)"
        [ -n "$fp" ] || { echo "missing image $img" >&2; exit 1; }
        lbl="$(find_image_field "$img" 3)"
        cfg="$(cat "$MOCK_DIR/compose_crawler_hash")"
        upsert_container "news-project" "crawler" "cid-crawler-${img//[:\/]/_}" "true" "$img" "$fp" "$cfg" "${lbl:-1}" "1" "healthy"
        exit 0
      elif [ "$proj" = "news-project" ] && [ "$last" = "proxy" ]; then
        upsert_container "news-project" "proxy" "cid-proxy" "true" "nginx:alpine" "FP_PROXY" "CFG_PROXY" "" "0" "healthy"
        exit 0
      else
        color="${DEPLOY_COLOR:-blue}"
        upsert_container "$proj" "web" "cid-web-$color" "true" "news-web:$color" "FP_WEB" "CFG_WEB" "" "0" "healthy"
        upsert_container "$proj" "backend" "cid-backend-$color" "true" "news-backend:$color" "FP_BE" "CFG_BE" "" "0" "healthy"
        exit 0
      fi
      ;;
    down)
      remove_container_proj "$proj"
      exit 0
      ;;
    logs|create|start|rm)
      exit 0
      ;;
  esac
  exit 0
fi

case "${1:-}" in
  ps)
    exit 0
    ;;
  exec)
    exit 0
    ;;
  tag)
    src="$2"
    dst="$3"
    fp="$(find_image_field "$src" 2)"
    lbl="$(find_image_field "$src" 3)"
    [ -n "$fp" ] || exit 1
    upsert_image "$dst" "$fp" "$lbl"
    exit 0
    ;;
  image)
    sub="${2:-}"
    shift 2 || true
    case "$sub" in
      inspect)
        fmt=""
        if [ "${1:-}" = "-f" ]; then
          fmt="$2"
          shift 2
        fi
        ref="$1"
        line="$(awk -F'|' -v r="$ref" '$1 == r { print; exit }' "$MOCK_DIR/images.db")"
        if [ -z "$line" ]; then
          # support inspecting by FP pseudo-id if queried
          line="$(awk -F'|' -v r="$ref" '$2 == r { print; exit }' "$MOCK_DIR/images.db")"
        fi
        [ -n "$line" ] || exit 1
        fp="$(printf '%s' "$line" | cut -d'|' -f2)"
        lbl="$(printf '%s' "$line" | cut -d'|' -f3)"
        case "$fmt" in
          *'RootFS.Layers'*)
            printf '{"Layers":["%s"]}{"Env":["%s"]}\n' "$fp" "$lbl"
            ;;
          *'news.crawler.shared-lock'*)
            printf '%s\n' "$lbl"
            ;;
          *)
            printf '%s\n' "$ref"
            ;;
        esac
        exit 0
        ;;
      ls)
        shift || true
        awk -F'|' '$1 ~ /^news-crawler:/ { print $1 }' "$MOCK_DIR/images.db"
        exit 0
        ;;
      rm)
        for ref in "$@"; do
          remove_image "$ref"
        done
        exit 0
        ;;
      prune)
        for a in "$@"; do
          if [ "$a" = "-a" ] || [ "$a" = "--all" ]; then
            echo "FORBIDDEN_PRUNE_ALL" >>"$MOCK_DIR/docker_calls.log"
            exit 99
          fi
        done
        exit 0
        ;;
    esac
    ;;
  inspect)
    shift || true
    fmt=""
    if [ "${1:-}" = "-f" ]; then
      fmt="$2"
      shift 2
    fi
    cid="$1"
    line="$(find_container_by_id "$cid")"
    [ -n "$line" ] || exit 1
    running="$(printf '%s' "$line" | cut -d'|' -f4)"
    img="$(printf '%s' "$line" | cut -d'|' -f5)"
    fp="$(printf '%s' "$line" | cut -d'|' -f6)"
    cfg="$(printf '%s' "$line" | cut -d'|' -f7)"
    lbl="$(printf '%s' "$line" | cut -d'|' -f8)"
    mnt="$(printf '%s' "$line" | cut -d'|' -f9)"
    health="$(printf '%s' "$line" | cut -d'|' -f10)"
    case "$fmt" in
      '{{.State.Running}}') printf '%s\n' "$running" ;;
      *'.State.Health.Status'*) printf '%s\n' "$health" ;;
      '{{.Image}}') printf '%s\n' "$img" ;;
      '{{.Config.Image}}') printf '%s\n' "$img" ;;
      *'com.docker.compose.config-hash'*) printf '%s\n' "$cfg" ;;
      *'news.crawler.shared-lock'*) printf '%s\n' "$lbl" ;;
      *'Mounts'*)
        if [ "$mnt" = "1" ]; then
          printf '/run/crawler-lock\n'
        fi
        ;;
      *) printf '%s\n' "$cid" ;;
    esac
    exit 0
    ;;
esac
exit 0
EOF
  chmod +x "$ws/bin/docker"

  echo "$ws"
}

seed_running_crawler() {
  local ws="$1" img="$2" fp="$3" cfg="$4" lbl="$5" mnt="$6"
  printf '%s|%s|%s\n' "$img" "$fp" "$lbl" >>"$ws/mock_docker/images.db"
  printf 'news-project|crawler|cid-crawler-init|true|%s|%s|%s|%s|%s|healthy\n' \
    "$img" "$fp" "$cfg" "$lbl" "$mnt" >>"$ws/mock_docker/containers.db"
  printf 'news-project|proxy|cid-proxy|true|nginx:alpine|FP_PROXY|CFG_PROXY||0|healthy\n' \
    >>"$ws/mock_docker/containers.db"
}

run_in_ws() {
  local ws="$1"
  shift
  PATH="$ws/bin:$PATH" \
  MOCK_DOCKER_DIR="$ws/mock_docker" \
  DEPLOY_LOG_DIR="$ws/logs" \
  DRAIN_SECONDS=0 \
  PROXY_RELOAD_WAIT=0 \
  WAIT_TIMEOUT=10 \
  "$@"
}

# 1. 수집 시간대 예약 저장, 최신 배포로 예약 갱신, 타이머 자동 반영
test_deferred_reservation_created_and_updated_by_latest_deploy() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  # 1차 배포: 03:55 KST -> 보류 및 예약 저장
  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  local res_file="$ws/repo/.deploy/crawler-reservation.env"
  assert_file_exists "$res_file" "1차 배포 후 예약 파일 생성"
  assert_eq "$(read_kv "$res_file" "TARGET_SHA")" "2222222222222222222222222222222222222222"
  assert_eq "$(read_kv "$res_file" "TARGET_IMAGE")" "news-crawler:sha-222222222222"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-111111111111" "보류 중 기존 컨테이너 유지"

  # 2차 배포: 03:56 KST -> 최신 성공 배포로 예약 갱신
  echo "3333333333333333333333333333333333333333" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_3" DEPLOY_NOW_KST="03:56" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  assert_eq "$(read_kv "$res_file" "TARGET_SHA")" "3333333333333333333333333333333333333333"
  assert_eq "$(read_kv "$res_file" "TARGET_IMAGE")" "news-crawler:sha-333333333333"

  # 타이머 적용: 03:57 KST (유휴 상태, pre-crawl 구간 아님) -> 예약 버전 적용 및 예약 삭제
  DEPLOY_NOW_KST="03:57" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null

  assert_file_missing "$res_file" "헬스체크 성공 후 예약 파일 삭제"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-333333333333" "최신 예약 이미지 적용"
  assert_eq "$(read_kv "$ws/repo/.deploy/crawler-active.env" "PREVIOUS_IMAGE")" "news-crawler:sha-111111111111"
}

# 2. 실행 중인 버전과 같은 내용으로 되돌린 배포가 성공하면 기존 대기 예약을 정리한다
test_revert_to_active_clears_obsolete_pending_reservation() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  assert_file_exists "$ws/repo/.deploy/crawler-reservation.env"

  echo "4444444444444444444444444444444444444444" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_1" DEPLOY_NOW_KST="03:56" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  assert_file_missing "$ws/repo/.deploy/crawler-reservation.env" "실행 버전과 같아지면 구 대기 예약 정리"
}

# 3. 적용 중 새 예약이 도착해도 비교 삭제로 새 예약을 유실하지 않는다
test_compare_and_delete_preserves_new_reservation_arriving_during_apply() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  # 2222 적용 중 deploy.sh가 3333 예약을 갱신하는 상황을 hook으로 재현
  printf '%s|%s|1\n' "news-crawler:sha-333333333333" "FP_3" >>"$ws/mock_docker/images.db"
  cat >"$ws/mock_docker/on_crawler_up_hook" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "news-crawler:sha-222222222222" ] && [ ! -f "$ws/mock_docker/hook_ran" ]; then
  touch "$ws/mock_docker/hook_ran"
  echo "3333333333333333333333333333333333333333" >"$ws/mock_docker/git_head"
  PATH="$ws/bin:\$PATH" MOCK_DOCKER_DIR="$ws/mock_docker" DEPLOY_LOG_DIR="$ws/logs" \
    DRAIN_SECONDS=0 PROXY_RELOAD_WAIT=0 WAIT_TIMEOUT=10 MOCK_BUILD_FP="FP_3" DEPLOY_NOW_KST="03:56" \
    bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
fi
EOF
  chmod +x "$ws/mock_docker/on_crawler_up_hook"

  DEPLOY_NOW_KST="03:57" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null

  local res_file="$ws/repo/.deploy/crawler-reservation.env"
  assert_file_exists "$res_file" "적용 중 도착한 새 예약은 삭제되지 않아야 한다"
  assert_eq "$(read_kv "$res_file" "TARGET_SHA")" "3333333333333333333333333333333333333333"

  DEPLOY_NOW_KST="03:58" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_missing "$res_file" "새 예약까지 반영 후 삭제"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-333333333333"
}

# 4. 헬스체크 실패 시 이전 이미지 복구 시도, 예약 및 실패 상태 보존, 상태 출력
test_healthcheck_failure_rolls_back_and_preserves_reservation_and_failure_state() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  echo "badbadbadbadbadbadbadbadbadbadbadbadbadb" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_BAD" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  echo "news-crawler:sha-badbadbadbad" >"$ws/mock_docker/fail_images"

  if DEPLOY_NOW_KST="03:56" run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null 2>&1; then
    fail "헬스체크 실패 시 non-zero 종료해야 한다"
  fi

  local res_file="$ws/repo/.deploy/crawler-reservation.env"
  local fail_file="$ws/repo/.deploy/crawler-failure.env"
  assert_file_exists "$res_file" "실패 후 예약 보존"
  assert_file_exists "$fail_file" "실패 후 실패 상태 보존"
  assert_eq "$(read_kv "$fail_file" "FAILED_SHA")" "badbadbadbadbadbadbadbadbadbadbadbadbadb"
  assert_eq "$(read_kv "$fail_file" "RECOVERY_STATUS")" "restored_previous"
  assert_eq "$(read_kv "$fail_file" "RECOVERY_IMAGE")" "news-crawler:sha-111111111111"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-111111111111" "이전 이미지로 복구됨"

  local status_out
  status_out="$(run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" status 2>&1)"
  assert_contains "$status_out" "badbadbadbad" "상태 출력에 실패/대기 SHA 포함"
  if [[ "$status_out" == *"dummy-not-printed"* ]]; then
    fail ".env 시크릿이 status에 노출되면 안 된다"
  fi

  # 백오프 동안은 동일 실패 예약을 즉시 재시도해 정상 컨테이너를 흔들지 않는다
  local calls_before
  calls_before="$(wc -l <"$ws/mock_docker/docker_calls.log")"
  DEPLOY_NOW_KST="03:57" run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  local calls_after
  calls_after="$(wc -l <"$ws/mock_docker/docker_calls.log")"
  if grep -q "up -d --no-deps --no-build --force-recreate --wait --wait-timeout 10 crawler" <(tail -n +$((calls_before + 1)) "$ws/mock_docker/docker_calls.log"); then
    fail "백오프 대기 중에는 crawler 교체를 재시도하면 안 된다"
  fi
  [ "$calls_after" -ge "$calls_before" ]

  # 문제 해결 후 FORCE_APPLY=1 재시도 시 정상 반영되고 예약·실패 상태가 정리된다
  rm -f "$ws/mock_docker/fail_images"
  FORCE_APPLY=1 DEPLOY_NOW_KST="03:58" run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_missing "$res_file" "재시도 성공 후 예약 삭제"
  assert_file_missing "$fail_file" "재시도 성공 후 실패 상태 정리"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-badbadbadbad"
}

# 5. 예약/복구/활성/실패 SHA 이미지 prune 보호
test_sha_images_protected_from_prune() {
  local ws
  ws="$(setup_mock_workspace)"
  mkdir -p "$ws/repo/.deploy"
  seed_running_crawler "$ws" "news-crawler:sha-222222222222" "FP_2" "CFG_HASH_V2" "1" "1"
  printf '%s|%s|1\n' "news-crawler:sha-000000000000" "FP_0" >>"$ws/mock_docker/images.db"
  printf '%s|%s|1\n' "news-crawler:sha-111111111111" "FP_1" >>"$ws/mock_docker/images.db"
  printf '%s|%s|1\n' "news-crawler:sha-333333333333" "FP_3" >>"$ws/mock_docker/images.db"
  printf '%s|%s|1\n' "news-crawler:latest" "FP_2" >>"$ws/mock_docker/images.db"

  cat >"$ws/repo/.deploy/crawler-active.env" <<'EOF'
ACTIVE_CONTAINER_ID=cid-crawler-init
ACTIVE_IMAGE=news-crawler:sha-222222222222
ACTIVE_SHA=2222222222222222222222222222222222222222
ACTIVE_FINGERPRINT=FP_2
ACTIVE_CONFIG_HASH=CFG_HASH_V2
PREVIOUS_IMAGE=news-crawler:sha-111111111111
EOF
  cat >"$ws/repo/.deploy/crawler-failure.env" <<'EOF'
FAILED_SHA=bad0000000000000000000000000000000000000
FAILED_IMAGE=news-crawler:sha-bad000000000
RECOVERY_IMAGE=news-crawler:sha-111111111111
RECOVERY_STATUS=restored_previous
EOF
  printf '%s|%s|1\n' "news-crawler:sha-bad000000000" "FP_BAD" >>"$ws/mock_docker/images.db"

  # 3333 예약 배포(03:55) 실행 -> 0000만 정리, 1111(복구)/2222(활성)/3333(예약)/bad000(실패)/latest는 보호
  echo "3333333333333333333333333333333333333333" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_3" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  local imgs calls
  imgs="$(cat "$ws/mock_docker/images.db")"
  calls="$(cat "$ws/mock_docker/docker_calls.log")"
  assert_contains "$imgs" "news-crawler:sha-111111111111" "복구용 이전 SHA 이미지 보호"
  assert_contains "$imgs" "news-crawler:sha-222222222222" "활성 SHA 이미지 보호"
  assert_contains "$imgs" "news-crawler:sha-333333333333" "예약 SHA 이미지 보호"
  assert_contains "$imgs" "news-crawler:sha-bad000000000" "실패 기록 SHA 이미지 보호"
  assert_contains "$imgs" "news-crawler:latest" "latest 태그 보호"
  if [[ "$imgs" == *"news-crawler:sha-000000000000"* ]]; then
    fail "더 이상 쓰이지 않는 과거 SHA 이미지는 정리되어야 한다"
  fi
  if [[ "$calls" == *"FORBIDDEN_PRUNE_ALL"* ]]; then
    fail "docker image prune -a 는 절대 사용하면 안 된다"
  fi
}

# 6. 레거시 컨테이너는 공유 잠금 미지원이므로 전체 수집 시간대 보호 유지, 전환 후에는 임박 구간만 보류
test_legacy_container_migration_keeps_full_window_protection() {
  local ws
  ws="$(setup_mock_workspace)"
  # legacy container: no shared-lock label, no /run/crawler-lock mount, old config hash
  seed_running_crawler "$ws" "news-crawler:latest" "FP_OLD" "CFG_HASH_LEGACY" "" "0"

  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  # 03:56 KST: 레거시 컨테이너는 공유 잠금 미지원이므로 06:00 전까지 교체 보류
  DEPLOY_NOW_KST="03:56" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_exists "$ws/repo/.deploy/crawler-reservation.env" "레거시 컨테이너는 03:56에 보류"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:latest"

  # 06:00 KST: 수집 시간대 종료 후 전환
  DEPLOY_NOW_KST="06:00" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_missing "$ws/repo/.deploy/crawler-reservation.env" "06:00 전환 완료"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-222222222222"

  # 전환 완료 후 새 예약은 00:55(시작 임박 구간)에서 보류
  echo "3333333333333333333333333333333333333333" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_3" DEPLOY_NOW_KST="00:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  DEPLOY_NOW_KST="00:56" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_exists "$ws/repo/.deploy/crawler-reservation.env" "시작 임박 구간(00:50~01:02)은 유휴여도 보류"
}

# 7. 잠금 사용 중일 때 교체 보류, 잠금 inode 유지, 자식 프로세스로 잠금 FD 미상속
test_busy_lock_defers_apply_and_preserves_lock_inode() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="03:55" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1

  local lock_file="$ws/repo/.deploy/locks/crawl.lock"
  assert_file_exists "$lock_file" "호스트 공유 잠금 파일이 미리 생성되어 있어야 한다"
  local ino_before
  ino_before="$(stat -c '%i' "$lock_file" 2>/dev/null || ls -i "$lock_file" | awk '{print $1}')"

  # mock flock으로 수집 중(잠금 점유) 시뮬레이션
  cat >"$ws/bin/flock" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-n" ] && [ "${2:-}" = "7" ] && [ -f "${MOCK_DOCKER_DIR:?}/crawl_lock_busy" ]; then
  exit 1
fi
exit 0
EOF
  chmod +x "$ws/bin/flock"
  touch "$ws/mock_docker/crawl_lock_busy"

  DEPLOY_NOW_KST="12:00" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_exists "$ws/repo/.deploy/crawler-reservation.env" "수집 잠금 점유 시 교체를 보류해야 한다"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-111111111111"

  rm -f "$ws/mock_docker/crawl_lock_busy"
  DEPLOY_NOW_KST="12:01" \
    run_in_ws "$ws" bash "$ws/repo/scripts/crawler-apply.sh" apply >/dev/null
  assert_file_missing "$ws/repo/.deploy/crawler-reservation.env" "수집 잠금 해제 후 교체 완료"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-222222222222"

  assert_file_exists "$lock_file" "잠금 파일은 적용 후에도 삭제되면 안 된다"
  local ino_after
  ino_after="$(stat -c '%i' "$lock_file" 2>/dev/null || ls -i "$lock_file" | awk '{print $1}')"
  assert_eq "$ino_after" "$ino_before" "잠금 파일 inode는 유지되어야 한다"
  if grep -q "LEAKED_LOCK_FD_" "$ws/mock_docker/docker_calls.log"; then
    fail "잠금 FD가 docker 자식 프로세스로 상속되면 안 된다"
  fi
}

# 8. 시간대 밖 배포라도 수집 잠금이 사용 중이면 보류하고, 유휴면 즉시 반영한다
test_outside_window_deploy_respects_crawl_lock() {
  local ws
  ws="$(setup_mock_workspace)"
  seed_running_crawler "$ws" "news-crawler:sha-111111111111" "FP_1" "CFG_HASH_V2" "1" "1"

  cat >"$ws/bin/flock" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-n" ] && [ "${2:-}" = "7" ] && [ -f "${MOCK_DOCKER_DIR:?}/crawl_lock_busy" ]; then
  exit 1
fi
exit 0
EOF
  chmod +x "$ws/bin/flock"
  touch "$ws/mock_docker/crawl_lock_busy"

  echo "2222222222222222222222222222222222222222" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_2" DEPLOY_NOW_KST="12:00" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  assert_file_exists "$ws/repo/.deploy/crawler-reservation.env" "수집 잠금 점유 중에는 시간대 밖 배포여도 예약 보존"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-111111111111"

  rm -f "$ws/mock_docker/crawl_lock_busy"
  echo "3333333333333333333333333333333333333333" >"$ws/mock_docker/git_head"
  MOCK_BUILD_FP="FP_3" DEPLOY_NOW_KST="12:05" \
    run_in_ws "$ws" bash "$ws/repo/scripts/deploy.sh" deploy >/dev/null 2>&1
  assert_file_missing "$ws/repo/.deploy/crawler-reservation.env" "유휴 상태면 즉시 반영 후 예약 삭제"
  assert_contains "$(cat "$ws/mock_docker/containers.db")" "news-crawler:sha-333333333333"
}

# 9. systemd unit/timer 파일 점검
test_systemd_unit_and_timer_files_structure() {
  assert_file_exists "$REPO_ROOT/scripts/systemd/news-crawler-apply.service"
  assert_file_exists "$REPO_ROOT/scripts/systemd/news-crawler-apply.timer"
  assert_contains "$(cat "$REPO_ROOT/scripts/systemd/news-crawler-apply.service")" "crawler-apply.sh"
  assert_contains "$(cat "$REPO_ROOT/scripts/systemd/news-crawler-apply.timer")" "OnCalendar="
}

run_test() {
  local name="$1" rc=0
  set +e
  ( set -euo pipefail; "$name" )
  rc=$?
  set -e
  if [ "$rc" -eq 0 ]; then
    echo "PASS: $name"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "FAILED: $name" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

TEST_FILTER="${1:-}"
for t in \
  test_deferred_reservation_created_and_updated_by_latest_deploy \
  test_revert_to_active_clears_obsolete_pending_reservation \
  test_compare_and_delete_preserves_new_reservation_arriving_during_apply \
  test_healthcheck_failure_rolls_back_and_preserves_reservation_and_failure_state \
  test_sha_images_protected_from_prune \
  test_legacy_container_migration_keeps_full_window_protection \
  test_busy_lock_defers_apply_and_preserves_lock_inode \
  test_outside_window_deploy_respects_crawl_lock \
  test_systemd_unit_and_timer_files_structure
do
  if [ -z "$TEST_FILTER" ] || [ "$TEST_FILTER" = "$t" ]; then
    run_test "$t"
  fi
done

echo "Summary: $PASS_COUNT passed, $FAIL_COUNT failed"
[ "$FAIL_COUNT" -eq 0 ]

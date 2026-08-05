#!/usr/bin/env bash
set -uo pipefail

mode="${1:-}"
shift || true
test_mode="${VANTALINE_DEPLOY_TEST_MODE:-0}"
fail_at="${VANTALINE_DEPLOY_FAIL_AT:-}"

die() { echo "$*" >&2; exit 1; }

require_path() {
  local path="$1"
  [[ -n "$path" && "$path" != "/" ]] || die "unsafe empty or root release path"
  if [[ "$test_mode" == "1" ]]; then
    [[ "$path" == /tmp/* ]] || die "test transaction path must be under /tmp: $path"
  else
    [[ "$path" == /opt/vantaline/* || "$path" == /etc/systemd/system/vantaline.service.d/* ]] \
      || die "production transaction path is outside the allowlist: $path"
  fi
}

privileged() {
  if [[ "$test_mode" == "1" ]]; then "$@"; else sudo "$@"; fi
}

service_ctl() {
  if [[ "$test_mode" == "1" ]]; then
    "${VANTALINE_DEPLOY_SYSTEMCTL:-true}" "$@"
  else
    sudo systemctl "$@"
  fi
}

inject_failure() {
  [[ "$fail_at" != "$1" ]] || die "injected deployment failure at $1"
}

restore_release() {
  local live="$1" previous="$2" absent_marker="${2}.absent" failed_release="${2}.failed"
  require_path "$live"; require_path "$previous"; require_path "$absent_marker"; require_path "$failed_release"
  if [[ -e "$previous" ]]; then
    [[ ! -e "$failed_release" ]] || return 1
    if [[ -e "$live" ]] && ! privileged mv "$live" "$failed_release"; then
      return 1
    fi
    if ! privileged mv "$previous" "$live"; then
      if [[ -e "$failed_release" ]]; then privileged mv "$failed_release" "$live" || true; fi
      return 1
    fi
    if [[ -e "$failed_release" ]]; then privileged rm -rf "$failed_release"; fi
  elif [[ -f "$absent_marker" ]]; then
    privileged rm -rf "$live"
    privileged rm -f "$absent_marker"
  fi
}

restore_dropin() {
  local dropin="$1" backup="$2" staging="${dropin}.staging.$$"
  require_path "$dropin"; require_path "$backup"; require_path "${backup}.absent"; require_path "$staging"
  if [[ -f "$backup" ]]; then
    privileged mkdir -p "$(dirname "$dropin")"
    privileged cp -a "$backup" "$staging"
    privileged mv "$staging" "$dropin"
  elif [[ -f "${backup}.absent" ]]; then
    privileged rm -f "$dropin"
  fi
}

apply_dropin_target() {
  local dropin="$1" target="$2" staging="${dropin}.staging.$$"
  require_path "$dropin"
  if [[ "$target" == "ABSENT" ]]; then
    privileged rm -f "$dropin"
  else
    require_path "$target"
    require_path "$staging"
    [[ -f "$target" ]] || die "target drop-in is missing: $target"
    privileged mkdir -p "$(dirname "$dropin")"
    privileged cp -a "$target" "$staging"
    privileged mv "$staging" "$dropin"
  fi
}

rollback_preview() {
  restore_release "$1" "$2"
}

rollback_production() {
  local live="$1" previous="$2" dropin="$3" dropin_backup="$4" service="$5"
  require_path "$live"; require_path "$previous"; require_path "$dropin"; require_path "$dropin_backup"
  service_ctl stop "$service" >/dev/null 2>&1 || true
  restore_release "$live" "$previous"
  restore_dropin "$dropin" "$dropin_backup"
  service_ctl daemon-reload
  service_ctl start "$service"
}

case "$mode" in
  acquire-lock)
    [[ $# -eq 2 ]] || die "acquire-lock requires LOCK_DIR OWNER"
    lock_dir="$1"; owner="$2"
    require_path "$lock_dir"
    [[ "$owner" =~ ^[a-zA-Z0-9_.-]+$ ]] || die "invalid release lock owner"
    privileged mkdir "$lock_dir" || die "another production release transaction already holds $lock_dir"
    privileged touch "${lock_dir}/owner-${owner}"
    ;;
  release-lock)
    [[ $# -eq 2 ]] || die "release-lock requires LOCK_DIR OWNER"
    lock_dir="$1"; owner="$2"
    require_path "$lock_dir"
    [[ "$owner" =~ ^[a-zA-Z0-9_.-]+$ ]] || die "invalid release lock owner"
    [[ -f "${lock_dir}/owner-${owner}" ]] || die "release lock owner mismatch"
    privileged rm -rf "$lock_dir"
    ;;
  activate-preview)
    [[ $# -eq 3 ]] || die "activate-preview requires LIVE STAGING PREVIOUS"
    live="$1"; staging="$2"; previous="$3"; absent_marker="${3}.absent"
    require_path "$live"; require_path "$staging"; require_path "$previous"; require_path "$absent_marker"
    [[ ! -e "$previous" && ! -e "$absent_marker" && ! -e "${previous}.failed" ]] \
      || die "preview transaction state already exists"
    committed=0
    on_exit() {
      local status=$?
      if [[ $status -ne 0 && $committed -eq 0 ]]; then rollback_preview "$live" "$previous" || true; fi
      exit "$status"
    }
    trap on_exit EXIT
    set -e
    inject_failure before-old-move
    if [[ -e "$live" ]]; then privileged mv "$live" "$previous"; else privileged touch "$absent_marker"; fi
    inject_failure after-old-move
    privileged mv "$staging" "$live"
    inject_failure after-new-move
    committed=1
    trap - EXIT
    ;;
  rollback-preview)
    [[ $# -eq 2 ]] || die "rollback-preview requires LIVE PREVIOUS"
    rollback_preview "$1" "$2"
    ;;
  activate-production)
    [[ $# -eq 8 ]] || die "activate-production requires LIVE STAGING PREVIOUS DROPIN DROPIN_BACKUP SERVICE CONFIRM TARGET_DROPIN"
    live="$1"; staging="$2"; previous="$3"; dropin="$4"; dropin_backup="$5"; service="$6"; confirm="$7"; target_dropin="$8"
    absent_marker="${previous}.absent"
    [[ "$confirm" == "CONFIRM_PRODUCTION_RELEASE_TRANSACTION" ]] || die "production activation confirmation mismatch"
    require_path "$live"; require_path "$staging"; require_path "$previous"; require_path "$absent_marker"
    require_path "$dropin"; require_path "$dropin_backup"; require_path "${dropin_backup}.absent"
    [[ ! -e "$previous" && ! -e "$absent_marker" && ! -e "${previous}.failed" ]] \
      || die "production transaction state already exists"
    [[ ! -e "$dropin_backup" && ! -e "${dropin_backup}.absent" ]] || die "drop-in backup state already exists"
    privileged mkdir -p "$(dirname "$dropin_backup")"
    if [[ -f "$dropin" ]]; then privileged cp -a "$dropin" "$dropin_backup"; else privileged touch "${dropin_backup}.absent"; fi
    committed=0
    on_exit() {
      local status=$?
      if [[ $status -ne 0 && $committed -eq 0 ]]; then rollback_production "$live" "$previous" "$dropin" "$dropin_backup" "$service" || true; fi
      exit "$status"
    }
    trap on_exit EXIT
    set -e
    inject_failure before-old-move
    if [[ -e "$live" ]]; then privileged mv "$live" "$previous"; else privileged touch "$absent_marker"; fi
    inject_failure after-old-move
    privileged mv "$staging" "$live"
    inject_failure after-new-move
    apply_dropin_target "$dropin" "$target_dropin"
    inject_failure after-dropin-change
    service_ctl daemon-reload
    inject_failure before-restart
    service_ctl restart "$service"
    inject_failure after-restart
    committed=1
    trap - EXIT
    ;;
  rollback-production)
    [[ $# -eq 5 ]] || die "rollback-production requires LIVE PREVIOUS DROPIN DROPIN_BACKUP SERVICE"
    rollback_production "$1" "$2" "$3" "$4" "$5"
    ;;
  *)
    die "unknown transaction mode: $mode"
    ;;
esac

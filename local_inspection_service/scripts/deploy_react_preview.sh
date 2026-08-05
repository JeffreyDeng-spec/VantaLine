#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  deploy_react_preview.sh cutover --confirm-production-cutover [--skip-install]
  deploy_react_preview.sh rollback-production [--backup <remote-backup-dir>]

Environment:
  VANTALINE_REMOTE              SSH target, default ubuntu@43.161.199.130
  VANTALINE_SSH_KEY             Optional SSH private key path
  VANTALINE_REMOTE_APP_ROOT     Remote app root, default /opt/vantaline/app
  VANTALINE_REMOTE_BACKUP_ROOT  Remote backup root, default /opt/vantaline/backups/react-deploy

Notes:
  - cutover is gated and requires explicit T J. approval before use.
  - preview deployment is retired because the server redirects /react-preview to /.
  - cutover and rollback both stage first, retain the previous release, verify
    HTML/API/hashed JS health, and automatically restore on failure.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
frontend_dir="${repo_root}/local_inspection_service/frontend"
transaction_helper="${repo_root}/local_inspection_service/scripts/react_release_transaction.sh"

remote="${VANTALINE_REMOTE:-ubuntu@43.161.199.130}"
remote_app_root="${VANTALINE_REMOTE_APP_ROOT:-/opt/vantaline/app}"
remote_backup_root="${VANTALINE_REMOTE_BACKUP_ROOT:-/opt/vantaline/backups/react-deploy}"
ssh_key="${VANTALINE_SSH_KEY:-}"

ssh_base=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "${ssh_key}" ]]; then
  ssh_base+=(-i "${ssh_key}")
fi
rsync_ssh="${ssh_base[*]}"

mode="${1:-}"
shift || true

skip_install=0
confirmed_cutover=0
backup_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-install)
      skip_install=1
      shift
      ;;
    --confirm-production-cutover)
      confirmed_cutover=1
      shift
      ;;
    --backup)
      backup_path="${2:-}"
      if [[ -z "${backup_path}" ]]; then
        echo "--backup requires a remote backup directory" >&2
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

remote_shell_quote() {
  printf '%q' "$1"
}

remote_run() {
  "${ssh_base[@]}" "${remote}" "$@"
}

release_lock_active=0
release_lock_dir="${remote_backup_root}/.production-release.lock"
release_lock_owner=""
release_lock_helper=""

acquire_release_lock() {
  release_lock_owner="$1"
  release_lock_helper="$2"
  remote_run "sudo mkdir -p $(remote_shell_quote "$(dirname "${release_lock_dir}")")
chmod 700 $(remote_shell_quote "${release_lock_helper}")
bash $(remote_shell_quote "${release_lock_helper}") acquire-lock $(remote_shell_quote "${release_lock_dir}") $(remote_shell_quote "${release_lock_owner}")"
  release_lock_active=1
}

release_release_lock() {
  if [[ "${release_lock_active}" -eq 1 ]]; then
    remote_run "bash $(remote_shell_quote "${release_lock_helper}") release-lock $(remote_shell_quote "${release_lock_dir}") $(remote_shell_quote "${release_lock_owner}")"
    release_lock_active=0
  fi
  if [[ -n "${release_lock_helper}" ]]; then
    remote_run "rm -f $(remote_shell_quote "${release_lock_helper}")" || true
  fi
}

require_frontend() {
  if [[ ! -f "${frontend_dir}/package-lock.json" ]]; then
    echo "Missing ${frontend_dir}/package-lock.json" >&2
    exit 1
  fi
}

install_frontend() {
  if [[ "${skip_install}" -eq 0 ]]; then
    (cd "${frontend_dir}" && npm ci)
  fi
}

build_production_cutover() {
  require_frontend
  install_frontend
  (cd "${frontend_dir}" && npm run build:production-cutover)
  test -f "${frontend_dir}/dist-production/index.html"
}

new_release_nonce() {
  od -An -N12 -tx1 /dev/urandom | tr -d ' \n'
}

verify_remote_http() {
  local page_path="$1"
  local asset_prefix="$2"
  remote_run "set -euo pipefail
for attempt in \$(seq 1 30); do
  if curl -fsS --max-time 3 $(remote_shell_quote "http://127.0.0.1:8765${page_path}") >/tmp/vantaline-deploy-page.html \
    && curl -fsS --max-time 3 http://127.0.0.1:8765/api/auth/status >/tmp/vantaline-deploy-auth.json; then
    asset_path=\$(grep -oE $(remote_shell_quote "${asset_prefix}[^\"' ]+\\.js") /tmp/vantaline-deploy-page.html | head -n 1 || true)
    if [ -n \"\${asset_path}\" ] && curl -fsS --max-time 5 \"http://127.0.0.1:8765\${asset_path}\" >/dev/null; then
      exit 0
    fi
  fi
  sleep 1
done
echo 'Deployment health check failed after 30 attempts' >&2
exit 1"
}

latest_backup() {
  local category="$1"
  local required="dist-production"
  remote_run "set -euo pipefail
root=$(remote_shell_quote "${remote_backup_root}/${category}")
if [ -d \"\${root}\" ]; then
  for candidate in \"\${root}\"/*; do
    [ -d \"\${candidate}\" ] || continue
    [ -f \"\${candidate}/COMPLETED\" ] || continue
    [ -d \"\${candidate}/$(remote_shell_quote "${required}")\" ] || continue
    printf '%s\n' \"\${candidate}\"
  done | sort | tail -n 1
fi"
}

cutover_production() {
  if [[ "${confirmed_cutover}" -ne 1 ]]; then
    echo "Refusing production cutover without --confirm-production-cutover." >&2
    echo "Use this only after explicit T J. approval." >&2
    exit 3
  fi

  local ts release_id production_dir backup_dir staging_dir previous_dir remote_helper dropin dropin_backup lock_owner
  ts="$(remote_run 'date +%Y%m%d%H%M%S')"
  release_id="${ts}-$(new_release_nonce)"
  production_dir="${remote_app_root}/local_inspection_service/frontend/dist-production"
  backup_dir="${remote_backup_root}/production-dist/${release_id}"
  staging_dir="${remote_app_root}/local_inspection_service/frontend/.dist-production.staging-${release_id}"
  previous_dir="${remote_app_root}/local_inspection_service/frontend/.dist-production.previous-${release_id}"
  remote_helper="/tmp/vantaline-react-release-transaction-${release_id}.sh"
  dropin="/etc/systemd/system/vantaline.service.d/30-react-production.conf"
  dropin_backup="${backup_dir}/30-react-production.conf"
  lock_owner="cutover-${release_id}"

  rsync -rtz --omit-dir-times --no-owner --no-group --no-perms -e "${rsync_ssh}" "${transaction_helper}" "${remote}:${remote_helper}"
  trap release_release_lock EXIT
  trap 'release_release_lock; exit 130' INT TERM
  acquire_release_lock "${lock_owner}" "${remote_helper}"

  build_production_cutover

  remote_run "set -euo pipefail
test ! -e $(remote_shell_quote "${staging_dir}")
test ! -e $(remote_shell_quote "${previous_dir}")
sudo mkdir -p $(remote_shell_quote "${backup_dir}") $(remote_shell_quote "${staging_dir}")
sudo chmod -R ugo+rwX $(remote_shell_quote "${staging_dir}")"

  rsync -rtz --delete --omit-dir-times --no-owner --no-group --no-perms -e "${rsync_ssh}" "${frontend_dir}/dist-production/" "${remote}:${staging_dir}/"
  remote_run "set -euo pipefail
test -f $(remote_shell_quote "${staging_dir}/index.html")
test -d $(remote_shell_quote "${staging_dir}/assets")
sudo chown -R vantaline:vantaline $(remote_shell_quote "${staging_dir}")
sudo find $(remote_shell_quote "${staging_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${staging_dir}") -type f -exec chmod 644 {} +
chmod 700 $(remote_shell_quote "${remote_helper}")
bash $(remote_shell_quote "${remote_helper}") activate-production $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${staging_dir}") $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${dropin}") $(remote_shell_quote "${dropin_backup}") vantaline CONFIRM_PRODUCTION_RELEASE_TRANSACTION ABSENT"

  if ! verify_remote_http "/" "/static/assets/"; then
    remote_run "bash $(remote_shell_quote "${remote_helper}") rollback-production $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${dropin}") $(remote_shell_quote "${dropin_backup}") vantaline"
    verify_remote_http "/" "/static/assets/" || true
    echo "Production cutover failed health checks and was rolled back." >&2
    exit 1
  fi

  remote_run "set -euo pipefail
if [ -e $(remote_shell_quote "${previous_dir}") ]; then sudo mv $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${backup_dir}/dist-production"); fi
sudo rm -f $(remote_shell_quote "${previous_dir}.absent")
sudo touch $(remote_shell_quote "${backup_dir}/COMPLETED")
printf 'production_dist=%s\nproduction_backup=%s\n' $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${backup_dir}")"
  release_release_lock
  trap - EXIT INT TERM
}

rollback_production() {
  local production_dir="${remote_app_root}/local_inspection_service/frontend/dist-production"
  local selected_backup="${backup_path}"
  if [[ -z "${selected_backup}" ]]; then
    selected_backup="$(latest_backup production-dist)"
  fi
  if [[ -z "${selected_backup}" ]]; then
    echo "No production backup found under ${remote_backup_root}/production-dist" >&2
    exit 1
  fi

  local ts release_id staging_dir previous_dir operation_backup remote_helper dropin dropin_backup target_dropin lock_owner
  ts="$(remote_run 'date +%Y%m%d%H%M%S')"
  release_id="${ts}-$(new_release_nonce)"
  staging_dir="${remote_app_root}/local_inspection_service/frontend/.dist-production.rollback-staging-${release_id}"
  previous_dir="${remote_app_root}/local_inspection_service/frontend/.dist-production.rollback-previous-${release_id}"
  operation_backup="${remote_backup_root}/production-dist/${release_id}-rollback"
  remote_helper="/tmp/vantaline-react-release-transaction-${release_id}-rollback.sh"
  dropin="/etc/systemd/system/vantaline.service.d/30-react-production.conf"
  dropin_backup="${operation_backup}/30-react-production.conf"
  lock_owner="rollback-${release_id}"

  rsync -rtz --omit-dir-times --no-owner --no-group --no-perms -e "${rsync_ssh}" "${transaction_helper}" "${remote}:${remote_helper}"
  trap release_release_lock EXIT
  trap 'release_release_lock; exit 130' INT TERM
  acquire_release_lock "${lock_owner}" "${remote_helper}"

  if remote_run "test -f $(remote_shell_quote "${selected_backup}/30-react-production.conf")"; then
    target_dropin="${selected_backup}/30-react-production.conf"
  elif remote_run "test -f $(remote_shell_quote "${selected_backup}/30-react-production.conf.absent")"; then
    target_dropin="ABSENT"
  else
    echo "Selected backup has no recorded systemd drop-in state: ${selected_backup}" >&2
    exit 1
  fi

  remote_run "set -euo pipefail
test -f $(remote_shell_quote "${selected_backup}/COMPLETED")
test -d $(remote_shell_quote "${selected_backup}/dist-production")
test ! -e $(remote_shell_quote "${staging_dir}")
test ! -e $(remote_shell_quote "${previous_dir}")
sudo mkdir -p $(remote_shell_quote "${operation_backup}")
sudo cp -a $(remote_shell_quote "${selected_backup}/dist-production") $(remote_shell_quote "${staging_dir}")
sudo chown -R vantaline:vantaline $(remote_shell_quote "${staging_dir}")
sudo find $(remote_shell_quote "${staging_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${staging_dir}") -type f -exec chmod 644 {} +"

  remote_run "set -euo pipefail
chmod 700 $(remote_shell_quote "${remote_helper}")
bash $(remote_shell_quote "${remote_helper}") activate-production $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${staging_dir}") $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${dropin}") $(remote_shell_quote "${dropin_backup}") vantaline CONFIRM_PRODUCTION_RELEASE_TRANSACTION $(remote_shell_quote "${target_dropin}")"

  if ! verify_remote_http "/" "/static/assets/"; then
    remote_run "bash $(remote_shell_quote "${remote_helper}") rollback-production $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${dropin}") $(remote_shell_quote "${dropin_backup}") vantaline"
    verify_remote_http "/" "/static/assets/" || true
    echo "Production rollback failed health checks and the pre-rollback release was restored." >&2
    exit 1
  fi

  remote_run "set -euo pipefail
if [ -e $(remote_shell_quote "${previous_dir}") ]; then sudo mv $(remote_shell_quote "${previous_dir}") $(remote_shell_quote "${operation_backup}/dist-production"); fi
sudo rm -f $(remote_shell_quote "${previous_dir}.absent")
sudo touch $(remote_shell_quote "${operation_backup}/COMPLETED")
printf 'restored_production_dist=%s\nfrom_backup=%s\nrollback_backup=%s\n' $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${selected_backup}") $(remote_shell_quote "${operation_backup}")"
  release_release_lock
  trap - EXIT INT TERM
}

case "${mode}" in
  cutover)
    cutover_production
    ;;
  rollback-production)
    rollback_production
    ;;
  -h|--help)
    usage
    ;;
  *)
    echo "Unknown mode: ${mode}" >&2
    usage >&2
    exit 2
    ;;
esac

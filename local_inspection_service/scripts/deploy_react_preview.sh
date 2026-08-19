#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  deploy_react_preview.sh preview [--skip-install]
  deploy_react_preview.sh rollback-preview [--backup <remote-backup-dir>]
  deploy_react_preview.sh cutover --confirm-production-cutover [--skip-install]
  deploy_react_preview.sh rollback-production [--backup <remote-backup-dir>]

Environment:
  VANTALINE_REMOTE              SSH target, default ubuntu@43.161.199.130
  VANTALINE_SSH_KEY             Optional SSH private key path
  VANTALINE_REMOTE_APP_ROOT     Remote app root, default /opt/vantaline/app
  VANTALINE_REMOTE_BACKUP_ROOT  Remote backup root, default /opt/vantaline/backups/react-deploy

Notes:
  - preview is the safe default and only replaces frontend/dist for /react-preview/.
  - cutover is gated and requires explicit T J. approval before use.
  - cutover builds React with root router basename and /static/ asset URLs,
    backs up frontend/dist-production, replaces it, then restarts the service.
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
frontend_dir="${repo_root}/local_inspection_service/frontend"

remote="${VANTALINE_REMOTE:-ubuntu@43.161.199.130}"
remote_app_root="${VANTALINE_REMOTE_APP_ROOT:-/opt/vantaline/app}"
remote_backup_root="${VANTALINE_REMOTE_BACKUP_ROOT:-/opt/vantaline/backups/react-deploy}"
ssh_key="${VANTALINE_SSH_KEY:-}"

ssh_base=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "${ssh_key}" ]]; then
  ssh_base+=(-i "${ssh_key}")
fi
rsync_ssh="${ssh_base[*]}"

mode="${1:-preview}"
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

build_preview() {
  require_frontend
  install_frontend
  (cd "${frontend_dir}" && npm run build)
  test -f "${frontend_dir}/dist/index.html"
}

build_production_cutover() {
  require_frontend
  install_frontend
  (cd "${frontend_dir}" && npm run build:production-cutover)
  test -f "${frontend_dir}/dist-production/index.html"
}

latest_backup() {
  local category="$1"
  remote_run "set -euo pipefail; if [ -d $(remote_shell_quote "${remote_backup_root}/${category}") ]; then find $(remote_shell_quote "${remote_backup_root}/${category}") -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1; fi"
}

deploy_preview() {
  build_preview

  local ts release_dir backup_dir
  ts="$(remote_run 'date +%Y%m%d%H%M%S')"
  release_dir="${remote_app_root}/local_inspection_service/frontend/dist"
  backup_dir="${remote_backup_root}/preview-dist/${ts}"

  remote_run "set -euo pipefail
sudo mkdir -p $(remote_shell_quote "${backup_dir}") $(remote_shell_quote "$(dirname "${release_dir}")")
if [ -e $(remote_shell_quote "${release_dir}") ]; then
sudo cp -a $(remote_shell_quote "${release_dir}") $(remote_shell_quote "${backup_dir}/dist")
fi
sudo mkdir -p $(remote_shell_quote "${release_dir}")
sudo chmod -R ugo+rwX $(remote_shell_quote "${release_dir}")"

  rsync -rtz --delete --omit-dir-times --no-owner --no-group --no-perms -e "${rsync_ssh}" "${frontend_dir}/dist/" "${remote}:${release_dir}/"

  remote_run "set -euo pipefail
sudo chown -R vantaline:vantaline $(remote_shell_quote "${release_dir}")
sudo find $(remote_shell_quote "${release_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${release_dir}") -type f -exec chmod 644 {} +
printf 'preview_release=%s\npreview_backup=%s\n' $(remote_shell_quote "${release_dir}") $(remote_shell_quote "${backup_dir}")"
}

rollback_preview() {
  local release_dir="${remote_app_root}/local_inspection_service/frontend/dist"
  local selected_backup="${backup_path}"
  if [[ -z "${selected_backup}" ]]; then
    selected_backup="$(latest_backup preview-dist)"
  fi
  if [[ -z "${selected_backup}" ]]; then
    echo "No preview backup found under ${remote_backup_root}/preview-dist" >&2
    exit 1
  fi

  remote_run "set -euo pipefail
test -d $(remote_shell_quote "${selected_backup}/dist")
sudo rm -rf $(remote_shell_quote "${release_dir}")
sudo cp -a $(remote_shell_quote "${selected_backup}/dist") $(remote_shell_quote "${release_dir}")
sudo chown -R vantaline:vantaline $(remote_shell_quote "${release_dir}")
sudo find $(remote_shell_quote "${release_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${release_dir}") -type f -exec chmod 644 {} +
printf 'restored_preview=%s\nfrom_backup=%s\n' $(remote_shell_quote "${release_dir}") $(remote_shell_quote "${selected_backup}")"
}

cutover_production() {
  if [[ "${confirmed_cutover}" -ne 1 ]]; then
    echo "Refusing production cutover without --confirm-production-cutover." >&2
    echo "Use this only after explicit T J. approval." >&2
    exit 3
  fi

  build_production_cutover

  local ts production_dir backup_dir
  ts="$(remote_run 'date +%Y%m%d%H%M%S')"
  production_dir="${remote_app_root}/local_inspection_service/frontend/dist-production"
  backup_dir="${remote_backup_root}/production-dist/${ts}"

  remote_run "set -euo pipefail
sudo mkdir -p $(remote_shell_quote "${backup_dir}") $(remote_shell_quote "$(dirname "${production_dir}")")
if [ -e $(remote_shell_quote "${production_dir}") ]; then
sudo cp -a $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${backup_dir}/dist-production")
fi
sudo mkdir -p $(remote_shell_quote "${production_dir}")
sudo chmod -R ugo+rwX $(remote_shell_quote "${production_dir}")"

  rsync -rtz --delete --omit-dir-times --no-owner --no-group --no-perms -e "${rsync_ssh}" "${frontend_dir}/dist-production/" "${remote}:${production_dir}/"

  remote_run "set -euo pipefail
test -f $(remote_shell_quote "${production_dir}/index.html")
test -d $(remote_shell_quote "${production_dir}/assets")
sudo chown -R vantaline:vantaline $(remote_shell_quote "${production_dir}")
sudo find $(remote_shell_quote "${production_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${production_dir}") -type f -exec chmod 644 {} +
sudo rm -f /etc/systemd/system/vantaline.service.d/30-react-production.conf
sudo systemctl daemon-reload
sudo systemctl restart vantaline
printf 'production_dist=%s\nproduction_backup=%s\n' $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${backup_dir}")"
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

  remote_run "set -euo pipefail
test -d $(remote_shell_quote "${selected_backup}/dist-production")
sudo rm -rf $(remote_shell_quote "${production_dir}")
sudo cp -a $(remote_shell_quote "${selected_backup}/dist-production") $(remote_shell_quote "${production_dir}")
sudo chown -R vantaline:vantaline $(remote_shell_quote "${production_dir}")
sudo find $(remote_shell_quote "${production_dir}") -type d -exec chmod 755 {} +
sudo find $(remote_shell_quote "${production_dir}") -type f -exec chmod 644 {} +
sudo rm -f /etc/systemd/system/vantaline.service.d/30-react-production.conf
sudo systemctl daemon-reload
sudo systemctl restart vantaline
printf 'restored_production_dist=%s\nfrom_backup=%s\n' $(remote_shell_quote "${production_dir}") $(remote_shell_quote "${selected_backup}")"
}

case "${mode}" in
  preview)
    deploy_preview
    ;;
  rollback-preview)
    rollback_preview
    ;;
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

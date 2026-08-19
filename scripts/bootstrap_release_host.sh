#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --deploy-public-key FILE --installer FILE --apply" >&2; exit 2; }
public_key=""
installer=""
apply=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deploy-public-key) public_key="$2"; shift 2 ;;
    --installer) installer="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage ;;
  esac
done
[[ -f "$public_key" && -f "$installer" && "$apply" -eq 1 ]] || usage

backup="/opt/vantaline/backups/release-bootstrap-$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -o root -g root -m 700 "$backup"
sudo cp -a /etc/systemd/system/vantaline.service "$backup/"
if [[ -d /etc/systemd/system/vantaline.service.d ]]; then
  sudo cp -a /etc/systemd/system/vantaline.service.d "$backup/"
fi
rollback_needed=1
rollback() {
  status=$?
  if [[ "$status" -ne 0 && "$rollback_needed" -eq 1 ]]; then
    sudo rm -f /etc/systemd/system/vantaline.service.d/60-immutable-release.conf
    sudo systemctl daemon-reload
    sudo systemctl restart vantaline || true
  fi
  exit "$status"
}
trap rollback EXIT

id -u vantaline-deploy >/dev/null 2>&1 || sudo useradd --system --create-home --home-dir /opt/vantaline/deploy --shell /bin/bash vantaline-deploy
sudo install -d -m 755 /opt/vantaline/releases /opt/vantaline/shared
sudo install -d -o vantaline-deploy -g vantaline-deploy -m 700 /opt/vantaline/incoming
for item in data models; do
  source="/opt/vantaline/app/$item"; [[ "$item" == "data" ]] && source="/opt/vantaline/app/local_inspection_service/data"
  destination="/opt/vantaline/shared/$item"; if [[ ! -e "$destination" ]]; then sudo cp -a "$source" "$destination"; fi
done
if [[ ! -L /opt/vantaline/app/local_inspection_service/data ]]; then
  sudo mv /opt/vantaline/app/local_inspection_service/data /opt/vantaline/app/local_inspection_service/data.pre-release-backup
  sudo ln -s /opt/vantaline/shared/data /opt/vantaline/app/local_inspection_service/data
fi
if [[ ! -L /opt/vantaline/app/models ]]; then
  sudo mv /opt/vantaline/app/models /opt/vantaline/app/models.pre-release-backup
  sudo ln -s /opt/vantaline/shared/models /opt/vantaline/app/models
fi
sudo ln -sfn /opt/vantaline/venv /opt/vantaline/app/.venv
sudo ln -sfn /opt/vantaline/app /opt/vantaline/current

deploy_home=/opt/vantaline/deploy
sudo install -d -o vantaline-deploy -g vantaline-deploy -m 700 "$deploy_home/.ssh"
sudo install -o vantaline-deploy -g vantaline-deploy -m 600 "$public_key" "$deploy_home/.ssh/authorized_keys"
sudo install -o root -g root -m 755 "$installer" /usr/local/sbin/vantaline-install-release
printf '%s\n' 'vantaline-deploy ALL=(root) NOPASSWD: /usr/local/sbin/vantaline-install-release' | sudo tee /etc/sudoers.d/vantaline-deploy >/dev/null
sudo chmod 440 /etc/sudoers.d/vantaline-deploy
sudo visudo -cf /etc/sudoers.d/vantaline-deploy

sudo install -d -m 755 /etc/systemd/system/vantaline.service.d
sudo tee /etc/systemd/system/vantaline.service.d/60-immutable-release.conf >/dev/null <<'EOF'
[Service]
WorkingDirectory=/opt/vantaline/current
Environment=VANTALINE_REPO_ROOT=/opt/vantaline/current
ExecStart=
ExecStart=/opt/vantaline/current/.venv/bin/python -m uvicorn local_inspection_service.server:app --host 127.0.0.1 --port 8765 --proxy-headers --forwarded-allow-ips=127.0.0.1
EOF
sudo systemctl daemon-reload
sudo systemctl restart vantaline
systemctl is-active --quiet vantaline
[[ "$(systemctl show vantaline -p WorkingDirectory --value)" == "/opt/vantaline/current" ]]
curl -fsS http://127.0.0.1:8765/ >/dev/null
rollback_needed=0
sudo sh -c "printf '%s\n' complete > '$backup/COMPLETED'"
echo "immutable release host bootstrap complete"

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

id -u vantaline-deploy >/dev/null 2>&1 || sudo useradd --system --create-home --home-dir /opt/vantaline/deploy --shell /bin/bash vantaline-deploy
sudo install -d -m 755 /opt/vantaline/releases /opt/vantaline/shared
sudo install -d -o vantaline-deploy -g vantaline-deploy -m 700 /opt/vantaline/incoming
sudo ln -sfn /opt/vantaline/app/local_inspection_service/data /opt/vantaline/shared/data
sudo ln -sfn /opt/vantaline/app/models /opt/vantaline/shared/models
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
EOF
sudo systemctl daemon-reload
sudo systemctl restart vantaline
systemctl is-active --quiet vantaline
[[ "$(systemctl show vantaline -p WorkingDirectory --value)" == "/opt/vantaline/current" ]]
curl -fsS http://127.0.0.1:8765/ >/dev/null
echo "immutable release host bootstrap complete"

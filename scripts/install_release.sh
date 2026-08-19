#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --archive PATH --release ID --apply" >&2
  exit 2
}

archive=""
release=""
apply=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive) archive="$2"; shift 2 ;;
    --release) release="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage ;;
  esac
done
[[ -f "$archive" && "$release" =~ ^[A-Za-z0-9._-]{8,160}$ ]] || usage
[[ "$apply" -eq 1 ]] || { echo "dry guard: --apply is required" >&2; exit 2; }

base=/opt/vantaline
releases="$base/releases"
target="$releases/$release"
current="$base/current"
lock="$base/backups/.production-release.lock"
db_url='postgresql:///vantaline?host=/var/run/postgresql&user=vantaline'
previous=""
switched=0
lock_owned=0

rollback() {
  set +e
  if [[ "$switched" -eq 1 && -n "$previous" ]]; then
    sudo ln -sfn "$previous" "$current.rollback"
    sudo mv -Tf "$current.rollback" "$current"
    sudo systemctl restart vantaline
  fi
}
cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then rollback; fi
  if [[ "$lock_owned" -eq 1 ]]; then sudo rm -f "$lock"; fi
  exit $status
}
trap cleanup EXIT INT TERM

sudo sh -c "set -o noclobber; printf '%s\n' '$$' > '$lock'"
lock_owned=1
systemctl is-active --quiet vantaline
working_directory="$(systemctl show vantaline -p WorkingDirectory --value)"
[[ "$working_directory" == "$current" ]] || {
  echo "systemd WorkingDirectory must be $current before immutable releases are enabled" >&2
  exit 1
}
[[ ! -e "$target" ]]
counts="$(sudo -u vantaline psql "$db_url" -tAc "select (select count(*) from vantaline.plc_workstation_leases)||'|'||(select count(*) from vantaline.plc_web_serial_dispatches where status not in ('acknowledged','failed','partial_success','uncertain'));")"
[[ "$counts" == "0|0" ]]

sudo mkdir -p "$target"
sudo tar -xzf "$archive" --strip-components=1 -C "$target"
(cd "$target" && sha256sum -c SHA256SUMS)
python3 - "$target/VERSION.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc["backend_protocol"] == "plc-web-serial-v4"
assert doc["frontend_protocol"] == "plc-web-serial-v4"
assert len(doc["git_commit"]) == 40
PY

if [[ -L "$current" ]]; then previous="$(readlink -f "$current")"; else previous="$base/app"; fi
sudo ln -sfn "$target" "$current.new"
sudo mv -Tf "$current.new" "$current"
switched=1
sudo systemctl restart vantaline
systemctl is-active --quiet vantaline
curl -fsS http://127.0.0.1:8765/api/version | python3 -c 'import json,sys; assert json.load(sys.stdin)["consistent"] is True'
curl -fsS http://127.0.0.1:8765/ >/dev/null
echo "release=$release previous=$previous"

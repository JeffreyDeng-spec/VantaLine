#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --archive PATH --archive-sha256 HEX --release ID --commit SHA --apply" >&2
  exit 2
}

archive=""
release=""
commit=""
archive_sha256=""
apply=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive) archive="$2"; shift 2 ;;
    --release) release="$2"; shift 2 ;;
    --commit) commit="$2"; shift 2 ;;
    --archive-sha256) archive_sha256="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage ;;
  esac
done
[[ -f "$archive" && "$release" =~ ^[A-Za-z0-9._-]{8,160}$ ]] || usage
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$archive_sha256" =~ ^[0-9a-f]{64}$ ]] || usage
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
counts="$(sudo -u vantaline psql "$db_url" -tAc "select (select count(*) from vantaline.plc_workstation_leases where state in ('connecting','active','draining') and expires_at >= extract(epoch from clock_timestamp())::bigint)||'|'||(select count(*) from vantaline.plc_web_serial_dispatches where status not in ('acknowledged','failed','partial_success','uncertain'));")"
[[ "$counts" == "0|0" ]] || { echo "PLC activity gate failed: $counts" >&2; exit 1; }

echo "$archive_sha256  $archive" | sha256sum -c -
sudo mkdir -p "$target"
sudo tar -xzf "$archive" --strip-components=1 -C "$target"
(sudo rm -rf "$target/local_inspection_service/data" "$target/models")
sudo ln -s /opt/vantaline/shared/data "$target/local_inspection_service/data"
sudo ln -s /opt/vantaline/shared/models "$target/models"
(cd "$target" && sha256sum -c SHA256SUMS)
python3 - "$target/VERSION.json" "$release" "$commit" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
assert doc["release"] == sys.argv[2]
assert doc["git_commit"] == sys.argv[3]
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
curl -fsS http://127.0.0.1:8765/api/version | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["consistent"] is True and d["git_commit"] == sys.argv[1]' "$commit"
curl -fsS http://127.0.0.1:8765/ >/dev/null
index="$(curl -fsS http://127.0.0.1:8765/)"
while read -r asset; do curl -fsS "http://127.0.0.1:8765$asset" >/dev/null; done < <(printf '%s' "$index" | grep -oE '/static/assets/[^" ]+\.(js|css)' | sort -u)
pid="$(systemctl show vantaline -p MainPID --value)"
! sudo journalctl _PID="$pid" --no-pager | grep -E 'Traceback|ERROR|CRITICAL'
sudo rm -f "$archive"
echo "release=$release previous=$previous"

#!/usr/bin/env bash
set -euo pipefail

usage() { echo "usage: $0 --archive /opt/vantaline/incoming/ID.tar.gz --archive-sha256 HEX --release ID --commit SHA --apply" >&2; exit 2; }
archive=""; archive_sha256=""; release=""; commit=""; apply=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive) archive="$2"; shift 2 ;;
    --archive-sha256) archive_sha256="$2"; shift 2 ;;
    --release) release="$2"; shift 2 ;;
    --commit) commit="$2"; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage ;;
  esac
done
[[ "$release" =~ ^v[0-9]{4}\.[0-9]{2}\.[0-9]+$ ]] || usage
[[ "$commit" =~ ^[0-9a-f]{40}$ && "$archive_sha256" =~ ^[0-9a-f]{64}$ ]] || usage
[[ "$archive" == "/opt/vantaline/incoming/$release.tar.gz" && -f "$archive" && "$apply" -eq 1 ]] || usage
available_kb="$(df -Pk /opt/vantaline | awk 'NR==2 {print $4}')"
[[ "$available_kb" =~ ^[0-9]+$ && "$available_kb" -ge 2097152 ]] || { echo "less than 2 GiB free on /opt/vantaline" >&2; exit 1; }

base=/opt/vantaline; releases="$base/releases"; target="$releases/$release"; current="$base/current"
staged_archive="$base/.staged-$release.tar.gz"
lock="$base/backups/.production-release.lock"
db_url='postgresql:///vantaline?host=/var/run/postgresql&user=vantaline'
previous=""; switched=0; lock_owned=0; service_stopped=0; target_created=0
shared_backgrounds=""; legacy_backgrounds=""
rollback() {
  set +e
  if [[ "$switched" -eq 1 && -n "$previous" ]]; then
    ln -sfn "$previous" "$current.rollback"; mv -Tf "$current.rollback" "$current"
  fi
  if [[ "$service_stopped" -eq 1 && -n "$shared_backgrounds" && -n "$legacy_backgrounds" ]]; then
    # The previous release still uses <repo>/backgrounds.  Repair that path
    # before restarting it.  If a compatibility link cannot be created, move
    # the directory back so rollback remains self-contained.
    if [[ -d "$shared_backgrounds" && ! -L "$shared_backgrounds" && ! -e "$legacy_backgrounds" && ! -L "$legacy_backgrounds" ]]; then
      ln -s "$shared_backgrounds" "$legacy_backgrounds" || mv "$shared_backgrounds" "$legacy_backgrounds"
    fi
    if [[ ! -d "$legacy_backgrounds" ]]; then
      echo "rollback stopped: previous backgrounds path is not accessible" >&2
      return
    fi
  fi
  if [[ "$service_stopped" -eq 1 ]]; then systemctl restart vantaline; fi
}
cleanup() {
  status=$?
  if [[ $status -ne 0 ]]; then
    rollback
    if [[ "$target_created" -eq 1 && "$(readlink -f "$current" 2>/dev/null || true)" != "$target" ]]; then rm -rf --one-file-system "$target"; fi
  fi
  if [[ "$lock_owned" -eq 1 ]]; then rm -f "$lock"; fi
  rm -f "$staged_archive"
  exit $status
}
trap cleanup EXIT INT TERM

sh -c "set -o noclobber; printf '%s\n' '$$' > '$lock'"; lock_owned=1
systemctl is-active --quiet vantaline
[[ "$(systemctl show vantaline -p WorkingDirectory --value)" == "$current" ]]
[[ "$(stat -c '%U:%G' "$archive")" == "vantaline-deploy:vantaline-deploy" ]]
echo "$archive_sha256  $archive" | sha256sum -c -
if [[ -d "$target" ]]; then
  python3 - "$target/VERSION.json" "$release" "$commit" <<'PY'
import json, sys
doc=json.load(open(sys.argv[1],encoding="utf-8"))
assert doc["release"]==sys.argv[2] and doc["git_commit"]==sys.argv[3]
PY
  [[ "$(readlink -f "$current")" == "$target" ]] || { echo "release target exists but is not current" >&2; exit 1; }
  rm -f "$archive"
  echo "release=$release already-installed=true"
  exit 0
fi
preflight="$(sudo -u vantaline psql "$db_url" -tAc "select (select count(*) from vantaline.plc_workstation_leases where state in ('connecting','active','draining') and expires_at >= extract(epoch from clock_timestamp())::bigint)||'|'||(select count(*) from vantaline.plc_web_serial_dispatches where status = 'browser_attempt_declared');")"
[[ "$preflight" == "0|0" ]] || { echo "PLC activity preflight failed: $preflight" >&2; exit 1; }

install -d -o vantaline -g vantaline -m 755 "$target"
target_created=1
install -o vantaline -g vantaline -m 0400 "$archive" "$staged_archive"
sudo -u vantaline python3 - "$staged_archive" "$target" <<'PY'
import pathlib, sys, tarfile
archive, target = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]).resolve()
with tarfile.open(archive, "r:gz") as handle:
    members = handle.getmembers()
    roots = {pathlib.PurePosixPath(m.name).parts[0] for m in members if pathlib.PurePosixPath(m.name).parts}
    if len(roots) != 1: raise SystemExit("release archive must contain exactly one root")
    root = next(iter(roots))
    for member in members:
        parts = pathlib.PurePosixPath(member.name).parts
        if not parts or parts[0] != root or member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise SystemExit(f"unsafe archive member: {member.name}")
        relative = pathlib.Path(*parts[1:]); destination = (target / relative).resolve()
        if destination != target and target not in destination.parents: raise SystemExit(f"archive traversal: {member.name}")
        member.name = relative.as_posix(); handle.extract(member, target)
PY
rm -f "$staged_archive"
(cd "$target" && sha256sum -c SHA256SUMS)
python3 - "$target/VERSION.json" "$release" "$commit" <<'PY'
import json, sys
doc=json.load(open(sys.argv[1],encoding="utf-8"))
assert doc["release"]==sys.argv[2] and doc["git_commit"]==sys.argv[3]
assert doc["backend_protocol"]==doc["frontend_protocol"]=="plc-web-serial-v4"
PY
sudo -u vantaline /opt/vantaline/venv/bin/python "$target/scripts/verify_production_dependencies.py" "$target/requirements-production.lock"
rm -rf "$target/local_inspection_service/data" "$target/models"
ln -s /opt/vantaline/shared/data "$target/local_inspection_service/data"
ln -s /opt/vantaline/shared/models "$target/models"
ln -s /opt/vantaline/venv "$target/.venv"

previous="$(readlink -f "$current")"
service_stopped=1
systemctl stop vantaline

# Background sets used to live at <repo>/backgrounds.  They are mutable runtime
# data and must live under the shared data tree before an immutable release is
# started.  The move is same-filesystem and happens while the service is stopped.
shared_backgrounds="$base/shared/data/backgrounds"
legacy_backgrounds="$previous/backgrounds"
if [[ -d "$shared_backgrounds" && ! -L "$shared_backgrounds" ]]; then
  if [[ -d "$legacy_backgrounds" && ! -L "$legacy_backgrounds" ]]; then
    echo "background directory conflict: both shared and legacy directories exist" >&2
    exit 1
  fi
elif [[ -e "$shared_backgrounds" || -L "$shared_backgrounds" ]]; then
  echo "shared backgrounds must be a real directory" >&2
  exit 1
else
  if [[ -d "$legacy_backgrounds" && ! -L "$legacy_backgrounds" ]]; then
    mv "$legacy_backgrounds" "$shared_backgrounds"
  elif [[ -e "$legacy_backgrounds" || -L "$legacy_backgrounds" ]]; then
    echo "legacy backgrounds has an unexpected type" >&2
    exit 1
  else
    install -d -o vantaline -g vantaline -m 755 "$shared_backgrounds"
  fi
fi
[[ -d "$shared_backgrounds" && ! -L "$shared_backgrounds" ]]
chown vantaline:vantaline "$shared_backgrounds"
sudo -u vantaline test -w "$shared_backgrounds"
# Keep the immediately previous version rollback-safe: its old code still
# resolves <repo>/backgrounds until the new release has passed health checks.
if [[ ! -e "$legacy_backgrounds" ]]; then
  ln -s "$shared_backgrounds" "$legacy_backgrounds"
fi
[[ -L "$legacy_backgrounds" && "$(readlink -f "$legacy_backgrounds")" == "$shared_backgrounds" ]]
for _ in $(seq 1 25); do
  active="$(sudo -u vantaline psql "$db_url" -tAc "select count(*) from vantaline.plc_workstation_leases where state in ('connecting','active','draining') and expires_at >= extract(epoch from clock_timestamp())::bigint;")"
  [[ "$active" == "0" ]] && break; sleep 1
done
final_gate="$(sudo -u vantaline psql "$db_url" -tAc "select (select count(*) from vantaline.plc_workstation_leases where state in ('connecting','active','draining') and expires_at >= extract(epoch from clock_timestamp())::bigint)||'|'||(select count(*) from vantaline.plc_web_serial_dispatches where status = 'browser_attempt_declared');")"
[[ "$final_gate" == "0|0" ]] || { echo "PLC fenced gate failed: $final_gate" >&2; exit 1; }

backup="$base/backups/db-schema-$release.sql"
sudo -u vantaline pg_dump -d vantaline --schema-only --schema=vantaline > "$backup"; chmod 600 "$backup"
sudo -u vantaline psql "$db_url" -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS vantaline.release_migration_checksums (version TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at BIGINT NOT NULL);"
for migration in "$target"/local_inspection_service/storage/migrations/*.sql; do
  [[ -e "$migration" ]] || continue
  version="$(basename "$migration" .sql)"; migration_sha="$(sha256sum "$migration" | awk '{print $1}')"
  [[ "$version" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid migration filename" >&2; exit 1; }
  stored="$(sudo -u vantaline psql "$db_url" -tAc "select sha256 from vantaline.release_migration_checksums where version = '$version';")"
  [[ -z "$stored" || "$stored" == "$migration_sha" ]] || { echo "migration checksum changed: $version" >&2; exit 1; }
  if [[ -z "$stored" ]]; then
    feature_applied="$(sudo -u vantaline psql "$db_url" -tAc "select count(*) from vantaline.feature_migrations where version = '$version';")"
    if [[ "$feature_applied" == "1" ]]; then
      sudo -u vantaline psql "$db_url" -v ON_ERROR_STOP=1 -c "BEGIN; SELECT pg_advisory_xact_lock(1448236621); INSERT INTO vantaline.release_migration_checksums(version,sha256,applied_at) VALUES ('$version','$migration_sha',extract(epoch from now())::bigint); COMMIT;"
      stored="$migration_sha"
    fi
  fi
  if [[ -z "$stored" ]]; then
    combined="$(mktemp)"
    python3 - "$migration" "$combined" "$version" "$migration_sha" <<'PY'
import pathlib, sys
source=pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").strip()
lines=source.splitlines()
if lines[0].strip().upper() != "BEGIN;" or lines[-1].strip().upper() != "COMMIT;": raise SystemExit("migration transaction wrapper missing")
body="\n".join(lines[1:-1])
version=sys.argv[3].replace("'", "''"); digest=sys.argv[4]
pathlib.Path(sys.argv[2]).write_text("BEGIN;\nSELECT pg_advisory_xact_lock(1448236621);\n"+body+f"\nINSERT INTO vantaline.release_migration_checksums(version,sha256,applied_at) VALUES ('{version}','{digest}',extract(epoch from now())::bigint);\nCOMMIT;\n",encoding="utf-8")
PY
    chown vantaline:vantaline "$combined"; chmod 0400 "$combined"
    if ! sudo -u vantaline psql "$db_url" -v ON_ERROR_STOP=1 -f "$combined"; then rm -f "$combined"; exit 1; fi
    rm -f "$combined"
  fi
done

chown -R root:root "$target"; find "$target" -type d -exec chmod go-w {} +; find "$target" -type f -exec chmod go-w {} +
ln -sfn "$target" "$current.new"; mv -Tf "$current.new" "$current"; switched=1
systemctl start vantaline
version_json="$(curl --max-time 5 --retry 45 --retry-delay 1 --retry-all-errors -fsS http://127.0.0.1:8765/api/version)"
printf '%s' "$version_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["consistent"] is True and d["git_commit"]==sys.argv[1]' "$commit"
index="$(curl --max-time 5 -fsS http://127.0.0.1:8765/)"
while read -r asset; do curl --max-time 5 -fsS "http://127.0.0.1:8765$asset" >/dev/null; done < <(printf '%s' "$index" | grep -oE '/static/assets/[^" ]+\.(js|css)' | sort -u)
pid="$(systemctl show vantaline -p MainPID --value)"; ! journalctl _PID="$pid" --no-pager | grep -E 'Traceback|ERROR|CRITICAL'
# The installer is part of the already checksummed release.  Promote it only
# after the new application has passed every health check, so subsequent
# releases cannot keep executing a stale bootstrap copy.
install -o root -g root -m 0755 "$target/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
cmp -s "$target/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
rm -f "$archive"; service_stopped=0; target_created=0
echo "release=$release previous=$previous"

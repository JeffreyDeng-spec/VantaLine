#!/usr/bin/env bash
set -euo pipefail

# Runs the actual installer in a private mount namespace. No host service,
# database, or release directory is used.
if [[ "${1:-}" != --inside ]]; then
  for scenario in active_lock success missing_manifest wrong_commit unknown_service boolean_schema bad_checksum health_failure promote_failure wrong_live_commit legacy_handoff legacy_current_no_downgrade term_before_commit int_after_commit; do
    if [[ "$EUID" -ne 0 ]]; then
      sudo unshare -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    else
      unshare -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    fi
  done
  echo 'PASS embedded release installer bridge fault matrix'
  exit 0
fi
scenario="${2:?scenario required}"
source_root="$(cd "$(dirname "$0")/.." && pwd)"
mount -t tmpfs -o size=3G tmpfs /opt
mount -t tmpfs -o size=16M tmpfs /usr/local/sbin
mount -t tmpfs -o size=16M,mode=0755 tmpfs /var/lib
base=/opt/vantaline
mkdir -p "$base"/{incoming,releases,backups,shared/data,shared/models,testbin,venv/bin}
ln -s "$(command -v python3)" "$base/venv/bin/python"
cat > "$base/testbin/sudo" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == -u ]]; then shift 2; fi
exec "$@"
SH
cat > "$base/testbin/install" <<'SH'
#!/usr/bin/env bash
args=()
while (($#)); do
  case "$1" in
    -o|-g) shift 2 ;;
    *) args+=("$1"); shift ;;
  esac
done
if [[ "${TEST_SIGNAL_POINT:-}" == promote && "${args[*]}" == *'/usr/local/sbin/.vantaline-install-release.'* ]]; then
  kill -INT "$PPID"
fi
if [[ "${TEST_FAIL_PROMOTE:-}" == 1 && "${args[*]}" == *'/usr/local/sbin/.vantaline-install-release.'* ]]; then
  exit 23
fi
exec /usr/bin/install "${args[@]}"
SH
cat > "$base/testbin/stat" <<'SH'
#!/usr/bin/env bash
if [[ "${1:-}" == -c && "${2:-}" == %U:%G ]]; then echo 'vantaline-deploy:vantaline-deploy'; exit 0; fi
if [[ "${1:-}" == -c && "${2:-}" == '%U:%G %a' ]]; then echo 'root:root 755'; exit 0; fi
exec /usr/bin/stat "$@"
SH
cat > "$base/testbin/chown" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$base/testbin/systemctl" <<'SH'
#!/usr/bin/env bash
if [[ "$1" == is-active ]]; then [[ "${3:-}" == vantaline ]] || exit 42
else [[ "${2:-}" == vantaline ]] || exit 42; fi
case "$1" in
  is-active) test -e /opt/vantaline/service-active ;;
  show)
    case "$4" in
      WorkingDirectory) echo /opt/vantaline/current ;;
      MainPID) echo 123 ;;
      *) exit 2 ;;
    esac ;;
  stop) echo stop >> /opt/vantaline/systemctl.log; rm -f /opt/vantaline/service-active
    if [[ "${TEST_SIGNAL_POINT:-}" == stop ]]; then kill -TERM "$PPID"; fi ;;
  start|restart) echo "$1" >> /opt/vantaline/systemctl.log; touch /opt/vantaline/service-active ;;
  *) exit 2 ;;
esac
SH
cat > "$base/testbin/psql" <<'SH'
#!/usr/bin/env bash
query="${*: -1}"
case "$query" in
  *'select (select count(*)'*) echo '0|0' ;;
  *'select count(*)'*) echo '0' ;;
esac
SH
cat > "$base/testbin/pg_dump" <<'SH'
#!/usr/bin/env bash
printf '%s\n' '-- isolated synthetic schema backup'
SH
cat > "$base/testbin/journalctl" <<'SH'
#!/usr/bin/env bash
exit 0
SH
cat > "$base/testbin/curl" <<'SH'
#!/usr/bin/env bash
if [[ "${TEST_FAIL_HEALTH:-}" == 1 && "$(readlink -f /opt/vantaline/current)" == /opt/vantaline/releases/v2026.10.1 ]]; then
  exit 22
fi
case "${*: -1}" in
  */api/version)
    python3 - <<'PY'
import json, pathlib
p = pathlib.Path('/opt/vantaline/current/VERSION.json')
d = json.loads(p.read_text())
print(json.dumps({'consistent': True, 'git_commit': __import__('os').environ.get('TEST_LIVE_COMMIT_OVERRIDE', d['git_commit']), 'release': d['release']}))
PY
    ;;
  */) printf '%s\n' '<html><body>ok</body></html>' ;;
  *) exit 22 ;;
esac
SH
chmod +x "$base/testbin"/*
export PATH="$base/testbin:$PATH"
previous="$base/releases/v2026.09.1"
mkdir -p "$previous/backgrounds"
printf '{"release":"v2026.09.1","git_commit":"%040d"}\n' 0 > "$previous/VERSION.json"
ln -s "$previous" "$base/current"
touch "$base/service-active"
printf '%s\n' old-installer > /usr/local/sbin/vantaline-install-release
work="$base/build/vantaline-v2026.10.1"
mkdir -p "$work/scripts" "$work/local_inspection_service/storage/migrations"
commit="$(printf 'a%.0s' {1..40})"
python3 - "$work/VERSION.json" "$commit" <<'PY'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({'release':'v2026.10.1','git_commit':sys.argv[2],
  'backend_protocol':'plc-web-serial-v4','frontend_protocol':'plc-web-serial-v4'}))
PY
python3 - "$work/RUNTIME_TOPOLOGY.json" "$commit" <<'PY'
import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text(json.dumps({'schema':1,'git_commit':sys.argv[2],
  'worker_mode':'embedded','services':['vantaline']}))
PY
cp "$source_root/scripts/install_release.sh" "$work/scripts/install_release.sh"
printf '#!/usr/bin/env python3\n' > "$work/scripts/verify_production_dependencies.py"
printf '#!/usr/bin/env python3\n' > "$work/scripts/configure_pdf_proxy.py"
case "$scenario" in
  active_lock)
    printf '%s\n' "$$" > "$base/backups/.production-release.lock"
    printf 'in-progress archive\n' > "$base/.staged-v2026.10.1.tar.gz"
    ;;
  missing_manifest) rm "$work/RUNTIME_TOPOLOGY.json" ;;
  unknown_service) python3 - "$work/RUNTIME_TOPOLOGY.json" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); d['services']=['vantaline','vantaline-label-worker']; p.write_text(json.dumps(d))
PY
    ;;
  boolean_schema) python3 - "$work/RUNTIME_TOPOLOGY.json" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); d['schema']=True; p.write_text(json.dumps(d))
PY
    ;;
  wrong_commit) python3 - "$work/RUNTIME_TOPOLOGY.json" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); d['git_commit']='b'*40; p.write_text(json.dumps(d))
PY
    ;;
  health_failure) export TEST_FAIL_HEALTH=1 ;;
  term_before_commit) export TEST_SIGNAL_POINT=stop ;;
  int_after_commit) export TEST_SIGNAL_POINT=promote ;;
  promote_failure) export TEST_FAIL_PROMOTE=1 ;;
esac
(cd "$work" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
if [[ "$scenario" == bad_checksum ]]; then printf x >> "$work/VERSION.json"; fi
archive="$base/incoming/v2026.10.1.tar.gz"
tar -C "$base/build" -czf "$archive" vantaline-v2026.10.1
cp "$archive" "$base/package.tar.gz"
archive_sha="$(sha256sum "$archive" | awk '{print $1}')"
run_installer() {
  bash "$source_root/scripts/install_release.sh" --archive "$archive" --archive-sha256 "$archive_sha" \
    --release v2026.10.1 --commit "$commit" --apply
}
case "$scenario" in
  legacy_current_no_downgrade)
    run_installer
    upgraded_sha="$(sha256sum /usr/local/sbin/vantaline-install-release | awk '{print $1}')"
    ln -sfn "$previous" "$base/current.previous"
    mv -Tf "$base/current.previous" "$base/current"
    (cd "$previous" && sha256sum VERSION.json > SHA256SUMS)
    legacy_archive="$base/incoming/v2026.09.1.tar.gz"
    printf 'legacy retry archive\n' > "$legacy_archive"
    legacy_sha="$(sha256sum "$legacy_archive" | awk '{print $1}')"
    bash /usr/local/sbin/vantaline-install-release --archive "$legacy_archive" \
      --archive-sha256 "$legacy_sha" --release v2026.09.1 \
      --commit "$(printf '0%.0s' {1..40})" --apply
    test "$(sha256sum /usr/local/sbin/vantaline-install-release | awk '{print $1}')" = "$upgraded_sha"
    test "$(grep -c '^stop$' "$base/systemctl.log")" = 1
    ;;
  legacy_handoff)
    test -f "${VANTALINE_BASE_INSTALLER:?baseline installer required}"
    cp "$VANTALINE_BASE_INSTALLER" /usr/local/sbin/vantaline-install-release
    bash /usr/local/sbin/vantaline-install-release --archive "$archive" --archive-sha256 "$archive_sha" \
      --release v2026.10.1 --commit "$commit" --apply
    cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
    second="$base/build/vantaline-v2026.10.2"
    cp -a "$work" "$second"
    second_commit="$(printf "c%.0s" {1..40})"
    python3 - "$second/VERSION.json" "$second/RUNTIME_TOPOLOGY.json" "$second_commit" <<'PY'
import json, pathlib, sys
version, topology, commit = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
a = json.loads(version.read_text()); a['release'] = 'v2026.10.2'; a['git_commit'] = commit
version.write_text(json.dumps(a))
b = json.loads(topology.read_text()); b['git_commit'] = commit
topology.write_text(json.dumps(b))
PY
    (cd "$second" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
    second_archive="$base/incoming/v2026.10.2.tar.gz"
    tar -C "$base/build" -czf "$second_archive" vantaline-v2026.10.2
    second_sha="$(sha256sum "$second_archive" | awk '{print $1}')"
    bash /usr/local/sbin/vantaline-install-release --archive "$second_archive" \
      --archive-sha256 "$second_sha" --release v2026.10.2 --commit "$second_commit" --apply
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.2"
    cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
    test "$(grep -c '^stop$' "$base/systemctl.log")" = 2
    ;;
  success)
    run_installer
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
    cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
    ;;
  active_lock|missing_manifest|wrong_commit|unknown_service|boolean_schema|bad_checksum)
    if run_installer > "$base/result.log" 2>&1; then cat "$base/result.log"; exit 1; fi
    test "$(readlink -f "$base/current")" = "$previous"
    test ! -s "$base/systemctl.log"
    if [[ "$scenario" == active_lock ]]; then test "$(cat "$base/.staged-v2026.10.1.tar.gz")" = "in-progress archive"; fi
    ;;
  term_before_commit)
    set +e
    run_installer > "$base/result.log" 2>&1
    status=$?
    set -e
    test "$status" -eq 143
    test "$(readlink -f "$base/current")" = "$previous"
    test -e "$base/service-active"
    test ! -e "$base/backups/.production-release.lock"
    ;;
  int_after_commit)
    set +e
    run_installer > "$base/result.log" 2>&1
    status=$?
    set -e
    test "$status" -eq 130
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
    test -e "$base/service-active"
    test ! -e "$base/backups/.production-release.lock"
    test "$(cat /usr/local/sbin/vantaline-install-release)" = old-installer
    ;;
  health_failure)
    if run_installer > "$base/result.log" 2>&1; then cat "$base/result.log"; exit 1; fi
    test "$(readlink -f "$base/current")" = "$previous"
    test -e "$base/service-active"
    test "$(cat /usr/local/sbin/vantaline-install-release)" = old-installer
    ;;
  wrong_live_commit)
    run_installer
    cp "$base/package.tar.gz" "$archive"
    export TEST_LIVE_COMMIT_OVERRIDE=wrong
    if run_installer > "$base/result.log" 2>&1; then cat "$base/result.log"; exit 1; fi
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
    test "$(grep -c "^stop$" "$base/systemctl.log")" = 1
    ;;
  promote_failure)
    if run_installer > "$base/result.log" 2>&1; then cat "$base/result.log"; exit 1; fi
    grep -q 'application_committed=true control_promotion=incomplete' "$base/result.log"
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
    test "$(cat /usr/local/sbin/vantaline-install-release)" = old-installer
    cp "$base/package.tar.gz" "$archive"
    if run_installer > "$base/retry-failure.log" 2>&1; then cat "$base/retry-failure.log"; exit 1; fi
    grep -q 'application_committed=true control_promotion=incomplete' "$base/retry-failure.log"
    unset TEST_FAIL_PROMOTE
    cp "$base/package.tar.gz" "$archive"
    run_installer
    cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
    ;;
esac
echo "PASS release installer $scenario"
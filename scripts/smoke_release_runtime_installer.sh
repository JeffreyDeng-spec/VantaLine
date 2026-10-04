#!/usr/bin/env bash
set -euo pipefail

# Runs the actual installer in a private mount namespace. No host service,
# database, or release directory is used.
if [[ "${1:-}" != --inside ]]; then
  for scenario in managed_legacy_queued_rollback managed_interrupt_rollback managed_journal_failure managed_interrupt_stopped managed_interrupt_switched managed_embedded_bridge managed_success managed_worker_failure managed_health_failure managed_database_failure managed_interrupted_accept managed_pointer_checkpoint managed_paused_rollback managed_embedded_510 managed_embedded_510_rollback managed_reject_web_499 managed_reject_web_511 managed_reject_worker_510 managed_reject_kill_mode; do
    if [[ "$EUID" -ne 0 ]]; then
      sudo unshare -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    else
      unshare -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    fi
  done
  echo 'PASS managed release installer fault matrix'
  exit 0
fi
scenario="${2:?scenario required}"
source_root="$(cd "$(dirname "$0")/.." && pwd)"
mount -t tmpfs -o size=3G tmpfs /opt
mount -t tmpfs -o size=16M tmpfs /usr/local/sbin
mount -t tmpfs -o size=16M,mode=0755 tmpfs /var/lib
base=/opt/vantaline
mkdir -p "$base"/{incoming,releases,backups,shared/data,shared/models,testbin,venv/bin}
# Configuration publication is confined to the same private namespace.
mkdir -p "$base/test-etc"
cp /etc/passwd /etc/group /etc/nsswitch.conf "$base/test-etc/"
cp -R -P --preserve=mode,timestamps /etc/alternatives "$base/test-etc/"
mount -t tmpfs -o size=16M,mode=0755 tmpfs /etc
cp -R -P --preserve=mode,timestamps "$base/test-etc/"* /etc/
mkdir -p /etc/systemd/system /etc/vantaline
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
if [[ "$TEST_RUNTIME_SCENARIO" == managed_journal_failure && "$(readlink -f /opt/vantaline/current)" == /opt/vantaline/releases/v2026.10.1 ]]; then
  printf '%s\n' 'ERROR synthetic-customer-secret'
fi
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

# The private passwd bind exposes a synthetic service uid in this user namespace.
cp /etc/passwd "$base/test-passwd"
printf 'vantaline:x:0:0:synthetic runtime:/nonexistent:/usr/sbin/nologin\n' >> "$base/test-passwd"
mount --bind "$base/test-passwd" /etc/passwd
mkdir -p "$base/shared/data/runtime-control"
export TEST_RUNTIME_SCENARIO="$scenario"
python3 - "$source_root" "$base/snapshot.json" <<'PY'
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
from local_inspection_service.runtime.configuration import ConfigurationSnapshot
snapshot = ConfigurationSnapshot.capture({'VANTALINE_DATA_STORE':'postgres', 'DATABASE_URL':'synthetic'}, pathlib.Path('/opt/vantaline/shared/data'))
pathlib.Path(sys.argv[2]).write_text(json.dumps(snapshot.export()))
PY
cat > "$base/mock-runtime.py" <<'PY'
import json, os, pathlib, signal, socket, struct, sys, time, uuid
base=pathlib.Path('/opt/vantaline'); service=sys.argv[1]
topology=json.loads((base/'current/RUNTIME_TOPOLOGY.json').read_text())
version=json.loads((base/'current/VERSION.json').read_text())
snapshot=json.loads((base/'snapshot.json').read_text())
path=base/'shared/data/runtime-control'/('web-control.sock' if service=='vantaline' else 'label-control.sock')
path.unlink(missing_ok=True)
listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); listener.bind(str(path)); path.chmod(0o600); listener.listen()
maintenance=base/'maintenance'
if topology['schema']==1: maintenance.unlink(missing_ok=True)  # Legacy runtime has no gate.
if version['release']=='v2026.10.1': maintenance.touch()
state='drained' if maintenance.exists() else 'ready'
revision='0'*32; instance=uuid.uuid4().hex
signal.signal(signal.SIGTERM,lambda *_: sys.exit(0))
try:
    while True:
        connection,_=listener.accept()
        with connection:
            connection.settimeout(2)
            peer=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if peer[1]!=0: continue
            raw=bytearray()
            while not raw.endswith(b'\n'):
                part=connection.recv(1024)
                if not part or len(raw)>4096: break
                raw.extend(part)
            request=json.loads(raw)
            if os.environ['TEST_RUNTIME_SCENARIO']=='managed_database_failure':
                connection.sendall(b'{"error":"database_unavailable"}\n'); continue
            command=request['command']
            with (base/'control-events').open('a') as log: log.write(version['release']+' '+command+'\n')
            if command!='status': revision=request['revision']
            if command=='close_admission': maintenance.touch()
            if command=='open_admission': maintenance.unlink(missing_ok=True)
            if (os.environ['TEST_RUNTIME_SCENARIO']=='managed_interrupt_rollback'
                    and version['release']=='v2026.09.1' and command=='open_admission'):
                marker=base/'interrupted-once'
                if not marker.exists():
                    marker.write_text(str(os.getpid()))
                    installer_pid=int((pathlib.Path('/proc')/str(peer[0])/'stat').read_text().split(') ')[1].split()[1])
                    os.kill(peer[0],signal.SIGKILL)
                    os.kill(installer_pid,signal.SIGKILL)
                    continue
                assert int(marker.read_text())==os.getpid(), 'rollback retry replaced the restored process'
            if command=='pause': state='drained'
            if command=='resume': state='ready'
            response={'schema':1,'git_commit':version['git_commit'],'release':version['release'],
                'role':'web' if service=='vantaline' else 'label','worker_mode':topology['worker_mode'],
                'instance':instance,'pid':os.getpid(),'heartbeat':time.monotonic(),'state':state,
                'control_revision':revision,'active_iterations':0,'queued_runs':int((base/'queued').read_text()) if (base/'queued').exists() else 0,'active_runs':0,
                'maintenance':maintenance.exists(),'config_revision':snapshot['revision']}
            if command=='configuration': response={'state':response,'snapshot':snapshot}
            connection.sendall(json.dumps(response).encode()+b'\n')
finally:
    listener.close(); path.unlink(missing_ok=True)
PY
cat > "$base/testbin/systemctl" <<'PY'
#!/usr/bin/python3
import json, os, pathlib, signal, subprocess, sys, time
base=pathlib.Path('/opt/vantaline'); args=sys.argv[1:]; command=args.pop(0)
services=['vantaline','vantaline-label-worker']
def pid(service):
    path=base/(service+'.pid')
    if not path.exists(): return 0
    number=int(path.read_text())
    try:
        status=pathlib.Path('/proc')/str(number)/'stat'
        if status.read_text().split(') ')[1].startswith('Z'): return 0
        os.kill(number,0); return number
    except (ProcessLookupError,FileNotFoundError): return 0
def event(*values):
    with (base/'runtime-events').open('a') as handle: handle.write(' '.join(values)+'\n')
if command=='daemon-reload': sys.exit(0)
if command=='is-active': sys.exit(0 if pid(args[-1]) else 3)
if command=='show':
    service=args[0]; field=args[2]; assert service in services
    values={'WorkingDirectory':str(base/'current'),'MainPID':str(pid(service)),'ControlPID':'0',
        'ActiveState':'active' if pid(service) else 'inactive',
        'LoadState':'loaded' if service=='vantaline' or pathlib.Path('/etc/systemd/system/vantaline-label-worker.service').exists() else 'not-found',
        'TimeoutStopUSec':'8min 20s','KillMode':'control-group'}
    # Read private synthetic administrator drop-ins in effective lexical order.
    for dropin in sorted((pathlib.Path('/etc/systemd/system')/(service+'.service.d')).glob('*.conf')):
        for line in dropin.read_text().splitlines():
            if line.startswith('TimeoutStopSec='): values['TimeoutStopUSec']=line.split('=',1)[1]+'s'
            if line.startswith('KillMode='): values['KillMode']=line.split('=',1)[1]
    print(values[field]); sys.exit(0)
if command=='is-enabled':
    print('enabled' if (base/'worker-enabled').exists() else 'disabled'); sys.exit(0)
if command in ('enable','disable'):
    assert args==['vantaline-label-worker']
    if command=='enable': (base/'worker-enabled').touch()
    else: (base/'worker-enabled').unlink(missing_ok=True)
    sys.exit(0)
if command=='stop':
    if (os.environ['TEST_RUNTIME_SCENARIO']=='managed_interrupt_rollback'
            and (base/'interrupted-once').exists() and (base/'current').resolve().name=='v2026.09.1'):
        journal=json.loads((pathlib.Path('/var/lib/vantaline-release/.runtime-transition-v2026.10.1.json')).read_text())
        if journal['phase'] in ('rolling_back','rollback_starting','rollback_verified','rolled_back'):
            (base/'unsafe-rollback-stop').touch()
            raise SystemExit(99)
    for service in [item for item in args if item!='--no-block']:
        assert service in services; event('stop',service)
        number=pid(service)
        if number: os.kill(number,signal.SIGTERM)
    sys.exit(0)
if command in ('start','restart'):
    service=args[0]; assert service in services
    if pid(service): sys.exit(0)
    event('start',service)
    if service=='vantaline-label-worker' and os.environ['TEST_RUNTIME_SCENARIO']=='managed_worker_failure': sys.exit(23)
    process=subprocess.Popen(['/usr/bin/python3',str(base/'mock-runtime.py'),service],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    (base/(service+'.pid')).write_text(str(process.pid))
    path=base/'shared/data/runtime-control'/('web-control.sock' if service=='vantaline' else 'label-control.sock')
    for _ in range(50):
        if path.exists(): break
        time.sleep(.02)
    sys.exit(0)
raise SystemExit(2)
PY
cat > "$base/testbin/mv" <<'SH_CHECKPOINT'
#!/usr/bin/env bash
/usr/bin/mv "$@"
if [[ "$TEST_RUNTIME_SCENARIO" == managed_interrupt_switched && "${*: -1}" == /opt/vantaline/current && ! -e /opt/vantaline/interrupted-once ]]; then
  touch /opt/vantaline/interrupted-once
  kill -KILL "$PPID"
fi
SH_CHECKPOINT
cat > "$base/testbin/pg_dump" <<'SH_CHECKPOINT'
#!/usr/bin/env bash
if [[ "$TEST_RUNTIME_SCENARIO" == managed_interrupt_stopped && ! -e /opt/vantaline/interrupted-once ]]; then
  touch /opt/vantaline/interrupted-once
  kill -KILL "$PPID"
fi
printf '%s\n' '-- isolated synthetic schema backup'
SH_CHECKPOINT
chmod +x "$base/testbin/systemctl" "$base/testbin/mv" "$base/testbin/pg_dump"
cleanup_runtime() {
  python3 - <<'PY'
import os,pathlib,signal
base=pathlib.Path('/opt/vantaline')
for path in base.glob('*.pid'):
    try:
        pid=int(path.read_text()); command=(pathlib.Path('/proc')/str(pid)/'cmdline').read_bytes()
        if b'/opt/vantaline/mock-runtime.py' in command: os.kill(pid,signal.SIGTERM)
    except (FileNotFoundError,ProcessLookupError): pass
PY
}
trap cleanup_runtime EXIT
python3 - "$previous" "$work" <<'PY'
import json,pathlib,sys,os
for directory,mode in ((pathlib.Path(sys.argv[1]),'embedded'),(pathlib.Path(sys.argv[2]),'external')):
    version=json.loads((directory/'VERSION.json').read_text())
    legacy=os.environ['TEST_RUNTIME_SCENARIO'] in ('managed_embedded_bridge', 'managed_legacy_queued_rollback', 'managed_root_journal_handoff', 'managed_root_journal_promotion_failure', 'managed_root_budget_handoff')
    if legacy or os.environ['TEST_RUNTIME_SCENARIO'].startswith('managed_embedded_510'): mode='embedded'
    doc={'schema':1 if legacy and directory==pathlib.Path(sys.argv[1]) else 2,'git_commit':version['git_commit'],
        'worker_mode':mode,'services':['vantaline']+(['vantaline-label-worker'] if mode=='external' else [])}
    if doc['schema']==2: doc['runtime_protocol']=1
    (directory/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(doc))
PY
if [[ "$scenario" == managed_paused_rollback ]]; then touch "$base/maintenance"; fi
if [[ "$scenario" == managed_paused_rollback || "$scenario" == managed_legacy_queued_rollback ]]; then printf 3 > "$base/queued"; fi
cat > "$work/scripts/configure_pdf_proxy.py" <<'PY_CHECKPOINT'
import json, os, pathlib, signal
base=pathlib.Path('/opt/vantaline'); scenario=os.environ['TEST_RUNTIME_SCENARIO']
if scenario=='managed_interrupted_accept' and not (base/'interrupted-once').exists():
    (base/'interrupted-once').touch()
    os.kill(os.getppid(),signal.SIGKILL)
elif scenario=='managed_pointer_checkpoint':
    journal=json.loads((pathlib.Path('/var/lib/vantaline-release/.runtime-transition-v2026.10.1.json')).read_text())
    (base/('current.runtime-rollback.'+journal['revision'])).symlink_to(journal['old']['directory'])
    raise SystemExit(23)
elif scenario in ('managed_paused_rollback', 'managed_legacy_queued_rollback'):
    raise SystemExit(23)
elif scenario=='managed_interrupt_rollback' and not (base/'interrupted-once').exists():
    raise SystemExit(23)
PY_CHECKPOINT
systemctl start vantaline
if [[ "$scenario" == managed_root_journal_handoff || "$scenario" == managed_root_journal_promotion_failure || "$scenario" == managed_root_budget_handoff ]]; then
  # Reproduce the observed application-owned layout using real ownership.
  # This case runs as root inside private mount namespaces, never on host paths.
  /usr/bin/chown 998:998 "$base" "$base/backups"
  test "$(/usr/bin/stat -c '%u %g %a' "$base/backups")" = '998 998 755'
  expected_predecessor=6e061881db09466198f3c42397d1b61f89a8d374c2fce5e2a6d7725f38c06515
  if [[ "$scenario" == managed_root_budget_handoff ]]; then expected_predecessor=748695bec0eaa2f56e5bc45d0d7b7f8a0d92affb4d6db8f218518979e2a38a1e; fi
  test "$(sha256sum "${VANTALINE_BASE_INSTALLER:?}" | awk '{print $1}')" = "$expected_predecessor"
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    bridge_admin=/etc/systemd/system/vantaline.service.d/90-administrator.conf
    mkdir -p "$(dirname "$bridge_admin")"
    printf '[Service]\nTimeoutStopSec=510\nKillMode=control-group\n' > "$bridge_admin"
    chmod 640 "$bridge_admin"
    bridge_admin_digest="$(sha256sum "$bridge_admin")"
  fi
  cp "$VANTALINE_BASE_INSTALLER" /usr/local/sbin/vantaline-install-release
  bridge="$base/build/vantaline-v2026.10.0"
  cp -a "$work" "$bridge"
  python3 - "$bridge" <<'PY_BRIDGE'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1]);version=json.loads((root/'VERSION.json').read_text())
version.update(release='v2026.10.0',git_commit='b'*40)
(root/'VERSION.json').write_text(json.dumps(version))
(root/'RUNTIME_TOPOLOGY.json').write_text(json.dumps({'schema':1,'git_commit':'b'*40,'worker_mode':'embedded','services':['vantaline']}))
PY_BRIDGE
  (cd "$bridge" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
  bridge_archive="$base/incoming/v2026.10.0.tar.gz"
  tar -C "$base/build" -czf "$bridge_archive" vantaline-v2026.10.0
  cp "$bridge_archive" "$base/bridge-package.tar.gz"
  bridge_sha="$(sha256sum "$bridge_archive" | awk '{print $1}')"
  bridge_release=v2026.10.0
  bridge_commit="$(printf 'b%.0s' {1..40})"
  if [[ "$scenario" == managed_root_journal_promotion_failure ]]; then
    if TEST_FAIL_PROMOTE=1 bash /usr/local/sbin/vantaline-install-release --archive "$bridge_archive" --archive-sha256 "$bridge_sha" \
      --release "$bridge_release" --commit "$bridge_commit" --apply > "$base/promotion-failed.log" 2>&1; then exit 1; fi
    grep -q 'application_committed=true control_promotion=incomplete' "$base/promotion-failed.log"
    cmp "$VANTALINE_BASE_INSTALLER" /usr/local/sbin/vantaline-install-release
    test "$(readlink -f "$base/current")" = "$base/releases/$bridge_release"
    committed_pid="$(cat "$base/vantaline.pid")"
    # Prove old A cannot safely retry this identity on the observed UID998 layout.
    cp "$base/bridge-package.tar.gz" "$bridge_archive"
    if bash /usr/local/sbin/vantaline-install-release --archive "$bridge_archive" --archive-sha256 "$bridge_sha" \
      --release "$bridge_release" --commit "$bridge_commit" --apply > "$base/old-retry.log" 2>&1; then exit 1; fi
    grep -q 'Runtime transition failed; retained recovery evidence requires inspection' "$base/old-retry.log"
    test "$(cat "$base/vantaline.pid")" = "$committed_pid"
    cmp "$VANTALINE_BASE_INSTALLER" /usr/local/sbin/vantaline-install-release
    # Recovery is a different complete schema-1 release, never a file/permission fix.
    bridge_release=v2026.10.2
    bridge_commit="$(printf 'c%.0s' {1..40})"
    next_bridge="$base/build/vantaline-$bridge_release"
    cp -a "$bridge" "$next_bridge"
    bridge="$next_bridge"
    python3 - "$bridge" "$bridge_release" "$bridge_commit" <<'PY_FRESH_BRIDGE'
import json,pathlib,sys
root=pathlib.Path(sys.argv[1])
for name in ('VERSION.json','RUNTIME_TOPOLOGY.json'):
    data=json.loads((root/name).read_text());data['git_commit']=sys.argv[3]
    if name=='VERSION.json': data['release']=sys.argv[2]
    (root/name).write_text(json.dumps(data))
PY_FRESH_BRIDGE
    (cd "$bridge" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
    bridge_archive="$base/incoming/$bridge_release.tar.gz"
    tar -C "$base/build" -czf "$bridge_archive" "vantaline-$bridge_release"
    cp "$bridge_archive" "$base/bridge-package.tar.gz"
    bridge_sha="$(sha256sum "$bridge_archive" | awk '{print $1}')"
  fi
  bash /usr/local/sbin/vantaline-install-release --archive "$bridge_archive" --archive-sha256 "$bridge_sha" \
    --release "$bridge_release" --commit "$bridge_commit" --apply
  cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    test "$(sha256sum "$bridge_admin")" = "$bridge_admin_digest"
    test "$(stat -c '%a' "$bridge_admin")" = 640
  fi
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    test "$(/usr/bin/stat -c '%u %a' /var/lib/vantaline-release)" = '0 700'
  else
    test ! -e /var/lib/vantaline-release
  fi
  # Capabilities must not create recovery storage even after successful promotion.
  bash /usr/local/sbin/vantaline-install-release --capabilities >/dev/null
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    test "$(/usr/bin/stat -c '%u %a' /var/lib/vantaline-release)" = '0 700'
  else
    test ! -e /var/lib/vantaline-release
  fi
  previous="$base/releases/$bridge_release"
  test "$(readlink -f "$base/current")" = "$previous"
  old_pid="$(cat "$base/vantaline.pid")"
  cp "$base/bridge-package.tar.gz" "$bridge_archive"
  bash /usr/local/sbin/vantaline-install-release --archive "$bridge_archive" --archive-sha256 "$bridge_sha" \
    --release "$bridge_release" --commit "$bridge_commit" --apply
  test "$(cat "$base/vantaline.pid")" = "$old_pid"
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    test "$(sha256sum "$bridge_admin")" = "$bridge_admin_digest"
    test "$(stat -c '%a' "$bridge_admin")" = 640
  fi
  test "$(/usr/bin/stat -c '%u %a' /var/lib/vantaline-release)" = '0 700'
  test "$(/usr/bin/stat -c '%u %g %a' "$base")" = '998 998 755'
  test "$(/usr/bin/stat -c '%u %g %a' "$base/backups")" = '998 998 755'
fi
: > "$base/runtime-events"
(cd "$work" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
archive="$base/incoming/v2026.10.1.tar.gz"
tar -C "$base/build" -czf "$archive" vantaline-v2026.10.1
archive_sha="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$scenario" == managed_root_journal_handoff ]]; then
  stable_pid="$(cat "$base/vantaline.pid")"
  storage=/var/lib/vantaline-release
  for storage_fault in old_regular old_dangling other_pending current_dangling current_directory current_fifo current_invalid current_owner root_owner root_mode root_symlink ancestor_mode; do
    probe="$storage/.runtime-transition-v2026.10.1.json"
    case "$storage_fault" in
      old_regular) probe="$base/backups/.runtime-transition-v2026.09.2.json"; printf '{}' > "$probe"; chmod 600 "$probe" ;;
      old_dangling) probe="$base/backups/.runtime-transition-v2026.09.2.json"; ln -s /nonexistent "$probe" ;;
      other_pending) probe="$storage/.runtime-transition-v2026.09.2.json"; printf '{}' > "$probe"; chmod 600 "$probe" ;;
      current_dangling) ln -s /nonexistent "$probe" ;;
      current_directory) mkdir "$probe" ;;
      current_fifo) mkfifo "$probe" ;;
      current_invalid) printf 'invalid' > "$probe"; chmod 600 "$probe" ;;
      current_owner) printf '{}' > "$probe"; chmod 600 "$probe"; /usr/bin/chown 998:998 "$probe" ;;
      root_owner) probe="$storage"; /usr/bin/chown 998:998 "$storage" ;;
      root_mode) probe="$storage"; chmod 777 "$storage" ;;
      root_symlink) mv "$storage" "$storage.saved"; ln -s "$storage.saved" "$storage"; probe="$storage" ;;
      ancestor_mode) probe=/var/lib; chmod 777 /var/lib ;;
    esac
    before="$(/usr/bin/stat -c '%F %u %g %a %s' "$probe")"
    if bash /usr/local/sbin/vantaline-install-release --archive "$archive" --archive-sha256 "$archive_sha" \
      --release v2026.10.1 --commit "$commit" --apply > "$base/storage-fault.log" 2>&1; then cat "$base/storage-fault.log"; exit 1; fi
    test "$(/usr/bin/stat -c '%F %u %g %a %s' "$probe")" = "$before"
    test "$(cat "$base/vantaline.pid")" = "$stable_pid"
    test "$(readlink -f "$base/current")" = "$previous"
    test ! -e "$base/releases/v2026.10.1"
    test ! -s "$base/runtime-events"
    case "$storage_fault" in
      root_owner) /usr/bin/chown 0:0 "$storage" ;;
      root_mode) chmod 700 "$storage" ;;
      root_symlink) rm "$storage"; mv "$storage.saved" "$storage" ;;
      ancestor_mode) chmod 755 /var/lib ;;
      current_directory) rmdir "$probe" ;;
      *) rm "$probe" ;;
    esac
    echo "PASS recovery storage rejects $storage_fault without stop or repair"
  done
fi
admin_file=""
case "$scenario" in
  managed_root_budget_handoff|managed_embedded_510|managed_embedded_510_rollback|managed_reject_web_499|managed_reject_web_511|managed_reject_kill_mode)
    admin_file=/etc/systemd/system/vantaline.service.d/90-administrator.conf
    seconds=510; kill_mode=control-group
    if [[ "$scenario" == managed_reject_web_499 ]]; then seconds=499; fi
    if [[ "$scenario" == managed_reject_web_511 ]]; then seconds=511; fi
    if [[ "$scenario" == managed_reject_kill_mode ]]; then kill_mode=process; fi
    ;;
  managed_reject_worker_510)
    admin_file=/etc/systemd/system/vantaline-label-worker.service.d/90-administrator.conf
    seconds=510; kill_mode=control-group
    ;;
esac
if [[ -n "$admin_file" ]]; then
  if [[ "$scenario" == managed_root_budget_handoff ]]; then
    test "$(sha256sum "$admin_file")" = "$bridge_admin_digest"
    test "$(stat -c '%a' "$admin_file")" = 640
  else
    mkdir -p "$(dirname "$admin_file")"
    printf '[Service]\nTimeoutStopSec=%s\nKillMode=%s\n' "$seconds" "$kill_mode" > "$admin_file"
    chmod 640 "$admin_file"
  fi
  admin_digest="$(sha256sum "$admin_file")"
  before_pid="$(cat "$base/vantaline.pid")"
fi
if [[ "$scenario" == managed_health_failure || "$scenario" == managed_embedded_510_rollback ]]; then export TEST_FAIL_HEALTH=1; fi
set +e
bash "$source_root/scripts/install_release.sh" --archive "$archive" --archive-sha256 "$archive_sha" \
  --release v2026.10.1 --commit "$commit" --apply > "$base/result.log" 2>&1
result=$?
set -e
if [[ "$scenario" == managed_interrupt_rollback ]]; then
  test "$result" -eq 137
  test ! -e "$base/maintenance"
  test "$(readlink -f "$base/current")" = "$previous"
  test "$(cat "$base/interrupted-once")" = "$(cat "$base/vantaline.pid")"
  python3 - "/var/lib/vantaline-release/.runtime-transition-v2026.10.1.json" <<'PY_ROLLBACK_CHECKPOINT'
import json,sys
assert json.load(open(sys.argv[1]))['phase']=='rollback_verified'
PY_ROLLBACK_CHECKPOINT
  bash "$source_root/scripts/install_release.sh" --archive "$archive" --archive-sha256 "$archive_sha" \
    --release v2026.10.1 --commit "$commit" --apply > "$base/recovery.log" 2>&1 || { cat "$base/recovery.log"; exit 1; }
  test ! -e "$base/unsafe-rollback-stop"
  result=0
fi
if [[ "$scenario" == managed_interrupted_accept || "$scenario" == managed_interrupt_stopped || "$scenario" == managed_interrupt_switched ]]; then
  test "$result" -eq 137
  test -e "$base/maintenance"
  test -e "/var/lib/vantaline-release/.runtime-transition-v2026.10.1.json"
  if [[ "$scenario" == managed_interrupt_stopped ]]; then
    test "$(readlink -f "$base/current")" = "$previous"
  else
    test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
  fi
  if [[ "$scenario" != managed_interrupted_accept ]]; then
    if systemctl is-active --quiet vantaline; then exit 1; fi
  fi
  bash "$source_root/scripts/install_release.sh" --archive "$archive" --archive-sha256 "$archive_sha" \
    --release v2026.10.1 --commit "$commit" --apply > "$base/recovery.log" 2>&1 || { cat "$base/recovery.log"; exit 1; }
  result=0
fi
if [[ "$scenario" == managed_embedded_510 || "$scenario" == managed_interrupt_rollback || "$scenario" == managed_success || "$scenario" == managed_interrupted_accept || "$scenario" == managed_embedded_bridge || "$scenario" == managed_root_journal_handoff || "$scenario" == managed_root_journal_promotion_failure || "$scenario" == managed_root_budget_handoff || "$scenario" == managed_interrupt_stopped || "$scenario" == managed_interrupt_switched ]]; then
  if [[ "$result" != 0 ]]; then cat "$base/result.log"; exit 1; fi
  test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
  systemctl is-active --quiet vantaline
  if [[ "$scenario" == managed_root_budget_handoff || "$scenario" == managed_embedded_510 || "$scenario" == managed_embedded_bridge || "$scenario" == managed_root_journal_handoff || "$scenario" == managed_root_journal_promotion_failure ]]; then
    if systemctl is-active --quiet vantaline-label-worker; then exit 1; fi
    test ! -e /etc/systemd/system/vantaline-label-worker.service
    test ! -e "$base/worker-enabled"
  else
    systemctl is-active --quiet vantaline-label-worker
    test -f /etc/systemd/system/vantaline-label-worker.service
    test -e "$base/worker-enabled"
  fi
  test ! -e "$base/maintenance"
  cmp "$source_root/scripts/install_release.sh" /usr/local/sbin/vantaline-install-release
else
  if [[ "$result" == 0 ]]; then cat "$base/result.log"; exit 1; fi
  test "$(readlink -f "$base/current")" = "$previous"
  systemctl is-active --quiet vantaline
  if systemctl is-active --quiet vantaline-label-worker; then exit 1; fi
  if [[ "$scenario" == managed_paused_rollback ]]; then
    test -e "$base/maintenance"
    python3 - "$source_root/scripts" <<'PY_PAUSED'
import pathlib,sys
sys.path.insert(0,sys.argv[1])
from release_runtime_client import request
pid=int(pathlib.Path('/opt/vantaline/vantaline.pid').read_text())
state=request('vantaline','status','f'*32,uid=0,pid=pid)
assert state['state']=='drained' and state['maintenance'] is True
PY_PAUSED
  else
    test ! -e "$base/maintenance"
  fi
  test ! -e /etc/systemd/system/vantaline-label-worker.service
  test ! -e "$base/worker-enabled"
  if [[ "$scenario" == managed_database_failure ]]; then test ! -s "$base/runtime-events"; fi
fi
if [[ -n "$admin_file" ]]; then
  test "$(sha256sum "$admin_file")" = "$admin_digest"
  test "$(stat -c '%a' "$admin_file")" = 640
  if [[ "$scenario" == managed_reject_* ]]; then
    test "$(cat "$base/vantaline.pid")" = "$before_pid"
    if grep -Eq '^(stop|start) ' "$base/runtime-events"; then exit 1; fi
    test ! -e /etc/systemd/system/vantaline.service.d/70-label-runtime.conf
  fi
  if [[ "$scenario" == managed_embedded_510_rollback ]]; then
    test ! -e /etc/systemd/system/vantaline.service.d/70-label-runtime.conf
  fi
fi
if [[ "$scenario" == managed_journal_failure ]]; then
  if grep -q synthetic-customer-secret "$base/result.log"; then exit 1; fi
fi
if [[ "$scenario" == managed_paused_rollback || "$scenario" == managed_legacy_queued_rollback ]]; then
  test "$(cat "$base/queued")" -eq 3
  if grep -q '^v2026.10.1 resume$' "$base/control-events"; then exit 1; fi
fi
if [[ "$scenario" == managed_root_journal_handoff || "$scenario" == managed_root_journal_promotion_failure || "$scenario" == managed_root_budget_handoff ]]; then
  test "$(/usr/bin/stat -c '%u %g %a' "$base")" = '998 998 755'
  test "$(/usr/bin/stat -c '%u %g %a' "$base/backups")" = '998 998 755'
fi
test ! -e "/var/lib/vantaline-release/.runtime-transition-v2026.10.1.json"
test ! -e "$base/backups/.production-release.lock"
echo "PASS release runtime installer $scenario"

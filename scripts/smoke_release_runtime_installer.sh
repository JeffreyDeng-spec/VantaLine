#!/usr/bin/env bash
set -euo pipefail

# Runs the actual installer in a private mount namespace. No host service,
# database, or release directory is used.
if [[ "${1:-}" != --inside ]]; then
  for scenario in managed_interrupt_rollback managed_journal_failure managed_interrupt_stopped managed_interrupt_switched managed_embedded_bridge managed_success managed_worker_failure managed_health_failure managed_database_failure managed_interrupted_accept managed_pointer_checkpoint managed_paused_rollback; do
    if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
      sudo unshare -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    else
      unshare -Ur -m --propagation private env VANTALINE_BASE_INSTALLER="${VANTALINE_BASE_INSTALLER:?}" bash "$0" --inside "$scenario"
    fi
  done
  echo 'PASS managed release installer fault matrix'
  exit 0
fi
scenario="${2:?scenario required}"
source_root="$(cd "$(dirname "$0")/.." && pwd)"
mount -t tmpfs -o size=3G tmpfs /opt
mount -t tmpfs -o size=16M tmpfs /usr/local/sbin
mount -t tmpfs -o size=16M tmpfs /etc/systemd/system
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
cat > "$base/mock-runtime.py" <<'PY'
import json, os, pathlib, signal, socket, struct, sys, time, uuid
base=pathlib.Path('/opt/vantaline'); service=sys.argv[1]
topology=json.loads((base/'current/RUNTIME_TOPOLOGY.json').read_text())
version=json.loads((base/'current/VERSION.json').read_text())
path=base/'shared/data/runtime-control'/('web-control.sock' if service=='vantaline' else 'label-control.sock')
path.unlink(missing_ok=True)
listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); listener.bind(str(path)); path.chmod(0o600); listener.listen()
maintenance=base/'maintenance'
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
                'control_revision':revision,'active_iterations':0,'queued_runs':0,'active_runs':0,
                'maintenance':maintenance.exists(),'config_revision':'e'*64}
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
        journal=json.loads((base/'backups/.runtime-transition-v2026.10.1.json').read_text())
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
    legacy=os.environ['TEST_RUNTIME_SCENARIO']=='managed_embedded_bridge'
    if legacy: mode='embedded'
    doc={'schema':1 if legacy and directory==pathlib.Path(sys.argv[1]) else 2,'git_commit':version['git_commit'],
        'worker_mode':mode,'services':['vantaline']+(['vantaline-label-worker'] if mode=='external' else [])}
    if doc['schema']==2: doc['runtime_protocol']=1
    (directory/'RUNTIME_TOPOLOGY.json').write_text(json.dumps(doc))
PY
if [[ "$scenario" == managed_paused_rollback ]]; then touch "$base/maintenance"; fi
cat > "$work/scripts/configure_pdf_proxy.py" <<'PY_CHECKPOINT'
import json, os, pathlib, signal
base=pathlib.Path('/opt/vantaline'); scenario=os.environ['TEST_RUNTIME_SCENARIO']
if scenario=='managed_interrupted_accept' and not (base/'interrupted-once').exists():
    (base/'interrupted-once').touch()
    os.kill(os.getppid(),signal.SIGKILL)
elif scenario=='managed_pointer_checkpoint':
    journal=json.loads((base/'backups/.runtime-transition-v2026.10.1.json').read_text())
    (base/('current.runtime-rollback.'+journal['revision'])).symlink_to(journal['old']['directory'])
    raise SystemExit(23)
elif scenario=='managed_paused_rollback':
    raise SystemExit(23)
elif scenario=='managed_interrupt_rollback' and not (base/'interrupted-once').exists():
    raise SystemExit(23)
PY_CHECKPOINT
systemctl start vantaline
: > "$base/runtime-events"
(cd "$work" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
archive="$base/incoming/v2026.10.1.tar.gz"
tar -C "$base/build" -czf "$archive" vantaline-v2026.10.1
archive_sha="$(sha256sum "$archive" | awk '{print $1}')"
if [[ "$scenario" == managed_health_failure ]]; then export TEST_FAIL_HEALTH=1; fi
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
  python3 - "$base/backups/.runtime-transition-v2026.10.1.json" <<'PY_ROLLBACK_CHECKPOINT'
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
  test -e "$base/backups/.runtime-transition-v2026.10.1.json"
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
if [[ "$scenario" == managed_interrupt_rollback || "$scenario" == managed_success || "$scenario" == managed_interrupted_accept || "$scenario" == managed_embedded_bridge || "$scenario" == managed_interrupt_stopped || "$scenario" == managed_interrupt_switched ]]; then
  if [[ "$result" != 0 ]]; then cat "$base/result.log"; exit 1; fi
  test "$(readlink -f "$base/current")" = "$base/releases/v2026.10.1"
  systemctl is-active --quiet vantaline
  if [[ "$scenario" == managed_embedded_bridge ]]; then
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
if [[ "$scenario" == managed_journal_failure ]]; then
  if grep -q synthetic-customer-secret "$base/result.log"; then exit 1; fi
fi
test ! -e "$base/backups/.runtime-transition-v2026.10.1.json"
test ! -e "$base/backups/.production-release.lock"
echo "PASS release runtime installer $scenario"

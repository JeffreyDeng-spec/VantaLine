"""Offline read-only diagnostic boundary tests; no production transport."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("diagnostic", ROOT / "scripts/read_production_release_state.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def report():
    return {"schema":1,"observed_at":"2026-10-04T10:00:00.000000+00:00", "lock":{"present":False},
            "services":{"vantaline":{"LoadState":"loaded","ActiveState":"active","SubState":"running",
                        "MainPID":"42","TimeoutStopUSec":"8min 30s","KillMode":"control-group"}},
            "current_version":{"release":"v2026.10.598","git_commit":"a"*40},
            "http_version":{"release":"v2026.10.598","git_commit":"a"*40,"consistent":True}}


class DiagnosticTests(unittest.TestCase):
    def test_closed_output_schema_and_cli_suppression(self):
        self.assertEqual(M.validate_report(report()), report())
        for path, value in [(('schema',),True),(('observed_at',),'2026-10-04T10:00:00password'),
             (('lock','secret'),'sensitive'),(('lock','mtime_epoch'),float('nan')),
             (('current_version','release'),'sensitive'),(('http_version','path'),'/private'),
             (('services','vantaline','TimeoutStopUSec'),'sensitive'),
             (('installed_script_sha256',),'g'*64)]:
            candidate=report();target=candidate
            for part in path[:-1]:target=target[part]
            target[path[-1]]=value
            with self.assertRaises((ValueError,KeyError)):M.validate_report(candidate)
        for data in ['secret banner\n'+json.dumps(report()),json.dumps({'secret':'dont-print-this'}),'x'*16385]:
            r=subprocess.run([sys.executable,str(ROOT/'scripts/read_production_release_state.py'),'--validate'],
                             input=data,capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,'')
            self.assertEqual(r.stderr.strip(),'Read-only diagnostic report rejected; raw output suppressed')

    def test_fixed_filesystem_metadata_never_reads_contents(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); journal=root/'journal'; journal.write_text('DO_NOT_READ')
            with mock.patch.object(M.os,'open',side_effect=AssertionError('content access forbidden')):
                directory=M.path_metadata(root); regular=M.path_metadata(journal)
                absent=M.path_metadata(root/'absent')
            self.assertEqual(directory['kind'],'directory'); self.assertEqual(regular['kind'],'regular')
            self.assertTrue(regular['stable_during_read']); self.assertEqual(absent,{'present':False})
            self.assertNotIn('DO_NOT_READ',json.dumps(regular))
            value=report();value['filesystem']={'backups':directory,'transition_605':regular}
            self.assertEqual(M.validate_report(value),value)
        path=mock.Mock();path.lstat.side_effect=PermissionError('private')
        self.assertEqual(M.path_metadata(path),{'present':None,'inspection':'unavailable'})

    def test_filesystem_validator_rejects_payloads_and_unknown_paths(self):
        for extra in ({'raw_journal':{'phase':'private'}},{'backups':{'path':'/private'}},
                      {'backups':{'owner_uid':True}}, {'backups':{'owner_gid':float('nan')}},
                      {'backups':{'kind':'secret'}}, {'backups':{'mode':'0o777 password'}},
                      {'backups':{'stable_during_read':1}}, {'backups':{'present':'false'}}):
            value=report();value['filesystem']=extra
            with self.assertRaises((ValueError,KeyError)):M.validate_report(value)
        self.assertEqual(set(M.METADATA_PATHS),{'base','backups','transition_605','installation_guard','managed_web_dropin'})
        self.assertEqual(str(M.METADATA_PATHS['transition_605']).replace('\\','/'),'/opt/vantaline/backups/.runtime-transition-v2026.10.605.json')

    def test_fixed_version_allowlist(self):
        self.assertEqual(M.version_fields({'release':'v2026.10.598','git_commit':'b'*40,
                         'secret':'hidden','path':'/private','consistent':True}),
                         {'release':'v2026.10.598','git_commit':'b'*40,'consistent':True})
        self.assertEqual(M.version_fields([]),{'inspection':'invalid'})
        self.assertEqual(M.version_fields({'release':'token','git_commit':'secret','consistent':1}),{})

    def test_bounded_file_and_lock_contents(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);lock=root/'lock';proc=root/'proc'
            self.assertEqual(M.lock_state(lock,proc),{'present':False})
            lock.write_bytes(b'private arbitrary string')
            state=M.lock_state(lock,proc)
            self.assertEqual(state['pid_format'],'invalid');self.assertNotIn('private',json.dumps(state))
            lock.write_bytes(b'42\n');before=lock.read_bytes()
            state=M.lock_state(lock,proc);self.assertFalse(state['process']['exists'])
            self.assertEqual(lock.read_bytes(),before);self.assertTrue(state['stable_during_read'])
            lock.write_bytes(b'x'*65)
            self.assertEqual(M.lock_state(lock,proc)['inspection'],'unavailable')
            with self.assertRaises(ValueError):M.bounded(lock,64)

    @unittest.skipIf(os.name=='nt','POSIX symlink and fifo contract')
    def test_symlink_fifo_and_swap_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);target=root/'target';target.write_bytes(b'secret')
            link=root/'link';link.symlink_to(target)
            self.assertFalse(M.lock_state(link)['regular_file'])
            with self.assertRaises(OSError):M.bounded(link,64)
            fifo=root/'fifo';os.mkfifo(fifo)
            with self.assertRaises(ValueError):M.bounded(fifo,64)
            self.assertEqual(target.read_bytes(),b'secret')

    def test_proc_safe_fields_and_disappearance(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);(root/'42').mkdir()
            # fields after comm: state(index0), ppid(index1), starttime(index19).
            fields=['S','7']+['0']*17+['1000']+['0']*5
            (root/'42/stat').write_text('42 (private process name) '+' '.join(fields))
            (root/'stat').write_bytes(b'btime 100\n')
            (root/'42/cmdline').write_bytes(b'/bin/sh\0/usr/local/sbin/vantaline-install-release\0secret-argument\0')
            with mock.patch.object(M.os,'sysconf',return_value=100,create=True):state=M.process_state(42,root)
            self.assertTrue(state['exists']);self.assertTrue(state['argv_names_installer'])
            self.assertEqual(state['started_at_epoch'],110);self.assertEqual(state['parent_pid'],7)
            self.assertNotIn('private',json.dumps(state));self.assertNotIn('secret',json.dumps(state))
            (root/'42/cmdline').unlink()
            with mock.patch.object(M.os,'sysconf',return_value=100,create=True):state=M.process_state(42,root)
            self.assertIn('inspection',state)

    def test_systemctl_fixed_read_only_command_and_failure(self):
        result=subprocess.CompletedProcess([],0,'ActiveState=active\nMainPID=42\nEnvironment=SECRET\n','')
        with mock.patch.object(M.subprocess,'run',return_value=result) as run:
            self.assertEqual(M.service_state('vantaline'),{'ActiveState':'active','MainPID':'42'})
            argv=run.call_args.args[0];self.assertEqual(argv[:3],['systemctl','show','vantaline'])
            self.assertEqual(run.call_args.kwargs['timeout'],5)
        with mock.patch.object(M.subprocess,'run',side_effect=ValueError('secret')):
            self.assertEqual(M.service_state('vantaline'),{'inspection':'unavailable'})
        with self.assertRaises(ValueError):M.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_main_fixed_localhost_and_redaction(self):
        reply=mock.MagicMock();reply.__enter__.return_value.read.return_value=json.dumps(report()['http_version']).encode()
        opener=mock.Mock();opener.open.return_value=reply
        def fake_read(path,limit):
            if path==M.INSTALLER:return b'installer'
            return json.dumps({**report()['current_version'],'secret':'NEVER_PRINT'}).encode()
        output=io.StringIO()
        with mock.patch.object(M,'lock_state',return_value={'present':False}), \
             mock.patch.object(M,'service_state',return_value={'inspection':'unavailable'}), \
             mock.patch.object(M,'bounded',side_effect=fake_read), \
             mock.patch.object(M.urllib.request,'build_opener',return_value=opener) as build, \
             contextlib.redirect_stdout(output):
            print(json.dumps(M.collect()))
        opener.open.assert_called_once_with('http://127.0.0.1:8765/api/version',timeout=5)
        self.assertEqual(build.call_args.args[0].proxies,{})
        self.assertIsInstance(build.call_args.args[1],M.NoRedirect)
        self.assertNotIn('NEVER_PRINT',output.getvalue());M.validate_report(json.loads(output.getvalue()))

    @unittest.skipIf(os.name=='nt','POSIX open-file rename semantics')
    def test_lock_aba_fd_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);lock=root/'lock';saved=root/'saved';replacement=root/'replacement'
            lock.write_bytes(b'42\n');replacement.write_bytes(b'77\n')
            actual_open=os.open;changed=[]
            def swap(path,flags,*args,**kwargs):
                if Path(path)==lock and not changed:
                    changed.append(True);lock.rename(saved);replacement.rename(lock)
                    fd=actual_open(path,flags,*args,**kwargs)
                    lock.rename(replacement);saved.rename(lock)
                    return fd
                return actual_open(path,flags,*args,**kwargs)
            with mock.patch.object(M.os,'open',side_effect=swap):value=M.lock_state(lock,root/'proc')
            self.assertEqual(lock.read_bytes(),b'42\n')
            self.assertFalse(value['stable_during_read']);self.assertNotIn('process',value)
            self.assertEqual(value['inspection'],'unavailable')

    @unittest.skipIf(os.name=='nt','POSIX diagnostic deadline')
    def test_overall_deadline_stops_drip_response(self):
        stopped=threading.Event()
        class Drip(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                self.send_response(200);self.end_headers()
                while not stopped.wait(.02):
                    try:self.wfile.write(b' ');self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):break
        server=ThreadingHTTPServer(('127.0.0.1',0),Drip)
        thread=threading.Thread(target=server.serve_forever);thread.start()
        real=M.urllib.request.build_opener(M.urllib.request.ProxyHandler({}),M.NoRedirect())
        opener=mock.Mock()
        opener.open.side_effect=lambda *a,**kw:real.open('http://127.0.0.1:'+str(server.server_port),timeout=.1)
        output=io.StringIO();started=time.monotonic()
        try:
            with mock.patch.object(M,'lock_state',return_value={'present':False}), \
                 mock.patch.object(M,'service_state',return_value={'inspection':'unavailable'}), \
                 mock.patch.object(M,'bounded',side_effect=OSError('private')), \
                 mock.patch.object(M.urllib.request,'build_opener',return_value=opener), \
                 mock.patch.object(M,'DEADLINE_SECONDS',.2),contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(SystemExit,'Diagnostic deadline exceeded; no report emitted'):M.main()
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(output.getvalue(),'')
            self.assertEqual(M.signal.getitimer(M.signal.ITIMER_REAL),(0,0))
        finally:
            stopped.set();server.shutdown();server.server_close();thread.join(timeout=2)

    def test_workflow_transport_and_environment_guards(self):
        source=(ROOT/'.github/workflows/release-readonly-diagnostics.yml').read_text()
        for required in ('environment: production','persist-credentials: false','StrictHostKeyChecking=yes',
             "head.ref == 'fix/backend-runtime-transition-diagnostics'",'head.repo.full_name == github.repository',
             'python3 -I -S -B -','--validate','2> "$task_dir/ssh.stderr"'):
            self.assertIn(required,source)
        for forbidden in ('pull_request_target','sudo ','StrictHostKeyChecking=no','continue-on-error','workflow_run:'):
            self.assertNotIn(forbidden,source)
        self.assertNotIn('PROD_', (ROOT/'scripts/read_production_release_state.py').read_text())


if __name__=='__main__':unittest.main()

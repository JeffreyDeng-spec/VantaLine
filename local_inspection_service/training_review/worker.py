"""Serial training reviewer; run as its own service, never the Web/label process."""
import argparse
from contextlib import contextmanager
import hmac
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import queue
import shutil
import socketserver
import subprocess
import tempfile
import threading
import time

from ..codex_compare.worker import sandbox_command, stop_process, proxy_environment
from ..storage.runtime_selector import build_runtime_repository
from ..storage.real_photo_feedback import RealPhotoRepository
from ..storage.artifacts.files import BusinessFiles
from ..storage.artifacts.runtime import get_runtime
from ..model_profiles.repository import Repository as Profiles
from ..model_profiles.service import validate_binding
from ..training.real_photo_api import accounts
from ..training.real_photo_annotation import annotate, canonical
from ..training.real_photo_contracts import MODEL, VERSION, digest, encode, review_report
from ..training.real_photo_workflow import apply_result, schedule

MODULE=Path(__file__).parent
SKILL=MODULE/'skills'/'vantaline-training-review'
MODEL_AGENT='gpt-6-astra'


def with_repo(fn):
    import psycopg
    selection=build_runtime_repository(postgres_connector=lambda d:psycopg.connect(d,connect_timeout=5,options='-c statement_timeout=10000'))
    if selection.store!='postgres':raise RuntimeError('training review requires PostgreSQL')
    repo=RealPhotoRepository(selection.repository)
    try:return fn(repo)
    finally:selection.repository.connection.close()


def settings(job, secret_file):
    ref=job['inputs']['profiles']['bbox_annotation']
    def read(repo):
        profiles=Profiles(repo.repository)
        with profiles.read_tx() as c:return profiles.get(c,f"{ref['id']}:{ref['version']}")
    profile=with_repo(read)
    if not profile:raise ValueError('frozen model profile missing')
    validate_binding('bbox_annotation',profile)
    # Only the trusted parent reads secret material. Never mount it in the child.
    path=Path(secret_file)
    if not path.is_file() or path.stat().st_size>1024*1024:raise ValueError('private profile secret file required')
    values={}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1)
            try:values[key.strip()]=json.loads(value)
            except ValueError:values[key.strip()]=value
    key=values.get(profile['secret_ref'])
    if not isinstance(key,str) or not key:raise ValueError('model profile secret unavailable')
    return {**{k:profile[k] for k in ('provider','model','base_url','timeout_seconds')},'api_key':key,'configured':True}


@contextmanager
def workspace(config):
    runtime=get_runtime()
    if runtime is not None:
        budget=runtime.store.budget
        if not budget.preallocated:raise RuntimeError('kernel-limited scratch required')
        size=min(budget.limits['work'],shutil.disk_usage(budget.scratch_roots['work']).free)-16*1024*1024
        if size<=0:raise RuntimeError('no review scratch capacity')
        with budget.workspace('work',size) as path:yield Path(path)
    else:
        with tempfile.TemporaryDirectory(prefix='rp_',dir=config['work_root']) as path:yield Path(path)


def prepare(job, directory, files):
    inputs=job['inputs'];public={**inputs,'classes':[],'samples':[]}
    if job['kind']=='review' and not 1<=len(inputs.get('samples',[]))<=10:
        raise ValueError('review invocation must contain 1 to 10 originals')
    for index,c in enumerate(inputs['classes']):
        raw=files.read_bytes(c['reference_path'],max_bytes=32*1024*1024)
        clean,meta=canonical(raw)
        if meta['source_sha256']!=c['reference_sha256']:raise ValueError('reference version changed')
        filename=f'reference-{index}.png';(directory/filename).write_bytes(clean)
        public['classes'].append({k:v for k,v in c.items() if k!='reference_path'}|{'image':'/input/'+filename})
    for index,s in enumerate(inputs.get('samples',[])):
        clean,meta=canonical(files.read_bytes(s['source_path'],max_bytes=32*1024*1024))
        if meta['source_sha256']!=s['image_sha256']:raise ValueError('original version changed')
        filename=f'actual-{index}.png';(directory/filename).write_bytes(clean)
        public['samples'].append({k:s.get(k) for k in ('sample_id','image_sha256','source_group','review_key','review','geometry')}
                                 |{'image':'/input/'+filename,'annotation':{'objects':s['annotation']['objects'],'version':s['annotation']['version'],'status':s['annotation']['status']}})
    schemas={
        'initialize':{'review_trigger':20,'approved_real_target':20,'reason':'concrete reason'},
        'review':{'decisions':[{'sample_id':'exact sample_id','review_key':'exact review_key','decision':'accept_positive|accept_negative|exclude|uncertain','reason':'concrete reason'}]},
        'assess':{'action':'train|collect|pause','approved_real_target':20,'next_increment':1,'reason':'concrete reason','gaps':[]}}
    (directory/'task.json').write_text(encode({'kind':job['kind'],'inputs':public,'schema':schemas[job['kind']],
                                            'prompt_version':VERSION,'deadline':job['deadline']}))


def broker(job, token, path, report, auth_file):
    lock=threading.Lock()
    auth=json.loads(Path(auth_file).read_text())
    secrets=[]
    def collect(value):
        if isinstance(value,dict):
            for key,v in value.items():
                if key.lower() in {'access_token','refresh_token','id_token','openai_api_key'} and isinstance(v,str) and v:secrets.append(v)
                else:collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(auth)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            status=422;body={'error':'invalid or stale report'}
            try:
                size=int(self.headers.get('Content-Length','0'))
                if self.path!='/' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token) or not 0<size<=65536:
                    raise ValueError('invalid request')
                clean=self.rfile.read(size).decode().replace(token,'[redacted]')
                for secret in secrets:clean=clean.replace(secret,'[redacted]')
                payload=json.loads(clean)
                review_report(job,payload)
                if not with_repo(lambda r:r.pulse(job['id'],token)):raise ValueError('inactive attempt')
                with lock:
                    if report and report[0]!=payload:raise ValueError('immutable report already submitted')
                    if not report:
                        with_repo(lambda r:r.receipt(job['id'],job['attempt_id'],{'evidence':payload}))
                        report.append(payload)
                status=200;body={'accepted':True,'fingerprint':digest(payload)}
            except (ValueError,TypeError,KeyError):pass
            except Exception:status=503;body={'error':'storage unavailable'}
            raw=encode(body).encode();self.send_response(status);self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    return socketserver.UnixStreamServer(str(path),Handler)


def review(job,token,config):
    report=[];metadata={};events=queue.Queue(maxsize=32);process=None;server=None;reader=None
    with workspace(config) as directory, tempfile.TemporaryDirectory(prefix='rp-sock-') as socket_dir:
        for name in ('input','work','auth','bin','tmp'):(directory/name).mkdir(mode=0o700)
        prepare(job,directory/'input',BusinessFiles())
        shutil.copyfile(Path(config['auth_home'])/'auth.json',directory/'auth'/'auth.json')
        (directory/'auth'/'config.toml').write_text('model = "'+MODEL_AGENT+'"\nweb_search = "disabled"\n')
        (directory/'bin'/'vantaline').write_text('#!/bin/sh\nexec /usr/bin/python3 /tools/cli.py "$@"\n');(directory/'bin'/'vantaline').chmod(0o755)
        server=broker(job,token,Path(socket_dir)/'report.sock',report,directory/'auth'/'auth.json')
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            command=sandbox_command(directory,directory/'auth',Path(config['binary']),token,MODEL_AGENT,
                                    Path(socket_dir)/'report.sock',config['proxy_url'],tools_module=MODULE,skill_directory=SKILL)
            if not with_repo(lambda r:r.pulse(job['id'],token)):raise RuntimeError('review no longer authorized')
            with_repo(lambda r:r.receipt(job['id'],job['attempt_id'],{'external_call_started':True}))
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                     start_new_session=True,env={'PATH':'/usr/bin:/bin'})
            last_pulse=[time.monotonic()];watchdog_stop=threading.Event()
            def watchdog():
                while not watchdog_stop.wait(.5):
                    if time.time()>=job['deadline'] or time.monotonic()-last_pulse[0]>20:
                        stop_process(process);return
            threading.Thread(target=watchdog,daemon=True).start()
            process.stdin.write((SKILL/'SKILL.md').read_bytes());process.stdin.close()
            def read():
                for line in iter(lambda:process.stdout.readline(65537),b''):
                    if len(line)>65536:continue
                    try:
                        event=json.loads(line)
                        if event.get('type') in {'thread.started','turn.completed','turn.failed'}:events.put_nowait(event)
                    except (ValueError,queue.Full):pass
            reader=threading.Thread(target=read,daemon=True);reader.start()
            complete=False;failed=False
            while True:
                exited=process.poll()
                if exited is not None:reader.join(timeout=1)
                while not events.empty():
                    event=events.get_nowait()
                    if event['type']=='thread.started':metadata['session_id']=str(event.get('thread_id',''))[:128]
                    if event['type']=='turn.failed':failed=True
                    if event['type']=='turn.completed':
                        complete=True
                        metadata['usage']={k:v for k,v in (event.get('usage') or {}).items()
                                           if k in {'input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens'} and type(v)is int and v>=0}
                if not with_repo(lambda r:r.pulse(job['id'],token)) or time.time()>=job['deadline']:
                    raise RuntimeError('review interrupted; no automatic retry')
                last_pulse[0]=time.monotonic()
                if metadata:with_repo(lambda r:r.receipt(job['id'],job['attempt_id'],metadata))
                if exited is not None and not reader.is_alive():
                    if exited!=0 or not complete or failed or not report or not metadata.get('session_id'):
                        raise RuntimeError('CLI did not complete review')
                    return report[0],metadata
                time.sleep(.5)
        finally:
            if process and 'watchdog_stop' in locals():watchdog_stop.set()
            if process:stop_process(process)
            if reader:reader.join(timeout=2)
            if server:server.shutdown();server.server_close()
            refreshed=directory/'auth'/'auth.json'
            try:
                if refreshed.is_file() and not refreshed.is_symlink():
                    contents=refreshed.read_bytes()
                    if len(contents)<=65536 and isinstance(json.loads(contents),dict):
                        target=Path(config['auth_home'])/'auth.json'
                        staging=target.with_suffix('.refresh');staging.write_bytes(contents);staging.chmod(0o600);staging.replace(target)
            except (OSError,ValueError):print('review auth refresh not persisted',flush=True)


def run(job,token,config):
    stopped=threading.Event()
    def heartbeat():
        while not stopped.wait(5):
            try:
                if not with_repo(lambda r:r.pulse(job['id'],token)):return
            except Exception:return
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    metadata={}
    try:
        if job['kind']=='annotate':
            files=BusinessFiles();sample=job['inputs']['sample'];raw=files.read_bytes(sample['source_path'],max_bytes=32*1024*1024)
            if digest(raw)!=sample['image_sha256']:raise ValueError('original changed')
            def transport(body,model_settings):
                from ..model_profiles.transport import invoke
                if not with_repo(lambda r:r.pulse(job['id'],token)):raise RuntimeError('annotation no longer authorized')
                with_repo(lambda r:r.receipt(job['id'],job['attempt_id'],{'external_call_started':True}))
                return invoke(body,model_settings)
            result=annotate(raw,job['inputs']['classes'],settings(job,config['secret_file']),lambda c:files.read_bytes(c['reference_path'],max_bytes=32*1024*1024),transport=transport)
            metadata['usage']=result['receipt']['usage']
            # Failed annotations are complete attempts, not admissible training labels.
        else:result,metadata=review(job,token,config)
        with_repo(lambda r:r.receipt(job['id'],job['attempt_id'],{**metadata,'evidence':result,'elapsed_seconds':time.time()-job['started_at']}))
        def finish(repo):
            def apply(state,current,c):
                current.update(metadata)
                apply_result(repo,state,current,c)
            return repo.finish(job['id'],token,result,apply)
        with_repo(finish)
    except Exception as exc:
        try:with_repo(lambda r:r.finish(job['id'],token,{'error_type':type(exc).__name__,**metadata},lambda *a:None,success=False))
        except Exception:pass  # claim recovery records uncertain attempts without requeueing.
    finally:stopped.set();thread.join(timeout=6)


def load_config():
    config={key:os.getenv('VANTALINE_TRAINING_REVIEW_'+key.upper(),'').strip()
            for key in ('binary','auth_home','work_root','secret_file','proxy_url')}
    if not accounts() or not all(config[k] for k in ('binary','auth_home','work_root','secret_file')):
        raise RuntimeError('explicit review account/runtime/secret configuration required')
    if os.getenv('VANTALINE_TRAINING_REVIEW_MODEL',MODEL_AGENT)!=MODEL_AGENT:raise RuntimeError('fixed review model required')
    if not shutil.which('bwrap') or not (Path(config['auth_home'])/'auth.json').is_file():raise RuntimeError('isolated Linux runtime and dedicated login required')
    auth=Path(config['auth_home'])/'auth.json'
    if auth.is_symlink() or auth.stat().st_mode & 0o077 or auth.stat().st_size>65536:
        raise RuntimeError('dedicated authentication must be a private bounded regular file')
    if not (Path(config['binary']).parent/'codex-code-mode-host').is_file():raise RuntimeError('complete pinned native runtime required')
    proxy_environment(config['proxy_url']);get_runtime()
    version=subprocess.run([config['binary'],'--version'],capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    config['version']=version[:128]+':'+digest({'prompt':(SKILL/'SKILL.md').read_text(),'cli':(MODULE/'cli.py').read_text(),'crop':(MODULE/'image_tools.py').read_text()})
    return config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    config=load_config()
    if args.check:print(encode({'ready':True,'version':config['version'],'model':MODEL_AGENT}));return
    while True:
        states=with_repo(lambda r:r.states(accounts()))
        for state in states:
            with_repo(lambda r:schedule(r,state['owner_user_id'],state['task_id']))
        claimed=with_repo(lambda r:r.claim(accounts(),{'initialize','review','assess','annotate'},MODEL_AGENT,config['version']))
        if claimed:run(*claimed,config)
        else:time.sleep(2)


if __name__=='__main__':main()

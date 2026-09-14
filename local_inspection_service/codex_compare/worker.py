"""Dedicated Linux worker. Launch: python -m local_inspection_service.codex_compare.worker.

The parent holds storage credentials. Bubblewrap exposes only OS tools, a pinned
Codex native runtime, private task files, and a task-specific report socket.
There is deliberately no unisolated fallback.
"""
from __future__ import annotations
import argparse
import base64
import hmac
import io
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit
from PIL import Image
from .api import enabled_owners, public
from .contracts import MAX_BYTES, PROMPT_VERSION, TERMINAL, box, digest, encode
from .media import MediaStore
from ..storage.codex_comparisons import CodexComparisonsRepository
from ..storage.agent_operations import OperationDenied, OperationConflict
from ..storage.runtime_selector import build_runtime_repository

MODULE = Path(__file__).parent
SKILL = MODULE/'skills'/'vantaline-label-inspection'
SKILL_VERSION = 'label-inspection-v3.0'


def repository():
    selection = build_runtime_repository()
    if selection.store != 'postgres':
        raise RuntimeError('Codex comparison requires PostgreSQL')
    return CodexComparisonsRepository(selection.repository)


def with_repo(fn):
    repo = repository()
    try:
        return fn(repo)
    finally:
        repo.repository.connection.close()


def artifact(media, owner, task, payload):
    if set(payload) != {'data', 'source', 'box'} or payload['source'] not in {'reference', 'actual'}:
        raise ValueError('Evidence needs data, source and original box')
    bounds = box(payload['box'])
    if bounds is None:
        raise ValueError('Evidence requires source bounds')
    data = base64.b64decode(payload['data'], validate=True)
    if len(data) > MAX_BYTES:
        raise ValueError('Evidence too large')
    # Verify the claimed transform against source pixels; agent metadata alone
    # cannot establish that arbitrary uploaded pixels came from the source.
    with Image.open(io.BytesIO(media.read(owner, task['inputs'][payload['source']]['image']))) as source:
        x, y, w, h = bounds
        crop_bounds = (round(x*source.width), round(y*source.height), round((x+w)*source.width), round((y+h)*source.height))
        crop = source.crop(crop_bounds).convert('RGB')
        if min(crop.size) < 1:
            raise ValueError('Empty crop')
        with Image.open(io.BytesIO(data)) as supplied:
            if supplied.width * supplied.height > 16_000_000:
                raise ValueError('Evidence too large')
            # Persist a server-generated crop, not an unverified altered image.
            size = supplied.size
            if max(size) > 4096 or min(size) < 32:
                raise ValueError('Evidence dimensions out of range')
        output = io.BytesIO()
        crop.resize(size, Image.Resampling.LANCZOS).save(output, 'PNG')
    value = media.image(owner, output.getvalue())
    value.update(source=payload['source'], box=bounds, source_pixels=list(crop_bounds),
                 transform={'crop_pixels': list(crop_bounds), 'output_size': size, 'resampler': 'LANCZOS'},
                 id='ev_' + digest({'source': payload['source'], 'box': bounds, 'size': size})[:32])
    return value


def decode(media, owner, task, payload):
    if not isinstance(payload, dict) or set(payload) != {'source', 'box'} or payload['source'] not in {'reference', 'actual'}:
        raise ValueError('Decode needs source and original box')
    bounds = box(payload['box'])
    if bounds is None:
        raise ValueError('Decode bounds required')
    with Image.open(io.BytesIO(media.read(owner, task['inputs'][payload['source']]['image']))) as im:
        x,y,w,h = bounds
        pixels = [round(x*im.width), round(y*im.height), round((x+w)*im.width), round((y+h)*im.height)]
        if pixels[2] <= pixels[0] or pixels[3] <= pixels[1]:
            raise ValueError('Empty decode crop')
        output = io.BytesIO()
        im.crop(pixels).save(output, 'PNG')
    try:
        process = subprocess.run([sys.executable, str(MODULE/'decode_helper.py')], input=output.getvalue(),
                                 capture_output=True, timeout=15, env={'PATH': '/usr/bin:/bin'})
        result = json.loads(process.stdout) if process.returncode == 0 else {'values': [], 'error': 'local_decoder_unavailable'}
    except (subprocess.TimeoutExpired, ValueError):
        result = {'values': [], 'error': 'local_decoder_timeout_or_invalid'}
    return {**result, 'source': payload['source'], 'box': bounds,
            'id': 'dc_'+digest(payload)[:32]}


def broker(task, token, media, path, auth_path=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                if self.path != '/' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                    raise OperationDenied('Invalid task token')
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 15 * 1024 * 1024:
                    raise ValueError('Request too large')
                raw = self.rfile.read(size)
                # Remove task bearer echoes before persistence.
                clean = raw.decode().replace(token, '[redacted]')
                if auth_path and Path(auth_path).is_file():
                    def redact_secrets(value):
                        nonlocal clean
                        if isinstance(value, dict):
                            for key, entry in value.items():
                                if key.lower() in {'access_token', 'refresh_token', 'id_token', 'openai_api_key'} and isinstance(entry, str) and entry:
                                    clean = clean.replace(entry, '[redacted]')
                                else:
                                    redact_secrets(entry)
                        elif isinstance(value, list):
                            for entry in value:
                                redact_secrets(entry)
                    redact_secrets(json.loads(Path(auth_path).read_text()))
                request = json.loads(clean)
                if set(request) != {'kind', 'key', 'payload'} or not isinstance(request['key'], str) or not 8 <= len(request['key']) <= 128:
                    raise ValueError('Invalid request envelope')
                kind, payload = request['kind'], request['payload']
                def operation(repo):
                    current = repo.get(task['owner_user_id'], task['id'])
                    if not current or current['status'] != 'running' or time.time() >= current['deadline'] or current.get('attempt_id') != task['attempt_id']:
                        raise OperationDenied('Task ended')
                    is_batch = current.get('report_version') == 'label-batch-v3'
                    lid = payload.get('label_id') if isinstance(payload, dict) else None
                    if kind == 'show':
                        if is_batch and lid:
                            from .batch_contracts import public_label
                            return public_label(current, lid, True)
                        return public(current)
                    scoped = payload.get('value') if is_batch and lid else payload
                    target = current
                    if is_batch and kind in {'artifact', 'decode'}:
                        from .batch_contracts import require_matched
                        target = require_matched(current, lid)
                    if kind == 'decode':
                        value = decode(media, task['owner_user_id'], target, scoped)
                    elif kind == 'artifact':
                        value = artifact(media, task['owner_user_id'], target, scoped)
                    else:
                        if len(raw) > 65536:
                            raise ValueError('Report payload too large')
                        value = payload
                    if is_batch and kind in {'artifact', 'decode'}:
                        value = {'label_id': lid, 'value': value}
                    result = repo.write_report(task['owner_user_id'], task['id'], task['attempt_id'], token, request['key'], kind, value)
                    return {**result, kind: value} if kind in {'artifact', 'decode'} else result
                result = with_repo(operation)
                status = 200
            except (ValueError, TypeError, KeyError, OSError) as exc:
                status, result = 422, {'error': str(exc)[:500]}
            except OperationDenied as exc:
                status, result = 403, {'error': str(exc)}
            except OperationConflict as exc:
                status, result = 409, {'error': str(exc)}
            except Exception:
                status, result = 503, {'error': 'Report storage unavailable; retain write ID before retrying'}
            body = encode(result).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = socketserver.UnixStreamServer(str(path), Handler)
    server.timeout = 1
    return server


def proxy_environment(value):
    """Only an explicit, credential-free local HTTP proxy enters the task."""
    if not value:
        return {}
    try:
        parsed = urlsplit(value)
        valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                 and parsed.port is not None and 1 <= parsed.port <= 65535
                 and parsed.username is None and parsed.password is None
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment
                 and not any(c.isspace() for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError('Codex proxy must be a credential-free http://127.0.0.1:PORT URL')
    canonical = f'http://127.0.0.1:{parsed.port}'
    return {'HTTP_PROXY': canonical, 'HTTPS_PROXY': canonical,
            'http_proxy': canonical, 'https_proxy': canonical,
            'NO_PROXY': 'localhost,127.0.0.1,::1', 'no_proxy': 'localhost,127.0.0.1,::1'}


def sandbox_command(task_dir, auth_dir, runtime, token, model, socket_path=None, proxy_url=''):
    executable = shutil.which('bwrap')
    if not executable or not runtime.is_file():
        raise RuntimeError('Linux bubblewrap and pinned native Codex binary are required')
    command = [executable, '--unshare-all', '--share-net', '--die-with-parent', '--new-session', '--clearenv']
    for path in ('/usr', '/bin', '/lib', '/lib64'):
        if Path(path).exists():
            command += ['--ro-bind', path, path]
    command += ['--dir', '/etc']
    for path in ('/etc/ssl', '/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf'):
        if Path(path).exists():
            command += ['--ro-bind', path, path]
    command += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--dir', '/run',
                '--ro-bind', str(runtime.parent), '/codex-runtime',
                '--ro-bind', str(task_dir/'input'), '/input', '--bind', str(task_dir/'work'), '/work',
                '--bind', str(auth_dir), '/codex', '--dir', '/tools', '--ro-bind', str(MODULE/'cli.py'), '/tools/cli.py',
                '--ro-bind', str(task_dir/'bin'), '/tools/bin',
                '--ro-bind', str(MODULE/'image_tools.py'), '/tools/image_tools.py',
                '--dir', '/work/.agents', '--dir', '/work/.agents/skills',
                '--ro-bind', str(SKILL), '/work/.agents/skills/vantaline-label-inspection',
                '--bind', str(socket_path or task_dir/'report.sock'), '/run/vantaline.sock', '--chdir', '/work']
    env = {'PATH': '/tools/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': '/work', 'CODEX_HOME': '/codex',
           'LANG': 'C.UTF-8', 'VANTALINE_TASK_SOCKET': '/run/vantaline.sock', 'VANTALINE_TASK_TOKEN': token}
    env.update(proxy_environment(proxy_url))
    for k, v in env.items():
        command += ['--setenv', k, v]
    # Bubblewrap is the outer sandbox; do not depend on nested Landlock support.
    command += ['/codex-runtime/'+runtime.name, 'exec', '--json', '--skip-git-repo-check',
                '--sandbox', 'danger-full-access', '--model', model, '-c', 'model_reasoning_effort="high"',
                '-c', 'web_search="disabled"', '-']
    return command


def stop_process(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)


def prepare_batch_input(task, directory, media):
    """Materialize bounded original files and paginated navigation-only contact sheets."""
    from PIL import ImageDraw
    (directory/'media').mkdir()
    entries = [(rid, r.get('media')) for rid, r in task['inputs']['references'].items()]
    entries += [(lid, e['actual']) for lid, e in task['labels'].items()]
    pages = []
    for offset in range(0, len(entries), 12):
        sheet = Image.new('RGB', (1000, 750), 'white')
        draw = ImageDraw.Draw(sheet)
        for index, (identifier, evidence) in enumerate(entries[offset:offset+12]):
            x, y = (index % 4)*250, (index//4)*250
            if evidence:
                path = directory/'media'/(evidence['image']+'.png')
                if not path.exists():
                    path.write_bytes(media.read(task['owner_user_id'], evidence['image']))
                with Image.open(path) as source:
                    thumb = source.copy()
                    thumb.thumbnail((240, 215))
                    sheet.paste(thumb, (x, y))
            draw.text((x+2, y+218), identifier, fill='black')
        filename = 'index-%03d.jpg' % (offset//12+1)
        sheet.save(directory/filename, quality=85)
        pages.append(filename)
    (directory/'batch.json').write_text(encode({'id': task['id'], 'labels': [{'id': lid, 'name': e['name'], 'image': '/input/media/'+e['actual']['image']+'.png', 'match': e['match']} for lid,e in task['labels'].items()],
        'references': task['inputs']['references'], 'index_pages': pages,
        'deadline': task['deadline'], 'path_rule': '/input/media/{image_sha256}.png'}))


def execute(task, token, config, media):
    base = Path(config['work_root'])
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = Path(tempfile.mkdtemp(prefix=task['id']+'-', dir=base))
    socket_directory = Path(tempfile.mkdtemp(prefix='vc-', dir='/tmp'))
    (directory/'owner.json').write_text(encode({'id': task['id'], 'owner': task['owner_user_id'], 'attempt': task['attempt_id'], 'socket_directory': str(socket_directory.resolve())}))
    process = None
    server = None
    watchdog_stop = threading.Event()
    last_heartbeat = [time.monotonic()]
    status, error = 'failed', 'Codex 启动或执行失败；请检查 worker 配置。'
    try:
        for name in ('input', 'work', 'bin', 'auth'):
            (directory/name).mkdir(mode=0o700)
        if task.get('report_version') == 'label-batch-v3':
            prepare_batch_input(task, directory/'input', media)
        else:
            for side in ('reference', 'actual'):
                (directory/'input'/f'{side}.png').write_bytes(media.read(task['owner_user_id'], task['inputs'][side]['image']))
        (directory/'input'/'task.json').write_text(encode({'id': task['id'], 'inputs': task['inputs'], 'prompt_version': SKILL_VERSION if task.get('report_version') in {'label-v2', 'label-batch-v3'} else PROMPT_VERSION}))
        (directory/'bin'/'vantaline').write_text('#!/bin/sh\nexec /usr/bin/python3 /tools/cli.py "$@"\n')
        (directory/'bin'/'vantaline').chmod(0o755)
        shutil.copyfile(Path(config['auth_home'])/'auth.json', directory/'auth'/'auth.json')
        (directory/'auth'/'config.toml').write_text('model = '+json.dumps(config['model'])+'\nmodel_reasoning_effort = "high"\nweb_search = "disabled"\n')
        server = broker(task, token, media, socket_directory/'report.sock', directory/'auth'/'auth.json')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if task.get('report_version') in {'label-v2', 'label-batch-v3'}:
            skill_body = (SKILL/'SKILL.md').read_bytes()
            skill_meta = {'skill_version': SKILL_VERSION, 'skill_sha256': digest(skill_body), 'tool_version': 'vantaline-cli-v3'}
            with_repo(lambda r: r.pulse(task['owner_user_id'], task['id'], task['attempt_id'], skill_meta))
            # Include the exact skill bytes as well as an explicit named invocation;
            # loading never depends solely on implicit model skill discovery.
            prompt_file = 'batch_prompt.md' if task.get('report_version') == 'label-batch-v3' else 'label_prompt.md'
            prompt = (MODULE/prompt_file).read_bytes() + b'\n\n' + skill_body
        else:
            prompt = (MODULE/'prompt.md').read_bytes()
        command = sandbox_command(directory, directory/'auth', Path(config['binary']), token, config['model'], socket_directory/'report.sock', proxy_url=config.get('proxy_url', ''))
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   start_new_session=True, env={'PATH': '/usr/bin:/bin'})
        def watchdog():
            while not watchdog_stop.wait(0.5):
                if time.time() >= task['deadline'] or time.monotonic() - last_heartbeat[0] > 20:
                    stop_process(process)
                    return
        threading.Thread(target=watchdog, daemon=True).start()
        process.stdin.write(prompt)
        process.stdin.close()
        events = queue.Queue(maxsize=100)
        def read_events():
            while True:
                line = process.stdout.readline(65537)
                if not line:
                    return
                if len(line) > 65536:
                    continue
                try:
                    value = json.loads(line)
                    if value.get('type') in {'thread.started', 'turn.completed', 'turn.failed'}:
                        events.put_nowait(value)
                except (ValueError, queue.Full):
                    pass
        reader = threading.Thread(target=read_events, daemon=True)
        reader.start()
        metadata = {}
        turn_completed = False
        turn_failed = False
        while True:
            if process.poll() is not None:
                reader.join(timeout=1)
            while not events.empty():
                event = events.get_nowait()
                if event['type'] == 'thread.started':
                    metadata['session_id'] = str(event.get('thread_id', ''))[:128]
                elif event['type'] == 'turn.failed':
                    turn_failed = True
                elif event['type'] == 'turn.completed':
                    turn_completed = True
                    metadata['usage'] = {k: v for k, v in (event.get('usage') or {}).items() if k in {'input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens'} and type(v) is int and v >= 0}
            current = with_repo(lambda r: r.pulse(task['owner_user_id'], task['id'], task['attempt_id'], metadata))
            last_heartbeat[0] = time.monotonic()
            if not current or current['status'] == 'cancel_requested':
                status, error = 'cancelled', ''
                break
            if time.time() >= task['deadline']:
                status, error = 'timed_out', '已达到 10 分钟时限；部分报告已保留。'
                break
            if process.poll() is not None:
                # Drain reader once after process exit before deciding completion.
                if process.returncode == 0 and turn_completed and not turn_failed and metadata.get('session_id'):
                    status, error = 'completed', ''
                else:
                    status, error = 'failed', 'Codex 未正常完成；部分报告已保留。'
                break
            time.sleep(0.5)
    finally:
        watchdog_stop.set()
        if process:
            stop_process(process)
        if server:
            server.shutdown()
            server.server_close()
        # Preserve refreshed authentication only, never generated config/plugins/history.
        refreshed = directory/'auth'/'auth.json'
        if refreshed.is_file() and not refreshed.is_symlink():
            try:
                target = Path(config['auth_home'])/'auth.json'
                staging = target.with_suffix('.refresh')
                contents = refreshed.read_bytes()
                if len(contents) > 65536 or not isinstance(json.loads(contents), dict):
                    raise ValueError('Invalid refreshed authentication')
                staging.write_bytes(contents)
                staging.chmod(0o600)
                staging.replace(target)
            except (OSError, ValueError):
                print(encode({'event': 'auth_refresh_not_persisted'}), flush=True)
        with_repo(lambda r: r.settle(task['owner_user_id'], task['id'], task['attempt_id'], status, error))
        shutil.rmtree(directory)
        shutil.rmtree(socket_directory)


def cleanup_finished(config):
    """Collect only our recorded terminal scratch after hard process death."""
    base = Path(config['work_root']).resolve()
    if not base.is_dir():
        return
    for directory in base.glob('cc_*'):
        if directory.is_symlink() or not directory.is_dir():
            continue
        marker = directory/'owner.json'
        if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
            continue
        try:
            value = json.loads(marker.read_text())
            if not isinstance(value, dict) or any(not isinstance(value.get(k), str) for k in ('owner', 'id', 'attempt', 'socket_directory')):
                continue
        except (ValueError, OSError):
            continue
        task = with_repo(lambda r: r.get(value['owner'], value['id']))
        if not task or task.get('attempt_id') != value['attempt'] or task['status'] not in TERMINAL:
            continue
        socket_directory = Path(value['socket_directory'])
        if (socket_directory.parent == Path('/tmp').resolve() and socket_directory.name.startswith('vc-')
                and not socket_directory.is_symlink() and socket_directory.is_dir()):
            shutil.rmtree(socket_directory)
        shutil.rmtree(directory)


def load_config():
    config = {key: os.environ.get('VANTALINE_CODEX_COMPARE_'+key.upper(), '').strip()
              for key in ('model', 'binary', 'auth_home', 'work_root', 'media_root')}
    if not all(config.values()):
        raise RuntimeError('Missing Codex comparison worker configuration')
    config['proxy_url'] = os.environ.get('VANTALINE_CODEX_COMPARE_PROXY_URL', '').strip()
    proxy_environment(config['proxy_url'])
    if not (Path(config['auth_home'])/'auth.json').is_file():
        raise RuntimeError('Dedicated Codex account login is required')
    if not (Path(config['binary']).parent/'codex-code-mode-host').is_file():
        raise RuntimeError('Complete pinned Codex runtime including codex-code-mode-host is required')
    for required in (SKILL/'SKILL.md', SKILL/'references'/'cli.md', MODULE/'label_prompt.md'):
        if not required.is_file():
            raise RuntimeError('Versioned label inspection skill is missing')
    if not shutil.which('bwrap'):
        raise RuntimeError('Linux bubblewrap is required; no unisolated fallback')
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Validate installed runtime without claiming work')
    args = parser.parse_args()
    config = load_config()
    # Check the native binary without printing auth/configuration.
    result = subprocess.run([config['binary'], '--version'], capture_output=True, text=True, check=True, timeout=10)
    version = result.stdout.strip()[:100]
    if args.check:
        print(encode({'runtime': version, 'model': config['model'], 'isolation': 'bubblewrap available; task launch still requires commissioning'}))
        return
    media = MediaStore(config['media_root'])
    while True:
        try:
            with_repo(lambda r: r.recover())
            cleanup_finished(config)
            claimed = with_repo(lambda r: r.claim(enabled_owners(), config['model'], version))
            if claimed:
                execute(*claimed, config, media)
            else:
                time.sleep(2)
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(encode({'event': 'worker_error', 'type': type(exc).__name__}), flush=True)
            time.sleep(2)


if __name__ == '__main__':
    main()

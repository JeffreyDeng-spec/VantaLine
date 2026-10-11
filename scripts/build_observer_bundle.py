"""Build fixed, hash-locked wheels; never execute service-environment code."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import urllib.request
import zipfile

from observer_bundle_contract import observer_bundle_lock, observer_member_name, verify_observer_bundle


def build_observer_bundle(output, lock_path):
    output = Path(output)
    lock_path = Path(lock_path)
    lock = observer_bundle_lock(lock_path)
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    allowed = {'psycopg', 'psycopg_binary', 'psycopg_binary.libs', 'typing_extensions.py',
               'psycopg-3.3.4.dist-info', 'psycopg_binary-3.3.4.dist-info',
               'typing_extensions-4.15.0.dist-info'}
    for wheel in lock['wheels']:
        with urllib.request.urlopen(wheel['url'], timeout=60) as response:
            raw = response.read(20*1024*1024+1)
        if len(raw) > 20*1024*1024 or hashlib.sha256(raw).hexdigest() != wheel['sha256']:
            raise RuntimeError('Observer wheel checksum differs')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or len(infos) != len({info.filename for info in infos}):
                raise RuntimeError('Invalid observer wheel archive')
            for info in infos:
                name = info.filename.rstrip('/') if info.is_dir() else info.filename
                path = observer_member_name(name)
                if path.parts[0] not in allowed:
                    raise RuntimeError('Unexpected observer dependency')
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise RuntimeError('Invalid observer wheel member type')
                destination = output/name
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                if name in files or info.file_size > 20*1024*1024:
                    raise RuntimeError('Invalid observer wheel file')
                data = archive.read(info)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                files[name] = hashlib.sha256(data).hexdigest()
    manifest = {'schema': 1, 'lock_sha256': hashlib.sha256(lock_path.read_bytes()).hexdigest(), 'files': files}
    (output/'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2)+'\n', encoding='utf8')
    verify_observer_bundle(output, lock_path, require_root=False, require_runtime=False)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    value = build_observer_bundle(args.output, Path(__file__).resolve().parents[1]/'release/observer-dependencies.json')
    print(json.dumps({'schema': 1, 'files': len(value['files']), 'lock_sha256': value['lock_sha256']}))

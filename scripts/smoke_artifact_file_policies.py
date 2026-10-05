"""File hashing and generated-name contracts using synthetic byte streams."""
import ast
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_FILE_POLICIES_BASELINE_SOURCE')


def create(reader):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in {'file_sha256', 'safe_name'}]
        assert len(nodes) == 2
        namespace = dict(Path=Path, hashlib=hashlib, time=time, uuid=uuid, _business_files=reader)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), namespace)
        return SimpleNamespace(**namespace)
    from local_inspection_service.storage.artifacts.files import FileDigest
    from local_inspection_service.runtime.service_paths import safe_name
    return SimpleNamespace(file_sha256=FileDigest(lambda: reader).file_sha256, safe_name=safe_name)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.opened = []
        self.closed = []
        self.read_sizes = []
        self.payload = b'x' * (1024 * 1024 + 17)
        self.failure = None
        self.exit_failure = None
        owner = self
        class Stream(io.BytesIO):
            def read(self, size):
                owner.read_sizes.append(size)
                if owner.failure:
                    raise owner.failure
                return super().read(size)
        @contextmanager
        def open_read(path):
            self.opened.append(path)
            stream = Stream(self.payload)
            try:
                yield stream
            finally:
                stream.close()
                self.closed.append(stream.closed)
                if self.exit_failure:
                    raise self.exit_failure
        self.reader = SimpleNamespace(open_read=open_read)
        self.api = create(self.reader)

    def test_chunked_hash_and_close(self):
        path = Path('/synthetic/file')
        self.assertEqual(self.api.file_sha256(path), hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(self.opened, [path])
        self.assertEqual(self.read_sizes, [1024 * 1024] * 3)
        self.assertEqual(self.closed, [True])

    def test_empty_file_hash(self):
        self.payload = b''
        self.assertEqual(self.api.file_sha256(Path('empty')), hashlib.sha256(b'').hexdigest())
        self.assertEqual(self.closed, [True])

    def test_os_error_and_non_os_error_read_cleanup(self):
        self.failure = OSError('read')
        self.assertIsNone(self.api.file_sha256(Path('missing')))
        self.failure = ValueError('decode')
        with self.assertRaises(ValueError) as caught:
            self.api.file_sha256(Path('invalid'))
        self.assertIs(caught.exception, self.failure)
        self.assertEqual(self.closed, [True, True])

    def test_context_exit_error_boundary(self):
        self.exit_failure = OSError('close')
        self.assertIsNone(self.api.file_sha256(Path('close')))
        self.exit_failure = RuntimeError('close')
        with self.assertRaises(RuntimeError) as caught:
            self.api.file_sha256(Path('close'))
        self.assertIs(caught.exception, self.exit_failure)

    def test_open_error_boundary(self):
        def opening(path):
            raise PermissionError('open')
        self.reader.open_read = opening
        self.assertIsNone(self.api.file_sha256(Path('denied')))
        self.assertEqual(self.closed, [])

    def test_name_components_default_and_truncation(self):
        with patch.object(time, 'time', return_value=123.9), patch.object(uuid, 'uuid4', return_value=SimpleNamespace(hex='abcdef019999')):
            for value in ('a b.JPG', 'plain', '', 'x' * 100 + '.PNG', 'folder/name.tAr', 'a:b?.jpg'):
                expected = f"123_abcdef01_{Path(value).stem.replace(' ', '_')[:80] or 'upload'}{Path(value).suffix.lower() or '.bin'}"
                self.assertEqual(self.api.safe_name(value), expected)

    def test_filename_failure_before_clock(self):
        with patch.object(time, 'time', side_effect=AssertionError('clock must not run')):
            with self.assertRaises(TypeError):
                self.api.safe_name(None)

    @unittest.skipIf(bool(BASELINE), 'candidate isolated file provider')
    def test_selected_file_provider_and_no_implicit_runtime(self):
        from local_inspection_service.storage.artifacts.files import FileDigest
        calls = []
        digest = FileDigest(lambda: calls.append('provider') or self.reader)
        self.assertEqual(calls, [])
        digest.file_sha256(Path('fixture'))
        self.assertEqual(calls, ['provider'])


if __name__ == '__main__':
    unittest.main()

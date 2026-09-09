#!/usr/bin/env python3
"""Isolated direct-DOC extraction controls; real documents use benchmark script."""
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from local_inspection_service import document_images as module

DOC = bytes.fromhex("d0cf11e0a1b11ae1") + b"fixture"


def picture():
    stream = io.BytesIO(); Image.new("RGB", (40, 30), "white").save(stream, "PNG")
    return stream.getvalue()


def output(path, names=("image0001.bin",), contents=None):
    with zipfile.ZipFile(path, "w") as z:
        for name in names: z.writestr(name, contents or picture())
        z.writestr("manifest.tsv", "doc-images-v1\tpoi-5.5.1\n" + "".join(name+"\t0\n" for name in names))


class DocTests(unittest.TestCase):
    def test_bad_signature(self):
        with self.assertRaises(module.DocImageError): module.extract_doc_images(b"fake.doc")

    def test_missing_runtime(self):
        with patch.dict(module.os.environ, {"VANTALINE_DOC_IMAGE_BUNDLE": ""}):
            with self.assertRaises(module.DocImageUnavailable): module.extract_doc_images(DOC)

    def test_original_pixels_duplicates_and_pending(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/"images.zip"; output(path, ("image0001.bin", "image0002.bin"))
            items, blobs = module._read_output(path)
        self.assertEqual(blobs, [picture(), picture()])
        self.assertEqual(items[1]["duplicate_of"], items[0]["asset_id"])
        self.assertEqual(items[0]["status"], "needs_confirmation")

    def test_bad_paths_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/"images.zip"; output(path, ("../escape.bin",))
            with self.assertRaises(module.DocImageError): module._read_output(path)

    def test_unsupported_image_retained(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work)/"images.zip"; output(path, contents=b"undecodable image bytes")
            items, blobs = module._read_output(path)
        self.assertEqual(blobs, [b"undecodable image bytes"])
        self.assertEqual(items[0]["classification_reason"], "embedded_image_preview_unavailable")

    def test_process_environment_and_cleanup(self):
        visited = []
        class Process:
            def __init__(self, command, **kwargs):
                visited.append(Path(kwargs["cwd"]))
                assert "SECRET_KEY" not in kwargs["env"]
                assert "JAVA_TOOL_OPTIONS" not in kwargs["env"]
                assert "-Xmx256m" in command
                output(Path(command[-1]))
            def wait(self, timeout): return 0
        with patch.object(module, "_runtime", return_value=("java", "fixture.jar")), patch.object(module.subprocess, "Popen", Process), patch.dict(module.os.environ, {"SECRET_KEY": "test", "JAVA_TOOL_OPTIONS": "bad"}):
            module.extract_doc_images(DOC)
        self.assertFalse(visited[0].exists())

    def test_timeout_and_busy(self):
        class Process:
            pid = 123456
            def wait(self, timeout=None):
                if timeout: raise subprocess.TimeoutExpired("fixture", timeout)
        with patch.object(module, "_runtime", return_value=("java", "fixture.jar")), patch.object(module.subprocess, "Popen", return_value=Process()), patch.object(module.os, "killpg") as kill:
            with self.assertRaises(module.DocImageError): module.extract_doc_images(DOC)
            kill.assert_called_once_with(123456, module.signal.SIGKILL)
        module._slot.acquire()
        try:
            with patch.object(module, "_runtime", return_value=("java", "fixture.jar")):
                with self.assertRaises(module.DocImageUnavailable): module.extract_doc_images(DOC)
        finally: module._slot.release()


if __name__ == "__main__": unittest.main()

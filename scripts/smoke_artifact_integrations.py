#!/usr/bin/env python3
"""Storage adapters with real HTTP middleware, synthetic accounts/bytes, no cloud."""
import ast
import asyncio
import hashlib
import io
from pathlib import Path, PurePosixPath
import sys
import unittest
import zipfile

from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from smoke_artifact_storage import StorageTests
from local_inspection_service.auth.middleware import SecurityDependencies, register_security_middleware
from local_inspection_service.runtime.identity import RequestIdentity
from local_inspection_service.storage.artifacts.runtime import ArtifactRuntime
from local_inspection_service.storage.artifacts.files import BusinessFiles
from local_inspection_service.storage.artifacts.http import ArtifactStaticFiles
from local_inspection_service.storage.artifacts.types import ArtifactUnavailable
from local_inspection_service.codex_compare.media import MediaStore
from local_inspection_service.text_inspection.media import TextMedia, TextMediaRecords
from local_inspection_service.training.dataset_archives import DatasetArchives


class IntegrationTests(unittest.TestCase):
    setUp = StorageTests.setUp
    tearDown = StorageTests.tearDown
    put = StorageTests.put

    def runtime(self, mode="cos"):
        return ArtifactRuntime(self.store, self.root.resolve(), mode)

    def test_startup_guide_provenance_hashes_cos_bytes_without_local_source(self):
        from unittest.mock import patch
        from local_inspection_service.accessories import image_job_metadata
        from local_inspection_service.training import dataset_archives
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        row = self.put("anchor_pose_guides/fixture.png", b"verified guide bytes")
        path = self.root / row.path
        self.assertFalse(path.exists())
        files = BusinessFiles(runtime_provider=self.runtime)
        metadata = image_job_metadata.ImageJobMetadata(
            image_job_metadata.ProvenanceDependencies(
                lambda path: dataset_archives.file_sha256(path, files=files), lambda: "fixture",
                lambda: {"circle": [path]}, lambda: 8,
            ), None, files=files
        )
        job = {"pose_family": "circle", "input_files": []}
        self.assertTrue(metadata.ensure_image_job_target_guides(job))
        self.assertEqual(job["target_guide_sha256"], {path.name: row.sha256})
        self.assertFalse(path.exists())
        self.assertFalse(metadata.ensure_image_job_target_guides(job))

    def test_detection_native_port_publishes_verified_bytes_and_propagates_failure(self):
        import cv2
        import numpy as np
        from unittest.mock import patch
        from local_inspection_service.detection.inspection_image_store import InspectionImageStore
        from local_inspection_service.detection.media_ports import InspectionImagePolicy
        from local_inspection_service.storage.artifacts.images import image_backend
        self.budget.limits.update(cache=1024 * 1024, upload=1024 * 1024)
        self.budget.free_bytes = lambda: 10 * 1024 * 1024
        policy = InspectionImagePolicy(lambda: self.root / "outputs/inspection", lambda: 100, lambda: 90)
        writer = InspectionImageStore(lambda: cv2, policy, lambda: 1, lambda s: s, runtime_provider=self.runtime)
        pixels = np.full((8, 8, 3), 120, dtype=np.uint8)
        with patch("local_inspection_service.storage.artifacts.images.get_runtime", self.runtime):
            path = writer.write_mcp_inspection_image(pixels, "fixture")
            self.assertFalse(path.exists())
            restored = image_backend(cv2).imread(str(path))
            np.testing.assert_array_equal(restored, pixels)
            before = dict(self.locations.rows)
            self.client.fail = True
            with self.assertRaises(ArtifactUnavailable):
                writer.write_mcp_inspection_image(pixels, "failed")
            self.assertEqual(self.locations.rows, before)

    def test_storage_failure_does_not_trigger_paid_teacher_fallback(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from local_inspection_service.detection.analysis import DetectionAnalysis
        inputs = SimpleNamespace(scope=lambda: lambda v: v, load=lambda: {},
                                 select=lambda *a: {"is_ai_detection": True, "task_id": "fixture"},
                                 task_id=lambda: lambda v: v,
                                 state=lambda _: {"settings": {"enabled": True, "serving_mode": "promoted_yolo"},
                                                  "active_model_id": "fixture"})
        paid = Mock()
        routing = SimpleNamespace(analyze=Mock(side_effect=ArtifactUnavailable("synthetic COS failure")), ai=paid)
        with self.assertRaises(ArtifactUnavailable):
            DetectionAnalysis(inputs, routing, None, None, runtime_provider=lambda: None).analyze_bgr(None, "fixture")
        paid.assert_not_called()

    def test_retention_tombstones_index_and_keeps_remote_history(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from local_inspection_service.text_inspection import incoming_retention
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        source = self.put("outputs/incoming/source.png", b"history")
        record = {"id": "fixture", "created_at": 1, "source_path": str(self.root / source.path)}
        repository = Mock()
        repository.incoming_text_retention_candidates.return_value = [record]
        repository.mark_incoming_text_evidence_purged.return_value = True
        media = SimpleNamespace(root=lambda: self.root / "outputs", under=lambda p, root: p.is_relative_to(root))
        retention = incoming_retention.IncomingRetention(None, media, SimpleNamespace(repository=lambda: repository),
                                                         None, lambda: Mock(), lambda: "system",
                                                         files=BusinessFiles(runtime_provider=self.runtime))
        self.locations.fail = True
        with self.assertRaises(RuntimeError):
            retention.purge()
        repository.mark_incoming_text_evidence_purged.assert_not_called()
        self.locations.fail = False
        self.assertEqual(retention.purge(), {"records": 1, "files": 1})
        self.assertEqual(self.locations.rows[source.path].state, "deleted")
        self.assertEqual(self.client.rows[source.key], b"history")

    def test_multipart_admission_precedes_handler_and_releases_reservations(self):
        from fastapi import UploadFile, File
        from local_inspection_service.storage.artifacts.admission import UploadAdmission
        app, called = FastAPI(), []
        self.budget.limits["upload"] = 2000
        app.add_middleware(UploadAdmission, runtime_provider=self.runtime)
        @app.post("/upload")
        async def upload(file: UploadFile = File(...)):
            called.append(await file.read())
            return {"ok": True}
        with TestClient(app) as client:
            self.assertEqual(client.post("/upload", files={"file": ("a.png", b"small")}).status_code, 200)
            with self.budget.reserve("upload", 1950):
                self.assertEqual(client.post("/upload", files={"file": ("a.png", b"small")}).status_code, 503)
            self.assertEqual(client.post("/upload", files={"file": ("a.png", b"x" * 1100)}).status_code, 413)
            self.assertEqual(client.post("/upload", content=iter([b"x"]),
                                        headers={"content-type": "multipart/form-data; boundary=a"}).status_code, 411)
            self.assertEqual(client.post("/upload", files={"file": ("a.png", b"small")},
                                        headers={"content-length": "2"}).status_code, 413)
        self.assertEqual(called, [b"small"])
        self.assertFalse(list((self.budget.root / "reservations").iterdir()))

    def test_document_update_binds_generation_at_read_time(self):
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        from local_inspection_service.storage.artifacts.types import ArtifactConflict
        files = BusinessFiles(runtime_provider=self.runtime)
        path = self.root / "backgrounds/manifest.json"
        files.write_json(path, {"sets": {}})
        first, stale = files.read_json(path), files.read_json(path)
        first["sets"]["a"] = {"name": "first"}
        files.write_json(path, first)
        stale["sets"]["b"] = {"name": "stale"}
        with self.assertRaises(ArtifactConflict):
            files.write_json(path, stale)
        self.assertEqual(list(files.read_json(path)["sets"]), ["a"])

    def test_runpod_unknown_submission_is_not_repeated_and_disk_rejection_is_pre_call(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from local_inspection_service.training.runpod_flow import RunPodFlow
        from local_inspection_service.storage.artifacts.types import ArtifactConflict, DiskCapacityError
        submit = Mock(side_effect=TimeoutError("synthetic uncertain submission"))
        flow = RunPodFlow(None, None, SimpleNamespace(submit=submit), None, runtime_provider=self.runtime)
        with self.assertRaises(DiskCapacityError):
            flow._submit_once("fixture", {})
        submit.assert_not_called()
        self.budget.limits["upload"] = 1024 ** 3
        self.budget.free_bytes = lambda: 3 * 1024 ** 3
        with self.assertRaises(TimeoutError):
            flow._submit_once("fixture", {})
        with self.assertRaises(ArtifactConflict):
            flow._submit_once("fixture", {})
        submit.assert_called_once()
        self.assertFalse(list((self.budget.root / "reservations").iterdir()))

    def test_uncertain_cursor_write_does_not_submit_fallback(self):
        # Exercise the assembled worker function without model initialization or
        # external calls. The provider succeeds; persistence then fails.
        from unittest.mock import Mock, patch
        from dataclasses import fields
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        from local_inspection_service.accessories import image_job_execution
        from local_inspection_service.accessories.image_job_execution_ports import ImageExecutionFiles, ImageExecutionEvidence, ImageExecutionProviders
        import time
        output = self.root / "outputs/result.png"
        files = BusinessFiles(runtime_provider=self.runtime)
        input_path = self.root / "uploads/input.png"
        self.put("uploads/input.png", b"input")
        fallback, status = Mock(), Mock()
        scope = {"Path": Path, "Any": object, "time": time, "json": __import__("json"),
                 "image_job_output_path": lambda *a, **k: output, "IMAGE_WORKER_LOG_DIR": self.root / "image_worker_logs",
                 "safe_name": lambda v: v, "resolve_service_path": Path, "_business_files": files,
                 "cursor_image2_settings": lambda: {"configured": True, "endpoint_public": "fixture", "model": "fixture",
                                                     "endpoint": "fixture", "api_key": "fixture", "timeout_seconds": 1},
                 "CURSOR_IMAGE2_PROVIDER": "fixture", "run_codex_image_job": fallback,
                 "update_image_worker_status": status, "public_output_url": str,
                 "cursor_image2_payload": lambda *a: {}, "cursor_auth_headers": lambda *a: {},
                 "requests": Mock(), "extract_cursor_image2_bytes": lambda *a: b"image"}
        # The pre-call log fits; publication of the generated image fails.
        self.budget.limits["upload"] = 4096
        scope["requests"].post.return_value.json.return_value = {}
        original = files.write_bytes
        def write(path, data):
            if path == output:
                raise ArtifactUnavailable("synthetic upload failure")
            return original(path, data)
        files.write_bytes = write
        def ports(cls):
            return cls(**{field.name: lambda name=field.name: scope[name] for field in fields(cls)})
        worker = image_job_execution.ImageJobExecution(ports(ImageExecutionFiles), ports(ImageExecutionEvidence), ports(ImageExecutionProviders))
        with patch.object(image_job_execution, "requests", scope["requests"]):
            worker.run_cursor_image2_job(self.root / "candidate", {}, {"input_files": [str(input_path)]})
        scope["requests"].post.assert_called_once()
        fallback.assert_not_called()
        self.assertEqual(status.call_args.kwargs["status"], "failed")

    def test_comparison_media_two_accounts_and_no_local_files(self):
        media = MediaStore(self.root / "codex_comparisons", runtime_provider=self.runtime)
        sha = media.put("alice", b"image")
        self.assertFalse(media.path("alice", sha).exists())
        self.assertEqual(media.read("alice", sha), b"image")
        with self.assertRaises(FileNotFoundError):
            media.read("bob", sha)
        self.assertEqual(media.put("alice", b"image"), sha)
        self.assertEqual(len(self.client.calls), 1)

    def test_hybrid_tombstone_never_resurrects_local_comparison_media(self):
        media = MediaStore(self.root / "codex_comparisons", runtime_provider=lambda: self.runtime("hybrid"))
        sha = media.put("alice", b"image")
        path = media.path("alice", sha)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"image")
        self.store.remove(self.runtime().key(path), expected_generation=1)
        with self.assertRaises(FileNotFoundError):
            media.read("alice", sha)

    def test_text_media_integrity_owner_and_upload_failure(self):
        media = TextMedia(lambda: self.root / "text_inspection_v2", lambda b: hashlib.sha256(b).hexdigest(),
                          TextMediaRecords(lambda: None, lambda *args: True), runtime_provider=self.runtime)
        path = media.media_path("alice", "std", "source.png")
        media.write(path, b"source")
        self.assertFalse(path.exists())
        self.assertEqual(media.read_verified(str(path), "alice", "std"), b"source")
        for owner, standard, sha in [("bob", "std", ""), ("alice", "wrong", ""), ("alice", "std", "0"*64)]:
            with self.assertRaises(HTTPException):
                media.read_verified(str(path), owner, standard, expected_sha256=sha)
        self.client.fail = True
        with self.assertRaises(ArtifactUnavailable):
            media.write(path, b"changed")
        self.assertEqual(self.store.stat(self.runtime().key(path)).generation, 1)

    def http(self):
        outputs = self.root / "outputs"
        outputs.mkdir(exist_ok=True)
        app = FastAPI()
        from local_inspection_service.auth.account_projections import AccountProjections
        from local_inspection_service.auth.account_projection_ports import AccountAccess, AccountConfig, AccountModels, AccountMedia
        from dataclasses import fields
        bindings = {"OUTPUT_DIR": outputs, "user_is_admin": lambda u: u.get("role") == "admin"}
        def ports(cls):
            return cls(**{field.name: lambda name=field.name: bindings[name] for field in fields(cls)})
        ownership = AccountProjections(ports(AccountAccess), ports(AccountConfig), ports(AccountModels), ports(AccountMedia))
        def authenticate(request, **kwargs):
            owner = request.headers.get("x-test-owner")
            return ({"id": owner, "role": "user"} if owner else None, {"users": True}, False)
        register_security_middleware(app, SecurityDependencies(
            authenticate, lambda store: True, RequestIdentity(), ownership.output_path_visible_to_user,
            lambda *args: True, lambda *args: False))
        app.mount("/outputs", ArtifactStaticFiles(directory=outputs, runtime_provider=self.runtime))
        return TestClient(app)

    def test_http_owner_head_range_etag_and_legacy_share(self):
        self.put(contents=b"0123456789")
        self.put("outputs/legacy.png", b"legacy")
        with self.http() as client:
            url = "/outputs/users/a/image.png"
            self.assertEqual(client.get(url).status_code, 401)
            self.assertEqual(client.get(url, headers={"x-test-owner": "b"}).status_code, 404)
            headers = {"x-test-owner": "a"}
            response = client.get(url, headers=headers)
            self.assertEqual(response.content, b"0123456789")
            self.assertEqual(response.headers["content-type"], "image/png")
            head = client.head(url, headers=headers)
            self.assertEqual((head.status_code, head.content, head.headers["content-length"]), (200, b"", "10"))
            response = client.get(url, headers={**headers, "range": "bytes=2-4"})
            self.assertEqual((response.status_code, response.content), (206, b"234"))
            self.assertEqual(client.get(url, headers={**headers, "range": "bytes=99-100"}).status_code, 416)
            self.assertEqual(client.get(url, headers={**headers, "if-none-match": head.headers["etag"]}).status_code, 304)
            self.assertEqual(client.get("/outputs/legacy.png", headers={"x-test-owner": "b"}).content, b"legacy")

    def test_http_cos_failure_is_redacted_and_never_serves_old_local_file(self):
        row = self.put()
        local = self.root / row.path
        local.parent.mkdir(parents=True)
        local.write_bytes(b"stale")
        self.client.fail = True
        with self.http() as client:
            response = client.get("/" + row.path, headers={"x-test-owner": "a"})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(b"signed-secret", response.content)
            self.assertNotIn(b"stale", response.content)

    def test_cos_training_packages_without_local_dataset_and_keeps_original_bytes(self):
        self.budget.limits["work"] = 4*1024*1024
        self.budget.free_bytes = lambda: 20*1024*1024
        prefix = "outputs/users/a/dataset"
        self.put(prefix + "/images/train/a.png", b"native-png")
        self.put(prefix + "/labels/train/a.txt", b"0 0.5 0.5 0.2 0.2")
        self.put(prefix + "/previews/a.png", b"preview")
        archives = DatasetArchives(lambda s: s, lambda: {"previews"}, lambda: 90,
                                   lambda p: self.fail("no source disk access"), runtime_provider=self.runtime)
        dataset = self.root / prefix
        self.assertFalse(dataset.exists())
        self.assertEqual(len(archives.dataset_file_manifest(dataset)), 3)
        temp, path = archives.build_worker_training_bundle(dataset, "fixture")
        try:
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), ["images/train/a.png", "labels/train/a.txt"])
                self.assertEqual(archive.read("images/train/a.png"), b"native-png")
            with self.assertRaises(ArtifactUnavailable):
                archives.package_training_dataset(dataset, "second")
        finally:
            temp.cleanup()
        self.assertFalse(path.exists())

    def test_corrupt_training_input_never_returns_successful_package(self):
        self.budget.limits["work"] = 4*1024*1024
        self.budget.free_bytes = lambda: 20*1024*1024
        self.put("outputs/dataset/image.png", b"image")
        self.client.corrupt = True
        from local_inspection_service.storage.artifacts.archives import package
        with self.assertRaises(ArtifactUnavailable):
            package(self.store, "outputs/dataset")
        self.assertFalse(list((self.budget.root / "scratch").iterdir()))

    def test_runpod_export_token_download_upload_and_model_import(self):
        from local_inspection_service.training.runpod_exports import RunPodExports, RunPodExportPaths, RunPodExportPolicy
        from local_inspection_service.training.runpod_transfer import RunPodTrainingTransfer, TransferPaths
        from local_inspection_service.training.runpod_upload_store import RunPodUploadStore
        from local_inspection_service.training.runpod_artifacts import RunPodArtifacts, RunPodArtifactPaths
        self.budget.limits.update(work=4*1024*1024, upload=2*1024*1024, cache=2*1024*1024)
        self.budget.free_bytes = lambda: 20*1024*1024
        output = self.root / "outputs"
        dataset = output / "users/alice/training_datasets/sample"
        self.put(self.runtime().key(dataset / "images/train/a.png"), b"image")
        tasks = {"job": {"job_id": "job", "owner_user_id": "alice"}}
        updates = []
        def update(job, **values):
            updates.append(values)
            tasks[job].update(values)
        digest = lambda data: hashlib.sha256(data).hexdigest()
        archives = DatasetArchives(str, lambda: set(), lambda: 90, lambda p: digest(p.read_bytes()), runtime_provider=self.runtime)
        output_path = lambda kind, owner: output / "users" / owner / kind
        exports = RunPodExports(RunPodExportPaths(lambda: Path, output_path, str),
                                RunPodExportPolicy(lambda s: digest(s.encode()), lambda: 300, lambda: "https://fixture.invalid"),
                                archives.build_worker_training_bundle, lambda p: digest(p.read_bytes()), lambda: update,
                                runtime_provider=self.runtime)
        exported = exports.create_runpod_training_dataset_archive("job", tasks["job"], {"dataset_dir": str(dataset)})
        self.assertFalse(Path(exported["path"]).exists())
        token = exported["url"].split("/")[-2]
        receiver = RunPodUploadStore(lambda: 2*1024*1024, runtime_provider=self.runtime)
        transfers = RunPodTrainingTransfer(tasks.get, lambda s: digest(s.encode()), lambda: 0,
                                          TransferPaths(lambda: Path, lambda: output), receiver, lambda: update,
                                          runtime_provider=self.runtime)
        app = FastAPI()
        @app.get("/download/{token}")
        def download(token):
            return transfers.download_runpod_training_dataset("job", token)
        with TestClient(app) as client:
            self.assertEqual(client.get("/download/wrong").status_code, 404)
            response = client.get("/download/" + token)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(digest(response.content), exported["sha256"])
        upload = exports.create_runpod_training_artifact_upload("job", tasks["job"])
        upload_token = upload["url"].split("/")[-2]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("train/weights/best.pt", b"synthetic-model")
        class Body:
            async def stream(self):
                yield buffer.getvalue()
        received = asyncio.run(transfers.upload_runpod_training_artifact("job", upload_token, Body()))
        self.assertTrue(received["ok"])
        self.assertFalse(Path(upload["path"]).exists())
        importer = RunPodArtifacts(RunPodArtifactPaths(Path, lambda: output, lambda: output_path),
                                  tasks.get, lambda value: value, runtime_provider=self.runtime)
        result = importer.import_runpod_yolo_artifacts(tasks["job"], {"artifacts": {"best_pt": {"sha256": digest(b"synthetic-model")}}})
        self.assertEqual(self.store.read_bytes(self.runtime().key(Path(result["imported_model_path"])), max_bytes=100), b"synthetic-model")
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        from local_inspection_service.detection.local_models import LocalModels
        loaded_paths = []
        def load(path):
            loaded_paths.append(Path(path))
            self.assertEqual(Path(path).suffix, ".pt")
            return Path(path).read_bytes()
        models = LocalModels(lambda *args: {"id": "model", "path": result["imported_model_path"]},
                             lambda: load, lambda: [], lambda config: [], files=BusinessFiles(self.runtime))
        self.assertEqual(models.model("model"), b"synthetic-model")
        self.assertFalse(loaded_paths[0].exists())
        # A failed replacement upload cannot report success or update task refs.
        count = len(updates)
        self.client.fail = True
        with self.assertRaises(ArtifactUnavailable):
            asyncio.run(transfers.upload_runpod_training_artifact("job", upload_token, Body()))
        self.assertEqual(len(updates), count)
        self.assertFalse(list((self.budget.root / "scratch").iterdir()))

    def test_native_images_roundtrip_without_business_disk_and_fail_closed(self):
        import cv2
        import numpy as np
        from PIL import Image
        from local_inspection_service.storage.artifacts.images import ImageFiles
        from local_inspection_service.storage.artifacts.files import BusinessFiles
        self.budget.limits.update(cache=100000, upload=100000)
        self.budget.free_bytes = lambda: 1000000
        media = ImageFiles(lambda: cv2, lambda: Image, files=BusinessFiles(self.runtime))
        source = np.full((20, 30, 3), (23, 71, 119), dtype=np.uint8)
        path = self.root / "outputs/users/alice/sprite.png"
        self.assertTrue(media.imwrite(str(path), source))
        self.assertFalse(path.exists())
        np.testing.assert_array_equal(media.imread(str(path)), source)
        with media.open(path) as image:
            self.assertEqual(image.size, (30, 20))
            target = self.root / "backgrounds/fixture/copy.png"
            media.save(image, target, format="PNG")
        np.testing.assert_array_equal(media.imread(str(target)), source)
        self.assertTrue(media.files.exists(target))
        media.files.unlink(target)
        self.assertFalse(media.files.exists(target))
        self.client.fail = True
        with self.assertRaises(ArtifactUnavailable):
            media.imwrite(str(path), source + 1)
        self.assertEqual(self.store.stat(self.runtime().key(path)).generation, 1)

    def test_ordinary_upload_is_persisted_before_analysis_and_failure_stops_it(self):
        import cv2
        import numpy as np
        from types import SimpleNamespace
        from unittest.mock import patch
        from fastapi import UploadFile
        from local_inspection_service.detection import image_upload
        self.budget.limits.update(upload=100000, cache=100000)
        self.budget.free_bytes = lambda: 1000000
        payload = cv2.imencode(".png", np.zeros((20, 30, 3), dtype=np.uint8))[1].tobytes()
        analyzed = []
        def analyze(image, request_id, model_id, *, image_path):
            self.assertEqual(self.store.stat(self.runtime().key(image_path)).sha256, hashlib.sha256(payload).hexdigest())
            analyzed.append(request_id)
            return {"ok": True}
        service = image_upload.ImageUpload(SimpleNamespace(ensure=lambda: None, permit=lambda model: None),
                                         SimpleNamespace(name=lambda: (lambda filename: "fixture.png"), directory=lambda: self.root / "uploads"),
                                         lambda: np, lambda: cv2, analyze, files=lambda: BusinessFiles(runtime_provider=self.runtime))
        with self.subTest(storage="explicit runtime"):
            result = asyncio.run(service.analyze_image(UploadFile(file=io.BytesIO(payload), filename="image.png"), None))
            self.assertTrue(result["ok"])
            self.client.fail = True
            with self.assertRaises(ArtifactUnavailable):
                asyncio.run(service.analyze_image(UploadFile(file=io.BytesIO(payload), filename="image.png"), None))
        self.assertEqual(analyzed, ["fixture"])
        self.assertFalse((self.root / "uploads/fixture.png").exists())


if __name__ == "__main__":
    unittest.main(defaultTest="IntegrationTests")

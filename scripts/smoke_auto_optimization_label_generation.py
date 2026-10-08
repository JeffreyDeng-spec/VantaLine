"""Original/candidate auto-label generation with synthetic images and providers."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auto_optimization_test_ports import assert_capability_owner
from local_inspection_service.model_providers.errors import AiProviderError

BASELINE = os.environ.get("VANTALINE_AUTO_LABEL_GENERATION_BASELINE_SOURCE")
NAMES = {"auto_optimize_generate_labels_for_sample", "auto_optimize_generate_label_for_candidate"}


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == 2
        namespace = dict(bindings, Any=Any, Path=Path, cv2=cv2, np=np, os=os, time=time)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, "exec"), namespace)
        return SimpleNamespace(**{name: namespace[name] for name in NAMES}), lambda name, value: namespace.__setitem__(name, value)
    from local_inspection_service.training.auto_optimization_label_generation import AutoOptimizationLabelGeneration
    from local_inspection_service.training.auto_optimization_label_generation_ports import LabelGenerationArtifacts, LabelGenerationPolicy, LabelGenerationModels
    def ports(kind): return kind(**{f.name: (lambda name=f.name: bindings[name]) for f in fields(kind)})
    service = AutoOptimizationLabelGeneration(ports(LabelGenerationArtifacts), ports(LabelGenerationPolicy), ports(LabelGenerationModels))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service, lambda name, value: bindings.__setitem__(name, value)


class GenerationContract(unittest.TestCase):
    def fixture(self, count=1):
        temporary = tempfile.TemporaryDirectory(prefix="auto-label-contract-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); events = []
        image = np.full((24, 24, 3), 80, np.uint8); mask = np.full((24, 24), 255, np.uint8)
        candidates = [{"accessory_id": str(i), "label": "part " + str(i), "confidence": .9} for i in range(count)]
        sample = {"sample_id": "s", "source_image": {"path": "source.jpg"}, "candidate_accessories": candidates}
        settings = {"provider": "fixture"}
        state = {"readable": True, "source_readable": True, "encode": True, "mask": True, "bbox": [1, 1, 23, 23],
                 "gate": {"ok": True}, "compare": {"ok": True, "score": .8}, "decode": {"ok": True}}
        palette = [{"name": "green", "hex": "#00ff00", "bgr": [0, 255, 0]}, {"name": "red", "hex": "#ff0000", "bgr": [0, 0, 255]}]
        def read(path, flag):
            events.append(("read", Path(path).name))
            return image.copy() if state["source_readable" if Path(path).name == "source.jpg" else "readable"] else None
        def write(path, value, *args): events.append(("image-write", Path(path).name, value.copy())); return False
        def raw(path, data): events.append(("write-bytes", Path(path).name, data))
        def unlink(path, **kw): events.append(("unlink", Path(path).name, kw))
        def provider(*args):
            events.append(("provider", args))
            return {"bytes": b"synthetic", "latency_ms": 5, "attempts": 2, "retry_count": 1, "previous_errors": ["retry"], "usage_metadata": {"fixture": 1}}
        def decode(array, assignments):
            return ({str(a["candidate"]["accessory_id"]): mask.copy() for a in assignments} if state["mask"] else {}), {"ok": True}
        def sprite(**kwargs): events.append(("sprite", kwargs)); return {"url": "sprite", "raw_url": "raw"}
        def verify(sample, array, labels): events.append(("verify", list(labels))); return labels, [], {"enabled": True, "status": "accept"}
        bindings = {
            "resolve_service_path": lambda p: root / p, "_image_files": SimpleNamespace(imread=read, imwrite=write),
            "_business_files": SimpleNamespace(write_bytes=raw, unlink=unlink), "public_output_url_for_existing": lambda p: p.name,
            "safe_record_id": lambda v: v, "photo_highlight_input_data_url": lambda a: (a.copy(), "fixture-image", 1., 1.) if state["encode"] else None,
            "auto_optimize_accessory_lookup_for_sample": lambda s: {}, "auto_optimize_mask_target_profile": lambda c, a: {"visual_signature": "fixture"},
            "AUTO_OPTIMIZE_MASK_PALETTE": palette, "AUTO_OPTIMIZE_MASK_PROMPT_MODE": "fixture-mode",
            "auto_optimize_multicolor_mask_prompt": lambda assignments, **kw: "fixture-prompt:" + ",".join(a["candidate"]["accessory_id"] for a in assignments),
            "auto_optimize_generate_image_with_retry": provider, "AiProviderError": AiProviderError, "bounded_text": lambda v, n: str(v)[:n],
            "decode_multicolor_mask": decode, "alpha_bbox": lambda a, **kw: state["bbox"],
            "validate_auto_optimize_text_mask_region": lambda *a: state["gate"], "auto_optimize_write_sprite_artifact": sprite,
            "verify_auto_optimize_mask_sample": verify, "draw_auto_optimize_review_overlay": lambda *a: ("review", {"fixture": True}),
            "decode_photo_highlight_mask": lambda a: (mask.copy(), state["decode"]),
            "photo_highlight_auto_roi_mask": lambda a, m: (m.copy(), {"fixture": True}),
            "photo_highlight_auto_compare": lambda *a: state["compare"],
        }
        service, replace = create(bindings)
        return SimpleNamespace(service=service, replace=replace, root=root, events=events, image=image,
                               sample=sample, candidates=candidates, settings=settings, state=state)

    def call(self, f, single=False, attempts="3", targets="1"):
        with patch.dict(os.environ, {"VANTALINE_AUTO_OPTIMIZE_MASK_TARGETS_PER_CALL": targets, "VANTALINE_AUTO_OPTIMIZE_MASK_GENERATION_ATTEMPTS": attempts}), patch.object(time, "time", return_value=100):
            if single: return f.service.auto_optimize_generate_label_for_candidate(f.sample, f.candidates[0], f.settings, "pinned-model", f.root)
            return f.service.auto_optimize_generate_labels_for_sample(f.sample, f.settings, "pinned-model", f.root)

    def test_early_exits(self):
        for single in (False, True):
            for setting, reason in (("source_readable", "source_image_unreadable"), ("encode", "source_image_encode_failed")):
                f = self.fixture(); f.state[setting] = False; result = self.call(f, single)
                self.assertEqual((result[1] if single else result[1][0])["reason"], reason)
                self.assertFalse(any(e[0] == "provider" for e in f.events))
        f = self.fixture(0); self.assertEqual(self.call(f)[1][0]["reason"], "no_present_single_accessory_candidates")

    def test_chunk_order_settings_identity_artifacts_and_cleanup(self):
        f = self.fixture(3); labels, failures, meta = self.call(f, targets="2")
        self.assertEqual([x["accessory_id"] for x in labels], ["0", "1", "2"]); self.assertEqual(failures, [])
        calls = [e[1] for e in f.events if e[0] == "provider"]
        self.assertEqual([c[2] for c in calls], ["fixture-prompt:0,1", "fixture-prompt:2"])
        for args in calls:
            self.assertIs(args[0], f.settings); self.assertEqual(args[1], "pinned-model")
            self.assertEqual(args[3], [{"type": "image_url", "image_url": {"url": "fixture-image", "detail": "high"}}])
        self.assertEqual([c["chunk_index"] for c in meta["api_calls"]], [0, 1])
        self.assertEqual(meta["class_check"], {"expected_count": 3, "matched_count": 3, "missing_count": 0, "status": "matched"})
        self.assertEqual((meta["started_at"], meta["completed_at"]), (100, 100))
        self.assertEqual(len([e for e in f.events if e[0] == "unlink"]), 2)
        self.assertTrue(all(not {"full_mask", "profile", "candidate"} & set(label) for label in labels))
        self.assertFalse(any(p.is_file() for p in f.root.rglob("*")))

    def test_provider_failures_and_unreadable_generated_images(self):
        for single in (False, True):
            f = self.fixture(); error = AiProviderError("x" * 220, attempts=3, retry_count=2, previous_errors=["a", "b", "c", "d"])
            def fail(*a): raise error
            f.replace("auto_optimize_generate_image_with_retry", fail)
            result = self.call(f, single); failure = result[1] if single else result[1][0]
            self.assertEqual(len(failure["reason"]), 180); self.assertEqual(failure["previous_errors"], ["b", "c", "d"])
            self.assertEqual(failure["attempts"], 3)
            f = self.fixture(); f.state["readable"] = False; result = self.call(f, single)
            self.assertEqual((result[1] if single else result[1][0])["reason"], "generated_mask_unreadable")
            self.assertEqual(len([e for e in f.events if e[0] == "unlink"]), 0 if single else 1)

    def test_retry_reason_allowlist_and_fallback_metadata(self):
        for reason, expected_calls in (("no_highlight_component", 2), ("mask_decode_failed", 2), ("provider_timeout", 1)):
            f = self.fixture(); f.state["mask"] = False; attempts = []
            def fallback(*a): attempts.append(a); return None, {"reason": reason, "full_mask": object()}
            f.replace("auto_optimize_generate_label_for_candidate", fallback)
            labels, failures, meta = self.call(f)
            self.assertEqual(len(attempts), expected_calls); self.assertEqual(labels, [])
            self.assertNotIn("full_mask", failures[0]["fallback_failure"])
            self.assertEqual(len(meta["api_calls"]), 1)
        f = self.fixture(); f.state["mask"] = False
        fallback = {"accessory_id": "0", "label": "fallback", "mask_meta": {}, "color_bgr": [0, 255, 0]}
        f.replace("auto_optimize_generate_label_for_candidate", lambda *a: (fallback, {"status": "review_required"}))
        labels, failures, meta = self.call(f)
        self.assertIs(labels[0], fallback); self.assertEqual(failures, [])
        self.assertEqual(fallback["mask_meta"]["generation_attempt"], 2)
        self.assertEqual(fallback["mask_meta"]["fallback_reason"], "retry_after_no_highlight_component")
        self.assertEqual(len(meta["api_calls"]), 2)

    def test_empty_scaled_fallback_keeps_existing_call_accounting(self):
        f = self.fixture(); f.state["bbox"] = [0, 0, 0, 0]
        item = {"accessory_id": "0", "mask_meta": {}}
        f.replace("auto_optimize_generate_label_for_candidate", lambda *a: (item, {}))
        labels, failures, meta = self.call(f)
        self.assertIs(labels[0], item); self.assertEqual(failures, [])
        self.assertEqual(item["mask_meta"]["fallback_reason"], "retry_after_empty_scaled_mask")
        self.assertEqual(len(meta["api_calls"]), 1)

    def test_single_review_label_and_artifact_write_exception(self):
        f = self.fixture(); f.state["compare"] = {"ok": False, "reason": "ai_mask_auto_crop_mismatch", "score": .2}
        def write(*a): raise OSError("synthetic artifact failure")
        f.replace("_image_files", SimpleNamespace(imread=lambda *a: f.image.copy(), imwrite=write))
        label, evidence = self.call(f, single=True)
        self.assertIsNotNone(label); self.assertEqual(evidence["status"], "review_required")
        self.assertTrue(label["mask_meta"]["fallback_single_target"])
        self.assertIs(label["candidate"], f.candidates[0])
        self.assertTrue(any(e[0] == "sprite" for e in f.events))

    def test_text_gate_and_verifier_rejections_keep_evidence(self):
        for single in (False, True):
            f = self.fixture(); f.state["gate"] = {"ok": False, "reason": "document mismatch"}
            result = self.call(f, single); failure = result[1] if single else result[1][0]
            self.assertEqual(failure["reason"], "document mismatch")
            self.assertEqual("full_mask" in failure, single)
            self.assertFalse(any(e[0] in {"sprite", "verify"} for e in f.events))
        f = self.fixture()
        def reject(sample, image, labels):
            return [], [dict(labels[0], status="rejected", reason="mask_verifier_rejected")], {"status": "reject"}
        f.replace("verify_auto_optimize_mask_sample", reject)
        labels, failures, meta = self.call(f)
        self.assertEqual(labels, []); self.assertNotIn("full_mask", failures[0])
        self.assertEqual(meta["class_check"]["missing_count"], 0)
        writes = [e for e in f.events if e[0] == "image-write"]
        self.assertGreater(int(writes[0][2].sum()), 0); self.assertEqual(int(writes[-1][2].sum()), 0)

    def test_preparation_and_artifact_failures_propagate(self):
        for single in (False, True):
            for name in ("auto_optimize_multicolor_mask_prompt", "auto_optimize_write_sprite_artifact"):
                f = self.fixture(); error = AiProviderError("outside provider try")
                def fail(*args, **kwargs): raise error
                f.replace(name, fail)
                with self.assertRaises(AiProviderError) as caught: self.call(f, single)
                self.assertIs(caught.exception, error)
        f = self.fixture()
        with self.assertRaises(ValueError): self.call(f, attempts="invalid")
        self.assertFalse(any(e[0] == "provider" for e in f.events))

    @unittest.skipIf(BASELINE, "candidate-only composition")
    def test_root_composition_and_forwarders(self):
        from unittest.mock import Mock
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service = server._auto_optimization_label_generation
        for group in (service.artifacts, service.policy, service.models):
            for field in fields(group): assert_capability_owner(self, group, field.name, server)
        for name in NAMES:
            args = ({}, {}, "model", Path("fixture")) if name.endswith("for_sample") else ({}, {}, {}, "model", Path("fixture"))
            marker = object(); method = Mock(return_value=marker)
            with patch.object(server, "_auto_optimization_label_generation", SimpleNamespace(**{name: method})):
                self.assertIs(getattr(server, name)(*args), marker); method.assert_called_once_with(*args)

    @unittest.skipIf(BASELINE, "candidate-only lightweight import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable, "-c", "import sys; import local_inspection_service.training.auto_optimization_label_generation; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"], cwd=ROOT, check=True)


if __name__ == "__main__": unittest.main()

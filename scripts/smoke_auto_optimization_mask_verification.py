"""Synthetic mask-verifier behavior, provider boundary and composition contract."""
import ast
import asyncio
from contextvars import ContextVar
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.model_providers.errors import AiProviderError

BASELINE = os.environ.get("VANTALINE_AUTO_MASK_VERIFICATION_BASELINE_SOURCE")
NAME = "verify_auto_optimize_mask_sample"


def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body
                 if isinstance(n, ast.FunctionDef) and n.name == NAME]
        assert len(nodes) == 1
        namespace = dict(bindings, Any=object, np=np, json=json)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, "exec"), namespace)
        return namespace[NAME], lambda name, value: namespace.__setitem__(name, value)
    from local_inspection_service.training.auto_optimization_mask_verification import AutoOptimizationMaskVerification
    from local_inspection_service.training.auto_optimization_mask_verification_ports import AutoOptimizationMaskVerificationPorts
    ports = AutoOptimizationMaskVerificationPorts(**{
        field.name: (lambda name=field.name: bindings[name]) for field in fields(AutoOptimizationMaskVerificationPorts)
    })
    service = AutoOptimizationMaskVerification(ports)
    return getattr(service, NAME), lambda name, value: bindings.__setitem__(name, value)


class MaskVerificationContract(unittest.TestCase):
    def fixture(self):
        events = []
        settings = {"configured": True, "provider": "fixture", "model": "frozen-v1"}
        image = np.zeros((4, 4, 3), np.uint8)
        label = {"accessory_id": "a", "label": "配件 A", "bbox_xyxy": [0, 0, 4, 4],
                 "full_mask": np.ones((4, 4), np.uint8), "color_hex": "#00ff00",
                 "candidate": {"evidence": "sample"}, "profile": {"positive_cues": ["solid"]}}
        targets = [{"accessory_id": "a", "decision": "accept", "mask_region_matches_target": True,
                    "identity_score": .75, "localization_score": .70, "negative_match_score": .25}]
        parsed = {"targets": targets, "overall_decision": "fixture"}
        def provider(*args, **kw):
            events.append(("provider", args, kw))
            return parsed, 12, {"attempts": 2, "retry_count": 1}
        def encode(array, **kw):
            events.append(("encode", array, kw))
            return "fixture:" + str(int(array.sum()))
        def overlay(array, labels):
            events.append(("overlay", array, labels))
            return array + 1
        def crop(array, item):
            events.append(("crop", array, item))
            return array + 2
        def strings(value, *, max_items, max_len):
            return [str(x)[:max_len] for x in value[:max_items]] if isinstance(value, list) else []
        bindings = {"ai_detection_settings": lambda role: settings, "bounded_text": lambda v, n: str(v)[:n],
                    "string_list": strings, "image_bgr_data_url": encode, "auto_optimize_mask_verifier_overlay": overlay,
                    "auto_optimize_mask_verifier_crop": crop, "generate_provider_json_with_fallback": provider,
                    "MASK_VERIFIER_SYSTEM_PROMPT": "fixture system prompt", "AiProviderError": AiProviderError,
                    "clamp_unit_score": lambda value: max(0., min(1., float(value or 0.)))}
        call, replace = create(bindings)
        return SimpleNamespace(call=call, replace=replace, events=events, settings=settings,
                               image=image, label=label, targets=targets, parsed=parsed)

    def test_empty_and_unconfigured_do_not_call_provider(self):
        f = self.fixture()
        def missing(role): raise AssertionError("empty must not resolve settings")
        f.replace("ai_detection_settings", missing)
        labels = []
        result = f.call({}, f.image, labels)
        self.assertIs(result[0], labels)
        self.assertEqual(result[2], {"enabled": True, "status": "skipped_empty"})
        f.replace("ai_detection_settings", lambda role: {"configured": False})
        accepted, failures, meta = f.call({}, f.image, [f.label])
        self.assertEqual(accepted, [])
        self.assertIs(failures[0]["full_mask"], f.label["full_mask"])
        self.assertEqual(meta["reason"], "provider_not_configured")
        self.assertEqual(f.events, [])

    def test_content_and_provider_parameters_are_frozen(self):
        f = self.fixture()
        accepted, failures, meta = f.call({"request_id": "fixture-request"}, f.image, [f.label])
        self.assertIs(accepted[0], f.label)
        self.assertEqual(failures, [])
        self.assertEqual((meta["status"], meta["model"], meta["attempts"], meta["retry_count"]), ("accept", "frozen-v1", 2, 1))
        event, args, kwargs = f.events[-1]
        self.assertEqual(event, "provider")
        self.assertIs(args[0], f.settings)
        self.assertEqual(args[1], "fixture system prompt")
        self.assertEqual(kwargs, {"max_tokens": 1800, "max_attempts": 3, "overloaded_retry_delay_seconds": 3.0, "allow_overloaded_model_fallback": False})
        content = args[2]
        self.assertEqual(hashlib.sha256(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(), "11e945b88e17e56da56d17c956396232dbd85fa57b32b6a39d5c52532e93f499")
        self.assertEqual([event[2] for event in f.events if event[0] == "encode"],
                         [{"max_side": 1280, "quality": 82}, {"max_side": 1280, "quality": 84}, {"max_side": 768, "quality": 84}])

    def test_threshold_edges_rejection_and_missing_targets(self):
        for field, value, expected in (("identity_score", .74999, "review"), ("localization_score", .69999, "review"),
                                       ("negative_match_score", .25001, "review"), ("negative_match_score", .45, "review"),
                                       ("negative_match_score", .45001, "reject"), ("decision", "reject", "reject"),
                                       ("mask_region_matches_target", False, "review")):
            with self.subTest(field=field, value=value):
                f = self.fixture(); f.targets[0][field] = value
                accepted, failures, meta = f.call({}, f.image, [f.label])
                self.assertEqual(accepted, []); self.assertEqual(meta["status"], expected)
                self.assertIs(failures[0]["metrics"], f.label["mask_verifier"])
                self.assertIs(failures[0]["full_mask"], f.label["full_mask"])
        f = self.fixture(); f.parsed["targets"] = "invalid"
        self.assertEqual(f.call({}, f.image, [f.label])[2]["status"], "review")

    def test_duplicate_ids_and_decisions_keep_original_order(self):
        f = self.fixture(); last = dict(f.label, label="last")
        f.targets.insert(0, dict(f.targets[0], decision="reject"))
        accepted, failures, meta = f.call({}, f.image, [f.label, last])
        self.assertEqual(len(accepted), 1); self.assertIs(accepted[0], last)
        self.assertNotIn("mask_verifier", f.label)
        self.assertEqual(meta["status"], "review"); self.assertEqual(failures, [])
        payload = json.loads(f.events[-1][1][2][0]["text"].split("\n", 1)[1])
        self.assertEqual([item["negative_candidates"] for item in payload["targets"]], [[], []])

    def test_provider_error_evidence_and_exception_boundaries(self):
        f = self.fixture(); error = AiProviderError("x" * 300, attempts=3, retry_count=2, previous_errors=["a", "b", "c", "d"])
        def fail(*a, **kw): raise error
        f.replace("generate_provider_json_with_fallback", fail)
        accepted, failures, meta = f.call({}, f.image, [f.label])
        self.assertEqual(accepted, []); self.assertEqual(len(failures[0]["error"]), 220)
        self.assertEqual(failures[0]["previous_errors"], ["b", "c", "d"])
        self.assertEqual((len(meta["error"]), meta["attempts"], meta["retry_count"]), (240, 3, 2))
        self.assertNotIn("mask_verifier", f.label)
        for name, exception in (("ai_detection_settings", error), ("image_bgr_data_url", error),
                                ("generate_provider_json_with_fallback", ValueError("not a provider error"))):
            f = self.fixture()
            def raise_exact(*args, exc=exception, **kwargs): raise exc
            f.replace(name, raise_exact)
            with self.assertRaises(type(exception)) as raised: f.call({}, f.image, [f.label])
            self.assertIs(raised.exception, exception)

    def test_crop_none_and_normalized_evidence_limits(self):
        f = self.fixture(); f.replace("auto_optimize_mask_verifier_crop", lambda *a: None)
        f.targets[0].update(reason="x" * 300, wrong_object_evidence=["a" * 200] * 7, decision=" ACCEPT ")
        result = f.call({}, f.image, [f.label])
        self.assertEqual(len(f.events[-1][1][2]), 5)
        self.assertEqual(len(result[2]["targets"][0]["reason"]), 240)
        self.assertEqual(result[2]["targets"][0]["wrong_object_evidence"], ["a" * 160] * 5)

    def test_argument_side_effect_does_not_change_selected_encoder(self):
        f = self.fixture(); selected = []
        def old(*a, **kw): selected.append("old"); return "old"
        def new(*a, **kw): selected.append("new"); return "new"
        def overlay(*a): f.replace("image_bgr_data_url", new); return f.image
        f.replace("image_bgr_data_url", old); f.replace("auto_optimize_mask_verifier_overlay", overlay)
        f.call({}, f.image, [f.label])
        self.assertEqual(selected, ["old", "old", "new"])

    def test_caller_context_survives_async_threadpool_and_pins_settings(self):
        from starlette.concurrency import run_in_threadpool
        owner = ContextVar("mask-verifier-fixture-owner")
        pinned = ContextVar("mask-verifier-fixture-model")
        f = self.fixture(); calls = []
        def settings(role):
            self.assertEqual(role, "training_vision")
            return {"configured": True, "provider": "fixture", "model": pinned.get(), "owner": owner.get()}
        def provider(config, *args, **kwargs):
            calls.append((config["owner"], config["model"], owner.get(), pinned.get()))
            return {"targets": []}, 1, {}
        f.replace("ai_detection_settings", settings); f.replace("generate_provider_json_with_fallback", provider)
        async def request(account, model):
            a = owner.set(account); b = pinned.set(model)
            try: return await run_in_threadpool(f.call, {}, f.image, [dict(f.label)])
            finally: pinned.reset(b); owner.reset(a)
        async def run(): await asyncio.gather(request("alice", "v1"), request("bob", "v2"))
        asyncio.run(run())
        self.assertEqual(sorted(calls), [("alice", "v1", "alice", "v1"), ("bob", "v2", "bob", "v2")])

    @unittest.skipIf(BASELINE, "candidate-only actual root")
    def test_actual_root_composition_and_forwarder(self):
        from unittest.mock import Mock, patch
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service = server._auto_optimization_mask_verification
        for field in fields(service.ports): self.assertIs(getattr(service.ports, field.name)(), getattr(server, field.name))
        marker = object(); method = Mock(return_value=marker); args = ({}, object(), [])
        with patch.object(server, "_auto_optimization_mask_verification", SimpleNamespace(verify_auto_optimize_mask_sample=method)):
            self.assertIs(server.verify_auto_optimize_mask_sample(*args), marker)
            method.assert_called_once_with(*args)

    @unittest.skipIf(BASELINE, "candidate-only lightweight import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable, "-c", "import sys; import local_inspection_service.training.auto_optimization_mask_verification; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"], cwd=ROOT, check=True)


if __name__ == "__main__": unittest.main()

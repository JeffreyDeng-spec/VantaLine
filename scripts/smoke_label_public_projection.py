"""Behavior of the pure label public projection, including old error cases."""
import copy
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.label_inspection import api

class PublicProjectionContracts(unittest.TestCase):
    def test_owner_fields_always_private(self):
        for diagnostic in (False, True):
            with self.subTest(diagnostic=diagnostic):
                value = dict(id="fixture", owner_user_id="alice", idempotency_key="key",
                             parameters={"source": "fixture"}, kind="task", name="task")
                self.assertEqual(api.public(value, diagnostic=diagnostic), {"id": "fixture", "name": "task"})

    def test_run_fields_hidden_only_for_nondiagnostic_run(self):
        heavy = {name: ["synthetic"] for name in ("model", "prompt_hash", "layout", "transformations", "profile_snapshot")}
        for kind in (None, "task", "run"):
            for diagnostic in (False, True):
                value = {"id": "run", **heavy, "kind": kind}
                expected = {"id": "run"} if kind == "run" and not diagnostic else {"id": "run", **heavy}
                self.assertEqual(api.public(value, diagnostic=diagnostic), expected)

    def test_error_redaction_and_error_code_truthiness(self):
        value = {"kind": "run", "error": "internal synthetic failure"}
        hidden = "检测未完成，请稍后手动重新检测；如需协助，请提供检测编号。"
        self.assertEqual(api.public(value)["error"], hidden)
        for code in (None, "", False, 0, [], {}):
            self.assertEqual(api.public({**value, "error_code": code})["error"], hidden)
        for code in ("E_CODE", 1, [1]):
            self.assertEqual(api.public({**value, "error_code": code})["error"], value["error"])
        self.assertEqual(api.public(value, diagnostic=True)["error"], value["error"])
        self.assertEqual(api.public({**value, "kind": "task"})["error"], value["error"])
        self.assertEqual(api.public({"kind": "run", "error": ""})["error"], "")

    def test_quality_truthiness_and_shallow_identity(self):
        for quality in (None, "", False, 0, [], {}):
            self.assertIs(api.public({"kind": "run", "quality": quality})["quality"], quality)
        for quality in ({"score": 3}, [1], "yes", 1):
            self.assertEqual(api.public({"kind": "run", "quality": quality})["quality"], {"checked": True})
            self.assertIs(api.public({"kind": "run", "quality": quality}, diagnostic=True)["quality"], quality)

    def test_import_allowlist_applies_even_to_diagnostic(self):
        source = {"version": "v1", "completed": 2, "total": 3, "error": None,
                  "credential": "synthetic", "other": []}
        for diagnostic in (False, True):
            result = api.public({"kind": "task", "import": source}, diagnostic=diagnostic)
            self.assertEqual(result, {"import": {key: source[key] for key in ("version", "completed", "total", "error")}})
            self.assertIsNot(result["import"], source)

    def test_invalid_values_preserve_errors(self):
        for value in (None, [], "text", 3):
            with self.assertRaises(AttributeError):
                api.public(value)
            with self.assertRaises(AttributeError):
                api.public({"import": value})

    def test_shallow_projection_without_input_mutation(self):
        nested = {"value": [1]}
        value = {"kind": "run", "extra": nested, "quality": {"score": 1},
                 "error": "private", "import": {"version": "v1", "discard": 2}}
        before = copy.deepcopy(value)
        result = api.public(value)
        self.assertEqual(value, before)
        self.assertIs(result["extra"], nested)
        self.assertIsNot(result, value)

    def test_import_is_pure_and_api_is_direct_alias(self):
        from local_inspection_service.label_inspection.projection import public
        self.assertIs(api.public, public)
        subprocess.run([sys.executable, "-c", "from local_inspection_service.label_inspection.projection import public; "
                        "import sys; assert 'fastapi' not in sys.modules; "
                        "assert 'local_inspection_service.server' not in sys.modules; "
                        "assert not any(name.startswith('local_inspection_service.storage') for name in sys.modules); "
                        "assert public({'id':'fixture'}) == {'id':'fixture'}"],
                       cwd=Path(__file__).resolve().parents[1], check=True)


if __name__ == "__main__":
    unittest.main()

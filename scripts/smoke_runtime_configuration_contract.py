"""Synthetic shared-configuration contract; no real environment or credentials."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.configuration_contract import (
    ConfigurationError, configuration_capture, configuration_validate, configuration_bytes)


class ConfigurationContracts(unittest.TestCase):
    def capture(self, **changes):
        return configuration_capture({"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture", **changes}, "/synthetic/data")

    def test_unset_and_explicit_empty_are_distinct_and_unrelated_environment_is_excluded(self):
        unset = self.capture(UNRELATED_SECRET="never exported")
        empty = self.capture(HTTP_PROXY="")
        self.assertIsNone(unset["environment"]["HTTP_PROXY"])
        self.assertEqual(empty["environment"]["HTTP_PROXY"], "")
        self.assertNotEqual(configuration_validate(unset), configuration_validate(empty))
        self.assertNotIn(b"never exported", configuration_bytes(unset))

    def test_profile_references_remain_exact_without_rewriting_file_or_values(self):
        key = "VANTALINE_PROFILE_" + "A" * 32
        value = self.capture(**{key: "  synthetic-key  "})
        self.assertEqual(value["profile_environment"], {key: "  synthetic-key  "})
        before = copy.deepcopy(value)
        self.assertEqual(configuration_validate(value), configuration_validate(before))
        self.assertEqual(value, before)

    def test_rejects_executable_environment_and_malformed_payloads(self):
        value = self.capture()
        mutations = [lambda v: v["environment"].update(PYTHONPATH="/untrusted"),
                     lambda v: v.update(schema=True), lambda v: v.update(data_directory="/a/../b"),
                     lambda v: v["profile_environment"].update(VANTALINE_PROFILE_BAD="fixture"),
                     lambda v: v["environment"].update(DATABASE_URL=""),
                     lambda v: v["environment"].update(HTTP_PROXY="\x00"),
                     lambda v: v.update(extra="unexpected")]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(value)
                mutate(changed)
                with self.assertRaises(ConfigurationError):
                    configuration_validate(changed)

    def test_cos_requires_explicit_paths_and_a_credential_content_digest(self):
        env = {"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "fixture", "VANTALINE_FILE_STORE": "cos"}
        with self.assertRaises(ConfigurationError):
            configuration_capture(env, "/synthetic/data")
        env.update(VANTALINE_DATA_ROOT="/synthetic/data", VANTALINE_ARTIFACT_WORK_ROOT="/synthetic/work",
                   VANTALINE_ARTIFACT_CACHE_ROOT="/synthetic/cache", VANTALINE_COS_BUCKET="fixture-123",
                   CREDENTIALS_DIRECTORY="/run/credentials/web-only")
        value = configuration_capture(env, "/synthetic/data", cos_credential_sha256="a" * 64)
        self.assertNotIn(b"web-only", configuration_bytes(value))
        self.assertEqual(len(configuration_validate(value)), 64)


if __name__ == "__main__":
    unittest.main()

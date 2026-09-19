"""Offline key identity and local secret store contracts with synthetic data only."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))


class KeyMaterialContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix="key-material-app-")
        (Path(cls.root.name) / "local_inspection_service/static").mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.root.name, VANTALINE_DATA_STORE="json", LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false")
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="synthetic-secrets-")))
        self.path = self.directory / "data" / "secrets.env"
        self.stack.enter_context(patch.object(self.api, "DATA_DIR", self.path.parent))
        self.stack.enter_context(patch.object(self.api, "LOCAL_SECRET_ENV_PATH", self.path))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            self.stack.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))

    def test_mask_and_stable_identifiers_preserve_whitespace_rules(self):
        self.assertEqual([self.api.mask_secret(value) for value in ("", " a ", "12345678", " synthetic-key-value ")], ["", "****a", "****78", "synt...alue"])
        expected = "key_" + hashlib.sha256(b" synthetic ").hexdigest()[:12]
        self.assertEqual(self.api.ai_key_id(" synthetic "), expected)
        self.assertEqual(self.api.secret_key_item_id(" SYNTHETIC_ENV ", "synthetic-secret"), self.api.ai_key_id("SYNTHETIC_ENV"))
        self.assertEqual(self.api.secret_key_item_id("", " synthetic-secret "), self.api.ai_key_id("synthetic-secret"))

    def test_default_environment_prefix_seed_precedence_and_clock_fallback(self):
        digest = hashlib.sha256(b"synthetic-secret").hexdigest()[:10].upper()
        with patch.object(self.api.time, "time_ns", return_value=123456) as clock:
            self.assertEqual(self.api.default_secret_env_name("custom-key", "synthetic-secret", provider="provider"), "CUSTOM_KEY_" + digest)
            self.assertEqual(self.api.default_secret_env_name("123bad", provider="provider"), "VANTALINE_API_KEY_" + hashlib.sha256(b"provider").hexdigest()[:10].upper())
            clock.assert_not_called()
            self.assertEqual(self.api.default_secret_env_name(""), "VANTALINE_API_KEY_" + hashlib.sha256(b"123456").hexdigest()[:10].upper())
            clock.assert_called_once_with()

    def test_load_accepts_existing_formats_and_last_duplicate(self):
        self.path.parent.mkdir()
        self.path.write_text('# ignored\nINVALID-NAME="drop"\nA="first"\nB=\'synthetic raw\'\nC=123\nD={"x":1}\nA="last"\nEMPTY=""\nBROKEN\n', encoding="utf-8")
        self.assertEqual(self.api.load_local_secret_env(), {"A": "last", "B": "synthetic raw", "EMPTY": ""})

    def test_load_missing_and_os_error_return_empty_unknown_error_escapes_once(self):
        self.assertEqual(self.api.load_local_secret_env(), {})
        fake = Mock()
        fake.exists.return_value = True
        fake.read_text.side_effect = OSError("synthetic read failure")
        with patch.object(self.api, "LOCAL_SECRET_ENV_PATH", fake):
            self.assertEqual(self.api.load_local_secret_env(), {})
        fake.read_text.assert_called_once_with(encoding="utf-8")
        fake.read_text.reset_mock()
        error = RuntimeError("synthetic unknown failure")
        fake.read_text.side_effect = error
        with patch.object(self.api, "LOCAL_SECRET_ENV_PATH", fake), self.assertRaises(RuntimeError) as caught:
            self.api.load_local_secret_env()
        self.assertIs(caught.exception, error)
        fake.read_text.assert_called_once_with(encoding="utf-8")

    def test_save_is_sorted_filtered_and_uses_json_escaping(self):
        source = {"B": 'synthetic "quoted"\nline', "A": "first", "EMPTY": "", "BAD-NAME": "discard"}
        before = dict(source)
        self.api.save_local_secret_env(source)
        expected = 'A="first"\nB=' + json.dumps(source["B"]) + '\n'
        self.assertEqual(self.path.read_text(encoding="utf-8"), expected)
        self.assertEqual(source, before)
        self.assertFalse(self.path.with_name("secrets.env.tmp").exists())
        self.assertEqual(self.api.load_local_secret_env(), {"A": "first", "B": source["B"]})

    def test_save_chmod_os_errors_are_tolerated_on_both_paths(self):
        with patch.object(self.api.os, "chmod", side_effect=OSError("synthetic permission failure")) as chmod:
            self.api.save_local_secret_env({"SYNTHETIC_KEY": "synthetic-value"})
        self.assertEqual(self.api.load_local_secret_env(), {"SYNTHETIC_KEY": "synthetic-value"})
        self.assertEqual(chmod.call_args_list[0].args, (self.path.with_name("secrets.env.tmp"), 0o600))
        self.assertEqual(chmod.call_args_list[1].args, (self.path, 0o600))
        self.assertEqual(chmod.call_count, 2)

    def test_environment_precedence_cache_and_invalid_name_short_circuit(self):
        self.api.save_local_secret_env({"SYNTHETIC_KEY": " file-value "})
        os.environ["SYNTHETIC_KEY"] = " process-value "
        with patch.object(self.api, "load_local_secret_env", side_effect=AssertionError("unexpected file read")):
            self.assertEqual(self.api.local_secret_env_value(" SYNTHETIC_KEY "), "process-value")
            self.assertEqual(self.api.local_secret_env_value("BAD-NAME"), "")
        os.environ.pop("SYNTHETIC_KEY")
        self.assertEqual(self.api.local_secret_env_value("SYNTHETIC_KEY"), "file-value")
        self.assertEqual(os.environ["SYNTHETIC_KEY"], "file-value")

    def test_set_validates_then_persists_before_updating_environment(self):
        with patch.object(self.api, "save_local_secret_env", side_effect=lambda values: self.assertNotIn("SYNTHETIC_KEY", os.environ)) as save:
            self.api.set_local_secret_env(" SYNTHETIC_KEY ", " synthetic-value ")
        save.assert_called_once_with({"SYNTHETIC_KEY": "synthetic-value"})
        self.assertEqual(os.environ["SYNTHETIC_KEY"], "synthetic-value")
        with self.assertRaises(self.api.HTTPException) as caught:
            self.api.set_local_secret_env("BAD-NAME", "synthetic-value")
        self.assertEqual(caught.exception.status_code, 400)
        with patch.object(self.api, "load_local_secret_env", side_effect=AssertionError("unexpected read")):
            self.api.set_local_secret_env("SYNTHETIC_EMPTY", " ")
            self.api.set_local_secret_env("", "synthetic")

    def test_replace_failure_keeps_old_file_and_environment_without_retry(self):
        self.api.set_local_secret_env("SYNTHETIC_KEY", "synthetic-old")
        error = OSError("synthetic replace failure")
        with patch.object(self.api.os, "replace", side_effect=error) as replace, self.assertRaises(OSError) as caught:
            self.api.set_local_secret_env("SYNTHETIC_KEY", "synthetic-new")
        self.assertIs(caught.exception, error)
        replace.assert_called_once_with(self.path.with_name("secrets.env.tmp"), self.path)
        self.assertEqual(self.api.load_local_secret_env(), {"SYNTHETIC_KEY": "synthetic-old"})
        self.assertEqual(os.environ["SYNTHETIC_KEY"], "synthetic-old")
        self.assertTrue(self.path.with_name("secrets.env.tmp").exists())

    def test_delete_persists_before_process_removal_and_skips_invalid_or_absent_file_key(self):
        self.api.set_local_secret_env("SYNTHETIC_KEY", "synthetic-value")
        original = self.api.save_local_secret_env
        def save(values):
            self.assertIn("SYNTHETIC_KEY", os.environ)
            self.assertEqual(os.environ["SYNTHETIC_KEY"], "synthetic-value")
            original(values)
        with patch.object(self.api, "save_local_secret_env", side_effect=save) as spy:
            self.api.delete_local_secret_env(" SYNTHETIC_KEY ")
        spy.assert_called_once_with({})
        self.assertNotIn("SYNTHETIC_KEY", os.environ)
        self.assertEqual(self.path.read_text(), "")
        os.environ["SYNTHETIC_ONLY_PROCESS"] = "synthetic"
        with patch.object(self.api, "save_local_secret_env", side_effect=AssertionError("unexpected write")):
            self.api.delete_local_secret_env("SYNTHETIC_ONLY_PROCESS")
            self.api.delete_local_secret_env("BAD-NAME")
        self.assertNotIn("SYNTHETIC_ONLY_PROCESS", os.environ)

    def test_persist_writes_before_deduplication_and_returns_references_only(self):
        entries = [{"id": "same", "provider": "qwen", "key": "synthetic-a", "env": "SYNTHETIC_A"}, {"id": "same", "provider": "qwen", "key": "synthetic-b", "env_name": "SYNTHETIC_B"}, {"id": "same", "provider": "gemini", "api_key_env": "PENDING_GEMINI"}, {}]
        with patch.object(self.api, "set_local_secret_env") as setter:
            result = self.api.persist_secret_key_items(entries, "SYNTHETIC_PREFIX")
        self.assertEqual(setter.call_count, 2)
        self.assertEqual(setter.call_args_list[1].args, ("SYNTHETIC_B", "synthetic-b"))
        self.assertEqual(result, [{"id": "same", "label": "API Key 1", "env": "SYNTHETIC_A", "provider": "qwen"}, {"id": "same", "label": "API Key 2", "env": "PENDING_GEMINI", "provider": "gemini"}])
        self.assertNotIn("synthetic-a", str(result))
        self.assertEqual(entries[0]["key"], "synthetic-a")

    def test_persist_generated_environment_identity_and_label_limit(self):
        with patch.object(self.api, "set_local_secret_env") as setter:
            result = self.api.persist_secret_key_items([{"key": "synthetic-key", "label": "x" * 100}], "SYNTHETIC_PREFIX")
        expected_env = self.api.default_secret_env_name("SYNTHETIC_PREFIX", "synthetic-key")
        self.assertEqual(result, [{"id": self.api.secret_key_item_id(expected_env, "synthetic-key"), "label": "x" * 80, "env": expected_env}])
        setter.assert_called_once_with(expected_env, "synthetic-key")


    def test_key_identifier_callee_is_captured_before_argument_conversion(self):
        first = Mock(return_value="first-id")
        later = Mock(return_value="late-id")
        api = self.api
        class Name:
            def __str__(inner):
                api.ai_key_id = later
                return " SYNTHETIC_ENV "
        with patch.object(api, "ai_key_id", first):
            self.assertEqual(api.secret_key_item_id(Name(), "synthetic"), "first-id")
        first.assert_called_once_with("SYNTHETIC_ENV")
        later.assert_not_called()

    def test_default_name_callee_is_captured_before_provider_argument(self):
        first = Mock(return_value="SYNTHETIC_FIRST")
        later = Mock(return_value="SYNTHETIC_LATER")
        api = self.api
        class Item(dict):
            def get(inner, name, default=None):
                if name == "provider":
                    api.default_secret_env_name = later
                return super().get(name, default)
        with patch.object(api, "default_secret_env_name", first), patch.object(api, "set_local_secret_env") as setter:
            result = api.persist_secret_key_items([Item(id="one", key="synthetic", provider="qwen")], "SYNTHETIC_PREFIX")
        self.assertEqual(result[0]["env"], "SYNTHETIC_FIRST")
        first.assert_called_once_with("SYNTHETIC_PREFIX", "synthetic", provider="qwen")
        later.assert_not_called()
        setter.assert_called_once_with("SYNTHETIC_FIRST", "synthetic")

    def test_secret_path_is_read_at_each_original_expression(self):
        api = self.api
        replacement_path = self.directory / "second.env"
        temporary_path = self.directory / "synthetic.env.tmp"
        events = []
        class FirstPath:
            name = "first.env"
            @property
            def with_name(inner):
                api.LOCAL_SECRET_ENV_PATH = replacement_path
                def selected(name):
                    events.append(name)
                    return temporary_path
                return selected
        with patch.object(api, "LOCAL_SECRET_ENV_PATH", FirstPath()), patch.object(api.os, "chmod") as chmod, patch.object(api.os, "replace") as replace:
            api.save_local_secret_env({"SYNTHETIC_KEY": "synthetic"})
        self.assertEqual(events, ["second.env.tmp"])
        replace.assert_called_once_with(temporary_path, replacement_path)
        self.assertEqual(chmod.call_args_list[-1].args, (replacement_path, 0o600))
        self.assertEqual(temporary_path.read_text(), 'SYNTHETIC_KEY="synthetic"\n')

    def test_environment_mapping_is_refreshed_after_file_callback(self):
        first, later = {}, {}
        def load():
            self.api.os.environ = later
            return {"SYNTHETIC_KEY": " synthetic-value "}
        with patch.object(self.api.os, "environ", first), patch.object(self.api, "load_local_secret_env", load):
            self.assertEqual(self.api.local_secret_env_value("SYNTHETIC_KEY"), "synthetic-value")
        self.assertEqual(first, {})
        self.assertEqual(later, {"SYNTHETIC_KEY": "synthetic-value"})

    def test_read_os_error_does_not_retry_a_later_success(self):
        from itertools import chain, repeat
        fake = Mock()
        fake.exists.return_value = True
        fake.read_text.side_effect = chain([OSError("synthetic read failure")], repeat('SYNTHETIC_KEY="synthetic-later"'))
        with patch.object(self.api, "LOCAL_SECRET_ENV_PATH", fake):
            self.assertEqual(self.api.load_local_secret_env(), {})
        fake.read_text.assert_called_once_with(encoding="utf-8")

    def test_unknown_temporary_chmod_error_escapes_before_replace(self):
        from itertools import chain, repeat
        error = RuntimeError("synthetic unknown chmod failure")
        with patch.object(self.api.os, "chmod", side_effect=chain([error], repeat(None))) as chmod, patch.object(self.api.os, "replace") as replace:
            with self.assertRaises(RuntimeError) as caught:
                self.api.save_local_secret_env({"SYNTHETIC_KEY": "synthetic-value"})
        self.assertIs(caught.exception, error)
        chmod.assert_called_once_with(self.path.with_name("secrets.env.tmp"), 0o600)
        replace.assert_not_called()
        self.assertFalse(self.path.exists())
        self.assertTrue(self.path.with_name("secrets.env.tmp").exists())


    def test_service_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.model_providers.key_identity import KeyIdentity
        from local_inspection_service.model_providers.local_secret_store import LocalSecretStore
        from local_inspection_service.model_providers.key_material_ports import KeyIdentityRuntime, SecretPaths, SecretCodec, SecretFileOperations, SecretEnvironment, SecretPolicy, SecretStoreAccess
        getter = Mock(return_value=None)
        def ports(kind):
            return kind(**{field.name: getter for field in fields(kind)})
        self.assertIsInstance(KeyIdentity(ports(KeyIdentityRuntime)), KeyIdentity)
        self.assertIsInstance(LocalSecretStore(*(ports(kind) for kind in (SecretPaths, SecretCodec, SecretFileOperations, SecretEnvironment, SecretPolicy, SecretStoreAccess))), LocalSecretStore)
        getter.assert_not_called()

    def test_independent_services_own_paths_environment_and_callbacks(self):
        import re
        from local_inspection_service.model_providers.key_identity import KeyIdentity
        from local_inspection_service.model_providers.local_secret_store import LocalSecretStore
        from local_inspection_service.model_providers.key_material_ports import KeyIdentityRuntime, SecretPaths, SecretCodec, SecretFileOperations, SecretEnvironment, SecretPolicy, SecretStoreAccess
        sha, clock, sub, match = hashlib.sha256, self.api.time.time_ns, re.sub, re.fullmatch
        chmod, replace, loads, dumps = os.chmod, os.replace, json.loads, json.dumps
        def make(prefix):
            environment = {}
            directory = self.directory / prefix
            path = directory / "synthetic.env"
            identity = KeyIdentity(KeyIdentityRuntime(lambda: sha, lambda: clock, lambda: sub, lambda: match, lambda: identity.ai_key_id))
            store = LocalSecretStore(
                SecretPaths(lambda: directory, lambda: path),
                SecretCodec(lambda: loads, lambda: dumps, lambda: json.JSONDecodeError),
                SecretFileOperations(lambda: chmod, lambda: replace),
                SecretEnvironment(lambda: environment),
                SecretPolicy(lambda: match, lambda: lambda value: str(value or "").strip(), lambda: identity.default_secret_env_name, lambda: identity.secret_key_item_id, lambda: lambda value, limit: str(value)[:limit]),
                SecretStoreAccess(lambda: store.load_local_secret_env, lambda: store.save_local_secret_env, lambda: store.set_local_secret_env),
            )
            return identity, store, environment, path
        first, second = make("first"), make("second")
        forbidden = Mock(side_effect=AssertionError("application callback used"))
        names = ("ai_key_id", "default_secret_env_name", "secret_key_item_id", "load_local_secret_env", "save_local_secret_env", "set_local_secret_env", "validate_ai_key_env", "bounded_text")
        with patch.multiple(self.api, **{name: forbidden for name in names}):
            for bundle, secret in ((first, "synthetic-first"), (second, "synthetic-second"), (first, "synthetic-first")):
                identity, store, environment, path = bundle
                refs = store.persist_secret_key_items([{"env": "SYNTHETIC_KEY", "key": secret}], "SYNTHETIC_PREFIX")
                self.assertEqual(refs[0]["id"], identity.ai_key_id("SYNTHETIC_KEY"))
                self.assertEqual(store.local_secret_env_value("SYNTHETIC_KEY"), secret)
                self.assertEqual(environment, {"SYNTHETIC_KEY": secret})
                self.assertEqual(store.load_local_secret_env(), {"SYNTHETIC_KEY": secret})
                self.assertEqual(path.read_text(), 'SYNTHETIC_KEY=' + json.dumps(secret) + '\n')
            first[1].delete_local_secret_env("SYNTHETIC_KEY")
            self.assertEqual(first[2], {})
            self.assertEqual(second[2], {"SYNTHETIC_KEY": "synthetic-second"})
            self.assertEqual(second[1].load_local_secret_env(), second[2])
            forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Synthetic contracts for Agent configuration policy, projections and legacy files."""
import copy
import json
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))


class AgentSettingsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.root = tempfile.TemporaryDirectory(prefix="agent-settings-app-")
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
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="synthetic-agent-settings-")))
        self.path = self.directory / "agent.json"
        self.stack.enter_context(patch.object(self.api, "DATA_DIR", self.directory))
        self.stack.enter_context(patch.object(self.api, "AGENT_LOCAL_CONFIG_PATH", self.path))
        self.lookup = self.stack.enter_context(patch.object(self.api, "local_secret_env_value", return_value=""))
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            self.stack.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))

    def configured(self, **changes):
        source = {"base_url": "https://synthetic.invalid/v1", "api_key": "synthetic-primary", "model": "synthetic-model", "connection_status": "connected"}
        source.update(changes)
        return self.api.normalize_agent_config(source)

    def test_provider_host_and_url_precedence(self):
        self.assertEqual(self.api.agent_base_url_host(" HTTPS://API.CURSOR.COM/path "), "api.cursor.com")
        self.assertEqual(self.api.agent_base_url_host("http://[broken"), "")
        self.assertTrue(self.api.is_cursor_base_url("https://api.cursor.com/v1"))
        self.assertFalse(self.api.is_cursor_base_url("https://api.cursor.com.synthetic.invalid"))
        self.assertEqual(self.api.detect_agent_provider_from_base_url("https://synthetic.invalid"), "openai_compatible")
        self.assertEqual(self.api.normalize_agent_provider("cursor", "https://synthetic.invalid"), "openai_compatible")
        self.assertEqual(self.api.normalize_agent_provider("other", "https://api.cursor.com"), "cursor")
        self.assertEqual(self.api.normalize_agent_provider(" CURSOR "), "cursor")
        self.assertEqual(self.api.normalize_agent_provider("qwen"), "openai_compatible")
        self.assertEqual([self.api.agent_provider_label(value) for value in (" CURSOR ", "qwen")], ["Cursor", "OpenAI 兼容"])

    def test_model_options_aliases_deduplication_and_limit(self):
        options = [" first ", {"value": "second", "display_name": "Second"}, {"id": "first", "label": "Duplicate"}, None, {}, {"id": "third", "name": "Third"}]
        before = copy.deepcopy(options)
        self.assertEqual(self.api.normalize_agent_model_options(options), [{"id": "first", "label": "first"}, {"id": "second", "label": "Second"}, {"id": "third", "label": "Third"}])
        self.assertEqual(options, before)
        self.assertEqual(len(self.api.normalize_agent_model_options([str(i) for i in range(260)])), 250)
        self.assertEqual(self.api.normalize_agent_model_options({"id": "ignored"}), [])
        result = self.api.agent_model_options_from_items([{"id": "model", "display_name": "Display", "aliases": [" a ", "b", "c", "d"]}], prepend=[{"id": "first", "label": "First"}])
        self.assertEqual(result, [{"id": "first", "label": "First"}, {"id": "model", "label": "model · Display · alias: a, b, c"}])

    def test_normalization_default_copy_cursor_defaults_and_unknown_field_exclusion(self):
        original = {"provider": "cursor", "base_url": "", "model": "", "unknown": "synthetic-private"}
        before = copy.deepcopy(original)
        result = self.api.normalize_agent_config(original)
        self.assertEqual(result["provider"], "cursor")
        self.assertEqual(result["base_url"], "https://api.cursor.com")
        self.assertEqual(result["model"], "auto")
        self.assertNotIn("unknown", result)
        self.assertEqual(original, before)
        self.assertIsNot(result, original)

    def test_active_key_selection_environment_fallback_and_reference_preservation(self):
        self.lookup.side_effect = lambda name: "synthetic-env" if name == "FALLBACK_KEY" else ""
        config = {"provider": "openai_compatible", "api_key_env": "FALLBACK_KEY", "api_key": "synthetic-inline", "active_key_id": "second", "api_keys": [{"id": "first", "key": "synthetic-first", "env": "FIRST_KEY"}, {"id": "second", "key": "synthetic-second", "env": "SECOND_KEY"}]}
        result = self.api.normalize_agent_config(config)
        self.assertEqual(result["active_key_id"], "second")
        self.assertEqual(result["api_key"], "synthetic-second")
        result = self.api.normalize_agent_config({"api_key_env": "FALLBACK_KEY", "api_keys": [{"id": "pending", "env": "PENDING_KEY"}], "active_key_id": "missing"})
        self.assertEqual(result["active_key_id"], "pending")
        self.assertEqual(result["api_key"], "synthetic-env")
        self.assertEqual(result["api_keys"][0]["env"], "PENDING_KEY")

    def test_numeric_bounds_connection_fields_and_invalid_environment(self):
        result = self.api.normalize_agent_config({"timeout_seconds": "bad", "connection_status": "unknown", "connection_message": " x" + "y" * 400, "last_tested_at": "bad", "last_model_count": -9})
        self.assertEqual((result["timeout_seconds"], result["connection_status"], result["last_tested_at"], result["last_model_count"]), (45.0, "untested", 0, 0))
        self.assertEqual(len(result["connection_message"]), 300)
        self.assertEqual(self.api.normalize_agent_config({"timeout_seconds": 1})["timeout_seconds"], 5.0)
        self.assertEqual(self.api.normalize_agent_config({"timeout_seconds": 900})["timeout_seconds"], 300.0)
        with self.assertRaises(self.api.HTTPException) as caught:
            self.api.normalize_agent_config({"api_key_env": "BAD-NAME"})
        self.assertEqual(caught.exception.status_code, 400)

    def test_credentials_required_fields_connection_and_recommendation_distinctions(self):
        config = self.configured()
        self.assertTrue(self.api.agent_required_fields_present(config))
        self.assertTrue(self.api.agent_credentials_present(config))
        self.assertTrue(self.api.agent_connected(config))
        self.assertTrue(self.api.agent_recommendation_supported(config))
        no_model = dict(config, model="")
        self.assertTrue(self.api.agent_credentials_present(no_model))
        self.assertFalse(self.api.agent_required_fields_present(no_model))
        self.assertFalse(self.api.agent_connected(no_model))
        cursor = dict(config, provider="cursor", base_url="https://api.cursor.com", model="")
        self.assertTrue(self.api.agent_required_fields_present(cursor))
        self.assertFalse(self.api.agent_recommendation_supported(cursor))
        self.assertFalse(self.api.agent_credentials_present(dict(config, enabled=False)))

    def test_empty_configuration_uses_current_model_bound_loader(self):
        config = self.configured()
        with patch.object(self.api, "load_agent_config", return_value=config) as load:
            self.assertTrue(self.api.agent_configured({}))
            self.assertTrue(self.api.agent_configured(None))
        self.assertEqual(load.call_count, 2)
        with patch.object(self.api, "load_agent_config", side_effect=AssertionError("unexpected loader")):
            self.assertTrue(self.api.agent_configured(config))

    def test_member_projection_has_only_six_safe_fields_and_skips_key_expansion(self):
        config = self.configured()
        with patch.object(self.api, "current_auth_user", return_value={"role": "member"}), patch.object(self.api, "normalize_agent_key_items", side_effect=AssertionError("member key expansion")):
            result = self.api.public_agent_config(config)
        self.assertEqual(result, {"enabled": True, "configured": True, "connection_status": "connected", "recommendation_supported": True, "auto_advance_default": True, "mode": "agent"})
        self.assertNotIn("synthetic-primary", str(result))
        self.assertNotIn("synthetic.invalid", str(result))

    def test_admin_projection_masks_keys_and_retains_existing_model_options_reference(self):
        config = self.configured(connection_message="Synthetic connected", last_tested_at=123, last_model_count=4)
        with patch.object(self.api, "current_auth_user", return_value={"role": "admin"}):
            result = self.api.public_agent_config(config)
        self.assertEqual(result["api_key_masked"], "synt...mary")
        self.assertEqual(result["mode"], "agent")
        self.assertTrue(result["has_api_key"])
        self.assertEqual(result["connection_message"], "Synthetic connected")
        self.assertEqual(result["last_tested_at"], 123)
        self.assertIs(result["model_options"], config["model_options"])
        self.assertNotIn("synthetic-primary", str(result))
        self.assertTrue(all("key" not in item for item in result["api_keys"]))

    def test_legacy_load_omits_absent_provider_and_ignores_unknown_fields(self):
        self.path.write_text(json.dumps({"base_url": "https://api.cursor.com", "unknown": "synthetic-private"}), encoding="utf-8")
        with patch.object(self.api, "normalize_agent_config", return_value={"normalized": True}) as normalizer:
            self.assertEqual(self.api._legacy_load_agent_config(), {"normalized": True})
        values = normalizer.call_args.args[0]
        self.assertNotIn("provider", values)
        self.assertNotIn("unknown", values)
        self.assertEqual(values["base_url"], "https://api.cursor.com")
        self.path.write_text("invalid json", encoding="utf-8")
        self.assertEqual(self.api._legacy_load_agent_config()["connection_status"], "untested")

    def test_save_uses_secret_references_and_preserves_input(self):
        config = self.configured()
        before = copy.deepcopy(config)
        refs = [{"id": "synthetic-id", "env": "SYNTHETIC_ENV", "label": "Synthetic", "provider": "openai_compatible"}]
        with patch.object(self.api, "persist_secret_key_items", return_value=refs) as persist:
            self.api.save_agent_config(config)
        payload = json.loads(self.path.read_text())
        self.assertEqual(payload["api_key"], "")
        self.assertEqual(payload["api_keys"], refs)
        self.assertEqual(persist.call_args.args[1], "VANTALINE_AGENT_KEY")
        self.assertEqual(config, before)
        self.assertNotIn("synthetic-primary", self.path.read_text())
        self.assertFalse(self.path.with_name("agent.json.tmp").exists())

    def test_save_replace_failure_preserves_previous_file_without_retry(self):
        self.path.write_text('"synthetic-previous"', encoding="utf-8")
        error = OSError("synthetic replacement failure")
        with patch.object(self.api, "persist_secret_key_items", return_value=[]), patch.object(self.api.os, "replace", side_effect=error) as replace:
            with self.assertRaises(OSError) as caught:
                self.api.save_agent_config(self.configured())
        self.assertIs(caught.exception, error)
        replace.assert_called_once_with(self.path.with_name("agent.json.tmp"), self.path)
        self.assertEqual(self.path.read_text(), '"synthetic-previous"')
        self.assertTrue(self.path.with_name("agent.json.tmp").exists())


    def test_admin_callback_is_selected_before_current_user(self):
        config = self.configured()
        events = []
        selected = Mock(side_effect=lambda user: events.append("selected") or False)
        late = Mock(return_value=True)
        def user():
            events.append("user")
            self.api.user_is_admin = late
            return {"role": "member"}
        with patch.object(self.api, "user_is_admin", selected), patch.object(self.api, "current_auth_user", user):
            result = self.api.public_agent_config(config)
        self.assertEqual(events, ["user", "selected"])
        self.assertEqual(set(result), {"enabled", "configured", "connection_status", "recommendation_supported", "auto_advance_default", "mode"})
        late.assert_not_called()

    def test_secret_masker_is_selected_before_value_subscription(self):
        selected = Mock(return_value="selected-mask")
        late = Mock(return_value="late-mask")
        api = self.api
        class EffectfulConfig(dict):
            def __getitem__(self, key):
                if key == "api_key":
                    api.mask_secret = late
                return super().__getitem__(key)
        config = EffectfulConfig(self.configured())
        with patch.object(api, "mask_secret", selected), patch.object(api, "public_ai_key_items", return_value=[]), patch.object(api, "current_auth_user", return_value={"role": "admin"}):
            result = api.public_agent_config(config)
        self.assertEqual(result["api_key_masked"], "selected-mask")
        selected.assert_called_once_with("synthetic-primary")
        late.assert_not_called()

    def test_save_selects_persist_before_nested_key_normalization(self):
        config = self.configured()
        events = []
        selected = Mock(side_effect=lambda items, prefix: events.append(("persist", items, prefix)) or [])
        late = Mock(return_value=[])
        def keys(value):
            events.append("keys")
            self.api.persist_secret_key_items = late
            return [{"id": "synthetic-key"}]
        with patch.object(self.api, "normalize_agent_config", return_value=config), patch.object(self.api, "normalize_agent_key_items", keys), patch.object(self.api, "persist_secret_key_items", selected):
            self.api.save_agent_config(config)
        self.assertEqual(events, ["keys", ("persist", [{"id": "synthetic-key"}], "VANTALINE_AGENT_KEY")])
        late.assert_not_called()

    def test_save_evaluates_present_mapping_defaults_before_write(self):
        config = self.configured()
        events = []
        error = RuntimeError("synthetic eager default failure")
        class Defaults(dict):
            def __getitem__(self, key):
                events.append(key)
                raise error
        defaults = Defaults(self.api.DEFAULT_AGENT_CONFIG)
        persist = Mock(return_value=[])
        with patch.object(self.api, "DEFAULT_AGENT_CONFIG", defaults), patch.object(self.api, "normalize_agent_config", return_value=config), patch.object(self.api, "persist_secret_key_items", persist):
            with self.assertRaises(RuntimeError) as caught:
                self.api.save_agent_config(config)
        self.assertIs(caught.exception, error)
        self.assertEqual(events, [next(iter(defaults))])
        persist.assert_called_once()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name("agent.json.tmp").exists())

    def test_unknown_replace_failure_preserves_prior_secret_write_and_temp_evidence(self):
        config = self.configured()
        self.path.write_text('"synthetic-old"', encoding="utf-8")
        events = []
        error = RuntimeError("synthetic unknown replace failure")
        real_replace = self.api.os.replace
        tmp = self.path.with_name("agent.json.tmp")
        def persist(items, prefix):
            self.assertFalse(tmp.exists())
            events.append("persist")
            return [{"id": "synthetic-id", "env": "SYNTHETIC_ENV"}]
        def replace(source, destination):
            events.append("replace")
            if events.count("replace") == 1:
                raise error
            return real_replace(source, destination)
        with patch.object(self.api, "persist_secret_key_items", persist), patch.object(self.api.os, "replace", replace), patch.object(self.api.os, "chmod") as chmod:
            with self.assertRaises(RuntimeError) as caught:
                self.api.save_agent_config(config)
        self.assertIs(caught.exception, error)
        self.assertEqual(events, ["persist", "replace"])
        self.assertEqual(self.path.read_text(), '"synthetic-old"')
        self.assertEqual(json.loads(tmp.read_text())["api_keys"], [{"id": "synthetic-id", "env": "SYNTHETIC_ENV"}])
        self.assertNotIn("synthetic-primary", tmp.read_text())
        chmod.assert_not_called()

    def test_unknown_legacy_read_error_escapes_without_retry_or_normalization(self):
        self.path.write_text("{}", encoding="utf-8")
        error = RuntimeError("synthetic unknown read failure")
        calls = []
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            if path == self.path:
                calls.append(path)
                if len(calls) == 1:
                    raise error
            return real_read(path, *args, **kwargs)
        with patch.object(Path, "read_text", read), patch.object(self.api, "normalize_agent_config", return_value={}) as normalize:
            with self.assertRaises(RuntimeError) as caught:
                self.api._legacy_load_agent_config()
        self.assertIs(caught.exception, error)
        self.assertEqual(calls, [self.path])
        normalize.assert_not_called()

    def test_public_short_circuit_keeps_dependency_order_and_modern_loader(self):
        events = []
        config = {"enabled": True, "auto_advance_default": True}
        with patch.object(self.api, "load_agent_config", side_effect=lambda: events.append("modern") or config), patch.object(self.api, "agent_credentials_present", side_effect=lambda value: events.append("credentials") or False), patch.object(self.api, "agent_recommendation_supported", side_effect=lambda value: events.append("recommendation") or False), patch.object(self.api, "current_auth_user", side_effect=lambda: events.append("identity") or {}), patch.object(self.api, "user_is_admin", side_effect=lambda value: events.append("permission") or False), patch.object(self.api, "normalize_agent_key_items") as keys:
            result = self.api.public_agent_config({})
        self.assertEqual(events, ["modern", "credentials", "recommendation", "identity", "permission"])
        self.assertEqual(result, {"enabled": True, "configured": False, "connection_status": "untested", "recommendation_supported": False, "auto_advance_default": True, "mode": "rules"})
        keys.assert_not_called()




    def test_service_constructors_do_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.agent import settings_ports as p
        from local_inspection_service.agent.settings_policy import AgentSettingsPolicy
        from local_inspection_service.agent.settings_projection import AgentSettingsProjection
        from local_inspection_service.agent.legacy_settings_store import LegacyAgentSettingsStore
        reads = []
        def group(kind):
            values = {field.name: Mock(return_value=None) for field in fields(kind)}
            reads.extend(values.values())
            return kind(**values)
        AgentSettingsPolicy(group(p.AgentSettingsDefaults), group(p.AgentProviderPolicy), group(p.AgentSettingsKeys))
        AgentSettingsProjection(group(p.AgentSettingsDefaults), group(p.AgentProviderPolicy), group(p.AgentSettingsAccess), group(p.AgentSettingsAuthorization), group(p.AgentSettingsKeys), group(p.AgentSettingsPresentation))
        LegacyAgentSettingsStore(group(p.AgentSettingsDefaults), group(p.AgentSettingsPaths), group(p.AgentSettingsCodec), group(p.AgentSettingsFiles), group(p.AgentSettingsPersistence))
        for getter in reads:
            getter.assert_not_called()

    def test_two_settings_compositions_use_their_own_policy_identity_and_paths(self):
        from dataclasses import fields
        from local_inspection_service.agent import settings_ports as p
        from local_inspection_service.agent.settings_policy import AgentSettingsPolicy
        from local_inspection_service.agent.settings_projection import AgentSettingsProjection
        from local_inspection_service.agent.legacy_settings_store import LegacyAgentSettingsStore
        def forbidden():
            raise AssertionError("unselected capability read")
        def group(kind, **selected):
            return kind(**{field.name: selected.get(field.name, forbidden) for field in fields(kind)})
        events = []
        def make(name):
            defaults = group(p.AgentSettingsDefaults, cursor=lambda: name, openai=lambda: "openai", config=lambda: {})
            provider = group(p.AgentProviderPolicy, normalize=lambda: lambda value, base: name)
            policy = AgentSettingsPolicy(defaults, provider, group(p.AgentSettingsKeys))
            config = {"enabled": True, "api_key": "synthetic", "base_url": "synthetic", "auto_advance_default": name == "first"}
            access = group(p.AgentSettingsAccess, load=lambda: lambda: config, credentials=lambda: lambda value: True, recommendation=lambda: lambda value: False)
            auth = group(p.AgentSettingsAuthorization, current_user=lambda: lambda: {"synthetic_identity": name}, is_admin=lambda: lambda user: events.append(user["synthetic_identity"]) or False)
            projection = AgentSettingsProjection(defaults, provider, access, auth, group(p.AgentSettingsKeys), group(p.AgentSettingsPresentation))
            path = self.directory / (name + ".json")
            path.write_text(json.dumps({"instance": name}), encoding="utf-8")
            defaults = group(p.AgentSettingsDefaults, config=lambda: {"instance": ""})
            paths = group(p.AgentSettingsPaths, file=lambda: path)
            codec = group(p.AgentSettingsCodec, loads=lambda: json.loads, decode_error=lambda: json.JSONDecodeError)
            persistence = group(p.AgentSettingsPersistence, normalize=lambda: lambda value: {"instance": name, "value": value})
            store = LegacyAgentSettingsStore(defaults, paths, codec, group(p.AgentSettingsFiles), persistence)
            return policy, projection, store, config
        instances = {name: make(name) for name in ("first", "second")}
        with patch.object(self.api, "current_auth_user", side_effect=AssertionError("root identity")), patch.object(self.api, "load_agent_config", side_effect=AssertionError("root loader")), patch.object(self.api, "normalize_agent_config", side_effect=AssertionError("root normalization")):
            for name in ("first", "second", "first"):
                with self.subTest(instance=name):
                    policy, projection, store, config = instances[name]
                    self.assertEqual(policy.agent_provider_label(name), "Cursor")
                    self.assertEqual(projection.public_agent_config(), {"enabled": True, "configured": True, "connection_status": "untested", "recommendation_supported": False, "auto_advance_default": name == "first", "mode": "rules"})
                    self.assertTrue(projection.agent_required_fields_present(config))
                    self.assertEqual(store._legacy_load_agent_config(), {"instance": name, "value": {"instance": name}})
        self.assertEqual(events, ["first", "second", "first"])


if __name__ == "__main__":
    unittest.main()

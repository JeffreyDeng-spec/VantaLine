"""Offline contracts for provider key registry behavior; synthetic values only."""
import copy
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path.cwd()))


def capture_key_registry_window(api, site, mode):
    """Synthetic root-callback trace; reusable with original or candidate adapters."""
    from unittest.mock import patch
    if site not in ('label', 'mask') or mode not in ('ordinary', 'prior', 'missing'):
        raise AssertionError((site, mode))
    events = []
    name = 'bounded_text' if site == 'label' else 'mask_secret'
    def callback(tag):
        def selected(*args):
            events.append(('call', tag, args))
            return tag + '-value'
        return selected
    first, prior, later = [callback(tag) for tag in ('A', 'B', 'C')]
    class Item(dict):
        def get(self, key, default=None):
            if (site == 'label' and key == 'id') or (site == 'mask' and key == 'label'):
                events.append(('prior', key))
                if mode != 'ordinary':
                    api.__dict__[name] = prior if mode == 'prior' else None
            if (site == 'label' and key == 'label') or (site == 'mask' and key == 'key'):
                events.append(('argument', key))
                api.__dict__[name] = later
            return super().get(key, default)
    item = Item(id='one', key='synthetic-key', label='given', provider='qwen')
    result = None
    error = None
    with patch.dict(api.__dict__, {name: first, 'local_secret_env_value': lambda name: '', 'AI_SUPPORTED_PROVIDERS': {'qwen'}}):
        try:
            rows = api.normalize_ai_key_items({'api_keys': [item]}, 'qwen') if site == 'label' else api.public_ai_key_items([item])
            result = rows
        except BaseException as caught:
            error = type(caught).__name__
    return {'events': events, 'result': result, 'error': error}


class ProviderKeyRegistryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ)
        cls.environment.start()
        cls.temporary = tempfile.TemporaryDirectory(prefix="provider-key-registry-")
        (Path(cls.temporary.name) / "local_inspection_service/static").mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=cls.temporary.name, VANTALINE_DATA_STORE="json", LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false")
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()
        cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            self.stack.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        self.lookup = self.stack.enter_context(patch.object(self.api, "local_secret_env_value", return_value=""))

    def test_json_skips_explicit_unknown_but_uses_fallback_for_absent_provider(self):
        config = {"provider": "unknown", "api_keys": [None, {"key": "synthetic-a", "provider": "unknown"}, {"key": "synthetic-b", "id": "b"}, {"env": "PENDING_KEY", "id": "pending"}]}
        with patch.object(self.api, "AI_DEFAULT_PROVIDER", "qwen"):
            result = self.api.normalize_ai_key_items(config)
        self.assertEqual([item["id"] for item in result], ["b", "pending"])
        self.assertEqual([item["provider"] for item in result], ["qwen", "qwen"])
        self.assertEqual(result[1]["key"], "")
        self.assertEqual(result[1]["env"], "PENDING_KEY")

    def test_json_environment_precedes_inline_and_aliases_are_supported(self):
        self.lookup.side_effect = lambda name: "synthetic-from-env" if name == "SYNTHETIC_KEY" else ""
        config = {"api_keys": [{"id": "one", "api_key": "synthetic-inline", "env_name": " SYNTHETIC_KEY ", "ai_provider": " QWEN "}, {"id": "two", "api_key_env": "PENDING_KEY"}]}
        result = self.api.normalize_ai_key_items(config, "qwen")
        self.assertEqual(result[0]["key"], "synthetic-from-env")
        self.assertEqual(result[0]["provider"], "qwen")
        self.assertEqual(result[1]["key"], "")
        self.assertEqual(self.lookup.call_args_list[0].args, ("SYNTHETIC_KEY",))

    def test_json_deduplicates_by_provider_and_id_preserving_order(self):
        config = {"api_keys": [{"id": "same", "key": "synthetic-first", "provider": "qwen"}, {"id": "same", "key": "synthetic-second", "provider": "qwen"}, {"id": "same", "key": "synthetic-third", "provider": "gemini"}]}
        result = self.api.normalize_ai_key_items(config, "qwen")
        self.assertEqual([item["key"] for item in result], ["synthetic-first", "synthetic-third"])
        self.assertEqual([item["provider"] for item in result], ["qwen", "gemini"])

    def test_legacy_json_identity_is_stable_and_existing_item_wins(self):
        secret = "synthetic-legacy"
        env = self.api.default_secret_env_name("VANTALINE_AI_KEY", secret, provider="qwen")
        identity = self.api.secret_key_item_id(env, secret)
        result = self.api.normalize_ai_key_items({"api_key": secret}, "qwen")
        self.assertEqual(result, [{"id": identity, "label": "Qwen API Key 1", "key": secret, "env": env, "provider": "qwen"}])
        result = self.api.normalize_ai_key_items({"api_key": secret, "api_keys": [{"id": identity, "key": "synthetic-existing", "provider": "qwen"}]}, "qwen")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "synthetic-existing")

    def test_image_unknown_provider_falls_back_and_pending_environment_is_kept(self):
        config = {"image_api_keys": [False, {"id": "one", "provider": "unknown", "key": "synthetic-one"}, {"id": "two", "image_provider": " QWEN_IMAGE ", "env": "PENDING_IMAGE"}, {}]}
        result = self.api.normalize_image_key_items(config, "qwen_image")
        self.assertEqual([item["provider"] for item in result], ["qwen_image", "qwen_image"])
        self.assertEqual([item["id"] for item in result], ["one", "two"])
        self.assertEqual(result[1]["env"], "PENDING_IMAGE")

    def test_image_legacy_prefix_and_environment_precedence(self):
        self.lookup.return_value = "synthetic-environment"
        result = self.api.normalize_image_key_items({"image_api_key": "synthetic-legacy", "image_api_keys": [{"id": "one", "key": "synthetic-inline", "env": "IMAGE_KEY"}]}, "qwen_image")
        self.assertEqual(result[0]["key"], "synthetic-environment")
        self.assertTrue(result[1]["env"].startswith("VANTALINE_QWEN_IMAGE_IMAGE_KEY_"))
        self.assertEqual(result[1]["key"], "synthetic-legacy")

    def test_agent_rewrites_old_ai_namespace_but_keeps_explicit_agent_environment(self):
        config = {"provider": "qwen", "api_keys": [{"id": "old", "env": "VANTALINE_AI_KEY_OLD", "key": "synthetic-one"}, {"id": "kept", "env": "CUSTOM_AGENT_KEY", "key": "synthetic-two"}, {"id": "pending", "env": "PENDING_AGENT"}]}
        result = self.api.normalize_agent_key_items(config)
        self.assertTrue(result[0]["env"].startswith("VANTALINE_AGENT_KEY_"))
        self.assertEqual(result[1]["env"], "CUSTOM_AGENT_KEY")
        self.assertEqual(result[2]["env"], "PENDING_AGENT")
        self.assertEqual(result[2]["key"], "")

    def test_agent_unknown_provider_label_prefix_legacy_and_deduplication(self):
        config = {"provider": "qwen", "api_key": "synthetic-legacy", "api_keys": [{"id": "same", "provider": "unknown", "key": "synthetic-a", "label": "API Key custom"}, {"id": "same", "key": "synthetic-b"}]}
        result = self.api.normalize_agent_key_items(config)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["provider"], "openai_compatible")
        self.assertEqual(result[0]["label"], "Agent API Key custom")
        self.assertTrue(result[1]["env"].startswith("VANTALINE_AGENT_KEY_"))
        self.assertEqual(result[1]["key"], "synthetic-legacy")

    def test_normalizers_preserve_input_and_bound_labels(self):
        for method, key, args in [(self.api.normalize_ai_key_items, "api_keys", ("qwen",)), (self.api.normalize_image_key_items, "image_api_keys", ("qwen_image",)), (self.api.normalize_agent_key_items, "api_keys", ())]:
            with self.subTest(method=method.__name__):
                config = {"provider": "qwen", key: [{"id": "one", "key": "synthetic", "label": "x" * 100}]}
                before = copy.deepcopy(config)
                result = method(config, *args)
                self.assertEqual(config, before)
                self.assertEqual(len(result[0]["label"]), 80)
                self.assertIsNot(result[0], config[key][0])

    def test_public_projection_has_only_safe_fields_and_no_raw_key(self):
        items = [{"id": "one", "key": "synthetic-private-value", "env_name": "SYNTHETIC_KEY", "extra": "synthetic-private-extra"}, {"id": "two", "key": "", "provider": "qwen", "label": "Named"}]
        before = copy.deepcopy(items)
        result = self.api.public_ai_key_items(items)
        self.assertEqual(result, [{"id": "one", "label": "API Key 1", "masked_key": "synt...alue", "env_name": "SYNTHETIC_KEY", "provider": ""}, {"id": "two", "label": "Named", "masked_key": "", "env_name": "", "provider": "qwen"}])
        self.assertEqual(items, before)
        self.assertNotIn("synthetic-private-value", str(result))

    def test_filters_preserve_item_identity_and_case_normalization(self):
        first = {"id": "one", "provider": " QWEN "}
        second = {"id": "two", "provider": "other"}
        for method in (self.api.ai_keys_for_provider, self.api.image_keys_for_provider, self.api.agent_keys_for_provider):
            result = method([first, second], " qwen ")
            self.assertEqual(result, [first])
            self.assertIs(result[0], first)
            self.assertEqual(method([], "qwen"), [])

    def test_environment_lookup_failure_escapes_once_without_retry(self):
        for method, key, args in [(self.api.normalize_ai_key_items, "api_keys", ("qwen",)), (self.api.normalize_image_key_items, "image_api_keys", ("qwen_image",)), (self.api.normalize_agent_key_items, "api_keys", ())]:
            error = RuntimeError("synthetic lookup failure")
            self.lookup.reset_mock()
            self.lookup.side_effect = error
            with self.assertRaises(RuntimeError) as caught:
                method({"provider": "qwen", key: [{"env": "SYNTHETIC_KEY", "key": "synthetic-inline"}]}, *args)
            self.assertIs(caught.exception, error)
            self.lookup.assert_called_once_with("SYNTHETIC_KEY")


    def test_label_formatter_is_captured_before_label_read(self):
        for method, key, args in [(self.api.normalize_ai_key_items, "api_keys", ("qwen",)), (self.api.normalize_image_key_items, "image_api_keys", ("qwen_image",)), (self.api.normalize_agent_key_items, "api_keys", ())]:
            selected = Mock(return_value="selected-label")
            late = Mock(return_value="late-label")
            api = self.api
            class Item(dict):
                def get(inner, name, default=None):
                    if name == "label":
                        api.bounded_text = late
                    return super().get(name, default)
            with patch.object(api, "bounded_text", selected):
                result = method({"provider": "qwen", key: [Item(id="one", key="synthetic", label="given")]}, *args)
            self.assertEqual(result[0]["label"], "selected-label")
            selected.assert_called_once_with("given", 80)
            late.assert_not_called()

    def test_public_masker_capture_then_refresh_for_next_item(self):
        selected = Mock(return_value="selected-mask")
        late = Mock(return_value="late-mask")
        api = self.api
        class Item(dict):
            def get(inner, name, default=None):
                if name == "key":
                    api.mask_secret = late
                return super().get(name, default)
        with patch.object(api, "mask_secret", selected):
            result = api.public_ai_key_items([Item(id="one", key="synthetic-a"), {"id": "two", "key": "synthetic-b"}])
        self.assertEqual([item["masked_key"] for item in result], ["selected-mask", "late-mask"])
        selected.assert_called_once_with("synthetic-a")
        late.assert_called_once_with("synthetic-b")

    def test_supported_providers_refresh_after_environment_resolution(self):
        def resolve(name):
            self.api.AI_SUPPORTED_PROVIDERS = {"qwen", "synthetic-provider"}
            return "synthetic-value"
        self.lookup.side_effect = resolve
        with patch.object(self.api, "AI_SUPPORTED_PROVIDERS", {"qwen"}):
            result = self.api.normalize_ai_key_items({"api_keys": [{"id": "one", "env": "SYNTHETIC_KEY", "provider": "synthetic-provider"}]}, "qwen")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["provider"], "synthetic-provider")

    def test_agent_normalizer_is_selected_before_configuration_reads(self):
        selected = Mock(return_value="openai_compatible")
        late = Mock(return_value="wrong-provider")
        api = self.api
        class Config(dict):
            def get(inner, name, default=None):
                if name == "provider":
                    api.normalize_agent_provider = late
                return super().get(name, default)
        with patch.object(api, "normalize_agent_provider", selected):
            result = api.normalize_agent_key_items(Config(provider="qwen", base_url="https://synthetic.invalid", api_keys=[{"id": "one", "key": "synthetic"}]))
        self.assertEqual(result[0]["provider"], "openai_compatible")
        selected.assert_called_once_with("qwen", "https://synthetic.invalid")
        late.assert_not_called()


    def test_label_and_mask_capture_windows_include_prior_and_missing_callbacks(self):
        for site, prior_key, argument_key, args in (("label", "id", "label", ("given", 80)), ("mask", "label", "key", ("synthetic-key",))):
            for mode in ("ordinary", "prior", "missing"):
                with self.subTest(site=site, mode=mode):
                    trace = capture_key_registry_window(self.api, site, mode)
                    events = [("prior", prior_key), ("argument", argument_key)]
                    if mode == "missing":
                        self.assertEqual(trace, {"events": events, "result": None, "error": "TypeError"})
                    else:
                        tag = "A" if mode == "ordinary" else "B"
                        events.append(("call", tag, args))
                        self.assertIsNone(trace["error"])
                        self.assertEqual(trace["events"], events)
                        self.assertEqual(trace["result"][0]["label" if site == "label" else "masked_key"], tag + "-value")


    def test_constructor_does_not_read_capabilities(self):
        from dataclasses import fields
        from local_inspection_service.model_providers.key_registry import ProviderKeyRegistry
        from local_inspection_service.model_providers.key_registry_ports import KeyMaterial, KeyPresentation, JsonKeyPolicy, ImageKeyPolicy, AgentKeyPolicy
        forbidden = Mock(return_value=None)
        groups = [kind(**{field.name: forbidden for field in fields(kind)}) for kind in (KeyMaterial, KeyPresentation, JsonKeyPolicy, ImageKeyPolicy, AgentKeyPolicy)]
        self.assertIsInstance(ProviderKeyRegistry(*groups), ProviderKeyRegistry)
        forbidden.assert_not_called()

    def test_independent_compositions_do_not_use_application_callbacks(self):
        from local_inspection_service.model_providers.key_registry import ProviderKeyRegistry
        from local_inspection_service.model_providers.key_registry_ports import KeyMaterial, KeyPresentation, JsonKeyPolicy, ImageKeyPolicy, AgentKeyPolicy
        def make(prefix):
            return ProviderKeyRegistry(
                KeyMaterial(lambda: lambda name: prefix + "-secret", lambda: lambda env, secret: prefix + "-id", lambda: lambda name, secret="", provider="": prefix + "-env"),
                KeyPresentation(lambda: lambda text, limit: str(text)[:limit], lambda: lambda secret: prefix + "-mask", lambda: lambda provider: prefix + "-json", lambda: lambda provider: prefix + "-image", lambda: lambda provider: prefix + "-agent"),
                JsonKeyPolicy(lambda: "qwen", lambda: {"qwen"}),
                ImageKeyPolicy(lambda: "qwen_image", lambda: {"qwen_image"}, lambda: lambda provider: provider),
                AgentKeyPolicy(lambda: {"openai_compatible"}, lambda: lambda provider, base: "openai_compatible"),
            )
        first, second = make("first"), make("second")
        forbidden = Mock(side_effect=AssertionError("application callback used"))
        names = ("local_secret_env_value", "secret_key_item_id", "default_secret_env_name", "bounded_text", "mask_secret", "ai_provider_label", "image_generation_provider_label", "agent_provider_label", "validate_image_generation_provider", "normalize_agent_provider")
        with patch.multiple(self.api, **{name: forbidden for name in names}):
            for service, prefix in ((first, "first"), (second, "second"), (first, "first")):
                json_items = service.normalize_ai_key_items({"api_keys": [{"env": "SYNTHETIC"}]})
                image_items = service.normalize_image_key_items({"image_api_keys": [{"env": "SYNTHETIC"}]}, "qwen_image")
                agent_items = service.normalize_agent_key_items({"api_keys": [{"env": "SYNTHETIC"}]})
                for items in (json_items, image_items, agent_items):
                    self.assertEqual(items[0]["id"], prefix + "-id")
                    self.assertEqual(items[0]["key"], prefix + "-secret")
                    self.assertEqual(service.public_ai_key_items(items)[0]["masked_key"], prefix + "-mask")
            forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()

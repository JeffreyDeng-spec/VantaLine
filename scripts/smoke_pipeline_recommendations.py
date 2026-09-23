"""Synthetic original contracts for pipeline recommendation helpers."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PipelineRecommendationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime = ExitStack()
        cls.lifetime.enter_context(patch.dict(os.environ))
        root = Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix="pipeline-recommendation-")))
        (root / "local_inspection_service/static").mkdir(parents=True)
        for key in ("DATABASE_URL", "VANTALINE_POSTGRES_DSN", "PGDSN"):
            os.environ.pop(key, None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE="json",
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER="0", VANTALINE_LABEL_INSPECTION_ENABLED="false",
                          YOLO_AUTOINSTALL="false")
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen", "subprocess.Popen", "os.kill"):
            cls.lifetime.enter_context(patch(name, side_effect=AssertionError("external operation forbidden")))
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.lifetime.close()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.task = {"id": "r1", "detection_method": "yolo", "stage": "draft", "status": "ready",
                     "accessory_ids": ["first", 2], "params": {"train_mode": "yolo"}}

    def replace(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.api, name, **kwargs))

    def test_signature_uses_ordered_ids_and_training_only_count(self):
        self.assertEqual(self.api.pipeline_recommendation_signature(self.task, "samples"), "samples|first,2|0")
        self.task["params"]["sample_count"] = "002"
        self.assertEqual(self.api.pipeline_recommendation_signature(self.task, "training"), "training|first,2|2")
        self.assertEqual(self.api.pipeline_recommendation_signature(self.task, "other"), "other|first,2|0")

    def test_signature_handles_null_params_and_invalid_training_count(self):
        self.task["params"] = None
        self.assertEqual(self.api.pipeline_recommendation_signature(self.task, "training"), "training|first,2|0")
        self.task["params"] = {"sample_count": "bad"}
        self.assertEqual(self.api.pipeline_recommendation_signature(self.task, "samples"), "samples|first,2|0")
        with self.assertRaises(ValueError):
            self.api.pipeline_recommendation_signature(self.task, "training")

    def test_signature_preserves_stringification_failure(self):
        error = RuntimeError("synthetic stringify")
        class Bad:
            def __str__(self):
                raise error
        self.task["accessory_ids"] = [Bad()]
        with self.assertRaises(RuntimeError) as raised:
            self.api.pipeline_recommendation_signature(self.task, "training")
        self.assertIs(raised.exception, error)

    def test_next_stage_draft_samples_and_training(self):
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "samples")
        self.task["params"]["sample_count"] = 0
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "")
        self.task["stage"] = "samples"
        self.task["status"] = "completed"
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "training")
        self.task["params"]["epochs"] = 0
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "")

    def test_next_stage_nontraining_and_missing_status(self):
        self.task["detection_method"] = "ai"
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "")
        self.task.update(detection_method="yolo", stage="samples", status="")
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "")

    def test_next_stage_selects_normalizer_and_training_policy_late(self):
        events = []
        self.replace("normalize_pipeline_detection_method", side_effect=lambda raw: events.append(("normalize", raw)) or "synthetic")
        self.replace("pipeline_method_uses_training", side_effect=lambda method: events.append(("training", method)) or True)
        self.task["detection_method"] = ""
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "samples")
        self.assertEqual(events, [("normalize", "yolo"), ("training", "synthetic")])

    def test_next_stage_does_not_normalize_malformed_truthy_params(self):
        normalize = self.replace("normalize_pipeline_detection_method", return_value="yolo")
        self.task["detection_method"] = ""
        self.task["params"] = ["wrong"]
        with self.assertRaises(AttributeError):
            self.api.pipeline_next_recommendation_stage(self.task)
        normalize.assert_not_called()

    def test_ready_requires_matching_stage_signature_and_dictionary_params(self):
        signature = self.api.pipeline_recommendation_signature(self.task, "samples")
        self.task["recommended_params"] = {"stage": "samples", "signature": signature, "params": {}}
        self.assertTrue(self.api.pipeline_recommendation_ready(self.task, "samples"))
        self.task["recommended_params"]["params"] = []
        self.assertFalse(self.api.pipeline_recommendation_ready(self.task, "samples"))
        self.task["recommended_params"]["params"] = {}
        self.assertFalse(self.api.pipeline_recommendation_ready(self.task, "training"))

    def test_ready_skips_signature_on_wrong_stage_and_uses_late_root(self):
        signature = self.replace("pipeline_recommendation_signature", return_value="late")
        self.task["recommended_params"] = {"stage": "other", "signature": "late", "params": {}}
        self.assertFalse(self.api.pipeline_recommendation_ready(self.task, "samples"))
        signature.assert_not_called()
        self.task["recommended_params"]["stage"] = "samples"
        self.assertTrue(self.api.pipeline_recommendation_ready(self.task, "samples"))
        signature.assert_called_once_with(self.task, "samples")

    def test_consume_returns_copy_and_clears_after_annotations(self):
        params = {"sample_count": 100}
        self.task["recommended_params"] = {"stage": "samples", "params": params, "reason": "because", "source": "rules"}
        result = self.api.consume_pipeline_recommendation(self.task, "samples")
        self.assertEqual(result, params)
        self.assertIsNot(result, params)
        self.assertNotIn("recommended_params", self.task)
        self.assertEqual((self.task["agent_reason"], self.task["agent_source"]), ("because", "rules"))

    def test_consume_mismatch_leaves_task_unchanged(self):
        self.task["recommended_params"] = {"stage": "training", "params": {"epochs": 3}}
        before = copy.deepcopy(self.task)
        self.assertIsNone(self.api.consume_pipeline_recommendation(self.task, "samples"))
        self.assertEqual(self.task, before)

    def test_consume_empty_reason_source_preserves_existing_metadata(self):
        self.task.update(agent_reason="old", agent_source="old")
        self.task["recommended_params"] = {"stage": "samples", "params": {}, "reason": "", "source": None}
        self.assertEqual(self.api.consume_pipeline_recommendation(self.task, "samples"), {})
        self.assertEqual((self.task["agent_reason"], self.task["agent_source"]), ("old", "old"))

    def test_collect_keeps_order_duplicates_and_none_id_string(self):
        first = dict(self.task, id=None)
        second = dict(self.task, id="same")
        third = dict(self.task, id="same")
        self.assertEqual(self.api.collect_pipeline_recommendation_pregen([first, second, third]),
                         [("None", "samples"), ("same", "samples"), ("same", "samples")])

    def test_collect_skips_ready_and_nontraining(self):
        ready = copy.deepcopy(self.task)
        ready["recommended_params"] = {"stage": "samples", "signature": self.api.pipeline_recommendation_signature(ready, "samples"), "params": {}}
        ai = dict(self.task, id="ai", detection_method="ai")
        self.assertEqual(self.api.collect_pipeline_recommendation_pregen([ready, ai]), [])

    def test_collect_uses_late_root_helpers_each_item(self):
        calls = []
        def next_stage(task):
            calls.append(("stage", task["id"]))
            return "samples"
        def ready(task, stage):
            calls.append(("ready", task["id"], stage))
            return task["id"] == "second"
        self.replace("pipeline_next_recommendation_stage", new=next_stage)
        self.replace("pipeline_recommendation_ready", new=ready)
        tasks = [dict(self.task, id="first"), dict(self.task, id="second")]
        self.assertEqual(self.api.collect_pipeline_recommendation_pregen(tasks), [("first", "samples")])
        self.assertEqual(calls, [("stage", "first"), ("ready", "first", "samples"),
                                 ("stage", "second"), ("ready", "second", "samples")])


    def test_next_stage_chooses_normalizer_before_effectful_str_and_refreshes_policy(self):
        events = []
        def old_normalize(raw):
            events.append(("old-normalize", raw))
            self.api.pipeline_method_uses_training = lambda method: events.append(("new-policy", method)) or True
            return "from-old"
        def late_normalize(raw):
            raise AssertionError("normalizer rebound during argument evaluation")
        self.replace("normalize_pipeline_detection_method", new=old_normalize)
        self.replace("pipeline_method_uses_training", new=lambda method: False)
        class Method:
            def __str__(inner):
                events.append(("str",))
                self.api.normalize_pipeline_detection_method = late_normalize
                return "yolo"
        self.task["detection_method"] = Method()
        self.assertEqual(self.api.pipeline_next_recommendation_stage(self.task), "samples")
        self.assertEqual(events, [("str",), ("old-normalize", "yolo"), ("new-policy", "from-old")])

    def test_ready_reselects_signature_after_effectful_record_get(self):
        events = []
        class Recommendation(dict):
            def get(inner, key, default=None):
                if key == "signature":
                    events.append("signature-value")
                    self.api.pipeline_recommendation_signature = lambda task, stage: "late"
                return super().get(key, default)
        self.task["recommended_params"] = Recommendation(stage="samples", signature="late", params={})
        self.replace("pipeline_recommendation_signature", new=lambda task, stage: "early")
        self.assertTrue(self.api.pipeline_recommendation_ready(self.task, "samples"))
        self.assertEqual(events, ["signature-value"])

    def test_consume_ignores_stale_signature_and_shallow_copies(self):
        nested = {"sample_count": 5}
        original = {"nested": nested}
        self.task["recommended_params"] = {"stage": "samples", "signature": "stale", "params": original}
        consumed = self.api.consume_pipeline_recommendation(self.task, "samples")
        self.assertEqual(consumed, original)
        self.assertIsNot(consumed, original)
        self.assertIs(consumed["nested"], nested)
        self.assertNotIn("recommended_params", self.task)

    def test_consume_pop_failure_keeps_prior_metadata_changes(self):
        error = TypeError("synthetic pop failure")
        class Task(dict):
            def pop(inner, key, default=None):
                raise error
        task = Task(self.task)
        recommendation = {"stage": "samples", "params": {}, "reason": "new", "source": "rules"}
        task["recommended_params"] = recommendation
        with self.assertRaises(TypeError) as raised:
            self.api.consume_pipeline_recommendation(task, "samples")
        self.assertIs(raised.exception, error)
        self.assertEqual((task["agent_reason"], task["agent_source"]), ("new", "rules"))
        self.assertIs(task["recommended_params"], recommendation)

    def test_consume_copy_failure_keeps_prior_metadata_changes(self):
        error = TypeError("synthetic copy failure")
        class BadCopy:
            @property
            def __class__(self):
                return dict
            def keys(self):
                raise error
        params = BadCopy()
        self.assertIsInstance(params, dict)
        recommendation = {"stage": "samples", "params": params, "reason": "new", "source": "rules"}
        self.task["recommended_params"] = recommendation
        with self.assertRaises(TypeError) as raised:
            self.api.consume_pipeline_recommendation(self.task, "samples")
        self.assertIs(raised.exception, error)
        self.assertEqual((self.task["agent_reason"], self.task["agent_source"]), ("new", "rules"))
        self.assertIs(self.task["recommended_params"], recommendation)
    def test_collect_refreshes_stage_and_ready_between_records(self):
        calls = []
        def first_stage(task):
            calls.append(("first-stage", task["id"]))
            return "samples"
        def second_stage(task):
            calls.append(("second-stage", task["id"]))
            return "training"
        def first_ready(task, stage):
            calls.append(("first-ready", task["id"], stage))
            self.api.pipeline_next_recommendation_stage = second_stage
            self.api.pipeline_recommendation_ready = lambda task, stage: calls.append(("second-ready", task["id"], stage)) or False
            return False
        self.replace("pipeline_next_recommendation_stage", new=first_stage)
        self.replace("pipeline_recommendation_ready", new=first_ready)
        tasks = [dict(self.task, id="one"), dict(self.task, id="two")]
        self.assertEqual(self.api.collect_pipeline_recommendation_pregen(tasks),
                         [("one", "samples"), ("two", "training")])
        self.assertEqual(calls, [("first-stage", "one"), ("first-ready", "one", "samples"),
                                 ("second-stage", "two"), ("second-ready", "two", "training")])


    def test_independent_services_keep_all_five_capabilities_isolated(self):
        from local_inspection_service.pipeline.recommendations import PipelineRecommendations
        from local_inspection_service.pipeline.recommendation_ports import (
            PipelineRecommendationLinks, PipelineRecommendationMethodPolicy,
        )
        poison = Mock(side_effect=AssertionError("root dependency escape"))
        for name in ("normalize_pipeline_detection_method", "pipeline_method_uses_training",
                     "pipeline_recommendation_signature", "pipeline_next_recommendation_stage",
                     "pipeline_recommendation_ready"):
            self.replace(name, new=poison)
        events = []
        def make(label):
            values = {
                "normalize": lambda raw: "yolo",
                "uses_training": lambda method: True,
                "signature": lambda task, stage: label + "-sig",
                "next_stage": lambda task: "samples",
                "ready": lambda task, stage: bool(task.get("skip")),
            }
            def getter(key):
                def get():
                    events.append((label, key))
                    return values[key]
                return get
            service = PipelineRecommendations(
                PipelineRecommendationMethodPolicy(**{key: getter(key) for key in ("normalize", "uses_training")}),
                PipelineRecommendationLinks(**{key: getter(key) for key in ("signature", "next_stage", "ready")}),
            )
            return service, set(values)
        a = make("A")
        b = make("B")
        self.assertEqual(events, [])
        for label, (service, keys) in (("A", a), ("B", b), ("A", a)):
            start = len(events)
            task = {"id": label, "detection_method": "yolo", "stage": "draft", "status": "ready",
                    "accessory_ids": ["part"], "params": {}}
            self.assertEqual(service.pipeline_recommendation_signature(
                dict(task, params={"sample_count": 3}), "training"), "training|part|3")
            self.assertEqual(service.pipeline_next_recommendation_stage(task), "samples")
            task["recommended_params"] = {"stage": "samples", "signature": label + "-sig", "params": {}}
            self.assertTrue(service.pipeline_recommendation_ready(task, "samples"))
            self.assertEqual(service.consume_pipeline_recommendation(task, "samples"), {})
            self.assertEqual(service.collect_pipeline_recommendation_pregen([task, dict(task, id="skip", skip=True)]),
                             [(label, "samples")])
            self.assertEqual({who for who, key in events[start:]}, {label})
            self.assertEqual({key for who, key in events[start:]}, keys)
        poison.assert_not_called()


if __name__ == "__main__":
    unittest.main()

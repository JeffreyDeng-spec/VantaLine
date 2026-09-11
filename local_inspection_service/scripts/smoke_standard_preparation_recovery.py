"""No provider calls. Recovery geometry, hostile proposals and original evidence."""
import copy
import unittest

from local_inspection_service import standard_preparation as engine
from local_inspection_service.standard_preparation_recovery import recover
from local_inspection_service.scripts.smoke_standard_preparation import fixture


class RecoveryContracts(unittest.TestCase):
    def setUp(self):
        self.image, self.original = fixture()
        self.elements = self.original[1:]
        self.classification = dict(kind="label_design", coverage_complete=True, reason="fixture",
            elements=[{k:e[k] for k in ("id", "state", "reason")} for e in self.elements],
            missing_regions=[dict(box=[.04, .04, .20, .08], state="exclude", reason="outside dimensions")])

    def observe(self, image, timeout):
        # Map the original fixture measurement into the rounded local crop.
        l, t, r, b = engine.pixels(self.classification["missing_regions"][0]["box"], self.image.size)
        x, y, w, h = self.original[0]["box"]
        return [{**self.original[0], "box": [(x*600-l)/(r-l), (y*500-t)/(b-t), w*600/(r-l), h*500/(b-t)]}]

    def test_recovers_without_rewriting_and_keeps_pixels(self):
        before = copy.deepcopy(self.elements)
        events = []
        merged, proof = recover(self.image, self.elements, self.classification, self.observe,
            progress=lambda state, image, overlay: events.append(state))
        self.assertEqual(before, self.elements)
        self.assertFalse(proof["reasons"])
        self.assertEqual(events[0]["regions"][0]["state"], "recognizing")
        recovered = merged[-1]
        self.assertEqual(recovered["id"], "r1e1")
        self.assertEqual(recovered["text"], self.original[0]["text"])
        for a, b in zip(recovered["box"], self.original[0]["box"]):
            self.assertAlmostEqual(a, b)
        expected, _ = engine.clean(self.image, self.original)
        actual, meta = engine.clean(self.image, merged)
        self.assertFalse(meta["reasons"])
        self.assertEqual(actual, expected)

    def test_schema_and_limits(self):
        for update in ({"text": "invented"}, {"box": [float("nan"),0,.1,.1]}, {"box":[0,0,1,1]}, {"state":"erase"}):
            bad = copy.deepcopy(self.classification)
            bad["missing_regions"][0].update(update)
            with self.assertRaises(ValueError): engine.classify(bad, self.elements)
        bad = copy.deepcopy(self.classification)
        bad["missing_regions"] *= 9
        with self.assertRaises(ValueError): engine.classify(bad, self.elements)
        bad["missing_regions"] = [dict(box=[0,0,.4,.4],state="keep",reason="fixture")]*3
        with self.assertRaises(ValueError): engine.classify(bad, self.elements)

    def test_fractional_crop_rounding_still_maps_to_source(self):
        self.classification["missing_regions"][0]["box"] = [.0391,.0394,.2019,.0821]
        merged, proof = recover(self.image, self.elements, self.classification, self.observe)
        self.assertFalse(proof["reasons"])
        for actual, expected in zip(merged[-1]["box"], self.original[0]["box"]):
            self.assertLess(abs(actual-expected)*max(self.image.size), 1)

    def test_empty_timeout_and_truncation_review(self):
        for observe in (lambda *a, **kw: [], lambda *a, **kw: [{**self.original[0], "box": [0,0,.4,.4]}]):
            _, proof = recover(self.image, self.elements, self.classification, observe)
            self.assertTrue(proof["reasons"])
        def failure(*args, **kwargs): raise TimeoutError("timeout")
        _, proof = recover(self.image, self.elements, self.classification, failure)
        self.assertTrue(proof["reasons"])
        _, proof = recover(self.image, self.elements, self.classification, self.observe, timeout=0)
        self.assertTrue(proof["reasons"])

    def test_duplicate_and_conflict_do_not_override_existing(self):
        merged, proof = recover(self.image, self.original, self.classification, self.observe)
        self.assertEqual(merged, self.original)
        self.assertEqual(proof["regions"][0]["deduplicated_ids"], ["e1"])
        def conflicting(*a, **kw):
            return [{**self.observe(*a, **kw)[0], "text":"different OCR reading"}]
        merged, proof = recover(self.image, self.original, self.classification, conflicting)
        self.assertEqual(merged[:-1], self.original)
        self.assertEqual(merged[-1]["state"], "uncertain")
        self.assertTrue(proof["reasons"])

    def test_no_local_calls_for_non_label(self):
        self.classification["kind"] = "non_label"
        def forbidden(*a, **kw): raise AssertionError("must not run OCR")
        _, proof = recover(self.image, self.elements, self.classification, forbidden)
        self.assertEqual(proof["reasons"], ["not_single_label_design"])

    def test_unremoved_separate_notes_block_auto_even_if_unobserved(self):
        # No erasure merely because a line is separated; human confirmation needed.
        _, result = engine.clean(self.image, self.elements)
        self.assertIn("separated_content_groups_require_review", result["reasons"])
        self.assertFalse(result["removed"])
        wrongly_kept = copy.deepcopy(self.original)
        wrongly_kept[0]["state"] = "keep"
        self.assertIn("separated_content_groups_require_review", engine.clean(self.image, wrongly_kept)[1]["reasons"])


if __name__ == "__main__": unittest.main()

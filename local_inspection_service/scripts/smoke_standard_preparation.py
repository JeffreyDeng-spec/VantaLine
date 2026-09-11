"""Synthetic contracts, not model accuracy evidence. Outputs inspectable PNGs."""
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import numpy as np
from PIL import Image, ImageDraw
from local_inspection_service import standard_preparation as engine


def fixture():
    image = Image.new("RGBA", (600, 500), "white")
    draw = ImageDraw.Draw(image)
    draw.text((42, 32), "DESIGN 46.6mm", fill="black")
    draw.rectangle((100, 150, 450, 450), fill="black")
    draw.text((125, 190), "MODEL ABC-120", fill="white")
    draw.text((125, 230), "20V", fill="white")
    draw.rectangle((125, 390, 155, 430), fill="white")
    elements = [dict(id="e1", text="DESIGN 46.6mm", type="text", state="exclude", reason="outside", confidence=.99, box=[.065, .058, .14, .035]),
                dict(id="e2", text="MODEL ABC-120", type="text", state="keep", reason="inside", confidence=.99, box=[.20, .37, .25, .06]),
                dict(id="e3", text="20V", type="text", state="keep", reason="inside", confidence=.99, box=[.20, .45, .09, .06])]
    return image, elements


class Contracts(unittest.TestCase):
    def test_pixels_and_reuse(self):
        image, elements = fixture()
        output, result = engine.clean(image, elements)
        self.assertFalse(result["reasons"])
        self.assertEqual(elements[0]["state"], "exclude")
        cleaned = np.asarray(Image.open(io.BytesIO(output)))
        left, top, right, bottom = result["crop_pixels"]
        source = np.asarray(image)[top:bottom, left:right]
        self.assertTrue(np.array_equal(cleaned, source))
        self.assertLess(left, 100)
        self.assertGreater(bottom, 450)
        for original, mapped in zip(elements, result["elements"]):
            self.assertAlmostEqual(mapped["clean_box"][0]*(right-left)+left, original["box"][0]*600)
        path = Path(tempfile.mkdtemp(prefix="standard-preparation-test-"))
        image.save(path/"original.png")
        (path/"clean.png").write_bytes(output)
        (path/"elements.png").write_bytes(engine.overlay(image, elements))
        (path/"result.json").write_text(json.dumps(result, indent=2))
        print("Synthetic image evidence:", path)

    def test_id_schema(self):
        _, elements = fixture()
        value = dict(kind="label_design", coverage_complete=True, reason="fixture", elements=[dict(id=e["id"], state=e["state"], reason="fixture") for e in elements])
        self.assertEqual(engine.classify(value, elements)[1]["text"], elements[1]["text"])
        value["elements"][0]["text"] = "rewritten"
        with self.assertRaises(ValueError): engine.classify(value, elements)
        value["elements"][0].pop("text")
        value["elements"][0]["id"] = "e2"
        with self.assertRaises(ValueError): engine.classify(value, elements)

    def test_fail_closed(self):
        image, elements = fixture()
        uncertain = copy.deepcopy(elements)
        uncertain[0]["state"] = "uncertain"
        self.assertTrue(engine.clean(image, uncertain)[1]["reasons"])
        unsafe = copy.deepcopy(elements)
        unsafe[0]["box"] = [.16, .3, .6, .15]
        self.assertTrue(engine.clean(image, unsafe)[1]["reasons"])
        dark = Image.new("RGBA", image.size, "gray")
        self.assertTrue(engine.clean(dark, elements)[1]["reasons"])
        for invalid in ([float("nan"), 0, .1, .1], [-.1, 0, .2, .2], [0, 0, 0, .1], [0, 0, 2, 1], [True, 0, 1, 1]):
            with self.assertRaises(ValueError): engine.box(invalid)
        with self.assertRaises(ValueError): engine.clean(image, elements, crop_box=[0, 0, .1, .1])

    def test_no_numeric_substring_pass(self):
        _, elements = fixture()
        elements[2]["clean_box"] = elements[2]["box"]
        expected = [elements[2]]
        for actual in ("120V", "20v", "20.0V"):
            observations = [dict(type="text", text=actual, box=[0, 0, .5, .5], confidence=1)]
            self.assertEqual(engine.match(expected, observations)[0]["state"], "review")
        self.assertEqual(engine.match(expected, [dict(type="text", text="20V", box=[0,0,.5,.5], confidence=1)])[0]["state"], "matched")


if __name__ == "__main__":
    unittest.main()

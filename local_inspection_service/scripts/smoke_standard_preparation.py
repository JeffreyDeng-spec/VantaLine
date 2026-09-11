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
    def test_edge_and_protected_subtraction(self):
        cases = {
            "top": (10, 0, 30, 12), "bottom": (10, 88, 30, 100),
            "left": (0, 10, 12, 30), "right": (88, 10, 100, 30),
            "corner": (0, 0, 20, 20), "overlap": (30, 30, 60, 60),
            "contained": (42, 42, 48, 48), "touch": (20, 40, 40, 60),
        }
        for name, rect in cases.items():
            for protected_state in ("keep", "uncertain"):
                with self.subTest(name=name, protected_state=protected_state):
                    image = Image.new("RGBA", (100, 100), "white")
                    data = np.asarray(image).copy()
                    x1, y1, x2, y2 = rect
                    data[y1:y2, x1:x2] = [0, 0, 0, 255]
                    data[40:60, 40:60] = [30, 60, 90, 123]
                    image = Image.fromarray(data)
                    elements = [dict(id="e1", type="text", text="note", state="exclude", confidence=1,
                                     box=[x1/100, y1/100, (x2-x1)/100, (y2-y1)/100]),
                                dict(id="e2", type="text", text="MODEL", state=protected_state, confidence=1,
                                     box=[.4, .4, .2, .2])]
                    output, result = engine.clean(image, elements, crop_box=[0, 0, 1, 1], human=True)
                    self.assertFalse(any("unsafe" in r or "overlap_or_edge" in r for r in result["reasons"]))
                    expected = data.copy()
                    ex1, ey1, ex2, ey2 = engine.pixels(elements[0]["box"], image.size)
                    expected[ey1:ey2, ex1:ex2] = 255
                    expected[40:60, 40:60] = data[40:60, 40:60]
                    self.assertTrue(np.array_equal(np.asarray(Image.open(io.BytesIO(output))), expected))
                    self.assertEqual(result["removed"][0]["erased_pixel_count"],
                                     (ex2-ex1)*(ey2-ey1)-max(0, min(ex2, 60)-max(ex1, 40))*max(0, min(ey2, 60)-max(ey1, 40)))

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
        value = dict(kind="label_design", coverage_complete=True, missing_regions=[], reason="fixture", elements=[dict(id=e["id"], state=e["state"], reason="fixture") for e in elements])
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

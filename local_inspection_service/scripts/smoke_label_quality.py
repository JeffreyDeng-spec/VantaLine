"""Local gate contracts; generated fixtures only, no provider/network/customer data."""

import base64
import copy
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import cv2
import numpy as np
from PIL import Image, ImageFilter
from local_inspection_service.label_inspection import model, quality
from local_inspection_service.label_inspection.worker import process


def picture(blur=0):
    a = np.full((600, 800, 3), 190, np.uint8)
    cv2.rectangle(a, (90, 65), (710, 535), (22, 22, 22), -1)
    for row in range(10):
        cv2.putText(
            a,
            f"LABEL {row} 20V 2000mAh",
            (115, 110 + row * 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (245, 245, 245),
            1,
            cv2.LINE_AA,
        )
    im = Image.fromarray(a)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def combined():
    sharp = Image.open(io.BytesIO(picture()))
    blur = Image.open(io.BytesIO(picture(7)))
    out = Image.new("RGB", (1600, 600), (190, 190, 190))
    out.paste(sharp, (0, 0))
    out.paste(blur, (800, 0))
    b = io.BytesIO()
    out.save(b, "PNG")
    return b.getvalue()


class Repo:
    def __init__(self):
        self.value = {}
        self.calls = []

    def update_run(self, owner, identity, **kw):
        self.value.update(copy.deepcopy(kw))

    def begin_call(self, *args):
        self.calls.append(args)
        return {"id": str(len(self.calls))}

    def finish_call(self, *args, **kw):
        pass


class Media:
    def __init__(self, actual):
        self.actual = actual

    def read(self, owner, key):
        return self.actual if key == "actual" else picture()

    def put(self, owner, data):
        return "sha"


def execute(actual, layout, policy=None):
    repo = Repo()
    bodies = []

    def invoke(body, key):
        bodies.append(copy.deepcopy(body))
        response = (
            layout
            if len(bodies) == 1
            else {"hasDiff": False, "similarity": 99, "issues": []}
        )
        return 200, json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(response)},
                    }
                ]
            }
        )

    run = {
        "owner_user_id": "alice",
        "id": "test",
        "model": model.MODEL,
        "prompt_hash": model.PROMPT_HASH,
        "reference": {"media": {"original": "reference"}},
        "actual": {"original": "actual"},
        "quality": {
            "policy": copy.deepcopy(quality.POLICY if policy is None else policy)
        },
    }
    process(repo, Media(actual), run, "fake-placeholder", invoke)
    return repo, bodies


def main():
    single = {"isMultiLabel": False, "labelCount": 1}
    original = picture()
    im, _ = model.decode(original)
    prepared = model.jpeg(im)
    result = quality.inspect(prepared, im.size)
    assert result["passed"], result
    assert prepared == model.jpeg(im)
    repo, bodies = execute(original, single)
    assert repo.value["status"] == "completed" and len(bodies) == 2, repo.value
    # Exact existing body/image bytes, no model-input mutation by gate.
    assert bodies[0] == model.payload("layout", [prepared])
    assert bodies[1] == model.payload(
        "compare", [model.jpeg(model.decode(picture())[0]), prepared], False
    )
    for raw in [picture(7), original]:
        if raw == original:
            b = io.BytesIO()
            Image.new("RGB", (800, 600), "white").save(b, "PNG")
            raw = b.getvalue()
        r, calls = execute(raw, single)
        assert (
            len(calls) == 0
            and r.value["decision"] == "REVIEW_REQUIRED"
            and r.value["error_code"].startswith("QUALITY_")
        ), r.value
        assert not r.value.get("result")
    r, calls = execute(original, single, {"version": "obsolete"})
    assert not calls and r.value["error_code"] == "QUALITY_POLICY_CHANGED"
    multi = combined()
    im, _ = model.decode(multi)
    pre = quality.inspect(model.jpeg(im), im.size)
    assert (
        len(pre["candidates"]) == 2 and sum(c["passed"] for c in pre["candidates"]) == 1
    ), pre
    for x, count in [(0, 2), (0.5, 1)]:
        layout = {
            "isMultiLabel": True,
            "labelCount": 2,
            "cropRect": {"x": x, "y": 0, "w": 0.5, "h": 1},
        }
        r, calls = execute(multi, layout)
        assert len(calls) == count, (x, r.value)
        if count == 2:
            crop = model.crop_rect(layout, im.size)
            a, b, w, h = crop
            assert calls[1] == model.payload(
                "compare",
                [
                    model.jpeg(model.decode(picture())[0]),
                    model.jpeg(im.crop((a, b, a + w, b + h))),
                ],
                True,
            )
        else:
            assert r.value["error_code"] == "QUALITY_SELECTED_REJECTED"
    r, calls = execute(multi, single)
    assert len(calls) == 1 and r.value["error_code"] == "QUALITY_TARGET_UNCERTAIN"
    for crop in [(0, 0, 1600, 600), (200, 150, 100, 100)]:
        assert quality.selected(pre, crop, im.size) is None
    for angle in [90, 180, 270]:
        rotated = model.decode(original)[0].rotate(angle, expand=True)
        assert quality.inspect(model.jpeg(rotated), rotated.size)["passed"]
    # Removing a printed line is a product defect, not a quality rejection.
    missing = np.array(model.decode(original)[0])
    missing[170:205, 110:690] = 22
    defect = Image.fromarray(missing)
    assert quality.inspect(model.jpeg(defect), defect.size)["passed"]
    # A white/light label is deliberately unsupported rather than silently admitted.
    inverted = Image.fromarray(255 - np.array(model.decode(original)[0]))
    assert not quality.inspect(model.jpeg(inverted), inverted.size)["passed"]
    small = model.decode(original)[0].resize((240, 180))
    assert not quality.inspect(model.jpeg(small), small.size)["passed"]
    print("label quality offline + 0/1/2-call/input-byte contracts PASS")


if __name__ == "__main__":
    main()

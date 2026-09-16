"""Synthetic PDF geometry and real PostgreSQL import/call isolation regressions."""

import copy
import io
import json
import uuid

import fitz
from PIL import Image
from local_inspection_service.label_inspection import model, manual, pdf_import
from local_inspection_service.label_inspection.api import PREFIX, image
from local_inspection_service.label_inspection.worker import process


def document():
    doc = fitz.open()
    for w, h, rotation in [(800, 400, 0), (400, 800, 90), (400, 800, 0), (400, 400, 0)]:
        p = doc.new_page(width=w, height=h)
        p.draw_rect(fitz.Rect(0, 0, w / 2, h), fill=(1, 0, 0), color=None)
        p.draw_rect(fitz.Rect(w / 2, 0, w, h), fill=(0, 0, 1), color=None)
        p.set_rotation(rotation)
    return doc.tobytes()


def check_all(client, check, repo, media, close_connections):
    agreement = {
        "reviewRequired": False,
        "hasDiff": False,
        "similarity": 100,
        "issues": [],
        "consistentItems": [{"description": "标题一致", "type": "text"}, "页码一致"],
    }
    before = copy.deepcopy(agreement)
    assert manual.result(agreement, None, (800, 1000))["consistent_items"] == [
        "标题一致",
        "页码一致",
    ]
    assert agreement == before
    for invalid in [
        {**agreement, "hasDiff": True},
        {**agreement, "consistentItems": [{}]},
        {**agreement, "consistentItems": [{"description": 42}]},
    ]:
        try:
            manual.result(invalid, None, (800, 1000))
        except ValueError:
            pass
        else:
            raise AssertionError("invalid or contradictory PDF results must not pass")
    data = document()
    entries = pdf_import.inspect(data)
    assert len(entries) == 6
    assert [e["side"] for e in entries] == ["左", "右", "左", "右", "整页", "整页"]
    with fitz.open(stream=data, filetype="pdf") as doc:
        left, _ = pdf_import.render(doc, entries[0])
        right, _ = pdf_import.render(doc, entries[1])
        rotated, _ = pdf_import.render(doc, entries[2])
        assert left.getpixel((100, 100)) == (255, 0, 0)
        assert right.getpixel((100, 100)) == (0, 0, 255)
        assert rotated.getpixel((100, 100)) == (255, 0, 0)
        assert rotated.getpixel((100, rotated.height - 100)) == (0, 0, 255)
        assert max(left.size) == 3200

    def create(payload=data, name="说明书.pdf", request=None, status=202):
        return check(
            client.post(
                PREFIX + "/tasks",
                data={"request_id": request or uuid.uuid4().hex},
                files={"file": (name, payload)},
            ),
            status,
        )

    request = uuid.uuid4().hex
    task = create(request=request)
    assert (
        task["status"] == "import_queued"
        and task["assets"] == []
        and task["revision"] == 0
    )
    assert create(request=request)["id"] == task["id"]
    check(
        client.get(PREFIX + "/tasks/" + task["id"], headers={"x-test-owner": "bob"}),
        404,
    )
    check(
        client.post(
            PREFIX + "/tasks/" + task["id"] + "/runs",
            data={"request_id": uuid.uuid4().hex, "revision": 0, "asset_id": "missing"},
            files={"file": ("x.png", b"bad")},
        ),
        422,
    )
    claim = repo.claim_pdf("first")
    assert claim["id"] == task["id"] and repo.claim_pdf("other") is None
    with fitz.open(stream=data, filetype="pdf") as doc:
        pic, blob = pdf_import.render(doc, entries[0])
    sha = media.put("alice", blob)
    assets = [
        {
            "id": "first-page",
            "ordinal": 1,
            "name": "第一张",
            "enabled": True,
            "pdf": entries[0],
            "media": {
                "original": sha,
                "image": sha,
                "preview": media.put("alice", model.jpeg(pic)),
            },
        }
    ]
    assert repo.pdf_progress("alice", task["id"], "first", assets)
    with repo.tx() as c:
        stale = repo.read(c, "alice", task["id"])
        stale["import"]["lease_until"] = 0
        repo.put(c, stale)
    resumed = repo.claim_pdf("resumed")
    assert resumed["import"]["completed"] == 1
    assert not repo.pdf_progress("alice", task["id"], "first", [], error="stale")
    pdf_import.process(repo, media, resumed, "resumed")
    ready = check(client.get(PREFIX + "/tasks/" + task["id"]))
    assert (
        ready["status"] == "ready"
        and ready["revision"] == 1
        and len(ready["assets"]) == 6
    )
    assert ready["assets"][0]["id"] == "first-page"
    assert "entries" not in ready["import"] and "token" not in ready["import"]
    assert any(
        t["id"] == task["id"]
        for t in check(client.get(PREFIX + "/tasks?source=pdf"))["items"]
    )
    close_connections()
    good = {
        "pageCount": 1,
        "complete": True,
        "readable": True,
        "certain": True,
        "cropRect": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
    }
    actual = image(media, "alice", manual.jpeg(Image.new("RGB", (1200, 1600), "white")))
    cases = [
        (
            good,
            {
                "reviewRequired": False,
                "hasDiff": False,
                "similarity": 100,
                "issues": [],
            },
            2,
            "MATCH",
        ),
        ({**good, "pageCount": 2}, {}, 1, "REVIEW_REQUIRED"),
        ({**good, "complete": False}, {}, 1, "REVIEW_REQUIRED"),
        ({**good, "readable": False}, {}, 1, "REVIEW_REQUIRED"),
        (
            {**good, "cropRect": {"x": 0, "y": 0, "w": 2, "h": 1}},
            {},
            1,
            "REVIEW_REQUIRED",
        ),
        (good, {"reviewRequired": True}, 2, "REVIEW_REQUIRED"),
    ]
    for layout, result, count, decision in cases:
        run = repo.submit(
            "alice",
            task["id"],
            uuid.uuid4().hex,
            1,
            ready["assets"][0]["id"],
            actual,
            model.MODEL,
            manual.PROMPT_HASH,
        )
        assert (
            run["strategy"] == manual.VERSION
            and run["quality"]["policy"] == manual.POLICY
        )
        calls = []

        def invoke(body, key):
            calls.append(body)
            assert (
                body["model"] == model.MODEL
                and body["temperature"] == 0.1
                and body["thinking"] == {"type": "disabled"}
            )
            assert body["max_tokens"] == (1024 if len(calls) == 1 else 8192)
            answer = layout if len(calls) == 1 else result
            return 200, json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(answer)},
                        }
                    ]
                }
            )

        process(repo, media, repo.claim(), "test", invoke)
        final = repo.get("alice", run["id"])
        assert len(calls) == count and final["decision"] == decision, (calls, final)
        assert (
            not final.get("result")
            if decision == "REVIEW_REQUIRED"
            else final["result"]
        )
    # A shared credential profile can name a different model; PDF transport AND
    # accounting must consistently retain the frozen Evolving model.
    from unittest.mock import patch

    run = repo.submit(
        "alice",
        task["id"],
        uuid.uuid4().hex,
        1,
        ready["assets"][0]["id"],
        actual,
        model.MODEL,
        manual.PROMPT_HASH,
    )
    accounts = []
    calls = []

    def routed(body, settings):
        assert settings["model"] == model.MODEL and settings["timeout_seconds"] == 180
        calls.append(body)
        value = (
            good
            if len(calls) == 1
            else {
                "reviewRequired": False,
                "hasDiff": False,
                "similarity": 100,
                "issues": [],
            }
        )
        return 200, json.dumps(
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(value)}}
                ]
            }
        )

    with patch("local_inspection_service.model_profiles.transport.invoke", routed):
        process(
            repo,
            media,
            repo.claim(),
            "test",
            resolved={
                "model": "old-profile-model",
                "provider": "doubao",
                "timeout_seconds": 30,
            },
            record_call=lambda settings, *_: accounts.append(settings["model"]),
        )
    assert (
        accounts == [model.MODEL, model.MODEL]
        and repo.get("alice", run["id"])["decision"] == "MATCH"
    )
    bad = copy.deepcopy(actual)
    bad["original"] = media.put("alice", b"corrupt")
    run = repo.submit(
        "alice",
        task["id"],
        uuid.uuid4().hex,
        1,
        ready["assets"][0]["id"],
        bad,
        model.MODEL,
        manual.PROMPT_HASH,
    )
    process(
        repo,
        media,
        repo.claim(),
        "test",
        lambda *_: (_ for _ in ()).throw(AssertionError("must not call")),
    )
    assert not [
        c for c in repo.list("alice", "call", task["id"]) if c["run_id"] == run["id"]
    ]
    assert repo.get("alice", run["id"])["status"] == "failed"
    close_connections()
    create(b"bad", status=422)
    with fitz.open(stream=data, filetype="pdf") as doc:
        encrypted = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="password"
        )
    create(encrypted, status=422)
    doc = fitz.open()
    for _ in range(251):
        doc.new_page(width=200, height=100)
    create(doc.tobytes(), status=422)
    failed = create()
    claimed = repo.claim_pdf("failure")
    assert claimed["id"] == failed["id"]
    repo.pdf_progress("alice", failed["id"], "failure", None, error="synthetic failure")
    assert check(client.get(PREFIX + "/tasks/" + failed["id"]))["revision"] == 0
    assert repo.claim_pdf("later") is None
    print(
        "PASS: PDF display rotation/split/async publication/checkpoint fencing/owner/0-1-2 calls/readability/encryption/entry limit"
    )

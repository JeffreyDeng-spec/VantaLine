"""Development-only Playwright check against Vite :5179; no customer media."""
import os
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=os.environ.get("LABEL_TEST_BROWSER") or None)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, mutations = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        def route(request):
            media = page.evaluate("window.fixtureUrl")
            if request.request.method == "POST":
                mutations.append(request.request.post_data_json)
                request.fulfill(json={"id": "result_v1"}); return
            root = "job_two" if "job_two" in request.request.url else "job_one"
            item = {"id": "item_" + root, "ordinal": 1, "status": "needs_confirmation", "size": [1000,600], "review_reason": "",
                    "media": {"normalized": media, "input": media}, "result": {"id": "result", "version": 0, "status": "needs_confirmation", "reason": "检查边缘", "box": [.2,.25,.8,.75], "media": {"crop": media}}}
            request.fulfill(json={"id": root, "status": "completed", "stage": "完成", "reason": "", "counts": {"candidate":0,"excluded":0,"needs_confirmation":1,"pending":0}, "items": [item], "diagnostics": {"raw": "<script>never execute</script>"}})
        page.route("**/api/text-inspection/document-imports/**", route)
        page.goto("http://127.0.0.1:5179/react-preview/tests/document-import.html")
        page.get_by_role("button", name="查看图片处理结果", exact=True).click()
        page.get_by_role("button", name="查看与调整", exact=True).click()
        confirm = page.get_by_role("button", name="确认裁剪并加入候选", exact=True)
        expect(confirm).to_be_disabled()
        page.get_by_role("checkbox").check(); expect(confirm).to_be_enabled()
        page.get_by_label("左边距", exact=True).fill("25"); expect(confirm).to_be_disabled()
        page.get_by_role("checkbox").check()
        preview = page.get_by_role("img", name="待确认裁剪预览", exact=True)
        # SVG viewBox alone does not clip the letterboxed area: explicit clipping
        # is essential, or outside document notes can appear in the crop preview.
        assert preview.locator("image").get_attribute("clip-path")
        assert float(preview.locator("clipPath rect").get_attribute("x")) == 250
        out = Path(tempfile.mkdtemp(prefix="document-import-browser-"))
        page.screenshot(path=str(out / "desktop.png"), full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        page.screenshot(path=str(out / "mobile.png"), full_page=True)
        confirm.click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        assert len(mutations) == 1, mutations
        assert all(abs(a-b) < 1e-12 for a,b in zip(mutations[0]["box"], [.25,.25,.85,.75])), mutations
        assert not page.locator("details").evaluate("e=>e.open")
        page.get_by_role("button",name="换订单",exact=True).click()
        expect(page.get_by_role("button",name="查看图片处理结果",exact=True)).to_be_visible()
        assert not errors, errors
        print("document import browser: PASS", out)
        browser.close()


if __name__ == "__main__":
    main()

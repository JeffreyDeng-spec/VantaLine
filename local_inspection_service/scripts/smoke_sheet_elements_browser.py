"""Real React fixture: preview/edit/confirm, responsive mapping, stale responses."""
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel=os.environ.get("LABEL_TEST_BROWSER") or None)
        page=browser.new_page(viewport={"width":1400,"height":1000})
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        state={"version":0,"status":"draft","asset":"asset_a","hold":False,"jobs":0}
        elements=[{"id":"e1","type":"parameter","expected":"20V","box":[.1,.1,.2,.1],"required":True,"ignore_reason":"","match":"exact"}]
        held=[]
        def value():
            image=page.evaluate("window.fixtureUrl")
            return {"id":"template_v"+str(state["version"]),"root_id":"template","version":state["version"],"status":state["status"],"standard_revision_id":state["asset"]+"_rev","elements":elements,"media":{"source":image}}
        def handle(route):
            url=route.request.url
            if "/templates?" in url:
                state["asset"]="asset_b" if "asset_b" in url else "asset_a"
                route.fulfill(json={"items":[value()]})
            elif url.endswith("/revise"):
                body=route.request.post_data_json;assert body["version"]==state["version"]
                elements[:]=body["elements"];state["version"]+=1;state["status"]="confirmed" if body.get("confirm") else "draft"
                route.fulfill(json=value())
            elif url.endswith("/jobs"):
                state["jobs"]+=1
                if state["hold"]:held.append(route);return
                route.fulfill(json={**value(),"id":"job_terminal","root_id":"job","status":"completed","result":{"decision":"REVIEW_REQUIRED","elements":[]}})
            else:route.fulfill(json=value())
        page.route("**/api/text-inspection/sheet/**",handle)
        page.goto("http://127.0.0.1:5178/react-preview/tests/sheet-elements.html")
        edit=page.get_by_role("button",name="编辑／确认模板",exact=True);expect(edit).to_be_enabled();edit.click()
        page.get_by_role("button",name="1. 20V · 必检",exact=True).click()
        for width,height in [(1400,1000),(390,844),(1000,650)]:
            page.set_viewport_size({"width":width,"height":height})
            box=page.locator(".sheet-editor .sheet-box").bounding_box();image=page.locator(".sheet-editor .sheet-image>img").bounding_box()
            assert abs((box["x"]-image["x"])/image["width"]-.1)*900<1
        page.get_by_role("button",name="1. 20V · 必检",exact=True).click()
        page.locator(".sheet-editor textarea").fill("20V ")
        checkbox=page.get_by_label("已核对全部文字、编码及图形，无遗漏",exact=True)
        checkbox.check()
        expect(page.get_by_role("button",name="确认模板",exact=True)).to_be_disabled()
        page.get_by_role("button",name="保存草稿",exact=True).click()
        page.get_by_role("button",name="确认模板",exact=True).click()
        expect(page.get_by_role("dialog")).to_have_count(0)
        page.get_by_role("button",name="开始整页核对",exact=True).click()
        expect(page.get_by_role("heading",name="待复核",exact=True)).to_be_visible()
        assert page.locator("details").evaluate_all("items=>items.every(el=>!el.open)")
        output=Path(tempfile.mkdtemp(prefix="sheet-browser-"))/"result.png"
        page.screenshot(path=str(output),full_page=True)
        state["hold"]=True
        page.get_by_role("button",name="更换实拍",exact=True).click()
        page.get_by_role("button",name="开始整页核对",exact=True).click()
        page.wait_for_timeout(100);assert held
        page.get_by_role("button",name="更换实拍",exact=True).click()
        held[0].fulfill(json={**value(),"id":"stale","root_id":"stale","status":"completed","result":{"decision":"MATCH","elements":[]}})
        page.wait_for_timeout(100)
        expect(page.get_by_role("heading",name="通过",exact=True)).to_have_count(0)
        page.get_by_role("button",name="更换标准",exact=True).click();expect(edit).to_be_enabled()
        assert not errors,errors
        browser.close();print("sheet browser smoke: PASS",output)


if __name__=="__main__":main()

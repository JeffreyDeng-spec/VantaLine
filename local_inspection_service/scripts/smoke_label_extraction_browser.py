#!/usr/bin/env python3
"""Run against Vite at :5177; requires development-only Python Playwright."""
import json
import os
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,channel=os.environ.get("LABEL_TEST_BROWSER") or None)
        page=browser.new_page(viewport={"width":1440,"height":1000},device_scale_factor=2)
        errors=[]; page.on("pageerror",lambda e:errors.append(str(e)))
        state={"version":0,"calls":0,"root":"ext_browser","polygon":[[.2,.25],[.8,.25],[.8,.75],[.2,.75]]}
        held=[]
        def handle(route):
            if state.get("hold") and not route.request.url.endswith("/revise"):
                held.append(route)
                return
            source=page.evaluate("window.fixtureUrl")
            if route.request.url.endswith("/revise"):
                body=route.request.post_data_json
                assert body["version"]==state["version"]
                state["version"]+=1;state["polygon"]=body["polygon"]
                status="confirmed" if body.get("confirm") else "ready"
            else:
                state["calls"]+=1;state["version"]=0;status="ready"
            route.fulfill(json={"id":state["root"]+"_v"+str(state["version"]),"root_id":state["root"],"version":state["version"],"status":status,"polygon":state["polygon"],"media":{"source":source,"crop":source,"mask":source},"diagnostics":{"provider":"fixture"}})
        page.route("**/api/text-inspection/extractions**",handle)
        page.goto("http://127.0.0.1:5177/react-preview/tests/label-extraction.html")
        guide=page.locator(".label-guide")
        guide.wait_for()
        for width,height in [(1440,1000),(700,1000),(390,844),(1100,650)]:
            page.set_viewport_size({"width":width,"height":height})
            page.wait_for_timeout(100)
            values=page.evaluate("""()=>{const stage=document.querySelector('.text-compare-stage').getBoundingClientRect(); const guide=document.querySelector('.label-guide').getBoundingClientRect(); return {stage:{x:stage.x,y:stage.y,w:stage.width,h:stage.height},guide:{x:guide.x,y:guide.y,w:guide.width,h:guide.height}};}""")
            a,b=values["stage"],values["guide"]
            scale=min(a["w"]/1000,a["h"]/600); w,h=1000*scale,600*scale
            assert abs((b["x"]-a["x"]-(a["w"]-w)/2)/scale-150)<1
            assert abs((b["y"]-a["y"]-(a["h"]-h)/2)/scale-90)<1
        page.set_viewport_size({"width":1440,"height":1000})
        page.get_by_role("button",name="提取框内标签",exact=True).click()
        page.get_by_role("button",name="确认标签并对比",exact=True).wait_for()
        assert page.get_by_role("button",name="确认标签并对比",exact=True).is_enabled()
        page.get_by_role("button",name="圆形轮廓",exact=True).click()
        assert page.get_by_role("button",name="确认标签并对比",exact=True).is_disabled()
        page.get_by_role("button",name="保存轮廓并预览",exact=True).click()
        page.get_by_role("button",name="确认标签并对比",exact=True).click()
        expect(page.get_by_test_id("comparison")).to_have_text("ext_browser_v2")
        assert state["calls"]==1,"manual edits must not call model"
        assert not page.locator("details").evaluate("el=>el.open")
        page.get_by_role("button",name="更换标准",exact=True).click()
        assert page.locator(".label-crop-preview img").count()==1
        page.get_by_role("button",name="四角轮廓",exact=True).click()
        assert page.get_by_role("button",name="确认标签并对比",exact=True).is_disabled()
        output=Path(tempfile.mkdtemp(prefix="label-extraction-browser-"))/"desktop.png"
        page.screenshot(path=str(output),full_page=True)
        page.get_by_role("button",name="换一张照片",exact=True).click()
        expect(page.locator(".label-crop-preview img")).to_have_count(0)
        state["hold"]=True
        page.get_by_role("button",name="提取框内标签",exact=True).click()
        page.wait_for_timeout(100)
        assert len(held)==1
        page.get_by_role("button",name="换一张照片",exact=True).click()
        held[0].fulfill(json={"id":"stale","root_id":"stale","version":0,"status":"ready","polygon":state["polygon"],"media":{"source":page.evaluate("window.fixtureUrl"),"crop":page.evaluate("window.fixtureUrl")}})
        page.wait_for_timeout(100)
        expect(page.locator(".label-crop-preview img")).to_have_count(0)
        assert not errors,errors
        print("single label browser smoke: PASS",output)
        browser.close()


if __name__=="__main__":main()

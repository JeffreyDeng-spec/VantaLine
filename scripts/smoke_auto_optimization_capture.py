"""Replay capture admission/classification and ordering with synthetic dependencies."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import sys
import time
import uuid
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get("VANTALINE_AUTO_CAPTURE_BASELINE_SOURCE")
NAMES={"auto_optimize_detection_candidates","record_auto_optimize_capture"}
def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==2
        ns=dict(bindings,Any=Any,Path=Path,time=time,uuid=uuid);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,"exec"),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),lambda n,v:ns.__setitem__(n,v)
    from local_inspection_service.training.auto_optimization_capture import AutoOptimizationCapture
    from local_inspection_service.training.auto_optimization_capture_ports import AutoOptimizationCapturePorts
    service=AutoOptimizationCapture(AutoOptimizationCapturePorts(**{f.name:(lambda name=f.name:bindings[name]) for f in fields(AutoOptimizationCapturePorts)}))
    bindings["auto_optimize_detection_candidates"]=service.auto_optimize_detection_candidates
    return service,lambda n,v:bindings.__setitem__(n,v)

class CaptureContract(unittest.TestCase):
    def fixture(self):
        events=[];state={"settings":{"enabled":True},"samples":[]};locked=[False]
        class Lock:
            def __enter__(self):assert not locked[0];locked[0]=True;events.append("enter")
            def __exit__(self,*args):locked[0]=False;events.append("exit")
        def load(task):self.assertTrue(locked[0]);events.append(("load",task));return state
        def save(s):self.assertTrue(locked[0]);self.assertIs(s,state);events.append("save")
        def start(task):self.assertFalse(locked[0]);events.append(("label",task))
        def shadow(task,sample):self.assertFalse(locked[0]);events.append(("shadow",task,sample))
        def owner():self.assertFalse(locked[0]);events.append("owner");return {"owner_user_id":"alice","owner_username":"a"}
        bindings={"_auto_optimize_lock":Lock(),"load_auto_optimize_state":load,"save_auto_optimize_state":save,
          "sanitize_ai_detection_task_id":lambda x:str(x).strip(),"auto_optimize_completed_model_id":lambda s:"",
          "auto_optimize_stop_capture_for_model_locked":lambda *a,**k:None,"auto_optimize_capture_enabled":lambda s:s["settings"]["enabled"],
          "resolve_service_path":lambda p:p,"bounded_text":lambda value,limit:str(value)[:limit],"current_owner_fields":owner,
          "start_auto_optimize_label_worker":start,"start_auto_optimize_shadow_worker":shadow}
        service,replace=create(bindings)
        result={"model":{"is_ai_detection":True,"task_id":"task","label":"Task","selected_accessory_ids":["a"],"required_accessory_counts":{"a":1}},"passed":True,"detections":[{"present":True,"accessory_id":"a","confidence":.9}]}
        record={"record_id":"record","source_image":{"path":"synthetic/image.png","url":"fixture-url"}}
        return SimpleNamespace(service=service,replace=replace,state=state,events=events,locked=locked,result=result,record=record)

    def call(self,f):
        with patch.object(time,"time",return_value=101.9),patch.object(uuid,"uuid4",return_value=SimpleNamespace(hex="12345678abcdef")):
            return f.service.record_auto_optimize_capture(f.record,f.result,"request",None)

    def test_candidate_filter_and_legacy_count_semantics(self):
        f=self.fixture();base={"present":True,"accessory_id":"a","confidence":.5}
        rows=[None,{}, {**base,"present":1},{**base,"confidence":"bad"},{**base,"confidence":0},{**base,"count":2},{**base,"count":0},base,{**base,"count":True},{**base,"count":1.2},{**base,"confidence":4,"evidence":"x"*200},{**base,"accessory_id":""}]
        result=f.service.auto_optimize_detection_candidates({"detections":rows});self.assertEqual(len(result),4);self.assertEqual([x["confidence"] for x in result],[.5,.5,.5,1]);self.assertEqual(len(result[-1]["evidence"]),180);self.assertEqual(f.events,[])
        self.assertEqual(f.service.auto_optimize_detection_candidates({"detections":{}}),[])

    def test_admission_early_returns(self):
        for mode in ("record","model","task","disabled","path"):
            f=self.fixture()
            if mode=="record":f.record=None
            if mode=="model":f.result["model"]={}
            if mode=="task":f.result["model"]["task_id"]=""
            if mode=="disabled":f.state["settings"]["enabled"]=False
            if mode=="path":f.record["source_image"]={}
            self.assertIsNone(self.call(f));self.assertEqual(f.state["samples"],[]);self.assertNotIn("save",f.events)
            self.assertEqual(f.events,[] if mode in ("record","model","task") else ["enter",("load","task"),"exit"])

    def test_positive_order_and_evidence_identity(self):
        f=self.fixture();self.call(f);sample=f.state["samples"][0]
        self.assertEqual(f.events,["enter",("load","task"),"exit","owner","enter",("load","task"),"save","exit",("label","task"),("shadow","task","autoopt_101_12345678")])
        self.assertEqual((sample["label_status"],sample["sample_type"],sample["shadow_status"]),("pending","positive_candidate","pending"));self.assertEqual(sample["source_image"],{"path":"synthetic/image.png","url":"fixture-url","filename":"image.png"})
        self.assertIs(sample["ai_result"]["model"],f.result["model"]);self.assertIs(sample["ai_result"]["detections"],f.result["detections"]);self.assertIs(f.state["selected_accessory_ids"],f.result["model"]["selected_accessory_ids"])
        self.assertEqual(f.state["owner_user_id"],"alice");self.assertEqual(sample["request_id"],"request")

    def test_failure_classification_and_no_worker(self):
        cases=[({"ai":{"error":"e"}},"provider_failure","ai_detection_provider_failed"),({"ai":{"provider_status":"TIMEOUT"}},"provider_failure","ai_detection_provider_failed"),({"ai":{"overloaded":True}},"provider_failure","ai_detection_provider_failed"),({"ai":{"timed_out":True}},"provider_failure","ai_detection_provider_failed"),({"passed":False},"failed_detection","ai_detection_not_passed"),({"detections":[]},"failed_detection","ai_detection_no_positive_candidates")]
        for changes,kind,reason in cases:
            f=self.fixture();f.result.update(changes);self.call(f);sample=f.state["samples"][0];self.assertEqual((sample["label_status"],sample["sample_type"],sample["label_reject_reason"]),("failed",kind,reason));self.assertFalse(any(isinstance(e,tuple) and e[0] in ("label","shadow") for e in f.events))

    def test_completed_model_is_saved_before_eligibility(self):
        f=self.fixture();f.replace("auto_optimize_completed_model_id",lambda s:"model")
        def stop(s,m,*,reason):self.assertTrue(f.locked[0]);self.assertEqual((m,reason),("model","completed_model_ready"));s["settings"]["enabled"]=False;f.events.append("stop")
        f.replace("auto_optimize_stop_capture_for_model_locked",stop);self.call(f);self.assertEqual(f.events,["enter",("load","task"),"stop","save","exit"]);self.assertEqual(f.state["samples"],[])

    def test_second_load_retains_original_no_recheck_behavior(self):
        f=self.fixture();other={"settings":{"enabled":False},"samples":[]};calls=[0]
        def load(task):calls[0]+=1;return f.state if calls[0]==1 else other
        f.replace("load_auto_optimize_state",load);f.replace("save_auto_optimize_state",lambda s:self.assertIs(s,other));self.call(f)
        self.assertEqual(f.state["samples"],[]);self.assertEqual(len(other["samples"]),1);self.assertFalse(other["settings"]["enabled"])

    def test_sample_limit_and_source_fallback(self):
        f=self.fixture();old=[{"sample_id":str(i)} for i in range(10001)];f.state["samples"]=old;self.call(f)
        self.assertEqual(len(f.state["samples"]),10000);self.assertIs(f.state["samples"][1],old[1]);self.assertEqual(f.state["samples"][-1]["sample_id"],"9998")
        f=self.fixture();f.record["source_image"]={};f.record["image_url"]="fallback"
        with patch.object(time,"time",return_value=1):f.service.record_auto_optimize_capture(f.record,f.result,"r",Path("new.png"))
        self.assertEqual(f.state["samples"][0]["source_image"],{"path":"new.png","url":"fallback","filename":"new.png"})

    def test_save_and_start_failures_do_not_retry(self):
        for stage in ("save","label","shadow"):
            f=self.fixture();error=RuntimeError(stage);calls=[]
            def fail(*a):calls.append(stage);raise error
            f.replace({"save":"save_auto_optimize_state","label":"start_auto_optimize_label_worker","shadow":"start_auto_optimize_shadow_worker"}[stage],fail)
            with self.assertRaises(RuntimeError) as raised:self.call(f)
            self.assertIs(raised.exception,error);self.assertEqual(calls,[stage]);self.assertFalse(f.locked[0]);self.assertEqual(len(f.state["samples"]),1)
            if stage in ("save","label"):self.assertFalse(any(isinstance(e,tuple) and e[0]=="shadow" for e in f.events))

    def test_callee_selection_before_argument_rebind(self):
        f=self.fixture();events=[]
        f.replace("bounded_text",lambda value,limit:events.append("old") or value)
        class Detection(dict):
            def get(self,key,*args):
                if key=="evidence":f.replace("bounded_text",lambda value,limit:events.append("new") or value)
                return super().get(key,*args)
        f.service.auto_optimize_detection_candidates({"detections":[Detection(present=True,accessory_id="a",confidence=.5,evidence="e")]});self.assertEqual(events,["old"])

    @unittest.skipIf(BASELINE,"candidate-only root composition")
    def test_actual_root_identity_and_forwarding(self):
        import asyncio
        import threading
        from unittest.mock import Mock
        from starlette.concurrency import run_in_threadpool
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_capture
        for field in fields(service.ports):self.assertIs(getattr(service.ports,field.name)(),getattr(server,field.name))
        for name,args in [("auto_optimize_detection_candidates",({},)),("record_auto_optimize_capture",({}, {}, "r", None))]:
            expected=object();method=Mock(return_value=expected)
            with patch.object(server,"_auto_optimization_capture",SimpleNamespace(**{name:method})):
                self.assertIs(getattr(server,name)(*args),expected);method.assert_called_once_with(*args)
        states={u:{"settings":{"enabled":True},"samples":[]} for u in ("alpha","beta")};barrier=threading.Barrier(2,timeout=10);saved=[];started=[]
        def user():return server._request_user.get()["id"]
        def owner():who=user();barrier.wait();return {"owner_user_id":who,"owner_username":who}
        def save(state):self.assertIs(state,states[user()]);saved.append(user())
        def load(task):self.assertEqual(task,user());return states[user()]
        async def request(who):
            result={"model":{"is_ai_detection":True,"task_id":who},"passed":True,"detections":[{"accessory_id":"a","present":True,"confidence":1}]}
            with server._request_user.bind({"id":who}):await run_in_threadpool(server.record_auto_optimize_capture,{"record_id":who,"source_image":{"path":"synthetic.png"}},result,who,None)
        async def both():await asyncio.gather(request("alpha"),request("beta"))
        with patch.object(server,"load_auto_optimize_state",side_effect=load),patch.object(server,"save_auto_optimize_state",side_effect=save),patch.object(server,"auto_optimize_completed_model_id",return_value=""),patch.object(server,"auto_optimize_capture_enabled",return_value=True),patch.object(server,"current_owner_fields",side_effect=owner),patch.object(server,"start_auto_optimize_label_worker",side_effect=lambda task:started.append(("label",user(),task))),patch.object(server,"start_auto_optimize_shadow_worker",side_effect=lambda task,sample:started.append(("shadow",user(),task))):asyncio.run(both())
        self.assertCountEqual(saved,["alpha","beta"])
        for who in states:self.assertEqual(states[who]["samples"][0]["owner_user_id"],who)
        self.assertTrue(all(who==task for _,who,task in started));self.assertEqual(len(started),4);self.assertIsNone(server._request_user.get())

    @unittest.skipIf(BASELINE,"candidate-only import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable,"-c","import sys; import local_inspection_service.training.auto_optimization_capture; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=="__main__":unittest.main()

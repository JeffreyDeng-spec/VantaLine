"""Original/candidate readiness and capture policy with synthetic lookup ports."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get("VANTALINE_AUTO_READINESS_BASELINE_SOURCE")
NAMES={"auto_optimize_phase_name","auto_optimize_completed_model_id","auto_optimize_linked_pipeline_model_id","auto_optimize_stop_capture_for_model_locked","auto_optimize_capture_enabled"}

def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
        assert len(nodes)==5
        namespace=dict(bindings,Any=Any,time=time)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,"exec"),namespace)
        return SimpleNamespace(**{n:namespace[n] for n in NAMES}),lambda n,v:namespace.__setitem__(n,v)
    from local_inspection_service.training.auto_optimization_readiness import AutoOptimizationReadiness
    from local_inspection_service.training.auto_optimization_readiness_ports import AutoOptimizationReadinessPorts
    ports=AutoOptimizationReadinessPorts(**{f.name:(lambda name=f.name:bindings[name]) for f in fields(AutoOptimizationReadinessPorts)})
    service=AutoOptimizationReadiness(ports)
    for n in NAMES:bindings[n]=getattr(service,n)
    return service,lambda n,v:bindings.__setitem__(n,v)

class ReadinessContract(unittest.TestCase):
    def fixture(self):
        events=[];tasks=[];training={};config={"marker":"config"}
        def canonical(c,ids):
            self.assertIs(c,config);events.append(("ids",tuple(ids)));return [x for x in ids if x!="missing"]
        def counts(c,ids,value):
            self.assertIs(c,config);events.append(("counts",tuple(ids)));return value or {x:1 for x in ids}
        def training_task(key):events.append(("training",key));return training.get(key)
        def load():events.append("config");return config
        def pipeline():events.append("pipeline");return tasks
        bindings={"load_config":load,"canonical_pipeline_accessory_ids":canonical,"normalize_pipeline_accessory_counts":counts,
            "load_pipeline_tasks":pipeline,"normalize_pipeline_detection_method":lambda v:v,
            "pipeline_task_model_status":lambda t:t.get("model_status","available"),"pipeline_task_model_id":lambda t:t.get("model_id", ""),
            "find_training_task":training_task,"default_auto_optimize_settings":lambda:{"enabled":False,"auto_promote":True,"serving_mode":"api_primary"}}
        service,replace=create(bindings)
        return SimpleNamespace(service=service,replace=replace,events=events,tasks=tasks,training=training)

    def test_phase_priority_and_malformed_collections(self):
        f=self.fixture();fn=f.service.auto_optimize_phase_name
        self.assertEqual(fn({"active_model_id":"m","settings":{"serving_mode":"promoted_yolo","enabled":False}}),"promoted")
        for state,expected in [({},"paused"),({"settings":[],"candidate_models":[1]},"paused"),({"settings":{"enabled":True},"candidate_models":[1],"datasets":[1]},"shadow_compare"),({"settings":{"enabled":True},"datasets":[1]},"training_candidate"),({"settings":{"enabled":True},"samples":[None,1,{"label_status":"trainable_bbox_only"}]},"weak_labeling"),({"settings":{"enabled":True},"samples":{}},"capture")]:self.assertEqual(fn(state),expected)
        self.assertEqual(f.events,[])

    def test_completed_model_priority_and_live_training_status(self):
        f=self.fixture();fn=f.service.auto_optimize_completed_model_id
        self.assertEqual(fn({"active_model_id":" live ","settings":{"serving_mode":"promoted_yolo"}}),"live");self.assertEqual(f.events,[])
        f.training["j"]={"status":"running"};state={"candidate_models":[None,{"model_id":""},{"model_id":"first","job_id":"j","status":"completed"},{"model_id":"second","status":"completed"}]}
        self.assertEqual(fn(state),"second");self.assertEqual(f.events,[("training","j"),("training","")])
        f.training["j"]["status"]="completed";self.assertEqual(fn(state),"first")

    def test_empty_selection_does_not_load_pipeline(self):
        f=self.fixture();self.assertEqual(f.service.auto_optimize_linked_pipeline_model_id({"selected_accessory_ids":["missing"]}),"");self.assertEqual(f.events,["config",("ids",("missing",))])

    def test_pipeline_filters_counts_owner_and_stable_ties(self):
        f=self.fixture();base={"stage":"library","status":"completed","detection_method":"yolo","accessory_ids":["b","a"],"accessory_counts":{"a":2,"b":1},"owner_user_id":"alice","model_id":"first","updated_at":20}
        f.tasks[:]=[None,{**base,"owner_user_id":"bob","updated_at":99},{**base,"stage":"training"},{**base,"status":"running"},{**base,"detection_method":"api"},{**base,"accessory_ids":["a"]},{**base,"accessory_counts":{"a":1,"b":1}},{**base,"model_status":"missing"},{**base,"model_id":""},base,{**base,"model_id":"tie"},{**base,"model_id":"older","updated_at":10}]
        state={"owner_user_id":"alice","selected_accessory_ids":["a","b"],"required_accessory_counts":{"a":2,"b":1}}
        self.assertEqual(f.service.auto_optimize_linked_pipeline_model_id(state),"first")
        f.tasks.append({**base,"owner_user_id":"","status":"已上线","detection_method":"yolo_ocr","updated_at":21,"model_id":"legacy-owner"})
        self.assertEqual(f.service.auto_optimize_linked_pipeline_model_id(state),"legacy-owner")
        f.tasks.append({**base,"owner_user_id":"bob","updated_at":22,"model_id":"other"});state["owner_user_id"]=""
        self.assertEqual(f.service.auto_optimize_linked_pipeline_model_id(state),"first")  # Blank owner retains the original cross-owner newest match.

    def test_fallback_and_capture_short_circuit(self):
        f=self.fixture();self.assertFalse(f.service.auto_optimize_capture_enabled({}));self.assertEqual(f.events,[])
        calls=[];f.replace("auto_optimize_completed_model_id",lambda s:calls.append(s) or "model")
        state={"settings":{"enabled":True}};self.assertFalse(f.service.auto_optimize_capture_enabled(state));self.assertIs(calls[0],state)
        f.replace("auto_optimize_linked_pipeline_model_id",lambda s:"linked");self.assertEqual(f.service.auto_optimize_completed_model_id({}),"linked")

    def test_stop_capture_preserves_metadata_and_two_clock_reads(self):
        f=self.fixture();state={"settings":{"enabled":True,"extra":1},"last_promotion":{"agreement":.7,"sample_count":4},"model_profiles":{"old":1}}
        original=state["settings"];snapshot=state["model_profiles"]
        with patch.object(time,"time",side_effect=[101.9,102.9]) as clock:self.assertTrue(f.service.auto_optimize_stop_capture_for_model_locked(state,"m",reason="ready"))
        self.assertEqual(clock.call_count,2);self.assertIsNot(state["settings"],original);self.assertTrue(original["enabled"]);self.assertIs(state["model_profiles"],snapshot)
        self.assertEqual(state["last_promotion"],{"model_id":"m","agreement":.7,"sample_count":4,"promoted_at":101,"source":"ready"});self.assertEqual(state["capture_stopped_at"],102)
        self.assertEqual(state["settings"],{"enabled":False,"extra":1,"auto_promote":True,"serving_mode":"promoted_yolo"})

    def test_stop_noop_and_no_auto_promote(self):
        f=self.fixture();state={"settings":{"enabled":False,"auto_promote":False}};original=state["settings"]
        with patch.object(time,"time",side_effect=AssertionError("unexpected clock")):
            self.assertFalse(f.service.auto_optimize_stop_capture_for_model_locked(state,"",reason="r"));self.assertFalse(f.service.auto_optimize_stop_capture_for_model_locked(state,"m",reason="r"))
        self.assertIs(state["settings"],original);self.assertNotIn("active_model_id",state)
        state["settings"]["enabled"]=True
        with patch.object(time,"time",return_value=1):self.assertTrue(f.service.auto_optimize_stop_capture_for_model_locked(state,"m",reason="r"))
        self.assertNotIn("active_model_id",state);self.assertNotIn("last_promotion",state)

    def test_exception_identity_and_partial_mutation(self):
        f=self.fixture();error=RuntimeError("fixture")
        def fail(*a):raise error
        f.replace("load_config",fail)
        with self.assertRaises(RuntimeError) as raised:f.service.auto_optimize_linked_pipeline_model_id({})
        self.assertIs(raised.exception,error)
        state={"settings":{"enabled":True}};original=state["settings"]
        with patch.object(time,"time",side_effect=[10,error]):
            with self.assertRaises(RuntimeError) as raised:f.service.auto_optimize_stop_capture_for_model_locked(state,"m",reason="r")
        self.assertIs(raised.exception,error);self.assertEqual(state["active_model_id"],"m");self.assertEqual(state["last_promotion"]["promoted_at"],10);self.assertIs(state["settings"],original);self.assertTrue(original["enabled"]);self.assertNotIn("capture_stopped_at",state)

    def test_callee_selection_before_argument_side_effect(self):
        f=self.fixture();events=[]
        f.replace("find_training_task",lambda key:events.append(("old",key)) or {"status":"completed"})
        class Key:
            def __str__(self):f.replace("find_training_task",lambda key:events.append(("new",key)) or None);return "j"
        state={"candidate_models":[{"model_id":"m","job_id":Key()}]}
        self.assertEqual(f.service.auto_optimize_completed_model_id(state),"m");self.assertEqual(events,[("old","j")])

    @unittest.skipIf(BASELINE,"candidate-only composition")
    def test_actual_root_ports_forwarders_and_request_identity(self):
        import asyncio
        import threading
        from unittest.mock import Mock
        from starlette.concurrency import run_in_threadpool
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_readiness
        for field in fields(service.ports):self.assertIs(getattr(service.ports,field.name)(),getattr(server,field.name))
        for name in NAMES:
            expected=object();method=Mock(return_value=expected);args=({},"m") if name=="auto_optimize_stop_capture_for_model_locked" else ({},);kw={"reason":"r"} if len(args)==2 else {}
            with patch.object(server,"_auto_optimization_readiness",SimpleNamespace(**{name:method})):
                self.assertIs(getattr(server,name)(*args,**kw),expected);method.assert_called_once_with(*args,**kw)
        barrier=threading.Barrier(2,timeout=10)
        def find(job):
            user=server._request_user.get()["id"];barrier.wait();self.assertEqual(job,user);return {"status":"completed"}
        async def request(user):
            with server._request_user.bind({"id":user}):return await run_in_threadpool(server.auto_optimize_completed_model_id,{"candidate_models":[{"model_id":user,"job_id":user}]})
        async def both():return await asyncio.gather(request("alpha"),request("beta"))
        with patch.object(server,"find_training_task",side_effect=find):self.assertEqual(asyncio.run(both()),["alpha","beta"])
        self.assertIsNone(server._request_user.get())

    @unittest.skipIf(BASELINE,"candidate-only import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable,"-c","import sys; import local_inspection_service.training.auto_optimization_readiness; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=="__main__":unittest.main()

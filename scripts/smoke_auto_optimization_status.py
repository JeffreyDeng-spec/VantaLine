"""Original/candidate status projection and settings mutation contracts."""
import ast
from collections import Counter
from dataclasses import fields, replace
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from auto_optimization_test_ports import test_capability, assert_capability_owner
BASELINE=os.environ.get("VANTALINE_AUTO_STATUS_BASELINE_SOURCE")
NAMES={"public_auto_optimize_state","auto_optimize_update_settings"}
def create(bindings):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding="utf-8-sig")).body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==2
        ns=dict(bindings,Any=Any,Counter=Counter);exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,"exec"),ns)
        return SimpleNamespace(**{n:ns[n] for n in NAMES}),lambda n,v:ns.__setitem__(n,v)
    from local_inspection_service.training.auto_optimization_status import AutoOptimizationStatus
    from local_inspection_service.training.auto_optimization_status_ports import AutoOptimizationStatusState,AutoOptimizationStatusPolicy
    def ports(kind):return kind(**{f.name:test_capability(bindings, f.name) for f in fields(kind)})
    service=AutoOptimizationStatus(ports(AutoOptimizationStatusState),ports(AutoOptimizationStatusPolicy))
    bindings["public_auto_optimize_state"]=service.public_auto_optimize_state
    return service,lambda n,v:bindings.__setitem__(n,v)

class StatusContract(unittest.TestCase):
    def fixture(self):
        events=[];locked=[False];state={"task_id":"stored","settings":{"enabled":False,"serving_mode":"api_primary"},"samples":[],"candidate_models":[],"datasets":[],"shadow_runs":[]};user={"id":"alice"};requirements={"fixture":1};parameters={"epochs":7};sprites=[{"sprite":"a"}]
        class Lock:
            def __enter__(self):assert not locked[0];locked[0]=True;events.append("enter")
            def __exit__(self,*a):locked[0]=False;events.append("exit")
        def load(task):self.assertTrue(locked[0]);events.append(("load",task));return state
        def save(s):self.assertTrue(locked[0]);self.assertIs(s,state);events.append("save")
        def hydrate(s):self.assertTrue(locked[0]);events.append("hydrate");return False
        def defaults():events.append("defaults");return {"enabled":False,"serving_mode":"api_primary","default":1}
        def required(opts,*,real_positive_source_count):events.append(("requirements",real_positive_source_count));return requirements
        def sanitize(value):return {k:v for k,v in value.items() if k!="path"}
        def start(task):self.assertFalse(locked[0]);events.append(("start",task))
        b={"_auto_optimize_lock":Lock(),"load_auto_optimize_state":load,"save_auto_optimize_state":save,"hydrate_auto_optimize_background_from_ai_task":hydrate,
          "auto_optimize_completed_model_id":lambda s:"","auto_optimize_stop_capture_for_model_locked":lambda *a,**k:False,"find_training_task":lambda job:None,
          "record_visible_to_user":lambda sample,user:sample.get("owner_user_id")==user["id"],"current_auth_user":lambda:user,"start_auto_optimize_label_worker":start,
          "default_auto_optimize_settings":defaults,"auto_optimize_public_sprite_pool":lambda s:sprites,"background_set_payload":lambda key:{"id":key,"path":"private"},
          "auto_optimize_samples_per_real_image":lambda opts:5,"auto_optimize_training_parameters":lambda opts:parameters,"auto_optimize_training_requirements":required,
          "auto_optimize_negative_samples_per_real_image":lambda opts:2,"auto_optimize_positive_derivatives_per_real_image":lambda opts:3,"AUTO_OPTIMIZE_REAL_BBOX_SAMPLE_WEIGHT":4,
          "public_path_sanitized":sanitize,"auto_optimize_phase_name":lambda s:"fixture-phase","normalize_expected_production_count":lambda x:int(x or 0),
          "public_auto_optimize_initialization_payload":lambda s,opts:{"fixture":"initialization"}}
        service,replace=create(b)
        return SimpleNamespace(service=service,replace=replace,state=state,events=events,locked=locked,user=user,requirements=requirements,parameters=parameters,sprites=sprites)

    def test_empty_projection_defaults_and_identity(self):
        f=self.fixture();result=f.service.public_auto_optimize_state("requested")
        self.assertEqual(result["task_id"],"stored");self.assertEqual(result["samples_total"],0);self.assertEqual(result["shadow_agreement"],0);self.assertEqual(result["latest_sample_at"],0);self.assertEqual(result["latest_dataset"],{});self.assertEqual(result["candidate_model_count"],0)
        self.assertIs(result["settings"],f.state["settings"]);self.assertIs(result["training_requirements"],f.requirements);self.assertIs(result["training_parameters"],f.parameters);self.assertIs(result["sprite_pool"],f.sprites)
        self.assertEqual(f.events,["enter",("load","requested"),"hydrate","exit",("requirements",0)])
        f.state["settings"]=[];f.service.public_auto_optimize_state("requested");self.assertIn("defaults",f.events)

    def test_sample_visibility_counts_and_limit(self):
        f=self.fixture();statuses=["trainable","trainable_bbox_only","negative","pending","review_required","rejected","failed"]
        f.state["samples"]=[{"owner_user_id":"alice","label_status":x,"created_at":i,"synthetic_count":1,"path":"private"} for i,x in enumerate(statuses)] + [{"owner_user_id":"alice","created_at":i} for i in range(10,100)] + [{"owner_user_id":"bob","label_status":"trainable","created_at":999}]
        result=f.service.public_auto_optimize_state("t",user=f.user)
        self.assertEqual(result["samples_total"],97);self.assertEqual(len(result["samples"]),80);self.assertEqual(result["latest_sample_at"],99);self.assertEqual(result["rejected_samples"],2);self.assertEqual(result["usable_training_samples"],3)
        self.assertEqual(result["projected_real_bbox_training_samples"],8);self.assertEqual(result["projected_positive_training_samples"],11);self.assertEqual(result["generated_negative_sample_count"],4);self.assertEqual(result["projected_training_samples"],16);self.assertEqual(result["synthetic_sample_count"],7);self.assertNotIn("path",result["samples"][0]);self.assertIn(("requirements",2),f.events)
        self.assertEqual(f.service.public_auto_optimize_state("t",user={})["samples_total"],98)

    def test_dataset_candidate_and_shadow_legacy_order(self):
        f=self.fixture();first={"job_id":"j","status":"old","progress":8,"note":"keep","path":"private"};f.state.update(datasets=[None,{"id":"first","synthetic_sample_count":10,"path":"private"},{"id":"last","synthetic_sample_count":20}],candidate_models=[None,first,{"job_id":"k"}],shadow_runs=[None,{"status":"completed","agreement":.3},{"status":"completed","agreement":.8},{"status":"failed","agreement":1}],background_set_id="bg",environment_background={"name":"room","path":"private"})
        def training(job):self.assertFalse(f.locked[0]);return {"status":"completed","progress":0,"note":""} if job=="j" else None
        f.replace("find_training_task",training);result=f.service.public_auto_optimize_state("t")
        self.assertEqual(result["latest_dataset"]["id"],"first");self.assertEqual(result["synthetic_sample_count"],30);self.assertEqual(result["shadow_runs"],3);self.assertEqual(result["shadow_agreement"],.55);self.assertEqual(result["candidate_model_count"],3)
        self.assertEqual(first["status"],"completed");self.assertEqual(first["progress"],8);self.assertEqual(first["note"],"keep");self.assertNotIn("path",result["latest_candidate_model"]);self.assertEqual(result["background_set"],{"id":"bg"})

    def test_hydration_and_completion_save_inside_lock(self):
        for hydrate,stop,expected in [(False,False,False),(True,False,True),(False,True,True),(True,True,True)]:
            f=self.fixture();f.replace("hydrate_auto_optimize_background_from_ai_task",lambda s:hydrate);f.replace("auto_optimize_completed_model_id",lambda s:"m")
            def stopping(s,m,*,reason):self.assertTrue(f.locked[0]);self.assertEqual((m,reason),("m","completed_model_ready"));return stop
            f.replace("auto_optimize_stop_capture_for_model_locked",stopping);f.service.public_auto_optimize_state("t");self.assertEqual(f.events.count("save"),int(expected))

    def test_update_bounds_request_protocol_and_start_before_public(self):
        f=self.fixture();f.state["settings"]["serving_mode"]="disabled";payload={"enabled":True,"auto_promote":False,"training_epochs":999,"training_image_size":1,"min_negative_samples":-2,"negative_samples_per_real_image":50,"mask_compare_min_score":2,"shadow_min_agreement":-1,"min_positive_samples":0,"unknown":1}
        class Request:
            def dict(self,*,exclude_unset):self_outer.assertTrue(exclude_unset);return payload
        self_outer=self;calls=[];expected=object()
        def public(task,*,user):self.assertFalse(f.locked[0]);self.assertIs(user,f.user);calls.append(task);return expected
        f.replace("public_auto_optimize_state",public);result=f.service.auto_optimize_update_settings("requested",Request());self.assertIs(result,expected)
        self.assertEqual(f.state["settings"],{"enabled":True,"serving_mode":"api_primary","default":1,"auto_promote":False,"training_epochs":500,"training_image_size":320,"min_negative_samples":0,"negative_samples_per_real_image":20,"mask_compare_min_score":1,"shadow_min_agreement":0,"min_positive_samples":1})
        self.assertEqual(f.events,["enter",("load","requested"),"defaults","save","exit",("start","stored")]);self.assertEqual(calls,["stored"])

    def test_completed_model_disables_newly_enabled_settings(self):
        f=self.fixture();f.replace("auto_optimize_completed_model_id",lambda s:"m")
        def stop(s,m,*,reason):s["settings"]["enabled"]=False;return True
        f.replace("auto_optimize_stop_capture_for_model_locked",stop);f.replace("public_auto_optimize_state",lambda *a,**k:{})
        f.service.auto_optimize_update_settings("t",{"enabled":True});self.assertFalse(f.state["settings"]["enabled"]);self.assertFalse(any(isinstance(e,tuple) and e[0]=="start" for e in f.events))

    def test_update_exception_boundaries_and_partial_state(self):
        for stage in ("parse","save","start","public"):
            f=self.fixture();error=RuntimeError(stage);original=f.state["settings"];calls=[]
            def fail(*a,**k):calls.append(stage);raise error
            payload={"enabled":True}
            if stage=="parse":
                class Bad:
                    def __int__(self):raise error
                payload["training_epochs"]=Bad()
            else:f.replace({"save":"save_auto_optimize_state","start":"start_auto_optimize_label_worker","public":"public_auto_optimize_state"}[stage],fail)
            with self.assertRaises(RuntimeError) as raised:f.service.auto_optimize_update_settings("t",payload)
            self.assertIs(raised.exception,error);self.assertFalse(f.locked[0])
            if stage=="parse":self.assertIs(f.state["settings"],original);self.assertNotIn("save",f.events)
            else:self.assertTrue(f.state["settings"]["enabled"]);self.assertEqual(calls,[stage])

    def test_public_callee_selected_before_current_user(self):
        f=self.fixture();events=[];f.replace("public_auto_optimize_state",lambda *a,**k:events.append("old") or {})
        def user():f.replace("public_auto_optimize_state",lambda *a,**k:events.append("new") or {});return f.user
        f.replace("current_auth_user",user);f.service.auto_optimize_update_settings("t",{});self.assertEqual(events,["old"])

    @unittest.skipIf(BASELINE,"candidate-only root composition")
    def test_actual_root_getters_forwarders_and_account_context(self):
        import asyncio
        import threading
        from unittest.mock import Mock,patch
        from starlette.concurrency import run_in_threadpool
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_status
        for port in (service.state,service.policy):
            for field in fields(port):assert_capability_owner(self, port, field.name, server)
        for name,args,kw in [("public_auto_optimize_state",("t",),{"user":{"id":"a"}}),("auto_optimize_update_settings",("t",{}),{})]:
            expected=object();method=Mock(return_value=expected)
            with patch.object(server,"_auto_optimization_status",SimpleNamespace(**{name:method})):
                self.assertIs(getattr(server,name)(*args,**kw),expected);method.assert_called_once_with(*args,**kw)
        states={u:{"task_id":u,"settings":{}} for u in ("alpha","beta")};barrier=threading.Barrier(2,timeout=10);saved=[]
        def who():return server._request_user.get()["id"]
        def load(task):self.assertEqual(task,who());return states[who()]
        def save(state):self.assertIs(state,states[who()]);saved.append(who())
        def public(task,*,user):barrier.wait();self.assertEqual((task,user["id"]),(who(),who()));return {"owner":who()}
        async def request(user):
            with server._request_user.bind({"id":user}):return await run_in_threadpool(server.auto_optimize_update_settings,user,{})
        async def both():return await asyncio.gather(request("alpha"),request("beta"))
        with patch.object(server,"load_auto_optimize_state",side_effect=load),patch.object(server,"save_auto_optimize_state",side_effect=save),patch.object(server,"_auto_optimization_status",replace(server._auto_optimization_status, policy=replace(server._auto_optimization_status.policy, default_auto_optimize_settings=lambda:{"enabled":False}))),patch.object(server,"auto_optimize_completed_model_id",return_value=""),patch.object(server,"current_auth_user",side_effect=lambda:server._request_user.get()),patch.object(server,"public_auto_optimize_state",side_effect=public):results=asyncio.run(both())
        self.assertEqual(results,[{"owner":"alpha"},{"owner":"beta"}]);self.assertCountEqual(saved,["alpha","beta"]);self.assertIsNone(server._request_user.get())

    @unittest.skipIf(BASELINE,"candidate-only import")
    def test_lightweight_import(self):
        import subprocess
        subprocess.run([sys.executable,"-c","import sys; import local_inspection_service.training.auto_optimization_status; assert not any(n in sys.modules for n in ('local_inspection_service.server','fastapi','psycopg'))"],cwd=ROOT,check=True)

if __name__=="__main__":unittest.main()

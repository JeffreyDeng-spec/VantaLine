"""Retained PLC worker ownership with captured fake targets; never serial I/O."""
import ast,os,sys,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from local_inspection_service.plc import legacy_workers as workers
BASELINE=os.environ.get('VANTALINE_PLC_LEGACY_WORKERS_BASELINE_SOURCE')
SPECS=(('plc_start_owner_heartbeat','owner_heartbeat','plc-io-owner-heartbeat'),('start_plc_dispatch_reconciler','dispatch_reconciler','plc-dispatch-reconciler'),('start_plc_capture_poller','capture_poller','plc-capture-input-poller'))


class StopLoop(BaseException):pass


def create(b):
    if BASELINE:
        nodes=[n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name in {v[0] for v in SPECS}];assert len(nodes)==3
        ns=dict(b)
        for _,part,_ in SPECS:ns['_plc_'+part+'_lock']=threading.Lock();ns['_plc_'+part+'_thread']=None
        exec(compile(ast.Module(body=nodes,type_ignores=[]),BASELINE,'exec'),ns)
        return SimpleNamespace(**{v[0]:ns[v[0]] for v in SPECS}),ns,lambda name:ns[name],lambda name,value:ns.__setitem__(name,value)
    h=workers.LegacyHeartbeatCapabilities(repository=lambda:b['runtime_postgres_repository_or_none'],config=lambda:b['load_config'],namespace=lambda:b['raw_plc_namespace'],renew=lambda:b['plc_claim_or_renew_io_owner'],seconds=lambda:b['PLC_IO_OWNER_HEARTBEAT_SECONDS'])
    loops=workers.LegacyLoopCapabilities(reconcile=lambda:b['plc_reconcile_pending_dispatches_once'],poll=lambda:b['plc_capture_poll_once'],seconds=lambda:b['PLC_CAPTURE_POLL_SECONDS'])
    owner=workers.LegacyPlcWorkers(h,loops)
    return owner,b,lambda name:getattr(owner,name),lambda name,value:setattr(owner,name,value)


class Contracts(unittest.TestCase):
    def setUp(self):
        self.created=[];self.trace=[]
        self.b={'PLC_IO_OWNER_HEARTBEAT_SECONDS':3,'PLC_CAPTURE_POLL_SECONDS':.1,'runtime_postgres_repository_or_none':lambda:self.trace.append('repo') or object(),'load_config':lambda:self.trace.append('config') or {'plc':{'enabled':True}},'raw_plc_namespace':lambda c:self.trace.append('namespace') or c['plc'],'plc_claim_or_renew_io_owner':lambda:self.trace.append('renew') or None,'plc_reconcile_pending_dispatches_once':lambda:self.trace.append('reconcile'),'plc_capture_poll_once':lambda:self.trace.append('poll'),'_thread_error':None,'_start_error':None,'_sleep':lambda n:self.trace.append(('sleep',n))}
        def factory(**kwargs):
            if self.b['_thread_error']:raise self.b['_thread_error']
            t=SimpleNamespace(**kwargs,alive=False,starts=0)
            t.is_alive=lambda:t.alive
            def start():
                t.starts+=1
                part=next(part for _,part,name in SPECS if name==t.name)
                self.assertIs(self.get('_plc_'+part+'_thread'),t)
                lock=self.get('_plc_'+part+'_lock');self.assertFalse(lock.acquire(blocking=False))
                if self.b['_start_error']:raise self.b['_start_error']
                t.alive=True
            t.start=start;self.created.append(t);return t
        thread_proxy=SimpleNamespace(Thread=factory,Lock=threading.Lock)
        clock_proxy=SimpleNamespace(sleep=lambda n:self.b['_sleep'](n))
        self.b.update(threading=thread_proxy,time=clock_proxy)
        if not BASELINE:
            a=patch.object(workers,'threading',thread_proxy);a.start();self.addCleanup(a.stop)
            a=patch.object(workers,'time',clock_proxy);a.start();self.addCleanup(a.stop)
        self.s,self.b,self.get,self.put=create(self.b)

    def start(self,name,epoch=7):
        return getattr(self.s,name)(epoch) if name=='plc_start_owner_heartbeat' else getattr(self.s,name)()

    def test_constructor_no_work_and_locks_are_distinct_nonreentrant(self):
        self.assertEqual(self.created,[]);self.assertEqual(self.trace,[])
        locks=[]
        for _,part,_ in SPECS:
            self.assertIsNone(self.get('_plc_'+part+'_thread'));lock=self.get('_plc_'+part+'_lock');locks.append(lock)
            self.assertTrue(lock.acquire(False));self.assertFalse(lock.acquire(False));lock.release()
        self.assertEqual(len({id(x) for x in locks}),3)

    def test_alive_skip_and_dead_restart(self):
        for name,part,title in SPECS:
            self.start(name);t=self.created[-1];self.assertEqual((t.name,t.daemon,t.starts),(title,True,1))
            count=len(self.created);self.start(name,99);self.assertEqual(len(self.created),count)
            t.alive=False;self.start(name);self.assertIsNot(self.get('_plc_'+part+'_thread'),t)

    def test_constructor_and_start_failure_retain_original_assignment_order(self):
        for name,part,_ in SPECS:
            old=SimpleNamespace(is_alive=lambda:False);self.put('_plc_'+part+'_thread',old)
            error=RuntimeError('construct');self.b['_thread_error']=error
            with self.assertRaises(RuntimeError) as caught:self.start(name)
            self.assertIs(caught.exception,error);self.assertIs(self.get('_plc_'+part+'_thread'),old)
            self.b['_thread_error']=None;self.b['_start_error']=error
            with self.assertRaises(RuntimeError) as caught:self.start(name)
            self.assertIs(caught.exception,error);self.assertIs(self.get('_plc_'+part+'_thread'),self.created[-1]);self.assertFalse(self.created[-1].alive)
            self.b['_start_error']=None

    def test_heartbeat_first_sleep_and_missing_repository(self):
        self.b['runtime_postgres_repository_or_none']=lambda:self.trace.append('repo')
        self.start(SPECS[0][0]);self.created[-1].target()
        self.assertEqual(self.trace,[('sleep',3),'repo'])

    def test_heartbeat_invalid_disabled_epoch_and_error_exit(self):
        cases=[('raw',None),('raw',{}),('raw',{'enabled':False}),('renew',None),('renew',{'epoch':8}),('renew',{'epoch':'bad'})]
        for kind,value in cases:
            with self.subTest(kind=kind,value=value):
                self.b['raw_plc_namespace']=(lambda c,v=value:v) if kind=='raw' else (lambda c:{'enabled':True})
                self.b['plc_claim_or_renew_io_owner']=lambda v=value:v
                self.start(SPECS[0][0]);self.created[-1].alive=False;self.created[-1].target()
        self.b['load_config']=Mock(side_effect=RuntimeError('config'));self.start(SPECS[0][0]);self.created[-1].target()
        self.b['load_config'].assert_called_once()

    def test_alive_heartbeat_retains_original_epoch_and_renew_callback(self):
        def renew():
            self.trace.append('renew');self.start(SPECS[0][0],99)
            return {'epoch':7}
        self.b['plc_claim_or_renew_io_owner']=renew
        calls=[]
        def sleep(n):
            calls.append(n)
            if len(calls)==2:raise StopLoop()
        self.b['_sleep']=sleep;self.start(SPECS[0][0],7);self.start(SPECS[0][0],99)
        with self.assertRaises(StopLoop):self.created[0].target()
        self.assertEqual(len(self.created),1);self.assertEqual(calls,[3,3]);self.assertIn('renew',self.trace)

    def test_poll_and_reconcile_catch_then_sleep_without_retry_in_iteration(self):
        for name,part,_ in SPECS[1:]:
            self.trace.clear();cap='plc_capture_poll_once' if part=='capture_poller' else 'plc_reconcile_pending_dispatches_once'
            def fail():self.trace.append('work');raise ValueError('work')
            def sleep(n):self.trace.append(('sleep',n));raise StopLoop()
            self.b[cap]=fail;self.b['_sleep']=sleep;self.start(name)
            with self.assertRaises(StopLoop):self.created[-1].target()
            self.assertEqual(self.trace,['work',('sleep',.1)])

    def test_sleep_errors_outside_catch_and_baseexception_not_swallowed(self):
        error=RuntimeError('sleep');self.b['_sleep']=Mock(side_effect=error)
        for name,_,_ in SPECS:
            self.start(name)
            with self.assertRaises(RuntimeError) as caught:self.created[-1].target()
            self.assertIs(caught.exception,error)
        self.b['_sleep']=lambda n:None;self.b['runtime_postgres_repository_or_none']=Mock(side_effect=StopLoop())
        with self.assertRaises(StopLoop):self.get('_plc_owner_heartbeat_thread').target()
        self.b['plc_capture_poll_once']=Mock(side_effect=StopLoop())
        with self.assertRaises(StopLoop):self.get('_plc_capture_poller_thread').target()

    def test_two_real_callers_serialize_only_fake_worker_start(self):
        for name,_,_ in SPECS:
            barrier=threading.Barrier(2);errors=[];before=len(self.created)
            def invoke():
                try:barrier.wait(timeout=5);self.start(name)
                except BaseException as exc:errors.append(exc)
            callers=[threading.Thread(target=invoke) for _ in range(2)]
            for t in callers:t.start()
            for t in callers:t.join(10);self.assertFalse(t.is_alive())
            self.assertEqual(errors,[]);self.assertEqual(len(self.created),before+1)

    @unittest.skipIf(bool(BASELINE),'candidate assembly only')
    def test_actual_root_has_bound_aliases_and_disabled_startup(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        owner=server._legacy_plc_workers
        for name,part,_ in SPECS:
            self.assertIs(getattr(server,name).__self__,owner)
            self.assertFalse(hasattr(server,'_plc_'+part+'_thread'))
        before=len(self.created);self.assertIsNone(server.start_plc_runtime_workers());self.assertEqual(len(self.created),before)
        self.assertEqual(server.app.router.on_startup.count(server.start_plc_runtime_workers),1)


if __name__=='__main__':unittest.main()

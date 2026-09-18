"""Synthetic failure projections; no inference, external process or device access."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_failure_formatter(ns, mode):
    events = []
    with patch.dict(ns):

        def third(value, limit):
            events.append(('C', limit))
            return 'C' + str(limit)

        def second(value, limit):
            events.append(('B', limit))
            return 'B' + str(limit)

        def first(value, limit):
            events.append(('A', limit))
            if mode == 'refresh' and limit == 160:
                ns['bounded_text'] = second
            return 'A' + str(limit)

        class Identifier:
            calls = 0

            def __str__(self):
                self.calls += 1
                events.append('id' + str(self.calls))
                if self.calls == 2:
                    ns['bounded_text'] = None if mode == 'missing' else second
                return 'id'

        class Required(dict):

            def get(self, key, default=None):
                if key == 'name':
                    events.append('name')
                    ns['bounded_text'] = third
                return super().get(key, default)
        ns['bounded_text'] = first
        ns['ai_tool_provider_meta'] = lambda settings: {}
        ns['AI_DETECTION_LABEL'] = 'label'
        caught = None
        result = None
        items = [{'accessory_id': 'a', 'name': 'A'}, {'accessory_id': 'b', 'name': 'B'}] if mode == 'refresh' else [Required(accessory_id=Identifier(), name='Name')]
        try:
            result = ns['ai_presence_failure_payload'](items, {}, reason='bad')
        except BaseException as exc:
            caught = exc
        if mode == 'missing':
            assert type(caught) is TypeError, (type(caught), events)
            assert events == ['id1', 'id2', 'name'], events
        elif mode == 'refresh':
            assert caught is None, (caught, events)
            assert events == [('A', 120), ('A', 160), ('B', 120), ('B', 160), ('B', 240), ('B', 240), ('B', 240)], events
            assert result['detections'][1]['label'] == 'B120' and result['detections'][1]['evidence'] == 'B160', result
        else:
            assert caught is None, (caught, events)
            assert events == ['id1', 'id2', 'name', ('B', 120), ('C', 160), ('C', 240), ('C', 240), ('C', 240)], events
            assert result['detections'][0]['label'] == 'B120', result
    return events


class DetectionFailureContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='failure-contract-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
        self.stack.enter_context(patch.object(self.api,'bounded_text',self.api.bounded_text))
        self.stack.enter_context(patch.object(self.api,'AI_DETECTION_LABEL','Inspection'))
        self.meta=self.stack.enter_context(patch.object(self.api,'ai_tool_provider_meta',return_value={'provider':'fixture','provider_model':'test-model','provider_status':'ready'}))
        self.settings={'status':'input-status','model':'test-model','api_key':'synthetic-only'}
    def failure(self,items,**kwargs): return self.api.ai_presence_failure_payload(items,self.settings,reason='bad response',**kwargs)

    def test_complete_failure_projection_duplicate_ids_and_empty_input(self):
        result=self.failure([{'accessory_id':'a','name':' A '},{'accessory_id':'a','label':'Again'},{'accessory_id':0},{}],timed_out=True,latency_ms=17)
        self.assertEqual(result,{'tool':'vision.inspect.presence','passed':False,'rule':{'match_policy':'ai_presence','label':'Inspection','present':[],
            'missing':['a','a'],'extra':[],'counts':{'a':0}},'detections':[
                {'accessory_id':'a','label':'A','present':False,'confidence':0.0,'evidence':'bad response','observed_text':[]},
                {'accessory_id':'a','label':'Again','present':False,'confidence':0.0,'evidence':'bad response','observed_text':[]}],
            'ai':{'latency_ms':17,'timed_out':True,'provider_failure':True,'failure_reason':'bad response','raw_summary':'bad response',
                'provider_status':'ready','error':'bad response','provider':'fixture','provider_model':'test-model'}})
        self.assertIsNot(result['detections'][0]['observed_text'],result['detections'][1]['observed_text'])
        self.meta.assert_called_once_with(self.settings); self.assertNotIn('synthetic-only',str(result))
        formatter=Mock(side_effect=['failure','summary','error']); self.api.bounded_text=formatter; self.meta.reset_mock()
        empty=self.failure([])
        self.assertTrue(empty['passed']); self.assertEqual(empty['detections'],[]); self.assertEqual(empty['rule']['missing'],[])
        self.assertEqual(formatter.call_args_list,[call('bad response',240)]*3); self.meta.assert_called_once_with(self.settings)
        self.assertEqual([empty['ai'][k] for k in ['failure_reason','raw_summary','error']],['failure','summary','error'])

    def test_two_pass_id_reads_and_single_pass_iterable_preserve_asymmetry(self):
        reads=[]
        class Item(dict):
            def get(inner,key,default=None):
                if key=='accessory_id': reads.append(key); return ['truthy','missing-id','detection-id'][len(reads)-1]
                return super().get(key,default)
        result=self.failure([Item()]); self.assertEqual(len(reads),3)
        self.assertEqual(result['rule']['missing'],['missing-id']); self.assertEqual(result['detections'][0]['accessory_id'],'detection-id')
        result=self.failure(iter([{'accessory_id':'a'}]))
        self.assertFalse(result['passed']); self.assertEqual(result['rule']['missing'],['a']); self.assertEqual(result['detections'],[])
        class Changed(dict):
            def get(inner,key,default=None):
                if key=='accessory_id': reads.append(key); return '' if len(reads)==1 else 'later'
                return super().get(key,default)
        reads.clear(); result=self.failure([Changed()]); self.assertTrue(result['passed']); self.assertEqual(result['rule']['missing'],[])
        self.assertEqual(result['detections'][0]['accessory_id'],'later'); self.assertEqual(len(reads),2)

    def test_formatter_limits_and_provider_meta_precede_late_label_and_overrides(self):
        calls=[]; marker={'overridden':True}; texts=iter(['label','evidence','reason','summary','error'])
        self.api.bounded_text=Mock(side_effect=lambda value,limit:calls.append((value,limit)) or next(texts))
        def metadata(settings):
            self.assertEqual(calls,[('name',120),('bad response',160)])
            self.api.AI_DETECTION_LABEL='Changed'; return {'provider_failure':False,'timed_out':marker,'error':marker,'provider_status':'overridden'}
        self.meta.side_effect=metadata
        result=self.failure([{'accessory_id':'a','name':'name'}])
        self.assertEqual(calls,[('name',120),('bad response',160),('bad response',240),('bad response',240),('bad response',240)])
        self.assertEqual(result['rule']['label'],'Changed'); self.assertFalse(result['ai']['provider_failure'])
        self.assertIs(result['ai']['timed_out'],marker); self.assertIs(result['ai']['error'],marker); self.assertEqual(result['ai']['provider_status'],'overridden')
        self.assertEqual(result['detections'][0]['label'],'label'); self.assertEqual(result['detections'][0]['evidence'],'evidence')
        self.assertEqual(result['ai']['failure_reason'],'reason'); self.assertEqual(result['ai']['raw_summary'],'summary')

    def test_metadata_expansion_errors_happen_after_all_formatting_without_retry(self):
        for stage in ['keys','getitem','nonstring','none']:
            with self.subTest(stage=stage):
                events=[]; self.api.bounded_text=Mock(side_effect=lambda value,limit:events.append('text') or 'text')
                class Metadata:
                    def keys(inner):
                        events.append('keys')
                        if stage=='keys': raise OSError('keys')
                        return [1] if stage=='nonstring' else ['value']
                    def __getitem__(inner,key):
                        events.append('getitem')
                        if stage=='getitem': raise OSError('getitem')
                        return 'value'
                self.meta.return_value=None if stage=='none' else Metadata(); self.meta.side_effect=None; self.meta.reset_mock()
                if stage=='nonstring':
                    # A dict display, unlike function **kwargs, accepts non-string mapping keys.
                    result=self.failure([]); self.assertEqual(result['ai'][1],'value')
                else:
                    with self.assertRaises(TypeError if stage=='none' else OSError): self.failure([])
                self.assertEqual(events,['text']*3+([] if stage=='none' else ['keys'] if stage=='keys' else ['keys','getitem']))
                self.meta.assert_called_once()


    def test_model_projection_preserves_truthy_collection_aliases_and_falsey_fresh_defaults(self):
        selected=['a']; counts={'a':2}; names=['A']; labels={'a':'A'}
        spec={'id':'model','label':None,'task_id':'task','task_label':'Task','selected_accessory_ids':selected,
            'required_accessory_counts':counts,'accessory_names':names,'accessory_labels':labels}
        result=self.api.ai_model_payload(spec,self.settings)
        self.assertEqual(result,{'id':'model','label':None,'variant':'ai_detection','is_ai_detection':True,'provider_model':'test-model',
            'uses_ocr':True,'task_id':'task','task_label':'Task','selected_accessory_ids':['a'],'required_accessory_counts':{'a':2},'accessory_names':['A'],'accessory_labels':{'a':'A'}})
        for key in ['selected_accessory_ids','required_accessory_counts','accessory_names','accessory_labels']: self.assertIs(result[key],spec[key])
        first=self.api.ai_model_payload({'id':'m','selected_accessory_ids':[],'required_accessory_counts':{}},{})
        second=self.api.ai_model_payload({'id':'m'},{}); self.assertEqual(first,second)
        self.assertEqual(first['label'],'Inspection'); self.assertEqual(first['provider_model'],'')
        for key in ['selected_accessory_ids','required_accessory_counts','accessory_names','accessory_labels']: self.assertIsNot(first[key],second[key])
        self.assertIsNot(first['selected_accessory_ids'],first['accessory_names']); self.assertIsNot(first['required_accessory_counts'],first['accessory_labels'])

    def test_model_reads_id_before_eager_label_default_even_with_existing_label(self):
        events=[]
        class Spec(dict):
            def __getitem__(inner,key): events.append(key); self.api.AI_DETECTION_LABEL='after-id'; return super().__getitem__(key)
            def get(inner,key,default=None):
                if key=='label': events.append(('label-default',default)); self.api.AI_DETECTION_LABEL='after-label'
                return super().get(key,default)
        for label in ['present',None]:
            events.clear(); result=self.api.ai_model_payload(Spec(id='m',label=label),{})
            self.assertEqual(result['label'],label); self.assertEqual(events,['id',('label-default','after-id')])
        events.clear()
        with self.assertRaises(KeyError): self.api.ai_model_payload(Spec(),{})
        self.assertEqual(events,['id'])

    def test_failure_formatters_rebind_per_expression_and_capture_before_label_argument(self):
        calls=[]; formatters=[]
        def make(index):
            def format(value,limit):
                calls.append((index,value,limit)); self.api.bounded_text=formatters[min(index+1,4)]; return 'format-'+str(index)
            return Mock(side_effect=format)
        formatters.extend(make(i) for i in range(5)); self.api.bounded_text=formatters[0]
        result=self.failure([{'accessory_id':'a','name':'name'}])
        self.assertEqual(calls,[(0,'name',120),(1,'bad response',160),(2,'bad response',240),(3,'bad response',240),(4,'bad response',240)])
        self.assertEqual([result['detections'][0]['label'],result['detections'][0]['evidence'],result['ai']['failure_reason'],result['ai']['raw_summary'],result['ai']['error']],['format-'+str(i) for i in range(5)])
        first=Mock(); second=Mock(return_value='second'); third=Mock(return_value='third'); self.api.bounded_text=first; reads=[]
        class Item(dict):
            def get(inner,key,default=None):
                if key=='accessory_id':
                    reads.append(key)
                    if len(reads)==3: self.api.bounded_text=second
                if key=='name': self.api.bounded_text=third
                return super().get(key,default)
        result=self.failure([Item(accessory_id='a',name='name')]); first.assert_not_called(); second.assert_called_once_with('name',120)
        self.assertEqual(result['detections'][0]['label'],'second'); self.assertEqual(third.call_count,4)

    def test_label_none_and_captured_error_evaluate_name_once_and_do_not_retry(self):
        for outcome in ['none','error','argument']:
            with self.subTest(outcome=outcome):
                error=OSError('once'); first=None if outcome=='none' else Mock(side_effect=[error,'retry-success']); later=Mock(return_value='later')
                self.api.bounded_text=first; reads=[]; self.meta.reset_mock()
                class Item(dict):
                    def get(inner,key,default=None):
                        reads.append(key)
                        if key=='name':
                            self.api.bounded_text=later
                            if outcome=='argument': raise error
                        return super().get(key,default)
                with self.assertRaises(TypeError if outcome=='none' else OSError) as caught: self.failure([Item(accessory_id='a',name='name')])
                if outcome!='none': self.assertIs(caught.exception,error); self.assertEqual(first.call_count,int(outcome=='error'))
                self.assertEqual(reads,['accessory_id','accessory_id','accessory_id','name']); later.assert_not_called(); self.meta.assert_not_called()

    def test_metadata_failure_happens_after_detection_formatters_without_retry(self):
        error=OSError('unknown'); self.meta.side_effect=[error,{}]; self.api.bounded_text=Mock(return_value='text')
        with self.assertRaises(OSError) as caught: self.failure([{'accessory_id':'a','name':'name'}])
        self.assertIs(caught.exception,error); self.meta.assert_called_once()
        self.assertEqual(self.api.bounded_text.call_args_list,[call('name',120),call('bad response',160)])

    def test_failure_result_reads_passed_before_model_then_shares_late_payload_fields(self):
        events=[]; settings={'settings':True}; item1={'id':'a'}; item2={'id':'b'}; rows=[{'accessory_id':'a'},{'accessory_id':'b'}]
        old_passed=object(); new_rule={'changed':True}; new_detections=[]; new_ai={'error':'changed'}; model_result={'model':'result'}
        class Payload(dict):
            def __getitem__(inner,key): events.append('payload:'+key); return super().__getitem__(key)
        payload=Payload(passed=old_passed,rule={},detections=[1],ai={})
        settings_call=Mock(side_effect=lambda:events.append('settings') or settings)
        profile=Mock(side_effect=lambda item,count:events.append('profile:'+item['id']) or rows[0 if item is item1 else 1])
        failure=Mock(side_effect=lambda *args,**kw:events.append('failure') or payload)
        def project(spec,value):
            events.append('model'); payload.update(passed=False,rule=new_rule,detections=new_detections,ai=new_ai); return model_result
        model=Mock(side_effect=project); spec={'id':'m'}; reason=object(); latency=object(); timeout=object()
        with patch.object(self.api,'ai_detection_settings',settings_call),patch.object(self.api,'required_accessory_profile_payload',profile),patch.object(self.api,'ai_presence_failure_payload',failure),patch.object(self.api,'ai_model_payload',model):
            result=self.api.ai_detection_failure_result('request',spec,[(item1,2),(item2,3)],'/image',reason=reason,timed_out=timeout,latency_ms=latency)
        self.assertEqual(events,['settings','profile:a','profile:b','failure','payload:passed','model','payload:rule','payload:detections','payload:ai'])
        self.assertEqual(result,{'request_id':'request','passed':old_passed,'model':model_result,'rule':new_rule,'detections':new_detections,'annotated_url':'/image','ai':new_ai})
        self.assertIs(result['passed'],old_passed); self.assertIs(result['model'],model_result); self.assertIs(result['rule'],new_rule); self.assertIs(result['detections'],new_detections); self.assertIs(result['ai'],new_ai)
        failure.assert_called_once_with(rows,settings,reason=reason,timed_out=timeout,latency_ms=latency); model.assert_called_once_with(spec,settings)
        self.assertIs(failure.call_args.args[0][0],rows[0]); self.assertEqual(profile.call_args_list,[call(item1,2),call(item2,3)])

    def test_failure_result_each_dependency_error_stops_following_work_without_retry(self):
        for stage in ['settings','profile1','profile2','failure','passed','model']:
            with self.subTest(stage=stage):
                error=OSError('once'); settings=Mock(return_value={}); profile=Mock(side_effect=lambda *args:{}); failure=Mock(return_value={'passed':False,'rule':{},'detections':[],'ai':{}}); model=Mock(return_value={})
                if stage=='settings': settings.side_effect=[error,{}]
                if stage.startswith('profile'):
                    def profile_once(*args):
                        if profile.call_count==(1 if stage=='profile1' else 2): raise error
                        return {}
                    profile.side_effect=profile_once
                if stage=='failure':
                    def failure_once(*args,**kwargs):
                        if failure.call_count==1: raise error
                        return {'passed':False,'rule':{},'detections':[],'ai':{}}
                    failure.side_effect=failure_once
                if stage=='model': model.side_effect=[error,{}]
                if stage=='passed': failure.return_value={}
                with patch.object(self.api,'ai_detection_settings',settings),patch.object(self.api,'required_accessory_profile_payload',profile),patch.object(self.api,'ai_presence_failure_payload',failure),patch.object(self.api,'ai_model_payload',model):
                    with self.assertRaises(KeyError if stage=='passed' else OSError) as caught: self.api.ai_detection_failure_result('r',{},[({},1),({},2)],'url',reason='bad')
                if stage!='passed': self.assertIs(caught.exception,error)
                self.assertEqual((settings.call_count,profile.call_count,failure.call_count,model.call_count),{
                    'settings':(1,0,0,0),'profile1':(1,1,0,0),'profile2':(1,2,0,0),'failure':(1,2,1,0),'passed':(1,2,1,0),'model':(1,2,1,1)}[stage])


    def test_independent_compositions_preserve_settings_formatters_labels_and_shared_results(self):
        from local_inspection_service.detection.failure_projection import FailureProjection
        from local_inspection_service.detection.failure_results import DetectionFailureResult
        def build(owner):
            formatter=Mock(side_effect=lambda value,limit:owner+':'+str(limit)+':'+str(value)); text=Mock(return_value=formatter)
            meta=Mock(return_value={'provider':owner}); label=Mock(return_value='Inspection '+owner)
            projection=FailureProjection(text,meta,label); settings_value={'model':owner}; settings=Mock(return_value=settings_value)
            profile=Mock(side_effect=lambda item,count:{'accessory_id':owner+'-'+item['id'],'name':owner,'expected_count':count})
            payloads=[]; models=[]
            def fail(*args,**kwargs):
                value=projection.ai_presence_failure_payload(*args,**kwargs); payloads.append(value); return value
            def project(*args):
                value=projection.ai_model_payload(*args); models.append(value); return value
            failure=Mock(side_effect=fail); model=Mock(side_effect=project)
            service=DetectionFailureResult(settings,profile,failure,model)
            callbacks=[formatter,text,meta,label,settings,profile,failure,model]
            for callback in callbacks: callback.assert_not_called()
            return owner,service,callbacks,payloads,models,settings_value
        instances=[build('alice'),build('bob')]
        for name in ['bounded_text','ai_tool_provider_meta','ai_detection_settings','required_accessory_profile_payload','ai_presence_failure_payload','ai_model_payload']:
            self.stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root dependency')))
        for index in [1,0,1,0]:
            owner,service,callbacks,payloads,models,settings_value=instances[index]
            for callback in callbacks: callback.reset_mock()
            spec={'id':'model','label':None,'selected_accessory_ids':[owner]}; item={'id':'part'}
            result=service.ai_detection_failure_result(owner,spec,[(item,2)],'/image',reason='bad',timed_out=True,latency_ms=123)
            self.assertEqual(result['rule']['missing'],[owner+'-part']); self.assertEqual(result['rule']['label'],'Inspection '+owner)
            self.assertEqual(result['detections'][0]['label'],owner+':120:'+owner); self.assertEqual(result['ai']['provider'],owner)
            self.assertEqual(result['ai']['failure_reason'],owner+':240:bad'); self.assertEqual(result['model']['provider_model'],owner); self.assertIsNone(result['model']['label'])
            self.assertIs(result['model'],models[-1]); self.assertIs(result['model']['selected_accessory_ids'],spec['selected_accessory_ids'])
            for key in ['rule','detections','ai']: self.assertIs(result[key],payloads[-1][key])
            self.assertEqual([callback.call_count for callback in callbacks],[5,5,1,2,1,1,1,1])
            callbacks[5].assert_called_once_with(item,2); callbacks[2].assert_called_once_with(settings_value)
            callbacks[7].assert_called_once_with(spec,settings_value)

    def test_independent_provider_errors_keep_exact_read_boundaries(self):
        from local_inspection_service.detection.failure_projection import FailureProjection
        error=OSError('lookup'); reads=[]
        class Item(dict):
            def get(inner,key,default=None): reads.append(key); return super().get(key,default)
        text=Mock(side_effect=error); meta=Mock(return_value={}); label=Mock(return_value='label')
        projection=FailureProjection(text,meta,label); text.assert_not_called(); meta.assert_not_called(); label.assert_not_called()
        with self.assertRaises(OSError) as caught: projection.ai_presence_failure_payload([Item(accessory_id='a',name='name')],{},reason='bad')
        self.assertIs(caught.exception,error); text.assert_called_once_with(); meta.assert_not_called(); label.assert_not_called()
        self.assertEqual(reads,['accessory_id']*3)
        text.reset_mock(); text.side_effect=None; text.return_value=Mock(return_value='text'); label.side_effect=error
        with self.assertRaises(OSError) as caught: projection.ai_presence_failure_payload([],{},reason='bad')
        self.assertIs(caught.exception,error); meta.assert_called_once_with({}); label.assert_called_once_with(); text.assert_not_called()
        class Spec(dict):
            def __getitem__(inner,key): reads.append(key); return super().__getitem__(key)
            def get(inner,key,default=None): reads.append(key); return super().get(key,default)
        reads.clear(); label.reset_mock()
        with self.assertRaises(OSError) as caught: projection.ai_model_payload(Spec(id='m',label='present'),{})
        self.assertIs(caught.exception,error); self.assertEqual(reads,['id']); label.assert_called_once_with()
        for position in range(5):
            with self.subTest(formatter_error_position=position):
                def format(value,limit):
                    if formatter.call_count==position+1: raise error
                    return 'would succeed'
                formatter=Mock(side_effect=format); text=Mock(return_value=formatter); meta=Mock(return_value={}); label=Mock(return_value='label')
                projection=FailureProjection(text,meta,label)
                with self.assertRaises(OSError) as caught: projection.ai_presence_failure_payload([{'accessory_id':'a','name':'name'}],{},reason='bad')
                self.assertIs(caught.exception,error); self.assertEqual(text.call_count,position+1); self.assertEqual(formatter.call_count,position+1)
                self.assertEqual(meta.call_count,int(position>=2)); self.assertEqual(label.call_count,int(position>=2))



    def test_each_failure_formatter_error_stops_without_retry_even_if_next_attempt_succeeds(self):
        expected=[call('name',120),call('bad response',160)]+[call('bad response',240)]*3
        for position in range(5):
            with self.subTest(position=position):
                error=OSError('once'); reads=[]
                def format(value,limit):
                    if formatter.call_count==position+1: raise error
                    return 'would succeed'
                formatter=Mock(side_effect=format); self.api.bounded_text=formatter; self.meta.reset_mock()
                class Settings(dict):
                    def get(inner,key,default=None): reads.append(key); return super().get(key,default)
                settings=Settings(status='status')
                with self.assertRaises(OSError) as caught: self.api.ai_presence_failure_payload([{'accessory_id':'a','name':'name'}],settings,reason='bad response')
                self.assertIs(caught.exception,error); self.assertEqual(formatter.call_args_list,expected[:position+1])
                self.assertEqual(self.meta.call_count,int(position>=2)); self.assertEqual(reads,['status'] if position==4 else [])


    def test_all_formatter_providers_fail_once_without_retry(self):
        from local_inspection_service.detection.failure_projection import FailureProjection
        for position in range(5):
            with self.subTest(position=position):
                error=RuntimeError('formatter provider failure'); calls=[]
                formatter=Mock(return_value='text'); meta=Mock(return_value={}); label=Mock(return_value='label')
                def provider():
                    calls.append('provider')
                    if len(calls)==position+1: raise error
                    return formatter
                projection=FailureProjection(provider,meta,label)
                with self.assertRaises(BaseException) as caught:
                    projection.ai_presence_failure_payload([{'accessory_id':'a','name':'name'}],{},reason='bad')
                self.assertIs(caught.exception,error); self.assertEqual(len(calls),position+1); self.assertEqual(formatter.call_count,position)
                self.assertEqual(meta.call_count,int(position>=2)); self.assertEqual(label.call_count,int(position>=2))

    def test_metadata_and_label_providers_fail_once_without_retry(self):
        from local_inspection_service.detection.failure_projection import FailureProjection
        for operation in ('metadata','failure_label','model_label'):
            with self.subTest(operation=operation):
                calls=[]; error=RuntimeError('projection provider failure'); formatter=Mock(return_value='text')
                def fail_once(*args):
                    calls.append(args)
                    if len(calls)==1: raise error
                    return {} if operation=='metadata' else 'label'
                meta=Mock(side_effect=fail_once if operation=='metadata' else lambda settings:{})
                label=Mock(side_effect=fail_once if operation!='metadata' else lambda:'label')
                projection=FailureProjection(lambda:formatter,meta,label)
                with self.assertRaises(BaseException) as caught:
                    if operation=='model_label': projection.ai_model_payload({'id':'m','label':'present'},{})
                    else: projection.ai_presence_failure_payload([],{},reason='bad')
                self.assertIs(caught.exception,error); self.assertEqual(len(calls),1); formatter.assert_not_called()
                if operation=='metadata': label.assert_not_called()
                if operation=='model_label': meta.assert_not_called()


    def test_failure_projection_mapping_failures_are_not_retried(self):
        for owner,key,index in [('item','accessory_id',1),('item','accessory_id',2),('item','accessory_id',3),('item','label',1),('settings','status',1)]:
            with self.subTest(owner=owner,key=key,index=index):
                reads=[]; error=RuntimeError('projection mapping')
                class Values(dict):
                    def get(inner,name,default=None):
                        if name==key:
                            reads.append(name)
                            if len(reads)==index: raise error
                        return super().get(name,default)
                item={'accessory_id':'a','label':'Label'}; settings={'status':'ready'}
                if owner=='item': item=Values(item)
                else: settings=Values(settings)
                with self.assertRaises(BaseException) as caught:
                    self.api.ai_presence_failure_payload([item],settings,reason='bad')
                self.assertIs(caught.exception,error); self.assertEqual(reads,[key]*index)

    def test_model_projection_mapping_failures_are_not_retried(self):
        for owner,key in [('spec',name) for name in ('label','task_id','task_label','selected_accessory_ids','required_accessory_counts','accessory_names','accessory_labels')]+[('settings','model')]:
            with self.subTest(owner=owner,key=key):
                reads=[]; error=RuntimeError('model mapping')
                class Values(dict):
                    def get(inner,name,default=None):
                        if name==key:
                            reads.append(name)
                            if len(reads)==1: raise error
                        return super().get(name,default)
                spec={'id':'model'}; settings={}
                if owner=='spec': spec=Values(spec)
                else: settings=Values(settings)
                with self.assertRaises(BaseException) as caught: self.api.ai_model_payload(spec,settings)
                self.assertIs(caught.exception,error); self.assertEqual(reads,[key])

    def test_result_field_reads_fail_once_without_retry(self):
        for key in ('passed','rule','detections','ai'):
            with self.subTest(key=key):
                reads=[]; error=RuntimeError('result field')
                class Payload(dict):
                    def __getitem__(inner,name):
                        reads.append(name)
                        if name==key and reads.count(key)==1: raise error
                        return super().__getitem__(name)
                payload=Payload(passed=False,rule={},detections=[],ai={}); model=Mock(return_value={})
                with patch.object(self.api,'ai_detection_settings',return_value={}),patch.object(self.api,'ai_presence_failure_payload',return_value=payload),patch.object(self.api,'ai_model_payload',model):
                    with self.assertRaises(BaseException) as caught:
                        self.api.ai_detection_failure_result('r',{},[],'url',reason='bad')
                self.assertIs(caught.exception,error)
                order=['passed','rule','detections','ai']; self.assertEqual(reads,order[:order.index(key)+1]); self.assertEqual(model.call_count,int(key!='passed'))


    def test_failure_formatters_refresh_after_conversion_and_between_items(self):
        for mode in ('near','missing','refresh'):
            with self.subTest(mode=mode):
                _capture_failure_formatter(self.api.__dict__,mode)


if __name__=='__main__': unittest.main()

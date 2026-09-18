"""Offline accessory identity and required-item contracts; no model, device or external I/O."""
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_policy_trace(ns,site):
    events=[]
    with patch.dict(ns):
        if site in ('aliases','lookup','aliases_none','lookup_none'):
            missing=site.endswith('_none');operation=site.split('_')[0]
            def forbidden(*a):raise AssertionError('callback captured before preceding id read')
            def next_uid(item):events.append('uidC');return 'uid2'
            def next_legacy(item):events.append('legacyC');return 'legacy2'
            def uid(item):events.append('uidB');ns['accessory_legacy_uid']=legacy;return 'uid'
            def legacy(item):events.append('legacyB');return 'legacy'
            class ID:
                def __bool__(self):events.append('bool');ns['accessory_uid']=next_uid;ns['accessory_legacy_uid']=next_legacy;return True
                def __str__(self):events.append('str');return 'raw'
            value=ID()
            class Item(dict):
                def get(self,key,default=None):
                    assert key=='id',key
                    events.append('get');ns['accessory_uid']=None if missing else uid;return value
            ns['accessory_uid']=forbidden;ns['accessory_legacy_uid']=forbidden
            item=Item();caught=None;result=None
            try:result=ns['accessory_id_aliases'](item) if operation=='aliases' else list(ns['accessory_lookup_by_id']({'accessories':[item,{'id':'second'}]}))
            except BaseException as exc:caught=exc
            if missing:
                assert type(caught) is TypeError,(type(caught),events);assert events==['get'],events
            else:
                assert caught is None,(caught,events)
                expected=['get','uidB','legacyB','bool','str']+(['uidC','legacyC'] if operation=='lookup' else [])
                assert events==expected,events
                assert result==['raw','uid','legacy']+(['second','uid2','legacy2'] if operation=='lookup' else []),result
        elif site=='required_uid_refresh':
            a={'id':'a'};b={'id':'b'}
            def later(item):events.append('uidB');assert item is b;return 'b'
            def first(item):events.append('uidA');assert item is a;ns['accessory_uid']=later;return 'a'
            ns['accessory_uid']=first
            result=ns['ai_required_accessories']({'accessories':[a,b]},{'is_specialized':True,'selected_accessory_ids':['a','b']})
            assert result==[(a,1),(b,1)] and result[0][0] is a and result[1][0] is b,result
            assert events==['uidA','uidB'],events
        elif site=='labels_get_binding':
            class Next(dict):
                def get(self,key,default=None):events.append('B');return 'second'
            class First:
                def __getattribute__(self,key):
                    assert key=='get',key
                    events.append('bindA');ns['CLASS_LABELS']=Next()
                    def get(key,default=None):events.append('A');return 'first'
                    return get
            ns['CLASS_LABELS']=First()
            result=ns['ai_required_accessories']({'required_classes':[7,7]}, {})
            assert [item['name'] for item,count in result]==['first','second'],result
            assert events==['bindA','A','B'],events
        else:raise AssertionError(site)
    return events


class AccessoryRequirementContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='accessory-requirements-root-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.uid=self.stack.enter_context(patch.object(self.api,'accessory_uid',side_effect=lambda item:item.get('uid',item.get('id',''))))
        self.legacy=self.stack.enter_context(patch.object(self.api,'accessory_legacy_uid',side_effect=lambda item:item.get('legacy','')))
        self.stack.enter_context(patch.object(self.api,'CLASS_LABELS',{0:'Object',1:'Manual'}))
        for target in ['requests.request','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))

    def test_lookup_first_collision_wins_order_and_record_aliases(self):
        a={'id':' a ','uid':'shared','legacy':' old-a '}; b={'id':'b','uid':'shared','legacy':'a'}; c={'id':0,'uid':False,'legacy':' c '}
        config={'accessories':[a,b,c]}; before=copy.deepcopy(config)
        result=self.api.accessory_lookup_by_id(config)
        self.assertEqual(list(result),['a','shared','old-a','b','c']); self.assertIs(result['shared'],a); self.assertIs(result['a'],a); self.assertIs(result['b'],b); self.assertIs(result['c'],c)
        self.assertEqual(config,before); result['old-a']['added']=1; self.assertEqual(a['added'],1)
        self.assertEqual(self.uid.call_args_list,[call(a),call(b),call(c)]); self.assertEqual(self.legacy.call_args_list,[call(a),call(b),call(c)])

    def test_aliases_normalize_order_dedupe_and_falsy_values(self):
        for item,expected in [({'id':' x ','uid':'x','legacy':' y '},['x','y']),({'id':None,'uid':0,'legacy':False},[]),({'id':12,'uid':' 13 ','legacy':'12'},['12','13'])]:
            with self.subTest(item=item):
                self.assertEqual(self.api.accessory_id_aliases(item),expected)
        self.assertEqual(self.api.accessory_lookup_by_id({}),{}); self.assertEqual(self.api.accessory_id_aliases({}),[])

    def test_eager_tuple_resolves_replaced_legacy_before_id_conversion(self):
        for operation in ['aliases','lookup']:
            with self.subTest(operation=operation):
                events=[]
                class ID:
                    def __bool__(inner): events.append('bool'); return True
                    def __str__(inner): events.append('str'); return 'raw'
                item={'id':ID()}; late=Mock(side_effect=lambda item:events.append('legacy-late') or 'legacy')
                def uid(item): events.append('uid'); self.api.accessory_legacy_uid=late; return 'uid'
                self.uid.side_effect=uid; self.api.accessory_legacy_uid=self.legacy
                result=self.api.accessory_id_aliases(item) if operation=='aliases' else list(self.api.accessory_lookup_by_id({'accessories':[item]}))
                self.assertEqual(result,['raw','uid','legacy']); self.assertEqual(events,['uid','legacy-late','bool','str']); self.legacy.assert_not_called(); late.assert_called_once_with(item)

    def test_tuple_and_identifier_errors_propagate_without_retry(self):
        for operation in ['aliases','lookup']:
            for stage in ['uid','legacy','bool','str']:
                with self.subTest(operation=operation,stage=stage):
                    events=[]; error=OSError(stage)
                    def step(name):
                        events.append(name)
                        if stage==name and events.count(name)==1: raise error
                    class ID:
                        def __bool__(inner): step('bool'); return True
                        def __str__(inner): step('str'); return 'raw'
                    self.uid.side_effect=lambda item:step('uid') or 'uid'
                    self.legacy.side_effect=lambda item:step('legacy') or 'legacy'
                    item={'id':ID()}
                    with self.assertRaises(OSError) as caught:
                        if operation=='aliases': self.api.accessory_id_aliases(item)
                        else: self.api.accessory_lookup_by_id({'accessories':[item,{'id':'not reached'}]})
                    self.assertIs(caught.exception,error)
                    self.assertEqual(events,{'uid':['uid'],'legacy':['uid','legacy'],'bool':['uid','legacy','bool'],'str':['uid','legacy','bool','str']}[stage])

    def test_lookup_accepts_single_pass_iterable_and_invalid_collections_fail(self):
        a={'id':'a'}; self.assertIs(self.api.accessory_lookup_by_id({'accessories':iter([a])})['a'],a)
        for invalid in [None,1]:
            with self.subTest(invalid=invalid), self.assertRaises(TypeError): self.api.accessory_lookup_by_id({'accessories':invalid})
        with self.assertRaises(AttributeError): self.api.accessory_lookup_by_id({'accessories':[None]})

    def test_specialized_last_uid_wins_and_selected_duplicates_keep_aliases(self):
        a={'id':'a','uid':'same','class_id':0}; b={'id':'b','uid':'same','class_id':1}
        config={'accessories':[a,b]}; spec={'is_specialized':True,'selected_accessory_ids':['same','missing','same'],
            'required_accessory_counts':{'same':3,'missing':0},'accessory_labels':{'missing':'Missing'}}
        before=copy.deepcopy((config,spec)); result=self.api.ai_required_accessories(config,spec)
        self.assertEqual([n for _,n in result],[3,1,3]); self.assertIs(result[0][0],b); self.assertIs(result[2][0],b)
        self.assertEqual(result[1][0],{'id':'missing','class_id':-1,'name':'Missing','material_type':'object','source_files':[],'normalized_assets':[]})
        self.assertEqual((config,spec),before); self.legacy.assert_not_called()

    def test_specialized_counts_collide_after_string_conversion_without_reordering_or_cap(self):
        spec={'is_specialized':1,'required_accessory_counts':{1:2,'1':8,2:1000000,'zero':-9},'accessory_labels':{1:None,2:False}}
        for selected in [None,[]]:
            spec['selected_accessory_ids']=selected; result=self.api.ai_required_accessories({},spec)
            self.assertEqual([(item['id'],item['name'],n) for item,n in result],[('1','None',8),('2','False',1000000),('zero','zero',1)])
        self.assertEqual(self.api.ai_required_accessories({},{'is_specialized':True}),[])

    def test_specialized_does_not_normalize_uid_or_selected_whitespace(self):
        numeric={'uid':1}; spaced={'uid':' x '}; exact={'uid':'x'}
        result=self.api.ai_required_accessories({'accessories':[numeric,spaced,exact]},
            {'is_specialized':True,'selected_accessory_ids':[1,' x ','x',' missing ',' missing '],'required_accessory_counts':{'x':9}})
        self.assertIsNot(result[0][0],numeric); self.assertEqual(result[0][0]['id'],'1')
        self.assertIs(result[1][0],spaced); self.assertIs(result[2][0],exact); self.assertEqual([n for _,n in result],[1,1,9,1,1])
        self.assertIsNot(result[3][0],result[4][0]); self.assertIsNot(result[3][0]['source_files'],result[4][0]['source_files'])
        self.assertIsNot(result[3][0]['source_files'],result[3][0]['normalized_assets'])

    def test_uid_index_is_eager_before_branch_and_ordinary_class_conversion(self):
        events=[]
        class Config(dict):
            def get(inner,key,default=None): events.append('config:'+key); return super().get(key,default)
        class Spec(dict):
            def get(inner,key,default=None): events.append('spec:'+key); return super().get(key,default)
        self.uid.side_effect=lambda item:events.append('uid') or item['id']
        result=self.api.ai_required_accessories(Config(accessories=[{'id':'a','class_id':0}],required_classes=[0]),Spec(is_specialized=False,required_accessory_counts={'bad':'bad'}))
        self.assertEqual(result,[({'id':'a','class_id':0},1)])
        self.assertEqual(events,['config:accessories','uid','spec:is_specialized','config:required_classes','config:min_counts'])
        self.uid.side_effect=RuntimeError('uid')
        with self.assertRaisesRegex(RuntimeError,'uid'): self.api.ai_required_accessories({'accessories':[{}]}, {})

    def test_ordinary_last_class_wins_duplicates_and_minimum_clamp(self):
        a={'id':'a','class_id':0}; b={'id':'b','class_id':'0'}; c={'id':'c','class_id':1}
        config={'accessories':[a,b,c,{'class_id':None},{'class_id':'bad'}],'required_classes':['0',1,0],'min_counts':{'0':-1,1:500000}}
        before=copy.deepcopy(config); result=self.api.ai_required_accessories(config,{'is_specialized':False})
        self.assertEqual([n for _,n in result],[1,500000,1]); self.assertIs(result[0][0],b); self.assertIs(result[1][0],c); self.assertIs(result[2][0],b); self.assertEqual(config,before)

    def test_ordinary_missing_metadata_complete_fail_closed_records_and_fresh_lists(self):
        result=self.api.ai_required_accessories({'required_classes':[0,1,-1,7,7]}, {})
        for (item,count),class_id in zip(result,[0,1,-1,7,7]):
            self.assertEqual(count,1); self.assertEqual(item,{'id':'required_class_'+str(class_id),'class_id':class_id,
                'name':{0:'Object',1:'Manual'}.get(class_id,'Required Class '+str(class_id)),
                'material_type':'object' if class_id==0 else 'text','status':'missing_accessory_metadata',
                'description':'Configured required class has no matching accessory metadata; fail closed.','source_files':[],'normalized_assets':[]})
        self.assertIsNot(result[3][0],result[4][0]); self.assertIsNot(result[3][0]['source_files'],result[4][0]['source_files'])
        self.assertIsNot(result[3][0]['source_files'],result[3][0]['normalized_assets'])
        self.assertEqual(self.api.ai_required_accessories({},{}),[])

    def test_conversion_errors_keep_original_narrow_catch(self):
        for config,spec,error in [({'required_classes':['bad']},{},ValueError),({'min_counts':{'bad':1}},{},ValueError),
            ({'min_counts':{1:None}},{},TypeError),({}, {'is_specialized':True,'required_accessory_counts':{'a':'bad'}},ValueError),
            ({'accessories':[{'class_id':float('inf')}]},{},OverflowError)]:
            with self.subTest(config=config,spec=spec), self.assertRaises(error): self.api.ai_required_accessories(config,spec)
        for value in [None,'bad']:
            result=self.api.ai_required_accessories({'accessories':[{'class_id':value}],'required_classes':[0]}, {})
            self.assertEqual(result[0][0]['status'],'missing_accessory_metadata')

    def test_single_pass_accessories_are_consumed_by_uid_index_before_classes(self):
        item={'id':'a','class_id':0}
        result=self.api.ai_required_accessories({'accessories':iter([item]),'required_classes':[0]}, {})
        self.assertIn('status',result[0][0]); self.assertEqual(result[0][0]['status'],'missing_accessory_metadata'); self.assertIsNot(result[0][0],item)

    def test_class_labels_are_read_only_for_each_missing_ordinary_item(self):
        events=[]; second={7:'next'}
        class Labels(dict):
            def get(inner,key,default=None): events.append(key); self.api.CLASS_LABELS=second; return 'first'
        self.api.CLASS_LABELS=Labels()
        item={'id':'a','class_id':0}; result=self.api.ai_required_accessories({'accessories':[item],'required_classes':[0,7,7]}, {})
        self.assertEqual([value['name'] if 'name' in value else 'present' for value,_ in result],['present','first','next']); self.assertEqual(events,[7])
        class Poison:
            def get(inner,*args): raise AssertionError('unexpected labels read')
        self.api.CLASS_LABELS=Poison()
        self.assertEqual(self.api.ai_required_accessories({'accessories':[item],'required_classes':[0]},{}),[(item,1)])
        self.assertEqual(self.api.ai_required_accessories({}, {'is_specialized':True,'selected_accessory_ids':['missing']})[0][0]['id'],'missing')

    def test_existing_resolver_consumer_keeps_tuple_record_alias_and_trim(self):
        item={'id':' a ','uid':'uid','legacy':'old'}
        result=self.api.resolve_accessory_id({'accessories':[item]},' old ')
        self.assertEqual(result,('uid',item)); self.assertIs(result[1],item)
        self.assertIsNone(self.api.resolve_accessory_id({'accessories':[item]},'missing'))


    def test_independent_compositions_keep_callbacks_labels_and_aliases_separate(self):
        from local_inspection_service.accessories.lookup import AccessoryLookup
        from local_inspection_service.detection.requirements import RequiredAccessories
        def build(owner):
            uid=Mock(side_effect=lambda item:owner+'-'+item['id']); legacy=Mock(side_effect=lambda item:'legacy-'+owner)
            labels=Mock(return_value={9:'Missing '+owner}); lookup=AccessoryLookup(uid,legacy); required=RequiredAccessories(uid,labels)
            for callback in [uid,legacy,labels]: callback.assert_not_called()
            item={'id':'part','class_id':0}; return owner,lookup,required,item,uid,legacy,labels
        instances=[build('alice'),build('bob')]
        with patch.object(self.api,'accessory_uid',side_effect=AssertionError('root UID')), patch.object(self.api,'accessory_legacy_uid',side_effect=AssertionError('root legacy')), patch.object(self.api,'CLASS_LABELS',None):
            for index in [1,0,1,0]:
                owner,lookup,required,item,uid,legacy,labels=instances[index]
                uid.reset_mock(); legacy.reset_mock(); labels.reset_mock()
                aliases=lookup.accessory_id_aliases(item); self.assertEqual(aliases,['part',owner+'-part','legacy-'+owner])
                result=lookup.accessory_lookup_by_id({'accessories':[item]}); self.assertEqual(list(result),aliases); self.assertTrue(all(value is item for value in result.values()))
                self.assertEqual(required.ai_required_accessories({'accessories':[item],'required_classes':[0]},{}),[(item,1)]); labels.assert_not_called()
                spec={'is_specialized':True,'selected_accessory_ids':[owner+'-part'],'required_accessory_counts':{owner+'-part':2}}
                specialized=required.ai_required_accessories({'accessories':[item]},spec); self.assertEqual(specialized,[(item,2)]); labels.assert_not_called()
                missing=required.ai_required_accessories({'required_classes':[9,9]},{}); self.assertEqual(labels.call_count,2)
                self.assertEqual([value['name'] for value,_ in missing],['Missing '+owner]*2); self.assertIsNot(missing[0][0],missing[1][0])
                self.assertEqual(uid.call_args_list,[call(item)]*4); self.assertEqual(legacy.call_args_list,[call(item)]*2)
        failure=Mock(side_effect=OSError('uid policy')); labels=Mock()
        service=RequiredAccessories(failure,labels)
        with self.assertRaisesRegex(OSError,'uid policy'): service.ai_required_accessories({'accessories':[{}]},{})
        failure.assert_called_once_with({}); labels.assert_not_called()


    def test_injected_policy_failures_are_not_retried(self):
        from local_inspection_service.accessories.lookup import AccessoryLookup
        from local_inspection_service.detection.requirements import RequiredAccessories
        for operation in ('aliases','lookup','required_uid','required_labels'):
            for error_type in (OSError,TypeError,ValueError,KeyboardInterrupt):
                with self.subTest(operation=operation,error=error_type):
                    error=error_type('first policy failure'); calls=[]
                    def failing(*args):
                        calls.append(args)
                        if len(calls)==1: raise error
                        return {9:'recovered'} if operation=='required_labels' else 'recovered'
                    uid=Mock(side_effect=failing if operation!='required_labels' else lambda item:'a')
                    legacy=Mock(return_value='old'); labels=Mock(side_effect=failing if operation=='required_labels' else lambda:{9:'Missing'})
                    lookup=AccessoryLookup(uid,legacy); required=RequiredAccessories(uid,labels); item={'id':'a'}
                    with self.assertRaises(BaseException) as caught:
                        if operation=='aliases': lookup.accessory_id_aliases(item)
                        elif operation=='lookup': lookup.accessory_lookup_by_id({'accessories':[item]})
                        elif operation=='required_uid': required.ai_required_accessories({'accessories':[item]}, {})
                        else: required.ai_required_accessories({'required_classes':[9]}, {})
                    self.assertIs(caught.exception,error); self.assertEqual(len(calls),1); legacy.assert_not_called()
                    if operation!='required_labels': labels.assert_not_called()
        for operation in ('aliases','lookup'):
            error=RuntimeError('legacy failure'); calls=[]
            def legacy_once(item):
                calls.append(item)
                if len(calls)==1: raise error
                return 'recovered'
            uid=Mock(return_value='uid'); legacy=Mock(side_effect=legacy_once); lookup=AccessoryLookup(uid,legacy); item={'id':'a'}
            with self.assertRaises(BaseException) as caught:
                if operation=='aliases': lookup.accessory_id_aliases(item)
                else: lookup.accessory_lookup_by_id({'accessories':[item]})
            self.assertIs(caught.exception,error); self.assertEqual(calls,[item]); uid.assert_called_once_with(item)

    def test_root_policy_failures_are_not_retried(self):
        for target in ('accessory_uid','accessory_legacy_uid'):
            for operation in ('aliases','lookup','required'):
                if target=='accessory_legacy_uid' and operation=='required': continue
                error=RuntimeError(target); calls=[]
                def once(item):
                    calls.append(item)
                    if len(calls)==1: raise error
                    return 'recovered'
                item={'id':'a'}
                with patch.object(self.api,target,side_effect=once):
                    with self.assertRaises(BaseException) as caught:
                        if operation=='aliases': self.api.accessory_id_aliases(item)
                        elif operation=='lookup': self.api.accessory_lookup_by_id({'accessories':[item]})
                        else: self.api.ai_required_accessories({'accessories':[item]}, {})
                self.assertIs(caught.exception,error); self.assertEqual(calls,[item])


    def test_mapping_reads_fail_once_without_retry(self):
        cases=[('lookup','config','accessories'),('lookup','item','id'),('aliases','item','id'),
               ('required','config','accessories'),('required','spec','is_specialized'),
               ('required','config','required_classes'),('required','config','min_counts'),
               ('specialized','spec','required_accessory_counts'),('specialized','spec','selected_accessory_ids'),
               ('specialized','spec','accessory_labels'),('required','item','class_id'),('required','labels',9)]
        for operation,target,key in cases:
            with self.subTest(operation=operation,target=target,key=key):
                calls=[]; error=RuntimeError('mapping first failure')
                class Once(dict):
                    def get(inner,name,default=None):
                        if name==key:
                            calls.append(name)
                            if len(calls)==1: raise error
                        return super().get(name,default)
                item={'id':'a','class_id':0}; spec={'is_specialized':operation=='specialized','selected_accessory_ids':['a']}
                if target=='item': item=Once(item)
                config={'accessories':[item],'required_classes':[9],'min_counts':{9:1}}
                if target=='config': config=Once(config)
                if target=='spec': spec=Once(spec)
                self.api.CLASS_LABELS=Once({9:'Missing'}) if target=='labels' else {9:'Missing'}
                with self.assertRaises(BaseException) as caught:
                    if operation=='lookup': self.api.accessory_lookup_by_id(config)
                    elif operation=='aliases': self.api.accessory_id_aliases(item)
                    else: self.api.ai_required_accessories(config,spec)
                self.assertIs(caught.exception,error); self.assertEqual(calls,[key])

    def test_class_id_mapping_type_errors_skip_without_retry(self):
        for error_type in (TypeError,ValueError):
            with self.subTest(error=error_type):
                calls=[]; error=error_type('class id failure')
                class Once(dict):
                    def get(inner,key,default=None):
                        if key=='class_id':
                            calls.append(key)
                            if len(calls)==1: raise error
                        return super().get(key,default)
                item=Once(id='a',class_id=0)
                result=self.api.ai_required_accessories({'accessories':[item],'required_classes':[0]}, {})
                self.assertEqual(calls,['class_id']); self.assertIn('status',result[0][0]); self.assertEqual(result[0][0]['status'],'missing_accessory_metadata'); self.assertIsNot(result[0][0],item)


    def test_policy_rebinding_follows_actual_argument_evaluation(self):
        for site in ('aliases','lookup','aliases_none','lookup_none','required_uid_refresh','labels_get_binding'):
            with self.subTest(site=site):
                _capture_policy_trace(self.api.__dict__,site)


if __name__=='__main__': unittest.main()

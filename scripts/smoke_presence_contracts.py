"""Offline contracts for presence payloads and provider count/coverage validation."""
from contextlib import ExitStack
from decimal import Decimal
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def _capture_name_formatter(ns,missing=False):
    events=[]
    with patch.dict(ns):
        def third(value,limit):events.append(('C',limit));return 'C'+str(limit)
        def second(value,limit):events.append(('B',limit));return 'B'+str(limit)
        def first(value,limit):events.append(('A',limit));return 'A'+str(limit)
        class Identifier:
            def __str__(self):events.append('id');ns['bounded_text']=None if missing else second;return 'id'
        class Required(dict):
            def get(self,key,default=None):
                if key=='name':events.append('name');ns['bounded_text']=third
                return super().get(key,default)
        ns['bounded_text']=first;ns['string_list']=lambda *a,**kw:[]
        item=Required(accessory_id=Identifier(),name='Name',material_type='object');caught=None;result=None
        try:result=ns['ai_detection_task_payload']([item])
        except BaseException as exc:caught=exc
        if missing:
            assert type(caught) is TypeError,(type(caught),events);assert events==[('A',180),'id','name'],events
        else:
            assert caught is None,(caught,events);assert events==[('A',180),'id','name',('B',80),('C',32)],events
            assert result['task']['required_accessories'][0]['name']=='B80',result
    return events


class PresenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='presence-contract-')
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
        self.stack.enter_context(patch.object(self.api,'string_list',self.api.string_list))
        self.stack.enter_context(patch.object(self.api,'bounded_text',self.api.bounded_text))
    def payload(self,items): return self.api.ai_detection_task_payload(items)
    def row(self,items): return self.payload(items)['task']['required_accessories'][0]

    def test_complete_payload_literals_and_actual_text_limits(self):
        item={'accessory_id':'a','name':'N'*90,'expected_count':'3','material_type':'M'*40,'profile':{
            'visual_signature':'V'*200,'distinguishing_text':[' A  A ','a a','B','C','D','E','F','ignored'],
            'tags':['tag1','tag2','tag3','tag4','tag5','tag6']}}
        expected={'task':{'policy':'presence_by_accessory_profile','expected_latency_seconds':5,
            'decision_rule':'passed is true only when every required accessory is present at exactly expected_count; undercounts and overcounts fail.',
            'output_mode':'compact','required_accessories':[{'accessory_id':'a','name':'N'*80,'expected_count':3,'material_type':'M'*32,
                'visual_cue':'V'*180,'text_cues':['A A','B','C','D','E','F'],'tags':['tag1','tag2','tag3','tag4','tag5']}]},
            'output_contract':{'detections':'Array of {accessory_id,label,present,confidence,count,evidence}. Count is optional unless multiple visible instances matter.',
                'rule':'Object with counts keyed by accessory_id.'}}
        self.assertEqual(self.payload([item]),expected); self.assertEqual(len(item['name']),90)
        self.assertEqual(self.payload([]),{**expected,'task':{**expected['task'],'required_accessories':[]}})

    def test_defaults_fallback_text_and_count_conversion_boundaries(self):
        default={'accessory_id':'','name':'','expected_count':1,'material_type':'','visual_cue':'','text_cues':[],'tags':[]}
        self.assertEqual(self.row([{}]),default)
        self.assertEqual(self.row([{'accessory_id':12,'label':' Label ','profile':{'description':' desc  text ','material_type':'text','tags':'One'}}]),
            {**default,'accessory_id':'12','name':'Label','visual_cue':'desc text','material_type':'text','tags':['One']})
        for value,expected in [(None,1),(False,1),(True,1),(-9,1),(0,1),(2.9,2),('3',3),('bad',1),(float('nan'),1),([],1),([1],1)]:
            with self.subTest(value=value): self.assertEqual(self.row([{'expected_count':value}])['expected_count'],expected)
        with self.assertRaises(OverflowError): self.payload([{'expected_count':float('inf')}])
        class Count:
            def __int__(inner): raise OSError('int')
        with self.assertRaisesRegex(OSError,'int'): self.payload([{'expected_count':Count()}])
        first=self.row([{}]); second=self.row([{}]); self.assertIsNot(first['tags'],second['tags']); self.assertIsNot(first['tags'],first['text_cues'])

    def test_profile_double_read_and_non_dict_shape_are_not_normalized(self):
        reads=[]; first={'visual_signature':'first'}; second={'visual_signature':'second'}
        class Required(dict):
            def get(inner,key,default=None):
                reads.append(key)
                if key=='profile': return first if reads.count('profile')==1 else second
                return super().get(key,default)
        self.assertEqual(self.row([Required()])['visual_cue'],'second'); self.assertEqual(reads.count('profile'),2)
        reads.clear(); second=None
        strings=Mock(); self.api.string_list=strings
        with self.assertRaises(AttributeError): self.payload([Required()])
        strings.assert_not_called(); self.assertEqual(reads,['expected_count','profile','profile'])
        reads.clear(); first=[]; second={'unused':True}; strings.side_effect=lambda *args,**kwargs:[]; self.row([Required()])
        self.assertEqual(reads.count('profile'),1)

    def test_string_callee_capture_before_profile_arguments_and_next_call_rebinding(self):
        for stage in ['distinguishing_text','tags']:
            with self.subTest(stage=stage):
                events=[]; first=Mock(side_effect=lambda value,**kw:events.append(('first',value,kw)) or ['first'])
                later=Mock(side_effect=lambda value,**kw:events.append(('later',value,kw)) or ['later']); self.api.string_list=first
                class Profile(dict):
                    def get(inner,key,default=None):
                        if key==stage: self.api.string_list=later
                        return super().get(key,default)
                profile=Profile(distinguishing_text='cues',tags='tags'); result=self.row([{'profile':profile}])
                self.assertEqual(result['text_cues'],['first']); self.assertEqual(result['tags'],['later'] if stage=='distinguishing_text' else ['first'])
                self.assertEqual(events,[('first','cues',{'max_items':6,'max_len':64}),('later' if stage=='distinguishing_text' else 'first','tags',{'max_items':5,'max_len':40})])
                first.reset_mock(); later.reset_mock(); self.row([{'profile':profile}]); first.assert_not_called(); self.assertEqual(later.call_count,2)

    def test_text_callee_capture_before_each_argument_and_after_previous_callbacks(self):
        for stage in ['visual_signature','name','material_type']:
            with self.subTest(stage=stage):
                first=Mock(side_effect=lambda value,limit:'first-'+str(limit)); later=Mock(side_effect=lambda value,limit:'later-'+str(limit))
                self.api.bounded_text=first; self.api.string_list=Mock(return_value=[])
                class Values(dict):
                    def get(inner,key,default=None):
                        if key==stage: self.api.bounded_text=later
                        return super().get(key,default)
                profile=Values(visual_signature='visual'); required=Values(name='name',material_type='material',profile=profile)
                row=self.row([required]); pivot={'visual_signature':0,'name':1,'material_type':2}[stage]
                self.assertEqual([row['visual_cue'],row['name'],row['material_type']],
                    [('first-' if index<=pivot else 'later-')+str(limit) for index,limit in enumerate([180,80,32])])
                self.assertEqual(first.call_args_list,[call(value,limit) for value,limit in [('visual',180),('name',80),('material',32)][:pivot+1]])
                first.reset_mock(); later.reset_mock(); self.row([required]); first.assert_not_called(); self.assertEqual(later.call_count,3)
        # A preceding string callback replacement must affect the following text expression.
        original=Mock(); selected=Mock(return_value='selected'); self.api.bounded_text=original
        self.api.string_list=Mock(side_effect=lambda *args,**kwargs:setattr(self.api,'bounded_text',selected) or [])
        row=self.row([{}]); original.assert_not_called(); self.assertEqual(selected.call_count,3); self.assertEqual(row['visual_cue'],'selected')

    def test_captured_none_or_error_still_reads_arguments_once_without_retry(self):
        order=['distinguishing_text','tags','visual_signature','name','material_type']
        for position,target in enumerate(order):
            for outcome in ['none','write']:
                with self.subTest(target=target,outcome=outcome):
                    reads=[]; calls=[]; error=OSError('captured'); attribute='string_list' if position<2 else 'bounded_text'
                    later=Mock(return_value=[] if position<2 else 'later')
                    first=None if outcome=='none' else Mock(side_effect=[error,[] if position<2 else 'second'])
                    def complete(stage):
                        calls.append(stage)
                        if order.index(stage)==position-1: setattr(self.api,attribute,first)
                    def strings(value,**kwargs): complete('distinguishing_text' if kwargs['max_items']==6 else 'tags'); return []
                    def text(value,limit): complete({180:'visual_signature',80:'name',32:'material_type'}[limit]); return 'text'
                    self.api.string_list=strings; self.api.bounded_text=text
                    if position==0: self.api.string_list=first
                    class Values(dict):
                        def get(inner,key,default=None):
                            reads.append(key)
                            if key==target: setattr(self.api,attribute,later)
                            return super().get(key,default)
                    profile=Values(distinguishing_text='cues',tags='tags',visual_signature='visual')
                    item=Values(profile=profile,accessory_id='id',name='name',material_type='material')
                    with self.assertRaises(TypeError if outcome=='none' else OSError) as caught: self.payload([item])
                    if outcome=='write':
                        self.assertIs(caught.exception,error)
                        expected=[call('cues',max_items=6,max_len=64),call('tags',max_items=5,max_len=40),call('visual',180),call('name',80),call('material',32)][position]
                        self.assertEqual(first.call_args_list,[expected])
                    later.assert_not_called(); self.assertEqual(calls,order[:position])
                    expected_reads=['expected_count','profile','profile','distinguishing_text','tags','visual_signature','accessory_id','name','material_type']
                    self.assertEqual(reads,expected_reads[:expected_reads.index(target)+1])

    def test_first_string_capture_follows_second_profile_read_and_precedes_cues_read(self):
        first=Mock(return_value=['first']); second=Mock(return_value=['second']); third=Mock(return_value=['third']); reads=[]
        self.api.string_list=first
        class Profile(dict):
            def get(inner,key,default=None):
                if key=='distinguishing_text': self.api.string_list=third
                return super().get(key,default)
        profile=Profile(distinguishing_text='cues',tags='tags')
        class Required(dict):
            def get(inner,key,default=None):
                if key=='profile':
                    reads.append('profile')
                    if len(reads)==2: self.api.string_list=second
                    return profile
                return super().get(key,default)
        row=self.row([Required()]); self.assertEqual(row['text_cues'],['second']); self.assertEqual(row['tags'],['third'])
        self.assertEqual(reads,['profile','profile']); first.assert_not_called()
        second.assert_called_once_with('cues',max_items=6,max_len=64); third.assert_called_once_with('tags',max_items=5,max_len=40)

    def test_profile_argument_error_prevents_captured_call_and_further_items(self):
        strings=Mock(return_value=[]); text=Mock(return_value='text'); self.api.string_list=strings; self.api.bounded_text=text
        error=OSError('argument'); reads=[]
        class Profile(dict):
            def get(inner,key,default=None):
                reads.append(key)
                if len(reads)==1: raise error
                return super().get(key,default)
        with self.assertRaises(OSError) as caught: self.payload([{'profile':Profile()},{'expected_count':float('inf')}])
        self.assertIs(caught.exception,error); self.assertEqual(reads,['distinguishing_text']); strings.assert_not_called(); text.assert_not_called()

    def test_coverage_any_intersection_from_detections_or_counts_and_shape_limits(self):
        covers=self.api.ai_detection_parsed_covers_required
        for parsed,expected in [(None,False),([],False),({},False),({'detections':[{'accessory_id':'a'}]},True),
            ({'rule':{'counts':{'a':0}}},True),({'detections':[None,1,{'accessory_id':None},{'accessory_id':'other'}]},False),
            ({'detections':({'accessory_id':'a'},)},False),({'rule':{'counts':[('a',1)]}},False),
            ({'detections':[{'accessory_id':0}]},True)]:
            with self.subTest(parsed=parsed): self.assertEqual(covers(parsed,{'a','0','missing'}),expected)
        class Poison(dict):
            def get(inner,*args): raise AssertionError('read parsed')
        self.assertTrue(covers(Poison(),set()))
        for parsed in [None, [], object(), 42, False]:
            with self.subTest(empty_required_parsed=parsed): self.assertTrue(covers(parsed,set()))
        self.assertFalse(covers({'detections':[{'accessory_id':' a '}]},{'a'}))

    def test_coverage_repeated_reads_preserve_order_and_changed_values(self):
        events=[]
        class Entry(dict):
            def get(inner,key,default=None): events.append('id'); return 'ignored' if events.count('id')==1 else 'a'
        class Counts(dict):
            def keys(inner): events.append('keys'); return super().keys()
        class Rule(dict):
            def get(inner,key,default=None): events.append('counts'); return Counts(other=1)
        class Parsed(dict):
            def get(inner,key,default=None):
                events.append(key)
                return [Entry()] if key=='detections' else Rule()
        self.assertTrue(self.api.ai_detection_parsed_covers_required(Parsed(),{'a'}))
        self.assertEqual(events,['detections','detections','id','id','rule','rule','counts','counts','keys'])
        class Changed(dict):
            def get(inner,key,default=None):
                events.append(key)
                if key=='detections': return [] if events.count(key)==1 else None
                return None
        events.clear()
        with self.assertRaises(TypeError): self.api.ai_detection_parsed_covers_required(Changed(),{'a'})
        self.assertEqual(events,['detections','detections'])

    def test_coverage_conversion_errors_propagate_without_retry(self):
        calls=[]; error=OSError('id conversion')
        class Identifier:
            def __str__(inner):
                calls.append('str')
                if len(calls)==1: raise error
                return 'a'
        with self.assertRaises(OSError) as caught: self.api.ai_detection_parsed_covers_required({'detections':[{'accessory_id':Identifier()}]}, {'a'})
        self.assertIs(caught.exception,error); self.assertEqual(calls,['str'])

    def test_counts_reject_ambiguous_types_and_keep_integer_identity(self):
        count=self.api.coerce_detection_count
        for value,expected in [(True,None),(False,None),(None,None),('2',None),(Decimal('2'),None),(-1,None),(0,0),(2,2),(2.0,2),(-0.0,0),(2.1,None),(-1.0,None),(float('nan'),None),(float('inf'),None),(float('-inf'),None)]:
            with self.subTest(value=value): self.assertEqual(count(value),expected)
        class Integer(int): pass
        value=Integer(2); self.assertIs(count(value),value)
        class Convertible:
            def __int__(inner): raise AssertionError('unexpected coercion')
        self.assertIsNone(count(Convertible()))

    def test_count_float_checks_short_circuit_and_preserve_exception_order(self):
        events=[]
        class Float(float):
            def is_integer(inner): events.append('integer'); return False
            def __ge__(inner,value): events.append('compare'); raise AssertionError('must short circuit')
        self.assertIsNone(self.api.coerce_detection_count(Float(2))); self.assertEqual(events,['integer'])
        class Broken(float):
            def is_integer(inner): events.append('integer'); raise OSError('integer check')
        events.clear()
        with self.assertRaisesRegex(OSError,'integer check'): self.api.coerce_detection_count(Broken(2))
        self.assertEqual(events,['integer'])


    def test_independent_payload_compositions_preserve_formatters_and_list_aliases(self):
        from local_inspection_service.detection.presence_payload import PresencePayload
        def build(owner):
            lists=[[owner+' cue'],[owner+' tag']]
            strings=Mock(side_effect=lambda value,**kw:lists[0] if kw['max_items']==6 else lists[1])
            text=Mock(side_effect=lambda value,limit:owner+':'+str(limit))
            strings_provider=Mock(return_value=strings); text_provider=Mock(return_value=text)
            service=PresencePayload(strings_provider,text_provider)
            for callback in [strings,text,strings_provider,text_provider]: callback.assert_not_called()
            return owner,service,lists,strings,text,strings_provider,text_provider
        instances=[build('alice'),build('bob')]
        with patch.object(self.api,'string_list',side_effect=AssertionError('root strings')), patch.object(self.api,'bounded_text',side_effect=AssertionError('root text')):
            for index in [1,0,1,0]:
                owner,service,lists,strings,text,strings_provider,text_provider=instances[index]
                for callback in [strings,text,strings_provider,text_provider]: callback.reset_mock()
                item={'accessory_id':'id','name':'name','material_type':'object','profile':{'visual_signature':'visual','distinguishing_text':'cues','tags':'tags'}}
                row=service.ai_detection_task_payload([item])['task']['required_accessories'][0]
                self.assertEqual(row,{'accessory_id':'id','name':owner+':80','expected_count':1,'material_type':owner+':32','visual_cue':owner+':180','text_cues':lists[0],'tags':lists[1]})
                self.assertIs(row['text_cues'],lists[0]); self.assertIs(row['tags'],lists[1])
                self.assertEqual(strings.call_args_list,[call('cues',max_items=6,max_len=64),call('tags',max_items=5,max_len=40)])
                self.assertEqual(text.call_args_list,[call('visual',180),call('name',80),call('object',32)])
                self.assertEqual(strings_provider.call_args_list,[call(),call()]); self.assertEqual(text_provider.call_args_list,[call(),call(),call()])

    def test_independent_payload_provider_failure_precedes_argument_reads(self):
        from local_inspection_service.detection.presence_payload import PresencePayload
        for stage in ['strings','text']:
            with self.subTest(stage=stage):
                events=[]; error=OSError('provider')
                class Profile(dict):
                    def get(inner,key,default=None): events.append(key); return key
                strings=Mock(return_value=[]); text=Mock(return_value='text')
                string_provider=Mock(side_effect=error if stage=='strings' else lambda:strings)
                text_provider=Mock(side_effect=error if stage=='text' else lambda:text)
                service=PresencePayload(string_provider,text_provider); string_provider.assert_not_called(); text_provider.assert_not_called()
                with self.assertRaises(OSError) as caught: service.ai_detection_task_payload([{'profile':Profile()}])
                self.assertIs(caught.exception,error); self.assertEqual(events,[] if stage=='strings' else ['distinguishing_text','tags'])
                self.assertEqual(string_provider.call_count,1 if stage=='strings' else 2); self.assertEqual(text_provider.call_count,int(stage=='text'))
                self.assertEqual(strings.call_count,0 if stage=='strings' else 2); text.assert_not_called()


    def test_payload_mapping_reads_fail_once_without_retry(self):
        sites=[('required','expected_count',1),('required','profile',1),('required','profile',2),
               ('profile','distinguishing_text',1),('profile','tags',1),('profile','visual_signature',1),
               ('profile','description',1),('required','accessory_id',1),('required','name',1),
               ('required','label',1),('required','accessory_id',2),('required','material_type',1),
               ('profile','material_type',1)]
        for owner,target,index in sites:
            with self.subTest(owner=owner,target=target,index=index):
                reads=[]; error=RuntimeError('first mapping failure')
                class Values(dict):
                    def get(inner,key,default=None):
                        if key==target:
                            reads.append(key)
                            if len(reads)==index: raise error
                        return super().get(key,default)
                profile={'description':'description','material_type':'object'}
                if owner=='profile': profile=Values(profile)
                item={'expected_count':4,'accessory_id':'id','profile':profile}
                if owner=='required': item=Values(item)
                with self.assertRaises(BaseException) as caught: self.payload([item])
                self.assertIs(caught.exception,error); self.assertEqual(reads,[target]*index)

    def test_expected_count_mapping_type_errors_fallback_without_retry(self):
        for error_type in (TypeError,ValueError):
            reads=[]; error=error_type('count lookup')
            class Values(dict):
                def get(inner,key,default=None):
                    if key=='expected_count':
                        reads.append(key)
                        if len(reads)==1: raise error
                    return super().get(key,default)
            row=self.row([Values(expected_count=4)])
            self.assertEqual(row['expected_count'],1); self.assertEqual(reads,['expected_count'])

    def test_each_payload_provider_first_failure_precedes_arguments(self):
        from local_inspection_service.detection.presence_payload import PresencePayload
        for stage in range(5):
            with self.subTest(stage=stage):
                reads=[]; calls=[]; error=RuntimeError('provider first failure')
                strings=Mock(return_value=[]); text=Mock(return_value='text')
                def provider(callback):
                    calls.append(callback)
                    if len(calls)==stage+1: raise error
                    return callback
                class Values(dict):
                    def get(inner,key,default=None): reads.append(key); return super().get(key,default)
                profile=Values(distinguishing_text='cues',tags='tags',visual_signature='visual')
                item=Values(profile=profile,accessory_id='id',name='name',material_type='object')
                service=PresencePayload(lambda:provider(strings),lambda:provider(text))
                with self.assertRaises(BaseException) as caught: service.ai_detection_task_payload([item])
                self.assertIs(caught.exception,error); self.assertEqual(len(calls),stage+1)
                all_reads=['expected_count','profile','profile','distinguishing_text','tags','visual_signature','accessory_id','name','material_type']
                cutoff=[3,4,5,7,8][stage]; self.assertEqual(reads,all_reads[:cutoff])
                self.assertEqual(strings.call_count,min(stage,2)); self.assertEqual(text.call_count,max(0,stage-2))


    def test_name_formatter_is_selected_after_identifier_conversion(self):
        for missing in (False,True):
            with self.subTest(missing=missing):
                _capture_name_formatter(self.api.__dict__,missing)


    def test_payload_formatters_refresh_for_each_required_item(self):
        events=[]
        def next_strings(value,**kwargs): events.append(('B-list',kwargs['max_items'])); return ['B']
        def next_text(value,limit): events.append(('B-text',limit)); return 'B'
        def first_strings(value,**kwargs): events.append(('A-list',kwargs['max_items'])); return ['A']
        def first_text(value,limit):
            events.append(('A-text',limit))
            if limit==32:
                self.api.string_list=next_strings; self.api.bounded_text=next_text
            return 'A'
        self.api.string_list=first_strings; self.api.bounded_text=first_text
        rows=self.payload([{'accessory_id':'first'},{'accessory_id':'second'}])['task']['required_accessories']
        self.assertEqual(events,[(owner+'-'+kind,value) for owner in ('A','B') for kind,value in [('list',6),('list',5),('text',180),('text',80),('text',32)]])
        self.assertEqual([(row['text_cues'],row['tags'],row['visual_cue'],row['name'],row['material_type']) for row in rows],[(['A'],['A'],'A','A','A'),(['B'],['B'],'B','B','B')])


if __name__=='__main__': unittest.main()

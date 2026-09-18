"""Offline contracts for presence result normalization; no models or device access."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _capture_result_policy_refresh(ns):
    events = []
    with patch.dict(ns):

        def counter(mark):

            def count(value):
                events.append((mark, 'count', value))
                return 1
            return count

        def formatter(mark):

            def text(value, limit):
                events.append((mark, 'text', value, limit))
                return '' if value is None else mark + str(limit)
            return text

        def strings(mark):

            def parse(value, **kwargs):
                events.append((mark, 'strings', value, kwargs))
                if mark == 'A' and 'max_len' in kwargs:
                    ns['coerce_detection_count'] = counter('B')
                    ns['bounded_text'] = formatter('B')
                    ns['string_list'] = strings('B')
                return [mark]
            return parse
        ns['coerce_detection_count'] = counter('A')
        ns['bounded_text'] = formatter('A')
        ns['string_list'] = strings('A')
        ns['ai_tool_provider_meta'] = lambda s: {}
        ns['AI_DETECTION_LABEL'] = 'label'
        parsed = {'detections': [{'accessory_id': 'a', 'present': True, 'count': 1, 'evidence': 'E', 'observed_text': []}, {'accessory_id': 'b', 'present': True, 'count': 1, 'evidence': 'E', 'observed_text': []}], 'rule': {'counts': {'a': 1, 'b': 1}}, 'raw_summary': 'S'}
        result = None
        caught = None
        try:
            result = ns['normalize_ai_detection_result'](parsed, [{'accessory_id': 'a', 'name': 'Name'}, {'accessory_id': 'b', 'name': 'Name'}], 0, {})
        except BaseException as exc:
            caught = exc
        assert caught is None, (caught, events)
        expected = []
        for mark in ('A', 'B'):
            expected.extend([(mark, 'count', 1), (mark, 'count', 1), (mark, 'text', None, 120), (mark, 'text', 'Name', 120), (mark, 'text', 'E', 180), (mark, 'strings', [], {'max_items': 6, 'max_len': 80})])
        expected.extend([('B', 'strings', [], {'max_items': 12}), ('B', 'text', 'S', 240)])
        assert events == expected, (events, expected)
        assert result['detections'][1]['label'] == 'B120' and result['detections'][1]['evidence'] == 'B180' and (result['detections'][1]['observed_text'] == ['B']), result
    return events


class PresenceResultContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='presence-results-')
        root = Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))
        for name in ['bounded_text', 'string_list', 'coerce_detection_count']:
            self.stack.enter_context(patch.object(self.api, name, getattr(self.api, name)))
        self.stack.enter_context(patch.object(self.api, 'AI_DETECTION_LABEL', 'Inspection'))
        self.meta = self.stack.enter_context(patch.object(self.api, 'ai_tool_provider_meta', return_value={'provider': 'fixture'}))
        self.settings = {'status': 'ready', 'api_key': 'synthetic-secret'}

    def normalize(self, parsed, required):
        return self.api.normalize_ai_detection_result(parsed, required, 23, self.settings)

    def test_complete_response_preserves_counts_extra_text_and_fields(self):
        parsed = {'detections': [
            {'accessory_id':'a','present':True,'confidence':1.7,'count':2,'label':'  A  ','evidence':' okay ','observed_text':[' One ','one','Two']},
            {'accessory_id':'b','present':True,'confidence':0.123456,'count':3},
            {'accessory_id':'c','present':'true','confidence':1,'count':4}],
            'rule':{'counts':{'a':2},'extra':['a','outside','OUTSIDE','b']},'summary':'  summary  '}
        result = self.normalize(parsed, [{'accessory_id':'a','expected_count':2}, {'accessory_id':'b','name':'B'}, {'accessory_id':'c','name':'C'}, {'accessory_id':'d','name':'D'}])
        self.assertEqual(result, {'tool':'vision.inspect.presence','passed':False,
            'rule':{'match_policy':'ai_presence','label':'Inspection','present':['a'],'missing':['b','c','d'],'extra':['outside','b'],
                    'counts':{'a':2,'b':3,'c':0,'d':0}, 'count_mismatches':{
                        'b':{'expected':1,'found':3,'issue':'over_count'},'c':{'expected':1,'found':0,'issue':'under_count'},'d':{'expected':1,'found':0,'issue':'under_count'}}},
            'detections':[
                {'accessory_id':'a','label':'A','present':True,'confidence':1.0,'evidence':'okay','observed_text':['One','Two'],'count':2},
                {'accessory_id':'b','label':'B','present':False,'confidence':0.1235,'evidence':'','observed_text':[],'count':3},
                {'accessory_id':'c','label':'C','present':False,'confidence':1.0,'evidence':'','observed_text':[],'count':0},
                {'accessory_id':'d','label':'D','present':False,'confidence':0.0,'evidence':'','observed_text':[]}],
            'ai':{'latency_ms':23,'timed_out':False,'provider_failure':False,'raw_summary':'summary','provider_status':'ready','provider':'fixture'}})
        self.meta.assert_called_once_with(self.settings)
        self.assertNotIn('synthetic-secret', str(result))
        self.assertIsNot(result['detections'][1]['observed_text'], result['detections'][2]['observed_text'])
        self.assertEqual(parsed['detections'][0]['label'], '  A  ')

    def test_rule_count_precedence_and_explicit_count_field(self):
        absent = object()
        for rule_count, detection_count, expected, found, passed, emits_count in [
            (absent,absent,1,1,True,False),(absent,absent,2,1,False,True),
            (absent,2,2,2,True,True),(3,2,2,3,False,True),
            (None,2,2,0,False,True),(True,2,1,0,False,True),
            ('2',2,2,0,False,True),(-1,2,1,0,False,True),(1.5,2,1,0,False,True),
            (float('nan'),2,1,0,False,True),(2.0,0,2,2,True,True),
            (absent,'2',1,1,True,True),(absent,0,1,0,False,True),(absent,-1,1,1,True,True)]:
            with self.subTest(rule=rule_count, detection=detection_count, expected=expected):
                row={'accessory_id':'a','present':True}
                if detection_count is not absent: row['count']=detection_count
                counts={} if rule_count is absent else {'a':rule_count}
                result=self.normalize({'detections':[row],'rule':{'counts':counts}},[{'accessory_id':'a','expected_count':expected}])
                self.assertEqual(result['passed'],passed); self.assertEqual(result['rule']['counts'],{'a':found})
                self.assertEqual('count' in result['detections'][0],emits_count)
                if emits_count: self.assertEqual(result['detections'][0]['count'],found)
                self.assertEqual(result['rule']['extra'],['a'] if found>expected else [])

    def test_confidence_validation_and_strict_present_keep_original_boundaries(self):
        absent=object()
        for value, expected in [(absent,0.5),(True,0.0),(False,0.0),(None,0.0),('bad',0.0),('0.25',0.25),
                                (float('inf'),0.0),(float('-inf'),0.0),(float('nan'),0.0),(-1,0.0),(2,1.0),(0.00001,0.0)]:
            with self.subTest(confidence=value):
                row={'accessory_id':'a','present':True,'count':4}
                if value is not absent: row['confidence']=value
                result=self.normalize({'detections':[row]},[{'accessory_id':'a','expected_count':4}])
                present=value==0.00001 or expected>0
                self.assertEqual(result['detections'][0]['confidence'],expected)
                self.assertEqual(result['passed'],present)
                self.assertEqual(result['rule']['counts'],{'a':4 if present else 0})
        for present in ['true',1,[],None,False]:
            result=self.normalize({'detections':[{'accessory_id':'a','present':present,'confidence':1,'count':2}]},[{'accessory_id':'a'}])
            self.assertFalse(result['passed']); self.assertEqual(result['rule']['counts'],{'a':0})
        class Overflow:
            def __float__(self): raise OverflowError('confidence overflow')
        with self.assertRaisesRegex(OverflowError,'confidence overflow'):
            self.normalize({'detections':[{'accessory_id':'a','present':True,'confidence':Overflow()}]},[{'accessory_id':'a'}])
        with self.assertRaises(OverflowError): self.normalize({},[{'accessory_id':'a','expected_count':float('inf')}])
        for expected in ['bad',None,0,-2]:
            result=self.normalize({'detections':[{'accessory_id':'a','present':True}]},[{'accessory_id':'a','expected_count':expected}])
            self.assertTrue(result['passed'])

    def test_duplicate_ids_last_provider_and_cumulative_presence_are_preserved(self):
        result=self.normalize({'detections':[None,{'accessory_id':None},{'accessory_id':'a','present':False},
            {'accessory_id':'a','present':True,'count':1}]},
            [{'accessory_id':'a','expected_count':1},{'accessory_id':'a','expected_count':2},{'accessory_id':0},{'accessory_id':''}])
        self.assertEqual(result['rule'],{'match_policy':'ai_presence','label':'Inspection','present':['a'],'missing':['a'],
            'extra':[],'counts':{'a':1},'count_mismatches':{'a':{'expected':2,'found':1,'issue':'under_count'}}})
        self.assertEqual([row['present'] for row in result['detections']],[True,True]); self.assertFalse(result['passed'])
        for required in [[{'accessory_id':' a '}], iter([{'accessory_id':' a '}])]:
            result=self.normalize({'rule':{'extra':[' a ','a']}},required)
            # The iterator has no remaining IDs during the second traversal; string_list then trims/deduplicates.
            self.assertEqual(result['rule']['extra'],['a'])
            self.assertEqual(result['rule']['missing'],[' a '])
        result=self.normalize({'rule':{'extra':['a']}},iter([{'accessory_id':'a'}]))
        self.assertEqual(result['rule']['extra'],['a'])
        self.assertEqual(self.normalize({'rule':{'extra':['a']}},[{'accessory_id':'a'}])['rule']['extra'],[])

    def test_repeated_shape_reads_and_eager_present_default(self):
        events=[]
        class Row(dict):
            def get(inner,key,default=None): events.append(key); return super().get(key,default)
        row=Row(accessory_id='a',present=True,confidence=0.8,label='A')
        result=self.normalize({'detections':[row]},[{'accessory_id':'a'}])
        self.assertTrue(result['passed'])
        self.assertEqual(events,['accessory_id','accessory_id','present','confidence','present','count','label','evidence','observed_text'])
        class Changing(dict):
            def __init__(inner,key,first,second): inner.key=key; inner.values=iter([first,second]); inner.calls=[]
            def get(inner,key,default=None):
                inner.calls.append(key)
                return next(inner.values) if key==inner.key else default
        for parsed in [Changing('detections',[],None), {'detections':[], 'rule':Changing('counts',{},None)}]:
            with self.assertRaises(TypeError): self.normalize(parsed,[{'accessory_id':'a'}])
        changed=Changing('rule',{},None)
        with self.assertRaises(AttributeError): self.normalize(changed,[])
        for parsed in [{'detections':{},'rule':[]},{'detections':None,'rule':{'counts':[],'extra':{}}}]:
            result=self.normalize(parsed,[]); self.assertTrue(result['passed']); self.assertEqual(result['detections'],[])

    def test_exact_formatter_arguments_metadata_order_and_result_aliases(self):
        observed=['observed']; extra=['extra']; events=[]
        strings=Mock()
        lists=iter([observed,extra])
        strings.side_effect=lambda value,**kwargs:events.append(('strings',value,kwargs)) or next(lists)
        text=Mock(side_effect=lambda value,limit:events.append(('text',value,limit)) or ('' if value is None else str(value)))
        self.api.string_list=strings; self.api.bounded_text=text
        marker={'kept':True}
        def metadata(settings):
            events.append(('meta',settings)); self.api.AI_DETECTION_LABEL='Changed'
            return {'raw_summary':marker,'provider_status':'override','provider_failure':marker,1:'nonstring'}
        self.meta.side_effect=metadata
        parsed={'detections':[{'accessory_id':'a','present':True,'evidence':'Evidence','observed_text':['T']}],
                'rule':{'extra':['a','other']},'raw_summary':'Summary'}
        result=self.normalize(parsed,[{'accessory_id':'a','name':'Name'}])
        self.assertEqual(text.call_args_list,[call(None,120),call('Name',120),call('Evidence',180),call('Summary',240)])
        self.assertEqual(strings.call_args_list,[call(['T'],max_items=6,max_len=80),call(['other'],max_items=12)])
        self.assertEqual([event[0] for event in events],['text','text','text','strings','strings','meta','text'])
        self.assertEqual(result['rule']['label'],'Changed'); self.assertIs(result['rule']['extra'],extra)
        self.assertIs(result['detections'][0]['observed_text'],observed); self.assertIs(result['ai']['raw_summary'],marker)
        self.assertIs(result['ai']['provider_failure'],marker); self.assertEqual(result['ai'][1],'nonstring')
        self.assertEqual(result['ai']['provider_status'],'override')

    def test_per_expression_capture_and_next_expression_rebinding(self):
        for stage in ['rule_count','detection_count','label','fallback','evidence','observed','summary']:
            with self.subTest(stage=stage):
                events=[]
                name='coerce_detection_count' if stage.endswith('count') else 'string_list' if stage=='observed' else 'bounded_text'
                initial=getattr(self.api,name)
                def old(*args,**kwargs): events.append(('old',args,kwargs)); return initial(*args,**kwargs)
                def new(*args,**kwargs): events.append(('new',args,kwargs)); return initial(*args,**kwargs)
                with patch.object(self.api,name,old):
                    class Changing(dict):
                        def __init__(inner,target,*args,**kwargs): super().__init__(*args,**kwargs); inner.target=target
                        def get(inner,key,default=None):
                            if key==inner.target: setattr(self.api,name,new)
                            return super().get(key,default)
                    row=Changing({'detection_count':'count','label':'label','evidence':'evidence','observed':'observed_text'}.get(stage,'unused'),
                                 accessory_id='a',present=True,evidence='E',observed_text=[])
                    required=Changing('name' if stage=='fallback' else 'unused',accessory_id='a',name='Name')
                    counts=Changing('a' if stage=='rule_count' else 'unused',a=1)
                    parsed=Changing('raw_summary' if stage=='summary' else 'unused',detections=[row],rule={'counts':counts},raw_summary='Summary')
                    self.normalize(parsed,[required])
                indexes={'rule_count':0,'detection_count':1,'label':0,'fallback':1,'evidence':2,'observed':0,'summary':3}
                captured=indexes[stage]
                self.assertEqual([e[0] for e in events],['old']*(captured+1)+['new']*(len(events)-captured-1))
                self.assertGreaterEqual(len(events),captured+1)

    def test_dependencies_fail_once_and_stop_later_reads(self):
        for name,total in [('coerce_detection_count',2),('bounded_text',4),('string_list',2),('ai_tool_provider_meta',1)]:
            for position in range(total):
                with self.subTest(dependency=name,position=position):
                    events=[]; error=OSError('first call fails'); original=getattr(self.api,name); calls=0
                    def dependency(*args,**kwargs):
                        nonlocal calls
                        calls+=1; events.append('call')
                        if calls==position+1: raise error
                        return original(*args,**kwargs)
                    class Settings(dict):
                        def get(inner,key,default=None): events.append('status'); return super().get(key,default)
                    previous=self.settings; self.settings=Settings(previous)
                    try:
                        with patch.object(self.api,name,dependency):
                            with self.assertRaises(OSError) as caught:
                                self.normalize({'detections':[{'accessory_id':'a','present':True}], 'rule':{'counts':{'a':1}}},[{'accessory_id':'a','name':'Name'}])
                        self.assertIs(caught.exception,error); self.assertEqual(calls,position+1)
                        self.assertEqual(events,['call']*(position+1))
                    finally: self.settings=previous


    def test_invalid_rule_count_still_evaluates_detection_count_and_can_fail(self):
        error=OSError('detection count'); parser=Mock(side_effect=[None,error,1])
        self.api.coerce_detection_count=parser
        with self.assertRaises(OSError) as caught:
            self.normalize({'detections':[{'accessory_id':'a','present':True,'count':9}],
                            'rule':{'counts':{'a':'invalid'}}},[{'accessory_id':'a'}])
        self.assertIs(caught.exception,error)
        self.assertEqual(parser.call_args_list,[call('invalid'),call(9)])
        self.meta.assert_not_called()

    def test_shape_and_id_second_reads_and_extra_capture_follow_comprehension(self):
        events=[]; initial=self.api.string_list
        def old(value,**kwargs): events.append('old'); return initial(value,**kwargs)
        def new(value,**kwargs): events.append('new'); return initial(value,**kwargs)
        self.api.string_list=old
        class Item:
            def __str__(inner): events.append('extra-str'); self.api.string_list=new; return 'outside'
        class Rule(dict):
            def get(inner,key,default=None):
                if key=='extra': events.append('extra-get')
                return super().get(key,default)
        result=self.normalize({'rule':Rule(extra=[Item()])},[])
        self.assertEqual(events,['extra-get','extra-get','extra-str','new','extra-str'])
        self.assertEqual(result['rule']['extra'],['outside'])
        class ChangedID(dict):
            def __init__(inner): super().__init__(present=True); inner.ids=iter(['checked','actual'])
            def get(inner,key,default=None): return next(inner.ids) if key=='accessory_id' else super().get(key,default)
        self.assertTrue(self.normalize({'detections':[ChangedID()]},[{'accessory_id':'actual'}])['passed'])
        class ChangedExtra(dict):
            def __init__(inner): inner.extras=iter([[],None])
            def get(inner,key,default=None): return next(inner.extras) if key=='extra' else default
        with self.assertRaises(TypeError): self.normalize({'rule':ChangedExtra()},[])

    def test_noncallable_formatter_keeps_argument_reads_and_stops(self):
        for stage in ['label','fallback','evidence','observed','extra','summary']:
            with self.subTest(stage=stage):
                events=[]; real_text=self.api.bounded_text; real_strings=self.api.string_list
                def text(value,limit):
                    events.append(('text',value,limit))
                    if stage=='fallback' and limit==120 and value is None: self.api.bounded_text=None
                    if stage=='evidence' and limit==120: self.api.bounded_text=None
                    if stage=='observed' and limit==180: self.api.string_list=None
                    return real_text(value,limit)
                class Row(dict):
                    def get(inner,key,default=None):
                        events.append(('row',key))
                        if stage=='label' and key=='count': self.api.bounded_text=None
                        if stage=='label' and key=='label' or stage=='evidence' and key=='evidence': self.api.bounded_text=text
                        if stage=='observed' and key=='observed_text': self.api.string_list=real_strings
                        return super().get(key,default)
                class Required(dict):
                    def get(inner,key,default=None):
                        events.append(('required',key))
                        if stage=='fallback' and key=='name': self.api.bounded_text=text
                        return super().get(key,default)
                class Rule(dict):
                    def get(inner,key,default=None):
                        events.append(('rule',key))
                        if stage=='extra' and key=='extra': self.api.string_list=None
                        return super().get(key,default)
                class Parsed(dict):
                    def get(inner,key,default=None):
                        events.append(('parsed',key))
                        if stage=='summary' and key=='raw_summary': self.api.bounded_text=text
                        return super().get(key,default)
                def meta(settings):
                    events.append(('meta',))
                    if stage=='summary': self.api.bounded_text=None
                    return {}
                self.meta.reset_mock(); self.meta.side_effect=meta
                with patch.object(self.api,'bounded_text',text), patch.object(self.api,'string_list',real_strings):
                    with self.assertRaises(TypeError):
                        self.normalize(Parsed(detections=[Row(accessory_id='a',present=True,
                            label=None if stage=='fallback' else 'Label',evidence='E',observed_text=[])],rule=Rule(extra=[]),raw_summary='Summary'),
                            [Required(accessory_id='a',name='Name')])
                boundary={'label':('row','label'),'fallback':('required','name'),'evidence':('row','evidence'),
                          'observed':('row','observed_text'),'extra':('rule','extra'),'summary':('parsed','raw_summary')}[stage]
                self.assertEqual(events[-1],boundary)
                self.assertEqual(self.meta.call_count,int(stage=='summary'))
                self.meta.side_effect=None

    def test_metadata_label_summary_status_and_merge_error_order(self):
        for failure in [None,'keys','getitem','mapping']:
            with self.subTest(failure=failure):
                events=[]; error=OSError('merge')
                class Settings(dict):
                    def get(inner,key,default=None): events.append('status'); return super().get(key,default)
                class Parsed(dict):
                    def get(inner,key,default=None):
                        if key=='raw_summary': events.append('summary-read'); self.api.AI_DETECTION_LABEL='too-late'
                        return super().get(key,default)
                class Metadata:
                    def keys(inner):
                        events.append('keys')
                        if failure=='keys': raise error
                        return ['raw_summary']
                    def __getitem__(inner,key):
                        events.append('getitem')
                        if failure=='getitem': raise error
                        return 'override'
                def metadata(settings): events.append('meta'); self.api.AI_DETECTION_LABEL='captured'; return None if failure=='mapping' else Metadata()
                self.meta.side_effect=metadata
                with patch.object(self.api,'string_list',side_effect=lambda value,**kw:events.append('extra') or []), \
                     patch.object(self.api,'bounded_text',side_effect=lambda value,limit:events.append('summary-format') or 'formatted'):
                    previous=self.settings; self.settings=Settings(status='ready')
                    try:
                        if failure:
                            with self.assertRaises(TypeError if failure=='mapping' else OSError) as caught: self.normalize(Parsed(raw_summary='Summary'),[])
                            if failure!='mapping': self.assertIs(caught.exception,error)
                        else:
                            result=self.normalize(Parsed(raw_summary='Summary'),[])
                            self.assertEqual(result['rule']['label'],'captured'); self.assertEqual(result['ai']['raw_summary'],'override')
                    finally: self.settings=previous
                suffix=[] if failure=='mapping' else ['keys'] if failure=='keys' else ['keys','getitem']
                self.assertEqual(events,['extra','meta','summary-read','summary-format','status']+suffix)
        self.meta.side_effect=None


    def test_count_capture_occurs_after_prior_fields_but_before_own_argument(self):
        for stage in ['get','int']:
            with self.subTest(stage=stage):
                events=[]; real=self.api.coerce_detection_count
                def parser(mark):
                    def parse(value): events.append(mark); return real(value)
                    return parse
                before=parser('before'); captured=parser('captured'); later=parser('later')
                class Expected:
                    def __int__(inner): self.api.coerce_detection_count=captured; return 1
                class Required(dict):
                    def get(inner,key,default=None):
                        if key=='expected_count' and stage=='get': self.api.coerce_detection_count=captured
                        return super().get(key,default)
                class Counts(dict):
                    def get(inner,key,default=None): self.api.coerce_detection_count=later; return super().get(key,default)
                with patch.object(self.api,'coerce_detection_count',before):
                    self.assertTrue(self.normalize({'detections':[{'accessory_id':'a','present':True,'count':1}],
                        'rule':{'counts':Counts(a=1)}},[Required(accessory_id='a',expected_count=Expected() if stage=='int' else 1)])['passed'])
                self.assertEqual(events,['captured','later'])

    def test_noncallable_count_parser_still_evaluates_arguments(self):
        for stage in ['rule','detection']:
            with self.subTest(stage=stage):
                events=[]; real=self.api.coerce_detection_count
                def parser(value):
                    events.append('parse')
                    if stage=='detection': self.api.coerce_detection_count=None
                    return real(value)
                class Counts(dict):
                    def __contains__(inner,key):
                        events.append('contains')
                        if stage=='rule': self.api.coerce_detection_count=None
                        return super().__contains__(key)
                    def get(inner,key,default=None): events.append('rule-get'); self.api.coerce_detection_count=parser; return super().get(key,default)
                class Row(dict):
                    def get(inner,key,default=None):
                        if key=='count': events.append('detection-get'); self.api.coerce_detection_count=parser
                        if key=='label': events.append('unexpected-label')
                        return super().get(key,default)
                self.meta.reset_mock()
                with patch.object(self.api,'coerce_detection_count',parser):
                    with self.assertRaises(TypeError):
                        self.normalize({'detections':[Row(accessory_id='a',present=True,count=1)],'rule':{'counts':Counts(a=1)}},[{'accessory_id':'a'}])
                self.assertEqual(events,['contains','rule-get'] if stage=='rule' else ['contains','rule-get','parse','detection-get'])
                self.meta.assert_not_called()


    def test_independent_compositions_interleave_without_root_callbacks(self):
        from local_inspection_service.detection.presence_results import PresenceResults
        services=[]
        for owner in ['alice','bob']:
            count=Mock(return_value=1); text=Mock(side_effect=lambda value,limit,owner=owner:owner+':'+str(limit))
            observed=[owner+'-observed']; extra=[owner+'-extra']; strings=Mock(side_effect=lambda value,owner=owner,observed=observed,extra=extra,**kw:observed if 'max_len' in kw else extra)
            metadata=Mock(return_value={'provider':owner}); label=Mock(return_value=owner+' label')
            cp,tp,sp=Mock(return_value=count),Mock(return_value=text),Mock(return_value=strings)
            service=PresenceResults(cp,tp,sp,metadata,label)
            for dependency in [cp,tp,sp,metadata,label,count,text,strings]: dependency.assert_not_called()
            services.append((owner,service,cp,tp,sp,metadata,label,count,text,strings,observed,extra))
        with ExitStack() as stack:
            for name in ['coerce_detection_count','bounded_text','string_list','ai_tool_provider_meta']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            for round_number in [1,2]:
                for owner,service,cp,tp,sp,metadata,label,count,text,strings,observed,extra in services:
                    settings={'status':owner}; result=service.normalize_ai_detection_result(
                        {'detections':[{'accessory_id':'a','present':True,'count':1,'label':'Name','evidence':'E','observed_text':['T']}],
                         'rule':{'counts':{'a':1}},'raw_summary':'Summary'},[{'accessory_id':'a'}],7,settings)
                    self.assertTrue(result['passed']); self.assertEqual(result['rule']['label'],owner+' label')
                    self.assertEqual(result['ai'],{'latency_ms':7,'timed_out':False,'provider_failure':False,'raw_summary':owner+':240','provider_status':owner,'provider':owner})
                    self.assertIs(result['detections'][0]['observed_text'],observed); self.assertIs(result['rule']['extra'],extra)
                    self.assertEqual(result['detections'][0]['label'],owner+':120')
                    self.assertEqual(result['detections'][0]['evidence'],owner+':180')
                    self.assertEqual(cp.call_args_list,[call()]*(2*round_number)); self.assertEqual(count.call_args_list,[call(1)]*(2*round_number))
                    self.assertEqual(tp.call_args_list,[call()]*(3*round_number)); self.assertEqual(text.call_args_list,[call('Name',120),call('E',180),call('Summary',240)]*round_number)
                    self.assertEqual(sp.call_args_list,[call()]*(2*round_number)); self.assertEqual(strings.call_args_list,[call(['T'],max_items=6,max_len=80),call([],max_items=12)]*round_number)
                    self.assertEqual(metadata.call_args_list,[call(settings)]*round_number); self.assertEqual(label.call_args_list,[call()]*round_number)

    def test_independent_provider_errors_precede_arguments_and_stop(self):
        from local_inspection_service.detection.presence_results import PresenceResults
        expected={('count',0):[],('count',1):['rule-count'],('text',0):['rule-count','count'],
                  ('text',1):['rule-count','count','label'],('text',2):['rule-count','count','label','name'],
                  ('strings',0):['rule-count','count','label','name','evidence'],
                  ('strings',1):['rule-count','count','label','name','evidence','observed_text'],
                  ('metadata',0):['rule-count','count','label','name','evidence','observed_text'],
                  ('label',0):['rule-count','count','label','name','evidence','observed_text'],
                  ('text',3):['rule-count','count','label','name','evidence','observed_text']}
        for (name,position), reads in expected.items():
            with self.subTest(dependency=name,position=position):
                events=[]; error=OSError('provider failed'); lookup_count=0
                class Row(dict):
                    def get(inner,key,default=None):
                        if key in ['count','label','evidence','observed_text']: events.append(key)
                        return super().get(key,default)
                class Counts(dict):
                    def get(inner,key,default=None): events.append('rule-count'); return super().get(key,default)
                class Required(dict):
                    def get(inner,key,default=None):
                        if key=='name': events.append(key)
                        return super().get(key,default)
                class Parsed(dict):
                    def get(inner,key,default=None):
                        if key=='raw_summary': events.append('summary')
                        return super().get(key,default)
                count=Mock(return_value=1); text=Mock(side_effect=lambda value,limit:'' if value is None else str(value)); strings=Mock(return_value=[])
                ports={'count':Mock(return_value=count),'text':Mock(return_value=text),'strings':Mock(return_value=strings),
                       'metadata':Mock(return_value={}), 'label':Mock(return_value='Inspection')}
                def lookup(*args):
                    nonlocal lookup_count
                    lookup_count+=1
                    if lookup_count==position+1: raise error
                    return ports[name].return_value
                ports[name].side_effect=lookup
                service=PresenceResults(ports['count'],ports['text'],ports['strings'],ports['metadata'],ports['label'])
                for port in ports.values(): port.assert_not_called()
                with self.assertRaises(OSError) as caught:
                    service.normalize_ai_detection_result(Parsed(detections=[Row(accessory_id='a',present=True)],rule={'counts':Counts(a=1)}),[Required(accessory_id='a',name='Name')],0,{})
                self.assertIs(caught.exception,error); self.assertEqual(events,reads); self.assertEqual(lookup_count,position+1)
                if name in ['count','text','strings']:
                    self.assertEqual({'count':count,'text':text,'strings':strings}[name].call_count,position)


    def test_mapping_reads_fail_once_without_retry(self):
        sites=[('parsed',key,index) for key in ('detections','rule') for index in (1,2)]
        sites += [('raw','accessory_id',index) for index in (1,2)]
        sites += [('rule',key,index) for key in ('counts','extra') for index in (1,2)]
        sites += [('required','accessory_id',index) for index in (1,2)]
        sites += [('required',key,1) for key in ('expected_count','name')]
        sites += [('raw','present',index) for index in (1,2)]
        sites += [('raw',key,1) for key in ('confidence','count','label','evidence','observed_text')]
        sites += [('counts','a',1),('parsed','raw_summary',1),('parsed','summary',1),('settings','status',1)]
        for owner,key,index in sites:
            with self.subTest(owner=owner,key=key,index=index):
                reads=[]; error=RuntimeError('mapping first failure')
                class Values(dict):
                    def get(inner,name,default=None):
                        if name==key:
                            reads.append(name)
                            if len(reads)==index: raise error
                        return super().get(name,default)
                counts={'a':1}
                if owner=='counts': counts=Values(counts)
                rule={'counts':counts,'extra':[]}
                if owner=='rule': rule=Values(rule)
                raw={'accessory_id':'a','present':True,'confidence':1.0,'count':1,'label':'','evidence':'seen','observed_text':[]}
                if owner=='raw': raw=Values(raw)
                parsed={'detections':[raw],'rule':rule,'raw_summary':'','summary':'summary'}
                if owner=='parsed': parsed=Values(parsed)
                required={'accessory_id':'a','expected_count':1,'name':'A'}
                if owner=='required': required=Values(required)
                settings={'status':'ready'}
                if owner=='settings': settings=Values(settings)
                with self.assertRaises(BaseException) as caught:
                    self.api.normalize_ai_detection_result(parsed,[required],23,settings)
                self.assertIs(caught.exception,error); self.assertEqual(reads,[key]*index)

    def test_expected_count_mapping_type_errors_keep_single_fallback(self):
        for error_type in (TypeError,ValueError):
            with self.subTest(error=error_type):
                reads=[]; error=error_type('expected count')
                class Required(dict):
                    def get(inner,key,default=None):
                        if key=='expected_count':
                            reads.append(key)
                            if len(reads)==1: raise error
                        return super().get(key,default)
                result=self.normalize({'detections':[{'accessory_id':'a','present':True,'count':1}]},[Required(accessory_id='a',expected_count=2)])
                self.assertEqual(reads,['expected_count']); self.assertTrue(result['passed']); self.assertEqual(result['rule']['count_mismatches'],{})


    def test_result_policies_refresh_between_required_items(self):
        _capture_result_policy_refresh(self.api.__dict__)


if __name__=='__main__': unittest.main()

"""Offline profile-cache policy, file persistence and provider-flow contracts."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def capture_presence_cache_chain(api, PresenceFixture, CacheFixture, root, mode):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        cache_entry=api.ensure_required_profile_cache
        presence=PresenceFixture();cache=CacheFixture(root)
        cache.bind(api,stack);presence.bind(api,stack)
        api.time=SimpleNamespace(time=cache.clock,monotonic=presence.clock)
        api.ensure_required_profile_cache=cache_entry
        presence.response['meta']={'integration':'kept'}
        if mode=='hit':cache.cache['entries']['0123456789abcdef']={'name':'cache/hit','expires_at':2000,'reference_images':1}
        elif mode=='unsupported':presence.settings['provider']='other'
        elif mode=='failure':
            calls=[0];original=cache.create.side_effect
            def unknown_once(*args,**kwargs):
                calls[0]+=1
                if calls[0]==1:raise OSError('unknown synthetic cache outcome')
                return original(*args,**kwargs)
            cache.create.side_effect=unknown_once
        elif mode!='create':raise AssertionError(mode)
        result=api.tool_vision_inspect_presence(presence.payload())
        assert result is presence.result
        assert result['ai']['integration']=='kept'
        evidence=result['ai']['profile_cache'];paid=int(mode in ('create','failure'))
        expected_status={'hit':'hit','create':'created','unsupported':'unsupported_provider','failure':'create_failed'}[mode]
        assert evidence['status']==expected_status,evidence
        assert evidence['provider_call_count']==paid and evidence['profile_provider_call_count']==paid,evidence
        assert evidence['provider_call_budget']==3 and evidence['generate_attempt_budget']==3-paid,evidence
        presence.tool.assert_called_once()
        name,args=presence.tool.call_args.args
        assert name=='provider.gemini.generate_json'
        assert args['max_attempts']==3-paid
        assert args['provider_config']==presence.settings and args['provider_config'] is not presence.settings
        if mode!='unsupported':assert args['provider_config'] is cache.key.call_args.args[1]
        assert args['schema_hint'] is presence.schema
        assert args['cached_content']==({'hit':'cache/hit','create':'cache/new'}.get(mode,''))
        assert cache.create.call_count==paid
        assert cache.save.call_count==int(mode=='create')
        if mode=='failure':assert calls==[1]
        if mode in ('create','hit'):assert cache.cache['entries']['0123456789abcdef']['name']==('cache/new' if mode=='create' else 'cache/hit')
        assert 'timing' in result['ai'] and result['ai']['timing']['provider_result_ready_ms']==5000
        return {'status':expected_status,'paid':paid,'budget':args['max_attempts'],'cached_content':args['cached_content']}


def capture_cache_root_window(api, Fixture, root, stage):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import Mock,patch
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        key=api.required_accessory_cache_key;context=api.cached_profile_context_content;save=api.save_ai_profile_cache
        f=Fixture(root);f.bind(api,stack);events=[];captured=None
        if stage=='strings_none':
            later=Mock(return_value=['late']);api.string_list=None
            class Profile(dict):
                def get(self,k,default=None):
                    if k=='distinguishing_text':events.append('arg');api.string_list=later
                    return super().get(k,default)
            try:key([{'accessory_id':'a','profile':Profile(distinguishing_text=['a'])}],f.settings)
            except BaseException as exc:captured=exc
            assert type(captured) is TypeError,(stage,captured,events)
            assert events==['arg'] and not later.called,(stage,events,later.call_count)
        elif stage in ('with_name','with_name_none'):
            temporary=f.path.with_name('profile.json.tmp');missing=stage.endswith('_none')
            def first(name):events.append(('A',name));return temporary
            class Initial:
                with_name=None if missing else staticmethod(first)
                @property
                def name(self):events.append('arg');api.AI_PROFILE_CACHE_PATH=f.path;return 'profile.json'
            api.AI_PROFILE_CACHE_PATH=Initial()
            try:save({'entries':{}})
            except BaseException as exc:captured=exc
            if missing:assert type(captured) is TypeError,(stage,captured,events)
            else:assert captured is None,(stage,captured,events)
            assert events==(['arg'] if missing else ['arg',('A','profile.json.tmp')]),(stage,events)
            assert f.files.replace.call_count==int(not missing)
        elif stage=='create_none':
            later=Mock(return_value=f.created);f.provider.create_cached_content=None
            def content(*a,**k):events.append('context');f.provider.create_cached_content=later;return f.content
            f.context.side_effect=content;result=api.ensure_required_profile_cache(f.required,f.settings)
            assert result['status']=='create_failed' and events==['context'],(stage,result,events)
            f.text.assert_called_once_with("'NoneType' object is not callable",220)
            later.assert_not_called();f.save.assert_not_called()
        elif stage=='strings_refresh':
            later=Mock(side_effect=lambda *a,**k:events.append('B') or ['B'])
            def first(*a,**k):events.append('A');api.string_list=later;return ['A']
            f.strings.side_effect=first
            result=key([{'accessory_id':'a'},{'accessory_id':'b'}],f.settings)[1]
            assert events==['A','B'],events
            assert [r['distinguishing_text'] for r in result]==[['A'],['B']],result
        elif stage=='reference_mode_refresh':
            class Reference(dict):
                def get(self,k,default=None):
                    if k=='mode':events.append('mode');api.AI_PROFILE_REFERENCE_MODE='new-mode'
                    return super().get(k,default)
            refs=[{'accessory_id':'a','data_url':'data:a','mode':'sheet'},Reference(accessory_id='b',data_url='data:b',mode='new-mode')]
            content=context(f.required,refs)
            assert events==['mode'],events
            assert 'CACHED_REFERENCE_SHEET' in content[1]['text'] and 'CACHED_REFERENCE_SHEET' in content[3]['text'],content
        else:raise AssertionError(stage)
        return events

def capture_cache_file_interface(api, Fixture, root, stage, missing):
    from contextlib import ExitStack
    from types import SimpleNamespace
    from unittest.mock import Mock,patch
    from local_inspection_service.detection.profile_cache_store import ProfileCacheStore
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture(root);f.bind(api,stack);events=[];count=[0];current=[f.files]
        b=SimpleNamespace(chmod=Mock(wraps=f.files.chmod),replace=Mock(wraps=f.files.replace))
        a_chmod=f.files.chmod;a_replace=f.files.replace
        if stage=='replace' and missing:f.files.replace=None
        if stage=='chmod':
            def replace(source,target):
                result=a_replace(source,target)
                current[0]=SimpleNamespace(chmod=None if missing else a_chmod)
                return result
            current[0]=SimpleNamespace(chmod=a_chmod,replace=replace)
        def path():
            count[0]+=1
            if count[0]==(3 if stage=='replace' else 4):events.append('arg');current[0]=b
            return f.path
        service=ProfileCacheStore(lambda:f.path.parent,path,lambda:current[0]);captured=None
        try:service.save_ai_profile_cache({'entries':{}})
        except BaseException as exc:captured=exc
        if missing:assert type(captured) is TypeError,(stage,captured,events)
        else:assert captured is None,(stage,captured,events)
        assert events==['arg'],events
        if stage=='replace':
            assert b.replace.call_count==0
            assert a_replace.call_count==int(not missing)
            assert f.path.with_name('profile.json.tmp').exists()==missing
        else:
            assert b.chmod.call_count==0
            assert a_chmod.call_count==1+int(not missing)
            assert f.path.exists()
        return events


class CacheFixture:
    def __init__(self,root):
        self.root=Path(root); self.path=self.root/'data'/'profile.json'; self.events=[]
        self.required=[{'accessory_id':'a'}]; self.settings={'provider':'gemini','configured':True,'model':'fixture'}
        self.cache={'entries':{}}; self.refs=[{'accessory_id':'a','data_url':'data:ref'}]; self.content=[{'type':'text','text':'cached content'}]
        self.created={'name':'cache/new','latency_ms':17,'usage_metadata':{'tokens':4}}
        def port(name,result): return Mock(side_effect=lambda *args,**kwargs:self.events.append(name) or result())
        self.key=port('key',lambda:('0123456789abcdef',[])); self.load=port('load',lambda:self.cache); self.save=port('save',lambda:None)
        self.clock=port('clock',lambda:1000); self.references=port('references',lambda:self.refs); self.create=port('create',lambda:self.created)
        class Gemini: pass
        self.provider_class=Gemini; self.provider=Gemini(); self.provider.create_cached_content=self.create
        self.factory=port('factory',lambda:self.provider); self.context=port('context',lambda:self.content); self.text=port('text',lambda:'safe error')
        self.task={'task':'synthetic'}; self.task_call=port('task',lambda:self.task); self.sheet=port('sheet',lambda:self.refs[0])
        self.strings=Mock(side_effect=lambda value,**kwargs:value if isinstance(value,list) else [])
        self.files=SimpleNamespace(chmod=Mock(wraps=os.chmod),replace=Mock(wraps=os.replace))
    def bind(self,api,stack):
        for name,value in {'required_accessory_cache_key':self.key,'load_ai_profile_cache':self.load,'save_ai_profile_cache':self.save,
            'time':SimpleNamespace(time=self.clock),'profile_reference_descriptors':self.references,'ai_provider_from_settings':self.factory,
            'GeminiAiProvider':self.provider_class,'cached_profile_context_content':self.context,'bounded_text':self.text,
            'AI_DETECTION_SYSTEM_PROMPT':'profile system','AI_PROFILE_CACHE_TTL_SECONDS':3600,'AI_PROFILE_CACHE_VERSION':7,
            'AI_PROFILE_REFERENCE_MODE':'sheet','AI_PROFILE_CACHE_PATH':self.path,'DATA_DIR':self.path.parent,
            'string_list':self.strings,'ai_detection_task_payload':self.task_call,'build_reference_sheet_descriptor':self.sheet,'os':self.files}.items():
            stack.enter_context(patch.object(api,name,value))


class ProfileCacheContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment=patch.dict(os.environ); cls.environment.start(); cls.runtime=tempfile.TemporaryDirectory(prefix='profile-cache-contract-')
        root=Path(cls.runtime.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill']:
            self.stack.enter_context(patch(target,side_effect=AssertionError('unexpected external operation')))
        self.key=self.api.required_accessory_cache_key; self.load=self.api.load_ai_profile_cache; self.save=self.api.save_ai_profile_cache
        self.context=self.api.cached_profile_context_content; self.references=self.api.profile_reference_descriptors
        self.f=CacheFixture(Path(self.runtime.name)/self.id().split('.')[-1]); self.f.bind(self.api,self.stack)
    def ensure(self): return self.api.ensure_required_profile_cache(self.f.required,self.f.settings)

    def test_cache_key_canonical_fields_sorting_and_return_order(self):
        required=[{'accessory_id':'b','expected_count':2,'profile':{'visual_signature':'blue','distinguishing_text':['字'],
                   'reference_images':[None,{}, {'source_path':'path-b','sha256':'sha-b','ignored':1}]}},
                  {'accessory_id':'a','expected_count':0,'profile':{}}]
        digest,items=self.key(required,self.f.settings)
        expected=[{'accessory_id':'b','expected_count':2,'visual_signature':'blue','distinguishing_text':['字'],'references':[{'source_path':'path-b','sha256':'sha-b'}]},
                  {'accessory_id':'a','expected_count':1,'visual_signature':'','distinguishing_text':[],'references':[]}]
        self.assertEqual(items,expected)
        payload={'version':7,'reference_mode':'sheet','provider':'gemini','model':'fixture','system':hashlib.sha256(b'profile system').hexdigest()[:16],'required':list(reversed(expected))}
        self.assertEqual(digest,hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest())
        reverse,reverse_items=self.key(list(reversed(required)),self.f.settings); self.assertEqual(reverse,digest); self.assertEqual(reverse_items,list(reversed(expected)))
        required[0]['ignored']='not hashed'; required[0]['profile']['description']='not hashed'; self.assertEqual(self.key(required,self.f.settings)[0],digest)
        self.assertEqual(self.f.strings.call_args_list[:2],[call(['字'],max_items=12),call(None,max_items=12)])
        required[0]['expected_count']=-2; self.assertEqual(self.key(required,self.f.settings)[1][0]['expected_count'],-2)
        required[0]['expected_count']='invalid'
        with self.assertRaises(ValueError): self.key(required,self.f.settings)

    def test_cache_key_changes_for_each_identity_field_and_preserves_reference_order(self):
        f=self.f; base=[{'accessory_id':'a','profile':{'reference_images':[{'source_path':'first','sha256':'1'},{'source_path':'second','sha256':'2'}]}}]
        original=self.key(base,f.settings)[0]
        for name,value in [('AI_PROFILE_CACHE_VERSION',8),('AI_PROFILE_REFERENCE_MODE','single'),('AI_DETECTION_SYSTEM_PROMPT','different')]:
            with self.subTest(name=name),patch.object(self.api,name,value): self.assertNotEqual(self.key(base,f.settings)[0],original)
        for key,value in [('provider','qwen'),('model','other')]: self.assertNotEqual(self.key(base,{**f.settings,key:value})[0],original)
        base[0]['profile']['reference_images'].reverse(); self.assertNotEqual(self.key(base,f.settings)[0],original)
        malformed=[{'profile':None}]; self.assertEqual(self.key(malformed,f.settings)[1][0]['accessory_id'],'')

    def test_context_prompts_exact_text_reference_order_and_detail_defaults(self):
        f=self.f; refs=[{}, {'accessory_id':'skip'}, {'accessory_id':'a','data_url':'data:sheet','mode':'sheet','sheet_items':[{'id':'字'}],'detail':None},
                       {'accessory_id':'b','data_url':'data:b'}]
        result=self.context(f.required,refs); f.task_call.assert_called_once_with(f.required)
        self.assertEqual(result,[
            {'type':'text','text':'REQUIRED_ACCESSORY_PROFILE_CONTEXT: reuse this context for later inspection images. Reference images are examples of required accessories only; never count them as present in an inspection image.\n'+json.dumps(f.task,ensure_ascii=False)},
            {'type':'text','text':'CACHED_REFERENCE_SHEET: one image containing all required accessory reference tiles. Use it only as appearance evidence and ID mapping. Never count objects in this sheet as present in the inspection image. Sheet item mapping:\n'+json.dumps([{'id':'字'}],ensure_ascii=False)},
            {'type':'image_url','image_url':{'url':'data:sheet','detail':None}},
            {'type':'text','text':'CACHED_REFERENCE_IMAGE for accessory_id=b. Use as profile appearance evidence only.'},
            {'type':'image_url','image_url':{'url':'data:b','detail':'low'}}])
        self.assertEqual(self.references(f.required),[f.refs[0]]); self.assertIs(self.references(f.required)[0],f.refs[0])
        f.sheet.side_effect=None; f.sheet.return_value={}; self.assertEqual(self.references(f.required),[])
        with self.assertRaises(AttributeError): self.context(f.required,[None])

    def test_store_load_normalization_and_filesystem_failures(self):
        f=self.f; self.assertEqual(self.load(),{'entries':{}}); f.path.parent.mkdir(parents=True)
        for text,expected in [('invalid',{}),('[]',{}),('{"entries":[]}',{}),('{"entries":{"key":{"name":"n"}},"extra":1}',{'key':{'name':'n'}})]:
            f.path.write_text(text,encoding='utf-8'); self.assertEqual(self.load(),{'entries':expected})
        with patch.object(Path,'read_text',side_effect=OSError('read')): self.assertEqual(self.load(),{'entries':{}})
        with patch.object(Path,'read_text',side_effect=UnicodeError('decode')):
            with self.assertRaises(UnicodeError): self.load()
        with patch.object(Path,'exists',side_effect=OSError('exists')):
            with self.assertRaises(OSError): self.load()

    def test_store_save_format_permissions_replace_and_no_extra_fields(self):
        f=self.f; cache={'entries':{'字':{'name':'n'}},'private':'omit'}; self.assertIsNone(self.save(cache))
        self.assertEqual(f.path.read_text(encoding='utf-8'),json.dumps({'entries':cache['entries']},ensure_ascii=False,indent=2))
        temporary=f.path.with_name('profile.json.tmp'); self.assertFalse(temporary.exists())
        self.assertEqual(f.files.chmod.call_args_list,[call(temporary,0o600),call(f.path,0o600)]); f.files.replace.assert_called_once_with(temporary,f.path)
        self.save({'entries':[]}); self.assertEqual(json.loads(f.path.read_text(encoding='utf-8')),{'entries':{}})
        self.assertEqual(cache,{'entries':{'字':{'name':'n'}},'private':'omit'})

    def test_store_chmod_ignores_only_oserror_and_replace_failure_leaves_temp(self):
        for stage in ['first_chmod','replace','second_chmod','chmod_oserror']:
            with self.subTest(stage=stage), ExitStack() as stack:
                f=CacheFixture(self.f.root/stage); f.bind(self.api,stack); error=ValueError(stage)
                if stage in ('first_chmod','second_chmod'):
                    attempts=[0]
                    def chmod_once(*args,**kwargs):
                        attempts[0]+=1
                        if attempts[0]==(1 if stage=='first_chmod' else 2):raise error
                        return os.chmod(*args,**kwargs)
                    f.files.chmod.side_effect=chmod_once
                elif stage=='chmod_oserror': f.files.chmod.side_effect=OSError('permissions')
                else: f.files.replace.side_effect=OSError('replace')
                if stage=='chmod_oserror': self.save({'entries':{}}); self.assertEqual(f.files.chmod.call_count,2); self.assertTrue(f.path.exists())
                else:
                    with self.assertRaises(OSError if stage=='replace' else ValueError): self.save({'entries':{}})
                    self.assertEqual(f.files.replace.call_count,0 if stage=='first_chmod' else 1)
                    self.assertEqual(f.path.with_name('profile.json.tmp').exists(),stage!='second_chmod')
                    self.assertEqual(f.path.exists(),stage=='second_chmod')

    def test_unsupported_provider_returns_before_any_dependency(self):
        for settings in [{'provider':'qwen','configured':True},{'provider':'Gemini','configured':True},{'provider':'gemini','configured':False},{}]:
            self.f.settings=settings; self.f.events.clear(); result=self.ensure()
            self.assertEqual(result,{'enabled':False,'status':'unsupported_provider','name':'','reference_images':0,'provider_call_count':0}); self.assertEqual(self.f.events,[])

    def test_existing_hit_uses_strict_expiry_margin_and_original_projection(self):
        f=self.f; f.cache={'entries':{'0123456789abcdef':{'name':'cached/hit','expires_at':1061,'reference_images':'4','extra':'private'}}}
        result=self.ensure(); self.assertEqual(result,{'enabled':True,'status':'hit','name':'cached/hit','reference_images':4,'cache_key':'0123456789ab','provider_call_count':0})
        self.assertEqual(f.events,['key','load','clock']); f.references.assert_not_called(); f.factory.assert_not_called(); f.save.assert_not_called()
        for expires in [1060,1059,0]:
            f.events.clear(); f.refs=[]; f.cache['entries']['0123456789abcdef']['expires_at']=expires; result=self.ensure()
            self.assertEqual(result,{'enabled':False,'status':'no_reference_images','name':'','reference_images':0,'provider_call_count':0}); self.assertEqual(f.events,['key','load','clock','references'])
        f.cache['entries']['0123456789abcdef']['expires_at']='invalid'
        with self.assertRaises(ValueError): self.ensure()

    def test_create_records_before_save_keeps_aliases_and_counts_one_call(self):
        f=self.f; result=self.ensure(); self.assertEqual(f.events,['key','load','clock','references','factory','context','create','save'])
        f.factory.assert_called_once_with(f.settings); f.create.assert_called_once_with('profile system',f.content,display_name='inspection-profile-0123456789ab',ttl_seconds=3600)
        f.context.assert_called_once_with(f.required,f.refs); f.save.assert_called_once_with(f.cache)
        self.assertEqual(f.cache['entries']['0123456789abcdef'],{'name':'cache/new','provider':'gemini','model':'fixture','created_at':1000,'expires_at':4600,'reference_images':1,'latency_ms':17,'usage_metadata':{'tokens':4}})
        self.assertIs(f.cache['entries']['0123456789abcdef']['usage_metadata'],f.created['usage_metadata']); self.assertIs(result['usage_metadata'],f.created['usage_metadata'])
        self.assertEqual(result,{'enabled':True,'status':'created','name':'cache/new','reference_images':1,'latency_ms':17,'usage_metadata':{'tokens':4},'cache_key':'0123456789ab','provider_call_count':1})

    def test_outer_stage_errors_propagate_and_inner_stage_errors_fail_once(self):
        for stage in ['key','load','clock','references','factory','context','create','save']:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=CacheFixture(self.f.root/stage); f.bind(self.api,stack); error=OSError(stage); callback=getattr(f,stage); normal=callback.side_effect; calls=0
                def fail(*args,**kwargs):
                    nonlocal calls
                    calls+=1
                    if calls==1: raise error
                    return normal(*args,**kwargs)
                callback.side_effect=fail
                if stage in ['key','load','clock','references']:
                    with self.assertRaises(OSError) as caught: self.api.ensure_required_profile_cache(f.required,f.settings)
                    self.assertIs(caught.exception,error); f.text.assert_not_called()
                else:
                    result=self.api.ensure_required_profile_cache(f.required,f.settings)
                    self.assertEqual(result,{'enabled':False,'status':'create_failed','name':'','reference_images':1,'error':'safe error','cache_key':'0123456789ab','provider_call_count':1})
                    f.text.assert_called_once_with(stage,220)
                self.assertEqual(calls,1); self.assertEqual('0123456789abcdef' in f.cache['entries'],stage=='save')
                if stage in ['key','load','clock','references','factory','context']: f.create.assert_not_called()

    def test_type_gate_and_baseexception_keep_original_boundary(self):
        f=self.f; f.provider=object(); result=self.ensure(); self.assertEqual(result['status'],'create_failed'); f.create.assert_not_called(); f.context.assert_not_called()
        self.assertIn('does not support Gemini cachedContent',f.text.call_args.args[0]); self.assertEqual(result['provider_call_count'],1)
        class Cancelled(BaseException): pass
        signal=Cancelled('stop'); f.factory.side_effect=signal; f.text.reset_mock()
        with self.assertRaises(Cancelled) as caught: self.ensure()
        self.assertIs(caught.exception,signal); f.text.assert_not_called()

    def test_save_failure_preserves_entry_and_false_save_result_is_ignored(self):
        f=self.f; error=OSError('disk full'); f.save.side_effect=[error,None]
        result=self.ensure(); self.assertEqual(result['status'],'create_failed'); self.assertEqual(f.cache['entries']['0123456789abcdef']['name'],'cache/new'); f.save.assert_called_once()
        f.cache['entries'].clear(); f.save.side_effect=None; f.save.return_value=False; result=self.ensure(); self.assertEqual(result['status'],'created')
        f.created={}; f.cache['entries'].clear(); f.save.reset_mock(); result=self.ensure(); self.assertEqual(result['status'],'create_failed'); self.assertEqual(f.cache['entries'],{}); f.save.assert_not_called()

    def test_provider_method_capture_precedes_context_and_ttl_is_read_twice(self):
        f=self.f; before=f.create; later=Mock(return_value=f.created)
        def context(*args): f.provider.create_cached_content=later; self.api.AI_PROFILE_CACHE_TTL_SECONDS=70; return f.content
        f.context.side_effect=context
        def create(*args,**kwargs): self.api.AI_PROFILE_CACHE_TTL_SECONDS=90; return f.created
        before.side_effect=create; self.ensure(); before.assert_called_once_with('profile system',f.content,display_name='inspection-profile-0123456789ab',ttl_seconds=70); later.assert_not_called()
        self.assertEqual(f.cache['entries']['0123456789abcdef']['expires_at'],1090)
        f.cache['entries'].clear(); f.provider.create_cached_content=None; self.ensure(); self.assertEqual(f.text.call_args.args[0],"'NoneType' object is not callable"); later.assert_not_called()

    def test_error_formatter_capture_before_exception_string_without_retry(self):
        f=self.f; later=Mock(return_value='late'); calls=[]
        class Failure(Exception):
            def __str__(inner): calls.append('str'); self.api.bounded_text=later; return 'create failed'
        failure=Failure(); f.create.side_effect=[failure,f.created]; self.ensure(); self.assertEqual(calls,['str']); f.text.assert_called_once_with('create failed',220); later.assert_not_called(); f.create.assert_called_once()
        f.create.reset_mock(); f.create.side_effect=failure; self.api.bounded_text=None
        with self.assertRaises(TypeError): self.ensure()
        self.assertEqual(calls,['str','str']); f.create.assert_called_once(); later.assert_not_called()


    def test_created_fields_repeated_after_save_and_falsey_usage_is_not_shared(self):
        f=self.f; events=[]; error=OSError('post-save projection')
        class Created(dict):
            def __getitem__(inner,key):
                events.append(key)
                if events.count('name')==2: raise error
                return super().__getitem__(key)
        f.created=Created(name='cache/new',usage_metadata={'tokens':4}); result=self.ensure()
        self.assertEqual(result['status'],'create_failed'); f.save.assert_called_once(); self.assertEqual(events,['name','name'])
        self.assertEqual(f.cache['entries']['0123456789abcdef']['name'],'cache/new'); f.text.assert_called_once_with('post-save projection',220)
        f.cache['entries'].clear(); f.created={'name':'new','usage_metadata':None}; f.save.reset_mock(); result=self.ensure()
        self.assertEqual(result['usage_metadata'],{}); self.assertEqual(f.cache['entries']['0123456789abcdef']['usage_metadata'],{})
        self.assertIsNot(result['usage_metadata'],f.cache['entries']['0123456789abcdef']['usage_metadata'])

    def test_type_is_read_after_factory_and_error_formatter_after_reference_length(self):
        f=self.f; before=f.provider_class
        class Next: pass
        instance=Next(); instance.create_cached_content=f.create
        def factory(settings): self.api.GeminiAiProvider=Next; return instance
        f.factory.side_effect=factory; self.assertEqual(self.ensure()['status'],'created'); self.assertNotIsInstance(instance,before)
        f.cache['entries'].clear(); events=[]; first=f.text; selected=Mock(return_value='selected'); later=Mock(return_value='late')
        class References(list):
            def __len__(inner): events.append('len'); self.api.bounded_text=selected; return super().__len__()
        class Failure(Exception):
            def __str__(inner): events.append('str'); self.api.bounded_text=later; return 'failed'
        f.refs=References(f.refs); f.factory.side_effect=Failure(); first.reset_mock()
        result=self.ensure(); self.assertEqual(result['error'],'selected'); self.assertEqual(events,['len','len','str'])
        first.assert_not_called(); selected.assert_called_once_with('failed',220); later.assert_not_called()

    def test_store_creates_only_data_dir_and_retains_partial_temporary_write(self):
        f=self.f; outside=f.root/'other'/'cache.json'; self.api.AI_PROFILE_CACHE_PATH=outside
        with self.assertRaises(FileNotFoundError): self.save({'entries':{}})
        self.assertTrue(f.path.parent.exists()); self.assertFalse(outside.parent.exists()); f.files.replace.assert_not_called()
        self.api.AI_PROFILE_CACHE_PATH=f.path; original=Path.write_text; error=OSError('partial write')
        writes=[]
        def partial(path,text,**kwargs):
            writes.append(path)
            if len(writes)==1:
                original(path,text[:4],**kwargs); raise error
            return original(path,text,**kwargs)
        with patch.object(Path,'write_text',partial):
            with self.assertRaises(OSError) as caught: self.save({'entries':{'a':1}})
        self.assertIs(caught.exception,error); self.assertEqual(writes,[f.path.with_name('profile.json.tmp')]); self.assertEqual(f.path.with_name('profile.json.tmp').read_text(encoding='utf-8'),'{\n  ')
        f.files.chmod.assert_not_called(); f.files.replace.assert_not_called(); self.assertFalse(f.path.exists())

    def test_hash_duplicate_ids_count_zero_string_and_formatter_capture(self):
        f=self.f; a={'accessory_id':'a','expected_count':0}; b={'accessory_id':'a','expected_count':'0'}
        digest,items=self.key([a,b],f.settings); self.assertEqual([item['expected_count'] for item in items],[1,0])
        self.assertNotEqual(self.key([b,a],f.settings)[0],digest)
        before=f.strings; selected=Mock(return_value=['selected']); later=Mock(return_value=['later']); events=[]
        class Profile(dict):
            def get(inner,key,default=None):
                if key=='visual_signature': self.api.string_list=selected; events.append('visual')
                if key=='distinguishing_text': self.api.string_list=later; events.append('text')
                return super().get(key,default)
        profile=Profile(distinguishing_text=['source']); result=self.key([{'accessory_id':'a','profile':profile}],f.settings)[1]
        self.assertEqual(result[0]['distinguishing_text'],['selected']); self.assertEqual(events,['visual','text'])
        before.reset_mock(); selected.assert_called_once_with(['source'],max_items=12); later.assert_not_called()


    def test_store_load_reselects_path_after_exists_and_propagates_decode_errors(self):
        events=[]; second=SimpleNamespace(read_text=Mock(return_value='{"entries":{"second":1}}'))
        def exists(): events.append('exists'); self.api.AI_PROFILE_CACHE_PATH=second; return True
        first=SimpleNamespace(exists=exists,read_text=Mock(side_effect=AssertionError('cached first path')))
        self.api.AI_PROFILE_CACHE_PATH=first; self.assertEqual(self.load(),{'entries':{'second':1}})
        self.assertEqual(events,['exists']); first.read_text.assert_not_called(); second.read_text.assert_called_once_with(encoding='utf-8')
        first.exists=lambda:True; first.read_text.side_effect=UnicodeDecodeError('utf-8',b'\xff',0,1,'invalid'); self.api.AI_PROFILE_CACHE_PATH=first
        with self.assertRaises(UnicodeDecodeError): self.load()

    def test_store_save_preserves_path_and_filesystem_target_capture_order(self):
        events=[]; temporary=SimpleNamespace(write_text=Mock(side_effect=lambda *args,**kwargs:events.append('write')))
        second=SimpleNamespace(with_name=lambda name:temporary); final=object(); newer=SimpleNamespace(chmod=Mock(side_effect=lambda *args:events.append('final chmod')),replace=Mock())
        class Initial:
            @property
            def name(inner): events.append('name'); self.api.AI_PROFILE_CACHE_PATH=second; return 'selected.json'
            def with_name(inner,name): events.append(('with_name',name)); return temporary
        initial=Initial(); self.api.AI_PROFILE_CACHE_PATH=initial
        def replace(source,target):
            events.append('replace'); self.api.AI_PROFILE_CACHE_PATH=final; self.api.os=newer
        first=SimpleNamespace(chmod=Mock(side_effect=lambda *args:events.append('first chmod')),replace=Mock(side_effect=replace)); self.api.os=first
        self.save({'entries':{}})
        self.assertEqual(events,['name',('with_name','selected.json.tmp'),'write','first chmod','replace','final chmod'])
        first.chmod.assert_called_once_with(temporary,0o600); first.replace.assert_called_once_with(temporary,second)
        newer.chmod.assert_called_once_with(final,0o600); newer.replace.assert_not_called()


    def test_independent_cache_compositions_create_and_hit_their_own_files(self):
        from local_inspection_service.detection.profile_cache_policy import ProfileCachePolicy
        from local_inspection_service.detection.profile_cache_store import ProfileCacheStore
        from local_inspection_service.detection.profile_cache import ProfileCacheFlow,CacheRecords,CacheEvidence,CacheProviders,CacheTiming
        services=[]
        for owner in ['alice','bob']:
            f=CacheFixture(self.f.root/owner); f.required=[{'accessory_id':owner}]; f.settings['model']=owner; f.created['name']='cache/'+owner
            directory=Mock(return_value=f.path.parent); path=Mock(return_value=f.path); files=Mock(return_value=f.files)
            policy=ProfileCachePolicy(lambda f=f:f.strings,lambda:7,lambda:'sheet',lambda owner=owner:'prompt '+owner,f.task_call,f.sheet)
            storage=ProfileCacheStore(directory,path,files)
            service=ProfileCacheFlow(CacheRecords(storage.load_ai_profile_cache,storage.save_ai_profile_cache),
                CacheEvidence(policy.required_accessory_cache_key,policy.profile_reference_descriptors,policy.cached_profile_context_content),
                CacheProviders(f.factory,lambda f=f:f.provider_class,lambda:RuntimeError),CacheTiming(f.clock,lambda:3600),
                lambda owner=owner:'prompt '+owner,lambda f=f:f.text)
            for dependency in [directory,path,files]: dependency.assert_not_called()
            self.assertEqual(f.events,[]); self.assertFalse(f.path.parent.exists()); services.append((owner,f,service))
        with ExitStack() as stack:
            for name in ['required_accessory_cache_key','load_ai_profile_cache','save_ai_profile_cache','profile_reference_descriptors',
                         'ai_provider_from_settings','cached_profile_context_content','bounded_text','string_list','ai_detection_task_payload','build_reference_sheet_descriptor']:
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            stack.enter_context(patch.object(self.api,'time',object())); stack.enter_context(patch.object(self.api,'os',object()))
            for status in ['created','hit']:
                for owner,f,service in services:
                    result=service.ensure_required_profile_cache(f.required,f.settings); self.assertEqual(result['status'],status); self.assertEqual(result['name'],'cache/'+owner)
                    f.create.assert_called_once(); self.assertEqual(f.create.call_args.args[0],'prompt '+owner)
                    records=json.loads(f.path.read_text(encoding='utf-8'))['entries']; self.assertEqual(len(records),1)
                    self.assertEqual(next(iter(records.values()))['name'],'cache/'+owner)
            self.assertNotEqual(services[0][1].path.read_text(encoding='utf-8'),services[1][1].path.read_text(encoding='utf-8'))

    def test_independent_path_provider_failure_occurs_at_read_without_constructor_io(self):
        from local_inspection_service.detection.profile_cache_store import ProfileCacheStore
        failure=ValueError('path provider'); path=Mock(side_effect=failure); directory=Mock(); files=Mock()
        store=ProfileCacheStore(directory,path,files); path.assert_not_called(); directory.assert_not_called(); files.assert_not_called()
        with self.assertRaises(ValueError) as caught: store.load_ai_profile_cache()
        self.assertIs(caught.exception,failure); path.assert_called_once_with(); directory.assert_not_called(); files.assert_not_called()


    def test_key_and_error_formatters_first_failure_is_never_retried(self):
        for stage in ['strings','text']:
            with self.subTest(stage=stage),ExitStack() as stack:
                f=CacheFixture(self.f.root/stage); f.bind(self.api,stack); error=OSError(stage); callback=getattr(f,stage)
                callback.side_effect=[error,[] if stage=='strings' else 'second success']
                if stage=='text': f.create.side_effect=ValueError('original provider failure')
                with self.assertRaises(OSError) as caught:
                    if stage=='strings': self.key([{'accessory_id':'a'}],f.settings)
                    else: self.api.ensure_required_profile_cache(f.required,f.settings)
                self.assertIs(caught.exception,error); callback.assert_called_once()
                if stage=='text': f.create.assert_called_once(); f.save.assert_not_called(); self.assertEqual(f.cache['entries'],{})


    def test_presence_cache_chain_preserves_budget_and_call_evidence(self):
        from scripts.smoke_presence_inspection import PresenceFixture
        for mode in ('hit','create','unsupported','failure'):
            with self.subTest(mode=mode):capture_presence_cache_chain(self.api,PresenceFixture,CacheFixture,self.f.root/mode,mode)



    def test_cache_callback_capture_and_refresh_windows(self):
        for stage in ('strings_none','with_name','with_name_none','create_none','strings_refresh','reference_mode_refresh'):
            with self.subTest(stage=stage),patch.multiple(self.api,required_accessory_cache_key=self.key,cached_profile_context_content=self.context,save_ai_profile_cache=self.save):
                capture_cache_root_window(self.api,CacheFixture,self.f.root/stage,stage)

    def test_independent_file_provider_capture_windows(self):
        for stage in ('replace','chmod'):
            for missing in (False,True):
                with self.subTest(stage=stage,missing=missing):capture_cache_file_interface(self.api,CacheFixture,self.f.root/(stage+str(missing)),stage,missing)

    def test_mapping_failures_preserve_first_error_and_partial_cache_state(self):
        # Each mapping remains valid after its selected first failure, so retries cannot hide.
        cases=[]
        for target,fields in {'required':['profile','accessory_id','expected_count'],'profile':['reference_images','visual_signature','distinguishing_text'],'reference':['source_path','sha256'],'key_settings':['provider','model'],'context_ref':['accessory_id','data_url','mode','sheet_items','detail'],'load_raw':['entries'],'save_cache':['entries'],'flow_cache':['entries'],'flow_entries':['0123456789abcdef'],'existing':['name','expires_at','reference_images'],'flow_settings':['provider','configured','model'],'created':['name','latency_ms','usage_metadata']}.items():
            for field in fields:
                occurrences=2 if (target,field) in [('required','profile'),('reference','source_path'),('load_raw','entries'),('save_cache','entries'),('flow_entries','0123456789abcdef'),('flow_settings','provider'),('created','name'),('created','latency_ms'),('created','usage_metadata')] else 1
                for occurrence in range(1,occurrences+1):cases.append((target,field,occurrence))
        cases.extend([('context_item','data_url',1),('existing_item','name',1)])
        for target,field,occurrence in cases:
            with self.subTest(target=target,field=field,occurrence=occurrence),ExitStack() as stack:
                f=CacheFixture(self.f.root/(target+field+str(occurrence)));f.bind(self.api,stack);error=RuntimeError('mapping '+target+' '+field);seen=[0]
                def visit(key):
                    if key==field:
                        seen[0]+=1
                        if seen[0]==occurrence:raise error
                class Mapping(dict):
                    def get(inner,key,default=None):
                        if target not in ('context_item','existing_item'):visit(key)
                        return super().get(key,default)
                    def setdefault(inner,key,default=None):visit(key);return super().setdefault(key,default)
                    def __getitem__(inner,key):
                        if target in ('context_item','existing_item') or (target=='created' and field=='name'):visit(key)
                        return super().__getitem__(key)
                required={'accessory_id':'a','expected_count':1};profile={'visual_signature':'blue','distinguishing_text':['a']};reference={'source_path':'x','sha256':'sha'}
                ref={'accessory_id':'a','data_url':'data:a','mode':'sheet','sheet_items':[{'id':'a'}],'detail':'low'}
                invoke=None;inner_failure=False;persisted=False
                if target in ('required','profile','reference','key_settings'):
                    if target=='reference':reference=Mapping(reference)
                    profile['reference_images']=[reference]
                    if target=='profile':profile=Mapping(profile)
                    required['profile']=profile
                    if target=='required':required=Mapping(required)
                    settings=Mapping(f.settings) if target=='key_settings' else f.settings
                    invoke=lambda:self.key([required],settings)
                elif target in ('context_ref','context_item'):
                    invoke=lambda:self.context(f.required,[Mapping(ref)])
                elif target=='load_raw':
                    f.path.parent.mkdir(parents=True);f.path.write_text('{}',encoding='utf-8')
                    stack.enter_context(patch.object(json,'loads',return_value=Mapping(entries={'x':1})));invoke=self.load
                elif target=='save_cache':invoke=lambda:self.save(Mapping(entries={}))
                else:
                    if target=='flow_cache':f.cache=Mapping(entries={})
                    elif target=='flow_entries':f.cache={'entries':Mapping({'0123456789abcdef':{}})}
                    elif target in ('existing','existing_item'):f.cache={'entries':{'0123456789abcdef':Mapping(name='hit',expires_at=2000,reference_images=1)}}
                    elif target=='flow_settings':f.settings=Mapping(f.settings);inner_failure=field=='model' or (field=='provider' and occurrence==2)
                    elif target=='created':f.created=Mapping(f.created);inner_failure=True;persisted=occurrence==2
                    invoke=lambda:self.api.ensure_required_profile_cache(f.required,f.settings)
                if inner_failure:
                    result=invoke();self.assertEqual(result['status'],'create_failed');self.assertEqual(result['provider_call_count'],1)
                    f.text.assert_called_once_with(str(error),220);self.assertEqual(f.save.call_count,int(persisted))
                    self.assertEqual('0123456789abcdef' in f.cache['entries'],persisted)
                else:
                    with self.assertRaises(RuntimeError) as caught:invoke()
                    self.assertIs(caught.exception,error);f.text.assert_not_called()
                self.assertEqual(seen[0],occurrence)

    def test_policy_callbacks_and_json_fail_once_without_retry(self):
        for stage in ('task','sheet','key_json','context_json','sheet_json','load_json','save_json'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=CacheFixture(self.f.root/stage);f.bind(self.api,stack);error=RuntimeError(stage);seen=[0]
                if stage in ('task','sheet'):callback=getattr(f,'task_call' if stage=='task' else 'sheet');normal=callback.side_effect
                else:normal=json.loads if stage=='load_json' else json.dumps
                target=2 if stage=='sheet_json' else 1
                def once(*args,**kwargs):
                    seen[0]+=1
                    if seen[0]==target:raise error
                    return normal(*args,**kwargs)
                if stage in ('task','sheet'):callback.side_effect=once
                else:stack.enter_context(patch.object(json,'loads' if stage=='load_json' else 'dumps',side_effect=once))
                with self.assertRaises(RuntimeError) as caught:
                    if stage=='sheet':self.references(f.required)
                    elif stage=='key_json':self.key(f.required,f.settings)
                    elif stage=='load_json':
                        f.path.parent.mkdir(parents=True);f.path.write_text('{}',encoding='utf-8');self.load()
                    elif stage=='save_json':self.save({'entries':{}})
                    else:self.context(f.required,[{'accessory_id':'a','data_url':'data:a','mode':'sheet','sheet_items':[1]}])
                self.assertIs(caught.exception,error);self.assertEqual(seen[0],target)

    def test_store_filesystem_operations_fail_once_without_retry(self):
        for stage in ('exists','read_text','mkdir','with_name'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=CacheFixture(self.f.root/stage);f.bind(self.api,stack);f.path.parent.mkdir(parents=True);f.path.write_text('{}',encoding='utf-8')
                normal=getattr(Path,stage);error=RuntimeError(stage);seen=[0]
                def once(path,*args,**kwargs):
                    seen[0]+=1
                    if seen[0]==1:raise error
                    return normal(path,*args,**kwargs)
                with patch.object(Path,stage,once):
                    with self.assertRaises(RuntimeError) as caught:
                        if stage in ('exists','read_text'):self.load()
                        else:self.save({'entries':{}})
                self.assertIs(caught.exception,error);self.assertEqual(seen[0],1);f.files.replace.assert_not_called()

    def test_independent_dependency_getters_fail_once_at_their_original_window(self):
        from local_inspection_service.detection.profile_cache_policy import ProfileCachePolicy
        from local_inspection_service.detection.profile_cache_store import ProfileCacheStore
        from local_inspection_service.detection.profile_cache import ProfileCacheFlow,CacheRecords,CacheEvidence,CacheProviders,CacheTiming
        cases=[('policy',x,1) for x in ('strings','version','reference_mode','prompt')]+[('context','reference_mode',1)]
        cases += [('load','path',i) for i in (1,2)]+[('save','path',i) for i in (1,2,3,4)]+[('save','files',i) for i in (1,2,3)]+[('save','data_dir',1)]
        cases += [('flow',x,i) for x,i in [('kind',1),('error',1),('error_constructor',1),('prompt',1),('ttl',1),('ttl',2),('text',1)]]
        for mode,dependency,occurrence in cases:
            with self.subTest(mode=mode,dependency=dependency,occurrence=occurrence),ExitStack() as stack:
                f=CacheFixture(self.f.root/(mode+dependency+str(occurrence)));f.bind(self.api,stack);error=RuntimeError(mode+' '+dependency);seen=[0]
                def getter(name,value):
                    def get():
                        if name==dependency:
                            seen[0]+=1
                            if seen[0]==occurrence:raise error
                        return value
                    return get
                policy=ProfileCachePolicy(getter('strings',f.strings),getter('version',7),getter('reference_mode','sheet'),getter('prompt','prompt'),f.task_call,f.sheet)
                storage=ProfileCacheStore(getter('data_dir',f.path.parent),getter('path',f.path),getter('files',f.files))
                def error_constructor(*args):
                    seen[0]+=1
                    if seen[0]==occurrence:raise error
                    return RuntimeError(*args)
                flow=ProfileCacheFlow(CacheRecords(f.load,f.save),CacheEvidence(f.key,f.references,f.context),CacheProviders(f.factory,getter('kind',f.provider_class),getter('error',error_constructor if dependency=='error_constructor' else RuntimeError)),CacheTiming(f.clock,getter('ttl',3600)),getter('prompt','prompt'),getter('text',f.text))
                if dependency in ('error','error_constructor'):f.provider=object()
                if dependency=='text':f.create.side_effect=ValueError('provider failure')
                if mode=='load':f.path.parent.mkdir(parents=True);f.path.write_text('{}',encoding='utf-8')
                def invoke():
                    if mode=='policy':return policy.required_accessory_cache_key(f.required,f.settings)
                    if mode=='context':return policy.cached_profile_context_content(f.required,f.refs)
                    if mode=='load':return storage.load_ai_profile_cache()
                    if mode=='save':return storage.save_ai_profile_cache({'entries':{}})
                    return flow.ensure_required_profile_cache(f.required,f.settings)
                if mode=='flow' and dependency!='text':
                    result=invoke();self.assertEqual(result['status'],'create_failed');f.text.assert_called_once_with(str(error),220);f.save.assert_not_called()
                    self.assertEqual(f.create.call_count,int(dependency=='ttl' and occurrence==2))
                else:
                    with self.assertRaises(RuntimeError) as caught:invoke()
                    self.assertIs(caught.exception,error)
                self.assertEqual(seen[0],occurrence)


if __name__=='__main__': unittest.main()

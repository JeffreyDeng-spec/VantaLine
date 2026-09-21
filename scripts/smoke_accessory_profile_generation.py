"""Offline original contracts for accessory profile generation."""

import os

from pathlib import Path

import sys

import tempfile

import unittest

from contextlib import ExitStack

from unittest.mock import Mock,patch,call

sys.path.insert(0,str(Path.cwd()))

class AccessoryProfileGenerationContracts(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))

        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='accessory-profile-generation-')))

        (cls.root/'local_inspection_service/static').mkdir(parents=True)

        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)

        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')

        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):

            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))

        from types import SimpleNamespace

        cls.import_factory=Mock(side_effect=AssertionError('Eager model load forbidden'));cls.import_remove=Mock(side_effect=AssertionError('Eager inference forbidden'))

        cls.lifetime.enter_context(patch.dict(sys.modules,{'rembg':SimpleNamespace(new_session=cls.import_factory,remove=cls.import_remove)}))

        from local_inspection_service import server

        cls.import_factory.assert_not_called();cls.import_remove.assert_not_called()

        cls.api=server

    @classmethod

    def tearDownClass(cls):cls.lifetime.close()

    def setUp(self):

        self.stack=ExitStack();self.addCleanup(self.stack.close)

    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))

    def tool_fixture(self):
        self.item={'id':'a','expected_count':4}
        self.fallback={'accessory_id':'a','name':'F'}
        self.settings={'configured':True,'model':'synthetic'}
        self.status={'source':'fallback','status':'ready','nested':[]}
        self.references=[{'accessory_id':'a','data_url':'data:synthetic','detail':'high'},{'accessory_id':'b','data_url':'data:other'}]
        self.profile={'name':'Normalized'};self.contexts=[{'id':'context'}]
        self.fallback_call=self.replace('fallback_accessory_ai_profile',return_value=self.fallback)
        self.settings_call=self.replace('ai_detection_settings',return_value=self.settings)
        self.status_call=self.replace('profile_generation_status',return_value=self.status)
        self.prompt_call=self.replace('accessory_profile_prompt_payload',return_value={'unicode':'配件'})
        self.normalize_call=self.replace('normalize_accessory_ai_profile',return_value=self.profile)
        self.context_call=self.replace('accessory_reference_image_contexts',return_value=self.contexts)
        self.provider_result={'ok':True,'parsed':{'raw':1},'latency_ms':12}
        def invoke(name,payload):
            if name=='accessory.reference.collect':return {'references':self.references}
            if name=='provider.gemini.generate_json':return self.provider_result
            raise AssertionError('Unexpected tool')
        self.invoke=self.replace('call_ai_mcp_tool',side_effect=invoke)

    def test_disabled_still_builds_fallback_settings_status(self):
        self.tool_fixture();events=[]
        self.fallback_call.side_effect=lambda item:(events.append('fallback'),self.fallback)[1]
        self.settings_call.side_effect=lambda kind:(events.append(kind),self.settings)[1]
        self.status_call.side_effect=lambda settings:(events.append('status'),self.status)[1]
        result=self.api.tool_accessory_profile_generate({'accessory':self.item,'allow_provider':False})
        self.assertEqual(events,['fallback','accessory','status'])
        self.assertEqual(result,{'tool':'accessory.profile.generate','profile':self.fallback,'status':self.status,'ok':False})
        self.assertIs(result['profile'],self.fallback);self.assertIs(result['status'],self.status)
        self.invoke.assert_not_called();self.context_call.assert_not_called()

    def test_input_copy_count_override_and_config_selection(self):
        self.tool_fixture();provided={'configured':False};nested=[];item={'nested':nested,'expected_count':7}
        self.api.tool_accessory_profile_generate({'accessory':item,'expected_count':None,'provider_config':provided})
        received=self.fallback_call.call_args.args[0]
        self.assertIsNot(received,item);self.assertIs(received['nested'],nested);self.assertIsNone(received['expected_count'])
        self.assertEqual(item,{'nested':nested,'expected_count':7});self.settings_call.assert_not_called()
        self.assertEqual(self.status_call.call_args.args[0],provided);self.assertIsNot(self.status_call.call_args.args[0],provided)

    def test_false_config_fallback_and_nondict_accessory(self):
        self.tool_fixture();self.settings['configured']=False
        self.api.tool_accessory_profile_generate({'accessory':['bad'],'provider_config':{}})
        self.fallback_call.assert_called_once_with({});self.settings_call.assert_called_once_with('accessory');self.invoke.assert_not_called()

    def test_reference_packet_defaults_and_explicit_none(self):
        self.tool_fixture();self.api.tool_accessory_profile_generate({'accessory':self.item})
        name,payload=self.invoke.call_args_list[0].args
        self.assertEqual(name,'accessory.reference.collect')
        self.assertEqual(payload,{'accessory':self.item,'reference_image_paths':None,'max_images':self.api.AI_PROFILE_REFERENCE_IMAGES,'max_side':self.api.AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE,'quality':self.api.AI_PROFILE_REFERENCE_IMAGE_QUALITY})
        self.api.tool_accessory_profile_generate({'accessory':self.item,'max_reference_images':None,'reference_max_side':0,'reference_quality':None})
        self.assertEqual({k:v for k,v in self.invoke.call_args_list[2].args[1].items() if k in ('max_images','max_side','quality')},{'max_images':None,'max_side':0,'quality':None})

    def test_provider_packet_content_order_and_json(self):
        self.tool_fixture();self.api.tool_accessory_profile_generate({'accessory':self.item})
        name,payload=self.invoke.call_args_list[1].args
        self.assertEqual(name,'provider.gemini.generate_json')
        self.assertEqual(payload['max_tokens'],900);self.assertEqual(payload['schema_hint'],{'required_keys':['accessory_id','name']})
        self.assertEqual(payload['user_content'],[{'type':'text','text':'{"unicode": "配件"}'},{'type':'text','text':'REFERENCE_IMAGE for accessory_id=a. Use this only as profile appearance evidence.'},{'type':'image_url','image_url':{'url':'data:synthetic','detail':'high'}},{'type':'text','text':'REFERENCE_IMAGE for accessory_id=b. Use this only as profile appearance evidence.'},{'type':'image_url','image_url':{'url':'data:other','detail':'low'}}])
        self.assertEqual(payload['provider_config'],self.settings)

    def test_success_normalization_alias_status_copy(self):
        self.tool_fixture();result=self.api.tool_accessory_profile_generate({'accessory':self.item})
        self.normalize_call.assert_called_once_with({'raw':1},self.item)
        self.assertIs(result['profile'],self.profile);self.assertIs(self.profile['reference_images'],self.contexts)
        self.assertEqual(result['status'],{'source':'provider','status':'generated','nested':[],'message':'AI profile generated by provider.','latency_ms':12,'reference_images':2})
        self.assertIsNot(result['status'],self.status);self.assertIs(result['status']['nested'],self.status['nested'])
        self.assertEqual(self.status,{'source':'fallback','status':'ready','nested':[]});self.assertTrue(result['ok'])

    def test_success_false_parsed_and_missing_latency(self):
        self.tool_fixture();self.provider_result={'ok':True,'parsed':[]}
        result=self.api.tool_accessory_profile_generate({'accessory':self.item})
        self.assertEqual(self.normalize_call.call_args.args[0],{});self.assertEqual(result['status']['latency_ms'],0)

    def test_failure_updates_original_status_and_fallback(self):
        self.tool_fixture();self.provider_result={'ok':False,'timed_out':'yes','error':'synthetic','latency_ms':None}
        result=self.api.tool_accessory_profile_generate({'accessory':self.item})
        self.assertIs(result['status'],self.status);self.assertIs(result['profile'],self.fallback)
        self.assertEqual(self.status,{'source':'fallback','status':'timeout','nested':[],'message':'synthetic','timed_out':True,'latency_ms':None,'reference_images':2})
        self.assertIs(self.fallback['reference_images'],self.contexts);self.normalize_call.assert_not_called();self.assertFalse(result['ok'])

    def test_failure_defaults_and_context_exception_partial_state(self):
        self.tool_fixture();self.provider_result={};failure=RuntimeError('synthetic context')
        self.context_call.side_effect=failure
        with self.assertRaises(RuntimeError) as raised:self.api.tool_accessory_profile_generate({'accessory':self.item})
        self.assertIs(raised.exception,failure)
        self.assertEqual(self.status['status'],'provider_error');self.assertEqual(self.status['message'],'AI provider failed to generate accessory profile.')
        self.assertEqual(self.status['latency_ms'],0);self.assertFalse(self.status['timed_out']);self.assertNotIn('reference_images',self.fallback)

    def test_reference_failure_stops_prompt_and_provider(self):
        self.tool_fixture();failure=ValueError('synthetic collect');self.invoke.side_effect=failure
        with self.assertRaises(ValueError) as raised:self.api.tool_accessory_profile_generate({'accessory':self.item})
        self.assertIs(raised.exception,failure);self.assertEqual(self.invoke.call_count,1);self.prompt_call.assert_not_called();self.normalize_call.assert_not_called();self.context_call.assert_not_called()

    def generate_fixture(self):
        self.item={'id':'a'};self.profile={'dimensions_mm':{'length_mm':3}};self.result={'profile':self.profile,'status':{'status':'ok'}};self.settings={'model':'synthetic'}
        self.invoke=self.replace('call_ai_mcp_tool',return_value=self.result);self.settings_call=self.replace('ai_detection_settings',return_value=self.settings)
        self.rename=self.replace('ensure_accessory_english_name',return_value=False);self.dimensions=self.replace('apply_ai_profile_dimensions_to_physical_size',return_value=False)

    def test_generate_mutations_and_call_arguments(self):
        self.generate_fixture();result=self.api.generate_accessory_ai_profile(self.item,allow_provider=False)
        self.invoke.assert_called_once_with('accessory.profile.generate',{'accessory':self.item,'allow_provider':False,'provider_config':self.settings})
        self.assertIs(result,self.profile);self.assertIs(self.item['ai_profile'],self.profile);self.assertIs(self.item['ai_profile_status'],self.result['status'])
        self.dimensions.assert_called_once_with(self.item,self.profile['dimensions_mm'])

    def test_generate_rename_failure_preserves_partial_assignment(self):
        self.generate_fixture();failure=RuntimeError('synthetic rename');self.rename.side_effect=failure
        with self.assertRaises(RuntimeError) as raised:self.api.generate_accessory_ai_profile(self.item)
        self.assertIs(raised.exception,failure);self.assertIs(self.item['ai_profile'],self.profile);self.assertNotIn('ai_profile_status',self.item);self.dimensions.assert_not_called()

    def test_generate_dimension_failure_and_nondict_profile(self):
        self.generate_fixture();failure=RuntimeError('synthetic dimensions');self.dimensions.side_effect=failure
        with self.assertRaises(RuntimeError) as raised:self.api.generate_accessory_ai_profile(self.item)
        self.assertIs(raised.exception,failure);self.assertIs(self.item['ai_profile_status'],self.result['status'])
        self.dimensions.reset_mock();self.result['profile']='legacy';self.assertEqual(self.api.generate_accessory_ai_profile(self.item),'legacy');self.dimensions.assert_not_called()

    def test_ensure_matching_short_circuit_returns_rename(self):
        item={'ai_profile':{'accessory_id':'a'}};self.replace('accessory_uid',return_value='a');marker=object();rename=self.replace('ensure_accessory_english_name',return_value=marker);generate=self.replace('generate_accessory_ai_profile',side_effect=AssertionError('forbidden'))
        self.assertIs(self.api.ensure_accessory_ai_profile(item,allow_provider=False),marker);rename.assert_called_once_with(item);generate.assert_not_called()

    def test_ensure_force_missing_and_mismatch_generate_once(self):
        uid=self.replace('accessory_uid',return_value='a');rename=self.replace('ensure_accessory_english_name',side_effect=AssertionError('forbidden'));generate=self.replace('generate_accessory_ai_profile',return_value={})
        for item,force in (({},False),({'ai_profile':{'accessory_id':'b'}},False),({'ai_profile':{'accessory_id':'a'}},True)):
            generate.reset_mock();self.assertTrue(self.api.ensure_accessory_ai_profile(item,force=force,allow_provider=False));generate.assert_called_once_with(item,allow_provider=False)
        rename.assert_not_called();self.assertEqual(uid.call_count,1)

    def test_callee_selection_and_cross_stage_refresh(self):
        self.generate_fixture();original=self.invoke;later=Mock(side_effect=AssertionError('Late invoke must not run'))
        def settings(kind):self.api.call_ai_mcp_tool=later;return self.settings
        self.settings_call.side_effect=settings
        self.assertIs(self.api.generate_accessory_ai_profile(self.item),self.profile)
        original.assert_called_once();later.assert_not_called()
        self.tool_fixture();initial=self.invoke;middle=Mock(side_effect=AssertionError('Intermediate invoke must not run'));final=Mock(return_value=self.provider_result);events=[]
        def collect(name,payload):events.append(name);self.api.call_ai_mcp_tool=middle;return {'references':self.references}
        def prompt(item):events.append('prompt');self.api.call_ai_mcp_tool=final;return {'test':True}
        initial.side_effect=collect;self.prompt_call.side_effect=prompt
        self.assertTrue(self.api.tool_accessory_profile_generate({'accessory':self.item})['ok'])
        self.assertEqual(events,['accessory.reference.collect','prompt']);initial.assert_called_once();middle.assert_not_called();final.assert_called_once()
        self.assertEqual(final.call_args.args[0],'provider.gemini.generate_json')

    def test_eager_defaults_json_callee_and_fixed_prompt(self):
        import hashlib
        self.tool_fixture();events=[];api=self.api
        self.stack.enter_context(patch.object(api,'AI_PROFILE_REFERENCE_IMAGES',3));self.stack.enter_context(patch.object(api,'AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE',128));self.stack.enter_context(patch.object(api,'AI_PROFILE_REFERENCE_IMAGE_QUALITY',70))
        class Payload(dict):
            def get(inner,key,default=None):
                if key=='max_reference_images':events.append((key,default));api.AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE=321;return 7
                if key=='reference_max_side':events.append((key,default));api.AI_PROFILE_REFERENCE_IMAGE_QUALITY=45;return 8
                if key=='reference_quality':events.append((key,default));return 9
                return super().get(key,default)
        early=Mock(return_value='early-json');late=Mock(side_effect=AssertionError('Late serializer forbidden'))
        self.stack.enter_context(patch.object(api.json,'dumps',early))
        def prompt(item):api.json.dumps=late;return {'synthetic':True}
        self.prompt_call.side_effect=prompt
        self.api.tool_accessory_profile_generate(Payload(accessory=self.item))
        self.assertEqual(events,[('max_reference_images',3),('reference_max_side',321),('reference_quality',45)])
        reference_payload=self.invoke.call_args_list[0].args[1]
        self.assertEqual([reference_payload[k] for k in ('max_images','max_side','quality')],[7,8,9])
        early.assert_called_once_with({'synthetic':True},ensure_ascii=False);late.assert_not_called()
        provider_payload=self.invoke.call_args_list[1].args[1];self.assertEqual(provider_payload['user_content'][0],{'type':'text','text':'early-json'})
        self.assertEqual(hashlib.sha256(provider_payload['system_prompt'].encode()).hexdigest(),'5201f38012028dc61a4cea7f4595d5244e5e911a0aa32c3c6ab2f22b79b39e66')

    def test_repeated_profile_read_late_uid_and_generation_failure(self):
        events=[];api=self.api;later=Mock(return_value='second');original=self.replace('accessory_uid',side_effect=AssertionError('Old uid forbidden'));rename=self.replace('ensure_accessory_english_name',return_value=False);generate=self.replace('generate_accessory_ai_profile',return_value={})
        class Current(dict):
            def get(inner,key,default=None):
                if key=='accessory_id':events.append('current-id');api.accessory_uid=later
                return super().get(key,default)
        first={'accessory_id':'first'};second=Current(accessory_id='second')
        class Item(dict):
            def get(inner,key,default=None):
                if key=='ai_profile':events.append('profile');return first if events.count('profile')==1 else second
                return super().get(key,default)
        item=Item();self.assertFalse(self.api.ensure_accessory_ai_profile(item));self.assertEqual(events,['profile','profile','current-id'])
        original.assert_not_called();later.assert_called_once_with(item);rename.assert_called_once_with(item);generate.assert_not_called()
        forbidden=self.replace('accessory_uid',side_effect=AssertionError('Force cannot read uid'));failure=RuntimeError('synthetic generate');generate.side_effect=failure
        with self.assertRaises(RuntimeError) as raised:self.api.ensure_accessory_ai_profile({'ai_profile':{'accessory_id':'x'}},force=True,allow_provider=False)
        self.assertIs(raised.exception,failure);forbidden.assert_not_called();generate.assert_called_once_with({'ai_profile':{'accessory_id':'x'}},allow_provider=False)

    def test_independent_generation_instances(self):
        from local_inspection_service.accessories.profile_generation import AccessoryProfileGeneration
        from local_inspection_service.accessories.profile_generation_ports import GenerationProfiles,GenerationCalls,GenerationReferences,GenerationUpdates
        records={};services={}
        names=['fallback_accessory_ai_profile','normalize_accessory_ai_profile','accessory_profile_prompt_payload','generate_accessory_ai_profile','ai_detection_settings','profile_generation_status','call_ai_mcp_tool','accessory_reference_image_contexts','AI_PROFILE_REFERENCE_IMAGES','AI_PROFILE_REFERENCE_IMAGE_MAX_SIDE','AI_PROFILE_REFERENCE_IMAGE_QUALITY','accessory_uid','ensure_accessory_english_name','apply_ai_profile_dimensions_to_physical_size']
        poisons=[self.replace(name,side_effect=AssertionError('Root capability forbidden')) for name in names]
        for tag in ('A','B'):
            events=[];records[tag]=events
            def getter(name,value,events=events):
                def read():events.append(name);return value
                return read
            profile={'tag':tag,'dimensions_mm':{'tag':tag}};status={'tag':tag};contexts=[{'tag':tag}]
            def invoke(name,payload,tag=tag,profile=profile,status=status):
                if name=='accessory.reference.collect':return {'references':[]}
                if name=='provider.gemini.generate_json':return {'ok':True,'parsed':{'tag':tag}}
                if name=='accessory.profile.generate':return {'profile':profile,'status':status}
                raise AssertionError('Unexpected tool')
            service=AccessoryProfileGeneration(
                GenerationProfiles(getter('fallback',lambda item,tag=tag:{'tag':tag}),getter('normalize',lambda raw,item,tag=tag:{'tag':tag}),getter('prompt',lambda item,tag=tag:{'tag':tag}),getter('generate',lambda item,allow_provider=True,events=events:events.append(('generate',allow_provider)) or {})),
                GenerationCalls(getter('settings',lambda kind,tag=tag:{'configured':True,'tag':tag}),getter('status',lambda settings,tag=tag:{'tag':tag}),getter('invoke',invoke)),
                GenerationReferences(getter('contexts',lambda item,contexts=contexts:contexts),getter('limit',3),getter('max_side',128),getter('quality',70)),
                GenerationUpdates(getter('uid',lambda item,tag=tag:tag),getter('rename',lambda item:False),getter('dimensions',lambda item,dimensions,events=events:events.append(('dimensions',dimensions)) or False)),
            )
            self.assertEqual(events,[])
            services[tag]=(service,profile,status,contexts)
        for tag in ('A','B','A'):
            service,profile,status,contexts=services[tag]
            generated=service.tool_accessory_profile_generate({'accessory':{'id':tag}})
            self.assertEqual(generated['profile'],{'tag':tag,'reference_images':contexts})
            item={'id':tag};self.assertIs(service.generate_accessory_ai_profile(item,allow_provider=False),profile)
            self.assertIs(item['ai_profile_status'],status)
            self.assertFalse(service.ensure_accessory_ai_profile({'ai_profile':{'accessory_id':tag}}))
            self.assertTrue(service.ensure_accessory_ai_profile({},allow_provider=False))
        for tag,events in records.items():
            self.assertEqual(set(x for x in events if isinstance(x,str)),{'fallback','normalize','prompt','generate','settings','status','invoke','contexts','limit','max_side','quality','uid','rename','dimensions'})
            self.assertEqual(events.count(('generate',False)),2 if tag=='A' else 1)
        for poison in poisons:poison.assert_not_called()


if __name__=='__main__':unittest.main()

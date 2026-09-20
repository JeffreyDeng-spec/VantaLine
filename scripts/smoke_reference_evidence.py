"""Offline original contracts for accessory reference evidence."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class ReferenceEvidenceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='reference-evidence-')))
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
    def image(self):
        import numpy as np
        return np.zeros((3, 5, 3), dtype=np.uint8)

    def asset_path(self, name='sample.PNG'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic')
        return path

    def decoder(self, **kwargs):
        import cv2
        return self.stack.enter_context(patch.object(cv2, 'imread', **kwargs))

    def test_inventory_order_mutation_and_dedup(self):
        a=self.asset_path('a.png'); b=self.asset_path('b.dat'); c=self.asset_path('c.JPG'); d=self.asset_path('default.png')
        jobs=[{'output_path':'a'},{'output_path':'skip','intermediate':True},{'output_path':'missing'}]
        item={'normalized_assets':[{'path':'b'},{'path':'a'}],'source_files':['c','bad','a']}
        paths={'a':a,'b':b,'c':c,'missing':self.root/'absent.png','bad':self.asset_path('bad.txt')}
        self.replace('candidate_image_jobs',return_value=jobs)
        resolve=self.replace('resolve_service_path',side_effect=lambda x:paths[x])
        self.replace('default_asset_for_accessory',return_value=d)
        self.assertEqual(self.api.accessory_image_paths(item),[a,b,c,d])
        self.assertEqual(jobs[0]['output_path'],str(a))
        self.assertEqual(jobs[1]['output_path'],'skip')
        self.assertEqual(jobs[2]['output_path'],'missing')
        self.assertEqual(item['normalized_assets'],[{'path':str(b)},{'path':str(a)}])
        self.assertEqual(resolve.call_args_list,[call(x) for x in ['a','missing','b','a','c','bad','a']])

    def test_inventory_missing_default_and_partial_error(self):
        a=self.asset_path('partial.png'); job={'output_path':'a'}
        self.replace('candidate_image_jobs',return_value=[job])
        error=ValueError('resolver sentinel')
        self.replace('resolve_service_path',side_effect=[a,error])
        default=self.replace('default_asset_for_accessory',return_value=None)
        with self.assertRaises(ValueError) as caught:self.api.accessory_image_paths({'normalized_assets':[{'path':'bad'}]})
        self.assertIs(caught.exception,error)
        self.assertEqual(job['output_path'],str(a))
        default.assert_not_called()

    def test_profile_paths_suffix_and_unique(self):
        a=self.asset_path('profile.WEBP'); b=self.asset_path('profile.txt')
        self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.webp'})
        self.replace('resolve_service_path',side_effect=lambda x:{'a':a,'b':b,'missing':self.root/'missing.webp'}[x])
        self.assertEqual(self.api.ai_profile_reference_paths({'ai_profile_reference_files':['a','b','a','missing']}),[a])
        self.assertEqual(self.api.ai_profile_reference_paths({'ai_profile_reference_files':None}),[])
        self.assertEqual(self.api.ai_profile_reference_paths({}),[])

    def test_context_bytes_dimensions_mime_and_id(self):
        import hashlib
        path=self.asset_path('context.PNG'); image=self.image()
        self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'})
        bounded=self.replace('bounded_text',return_value='bounded')
        decode=self.decoder(return_value=image)
        result=self.api.image_reference_context(path,'raw',4)
        self.assertEqual(result,{'accessory_id':'bounded','source_path':str(path),'sha256':hashlib.sha256(b'synthetic').hexdigest(),'mime_type':'image/png','width':5,'height':3,'ordinal':4})
        bounded.assert_called_once_with('raw',120)
        decode.assert_called_once_with(str(path),self.api.cv2.IMREAD_COLOR)

    def test_context_null_decode_keeps_hash_nonpng_jpeg(self):
        import hashlib
        path=self.asset_path('context.WEBP'); self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.webp'})
        self.decoder(return_value=None); self.replace('bounded_text',side_effect=lambda value,limit:value)
        result=self.api.image_reference_context(path,'x',1)
        self.assertEqual((result['width'],result['height'],result['mime_type']),(0,0,'image/jpeg'))
        self.assertEqual(result['sha256'],hashlib.sha256(b'synthetic').hexdigest())

    def test_context_missing_unsupported_skip_decode(self):
        self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'})
        decode=self.decoder(side_effect=AssertionError('decode forbidden'))
        self.assertIsNone(self.api.image_reference_context(self.root/'missing.png','x',1))
        self.assertIsNone(self.api.image_reference_context(self.asset_path('unsupported.txt'),'x',1))
        decode.assert_not_called()

    def test_context_oserror_only(self):
        path=self.asset_path('errors.png'); self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'})
        with patch.object(Path,'read_bytes',side_effect=OSError('read')):
            self.assertIsNone(self.api.image_reference_context(path,'x',1))
        decode=self.decoder(side_effect=OSError('decode'))
        self.assertIsNone(self.api.image_reference_context(path,'x',1))
        error=ValueError('decode'); decode.side_effect=error
        with self.assertRaises(ValueError) as caught:self.api.image_reference_context(path,'x',1)
        self.assertIs(caught.exception,error)

    def test_context_hash_does_not_use_root_hash_helper(self):
        path=self.asset_path('direct.png'); self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'})
        wrong=self.replace('file_sha256',side_effect=AssertionError('wrong hash helper'))
        self.decoder(return_value=None)
        result=self.api.image_reference_context(path,'x',1)
        self.assertEqual(len(result['sha256']),64)
        wrong.assert_not_called()

    def test_context_list_preferred_dedup_failed_and_ordinals(self):
        a=Path('a.png'); b=Path('b.png'); c=Path('c.png')
        self.replace('accessory_uid',return_value='uid')
        self.replace('ai_profile_reference_paths',return_value=[a,a,b,c])
        fallback=self.replace('first_source_ai_reference_path',side_effect=AssertionError('fallback forbidden'))
        inventory=self.replace('accessory_image_paths',side_effect=AssertionError('inventory forbidden'))
        one={'ordinal':1}; two={'ordinal':2}
        context=self.replace('image_reference_context',side_effect=[None,one,two])
        result=self.api.accessory_reference_image_contexts({},max_images=2)
        self.assertEqual(result,[one,two]); self.assertIs(result[0],one)
        self.assertEqual(context.call_args_list,[call(a,'uid',1),call(b,'uid',1),call(c,'uid',2)])
        fallback.assert_not_called(); inventory.assert_not_called()

    def test_context_list_first_source_before_inventory(self):
        p=Path('first.png'); item={}; self.replace('accessory_uid',return_value='uid')
        self.replace('ai_profile_reference_paths',return_value=[])
        source=self.replace('first_source_ai_reference_path',return_value=p)
        inventory=self.replace('accessory_image_paths',side_effect=AssertionError('inventory forbidden'))
        context=self.replace('image_reference_context',return_value={'ok':True})
        self.assertEqual(self.api.accessory_reference_image_contexts(item),[{'ok':True}])
        source.assert_called_once_with(item); context.assert_called_once_with(p,'uid',1); inventory.assert_not_called()

    def test_context_list_inventory_and_definition_bound_limit(self):
        self.replace('accessory_uid',return_value='uid'); self.replace('ai_profile_reference_paths',return_value=[])
        self.replace('first_source_ai_reference_path',return_value=None)
        self.replace('accessory_image_paths',return_value=[Path(str(i)) for i in range(5)])
        context=self.replace('image_reference_context',side_effect=lambda p,uid,n:{'n':n})
        self.replace('AI_PROFILE_REFERENCE_IMAGES',new=0)
        self.assertEqual(self.api.accessory_reference_image_contexts({}),[{'n':1},{'n':2},{'n':3}])
        self.assertEqual(context.call_count,3)
        context.reset_mock()
        self.assertEqual(len(self.api.accessory_reference_image_contexts({},max_images=4)),4)
        self.assertEqual(context.call_count,4)

    def test_context_zero_limit_still_one_attempt(self):
        self.replace('accessory_uid',return_value='uid')
        self.replace('ai_profile_reference_paths',return_value=[Path('a'),Path('b')])
        context=self.replace('image_reference_context',return_value=None)
        self.assertEqual(self.api.accessory_reference_image_contexts({},max_images=0),[])
        context.assert_called_once_with(Path('a'),'uid',1)
        context.reset_mock(); context.return_value={'ok':True}
        self.assertEqual(self.api.accessory_reference_image_contexts({},max_images=0),[{'ok':True}])
        context.assert_called_once_with(Path('a'),'uid',1)

    def test_screen_copy_normalization_and_fallback(self):
        nested=[]; options={'blue':{'name':'blue','nested':nested},'green':{'name':'green'}}
        self.replace('CHROMA_SCREEN_OPTIONS',new=options)
        result=self.api.normalize_chroma_screen({'name':' BLUE '})
        self.assertEqual(result,options['blue']); self.assertIsNot(result,options['blue']); self.assertIs(result['nested'],nested)
        self.assertEqual(self.api.normalize_chroma_screen('unknown'),{'name':'green'})
        self.assertEqual(self.api.normalize_chroma_screen(None),{'name':'green'})

    def test_chroma_exact_thresholds_and_signed_arithmetic(self):
        import numpy as np
        cases=[('blue',[[160,110,110],[159,110,110],[190,140,110],[189,140,110],[255,0,0]], [True,False,True,False,True]),
               ('red',[[110,110,160],[110,110,159],[120,120,170],[120,120,169],[0,0,255]], [True,False,True,False,True]),
               ('green',[[110,160,110],[110,159,110],[110,160,111],[111,161,110],[0,255,0]], [True,False,False,False,True])]
        for name,pixels,expected in cases:
            result=self.api.saturated_chroma_mask(np.array([pixels],dtype=np.uint8),{'name':name})
            self.assertEqual(result.tolist(),[expected]); self.assertEqual(result.dtype,np.dtype(bool))
        dark=np.array([[[255,0,255]]],dtype=np.uint8)
        self.assertEqual(self.api.saturated_chroma_mask(dark,{}).tolist(),[[False]])

    def test_chroma_invalid_shape_and_unknown_screen(self):
        import numpy as np
        for image in (None,np.zeros((2,2),dtype=np.uint8)):
            result=self.api.saturated_chroma_mask(image,{})
            self.assertEqual(result.shape,(0,0)); self.assertEqual(result.dtype,np.dtype(bool))
        image=np.array([[[0,255,0]]],dtype=np.uint8)
        self.assertEqual(self.api.saturated_chroma_mask(image,{'name':'BLUE'}).tolist(),[[True]])

    def test_fraction_max_skips_missing_empty_and_empty_mask(self):
        import numpy as np
        item={}; screen={'name':'green'}
        normalize=self.replace('normalize_chroma_screen',return_value=screen)
        refs=self.replace('accessory_reference_image_contexts',return_value=[{'source_path':str(i)} for i in range(5)])
        resolve=self.replace('resolve_service_path',side_effect=lambda x:Path(x))
        images=[None,np.empty((0,0,3),dtype=np.uint8),self.image(),self.image(),self.image()]
        decode=self.decoder(side_effect=images)
        mask=self.replace('saturated_chroma_mask',side_effect=[np.zeros((0,0),dtype=bool),np.array([[True,False]]),np.array([[True,True,True,False]])])
        self.assertEqual(self.api.accessory_reference_chroma_fraction(item,'green',max_images=5),.75)
        normalize.assert_called_once_with('green'); refs.assert_called_once_with(item,max_images=5)
        self.assertEqual(resolve.call_count,5); self.assertEqual(decode.call_count,5); self.assertEqual(mask.call_count,3)
        self.assertTrue(all(c.args[1] is screen for c in mask.call_args_list))

    def test_fraction_empty_and_error_propagation(self):
        self.replace('normalize_chroma_screen',return_value={'name':'green'})
        refs=self.replace('accessory_reference_image_contexts',return_value=[])
        self.assertEqual(self.api.accessory_reference_chroma_fraction({},'green'),0.0)
        refs.return_value=[{'source_path':'x'}]; self.replace('resolve_service_path',return_value=Path('x'))
        error=OSError('decoder'); self.decoder(side_effect=error)
        with self.assertRaises(OSError) as caught:self.api.accessory_reference_chroma_fraction({},'green')
        self.assertIs(caught.exception,error)

    def test_inventory_resolver_selected_before_job_get(self):
        path=self.asset_path('timing.png')
        old=self.replace('resolve_service_path',return_value=path)
        late=Mock(return_value=path); api=self.api
        class Job(dict):
            def get(self,key,default=None):
                if key=='output_path':api.resolve_service_path=late
                return super().get(key,default)
        job=Job(output_path='raw')
        self.replace('candidate_image_jobs',return_value=[job]); self.replace('default_asset_for_accessory',return_value=None)
        self.assertEqual(self.api.accessory_image_paths({}),[path])
        old.assert_called_once_with('raw'); late.assert_not_called()
        self.assertEqual(job['output_path'],str(path))

    def test_screen_fallback_reads_current_options_after_lookup(self):
        api=self.api; late={'green':{'name':'green','source':'late'}}
        class Options(dict):
            def get(self,name,default=None):
                api.CHROMA_SCREEN_OPTIONS=late
                return None
        self.replace('CHROMA_SCREEN_OPTIONS',new=Options())
        self.assertEqual(self.api.normalize_chroma_screen('missing'),{'name':'green','source':'late'})

    def test_context_bounded_oserror_remains_outside_catch(self):
        path=self.asset_path('bounded.png'); self.replace('IMAGE_REFERENCE_SUFFIXES',new={'.png'}); self.decoder(return_value=None)
        error=OSError('bounded outside try'); self.replace('bounded_text',side_effect=error)
        with self.assertRaises(OSError) as caught:self.api.image_reference_context(path,'id',1)
        self.assertIs(caught.exception,error)

    def test_suffix_policy_read_after_exists(self):
        path=self.asset_path('dynamic.png'); api=self.api
        def exists(p):
            api.IMAGE_REFERENCE_SUFFIXES={'.png'}
            return True
        self.replace('IMAGE_REFERENCE_SUFFIXES',new=set()); self.replace('resolve_service_path',return_value=path)
        with patch.object(Path,'exists',exists):
            self.assertEqual(self.api.ai_profile_reference_paths({'ai_profile_reference_files':['raw']}),[path])
        api.IMAGE_REFERENCE_SUFFIXES=set(); self.decoder(return_value=None)
        with patch.object(Path,'exists',exists):
            self.assertEqual(self.api.image_reference_context(path,'id',1)['source_path'],str(path))

    def test_context_callback_refreshed_and_empty_dict_not_counted(self):
        a=Path('a'); b=Path('b'); api=self.api; record={'ok':True}
        late=Mock(return_value=record)
        def first(*args):
            api.image_reference_context=late
            return {}
        early=self.replace('image_reference_context',side_effect=first)
        self.replace('accessory_uid',return_value='id'); self.replace('ai_profile_reference_paths',return_value=[a,a,b])
        self.assertEqual(self.api.accessory_reference_image_contexts({},max_images=2),[record])
        early.assert_called_once_with(a,'id',1); late.assert_called_once_with(b,'id',1)

    def test_fraction_resolver_and_mask_read_timing(self):
        import numpy as np
        api=self.api; path=Path('timed.png'); image=self.image(); screen={'name':'green'}
        late_resolve=Mock(return_value=path)
        class Ref(dict):
            def get(self,key,default=None):
                api.resolve_service_path=late_resolve
                return super().get(key,default)
        self.replace('normalize_chroma_screen',return_value=screen)
        self.replace('accessory_reference_image_contexts',return_value=[Ref(source_path='raw')])
        early_resolve=self.replace('resolve_service_path',return_value=path)
        late_mask=Mock(return_value=np.array([[True,False]])); early_mask=self.replace('saturated_chroma_mask',return_value=np.array([[False,False]]))
        def decode(*args):
            api.saturated_chroma_mask=late_mask
            return image
        self.decoder(side_effect=decode)
        self.assertEqual(self.api.accessory_reference_chroma_fraction({},'green'),.5)
        early_resolve.assert_called_once_with('raw'); late_resolve.assert_not_called(); early_mask.assert_not_called()
        late_mask.assert_called_once_with(image,screen)

    def test_two_reference_services_keep_dependencies_separate(self):
        from local_inspection_service.accessories.reference_evidence import ReferenceEvidence
        from local_inspection_service.accessories.reference_evidence_ports import ReferencePolicy,ReferencePaths,ReferenceContexts,ReferenceChroma
        import numpy as np
        names=['IMAGE_REFERENCE_SUFFIXES','CHROMA_SCREEN_OPTIONS','resolve_service_path','candidate_image_jobs','default_asset_for_accessory','ai_profile_reference_paths','first_source_ai_reference_path','accessory_image_paths','accessory_uid','bounded_text','image_reference_context','accessory_reference_image_contexts','normalize_chroma_screen','saturated_chroma_mask']
        poisons={name:self.replace(name,new=Mock(side_effect=AssertionError('root '+name))) for name in names}
        def build(tag, pixels):
            path=self.asset_path(tag+'.png'); image=np.full((3,5,3),pixels,dtype=np.uint8)
            record={'tag':tag}; screen={'name':'green','tag':tag}
            mask=np.array([[True,False,False,False]]) if tag=='first' else np.array([[True,True,True,False]])
            ops={'resolve':Mock(return_value=path),'jobs':Mock(side_effect=lambda item:[{'output_path':'raw'}]),'default':Mock(return_value=path),'preferred':Mock(return_value=[path]),'first_source':Mock(return_value=path),'inventory':Mock(return_value=[path]),'uid':Mock(return_value=tag),'bounded':Mock(return_value=tag),'context':Mock(return_value=record),'references':Mock(return_value=[{'source_path':str(path)}]),'normalize':Mock(return_value=screen),'mask':Mock(return_value=mask)}
            getters={name:Mock(return_value=value) for name,value in {'suffixes':{'.png'},'screens':{'green':screen},**ops}.items()}
            service=ReferenceEvidence(ReferencePolicy(getters['suffixes'],getters['screens']),ReferencePaths(*(getters[n] for n in ['resolve','jobs','default','preferred','first_source','inventory'])),ReferenceContexts(*(getters[n] for n in ['uid','bounded','context','references'])),ReferenceChroma(getters['normalize'],getters['mask']))
            for getter in getters.values():getter.assert_not_called()
            return service,ops,path,image,record,screen,float(mask.mean())
        a=build('first',30);b=build('second',70)
        images={str(a[2]):a[3],str(b[2]):b[3]}; decode=self.decoder(side_effect=lambda path,mode:images[path])
        for service,ops,path,image,record,screen,fraction in (a,b,a):
            self.assertEqual(service.accessory_image_paths({}),[path])
            self.assertEqual(service.ai_profile_reference_paths({'ai_profile_reference_files':['raw']}),[path])
            context=service.image_reference_context(path,'raw',4)
            self.assertEqual(context['accessory_id'],record['tag']); self.assertEqual((context['width'],context['height']),(5,3)); self.assertEqual(context['ordinal'],4)
            self.assertEqual(service.accessory_reference_image_contexts({},max_images=2),[record])
            normalized=service.normalize_chroma_screen('green'); self.assertEqual(normalized,screen); self.assertIsNot(normalized,screen)
            self.assertEqual(service.accessory_reference_chroma_fraction({},'green',max_images=2),fraction)
            ops['references'].assert_called_with({},max_images=2); ops['context'].assert_called_with(path,record['tag'],1)
        self.assertEqual([a[1]['resolve'].call_count,b[1]['resolve'].call_count],[6,3])
        self.assertEqual([a[1]['bounded'].call_count,b[1]['bounded'].call_count],[2,1])
        self.assertEqual([a[1]['mask'].call_count,b[1]['mask'].call_count],[2,1])
        for unit in (a,b):
            unit[1]['first_source'].assert_not_called();unit[1]['inventory'].assert_not_called()
        self.assertEqual(decode.call_count,6)
        for poison in poisons.values():poison.assert_not_called()

if __name__=='__main__':unittest.main()

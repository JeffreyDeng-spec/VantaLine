"""Offline ordinary image/video upload and projection baseline; no camera dispatch."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,AsyncMock,patch,call
import asyncio,io,os,sys,tempfile,unittest
import numpy as np
sys.path.insert(0,str(Path.cwd()))
from scripts.smoke_ai_detection_analysis import BindingResolver

def capture_upload_window(api, Fixture, root, site, mode):
    events=[]
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture(Path(root)/(site+'-'+mode));f.bind(api,stack)
        ns=api.__dict__;np_original=ns['np'];copy_original=ns['shutil'].copyfileobj
        def wrap(label,callback):
            def invoke(*a,**k):
                events.append(label)
                return callback(*a,**k)
            return invoke
        def phase():
            events.append('prior')
            if mode!='ordinary':install(None if mode=='missing' else 'B')
        def argument():
            events.append('argument');install('C')
        if site in ('image_safe','video_safe'):
            callbacks={k:wrap(k,lambda name:'safe.FILE.MP4') for k in 'ABC'}
            def install(label):ns['safe_name']=None if label is None else callbacks[label]
            class Upload:
                read=f.upload.read
                file=f.upload.file
                @property
                def filename(self):argument();return 'original.JPG'
            f.upload=Upload()
            if site=='image_safe':f.decode.side_effect=lambda *a:phase() or f.image
            else:f.permission.side_effect=lambda *a:phase()
            invoke=lambda:asyncio.run((api.analyze_image if site=='image_safe' else api.analyze_video)(f.upload,'model'))
        elif site=='array_frombuffer':
            callbacks={k:wrap(k,np_original.frombuffer) for k in 'ABC'}
            class Arrays:
                def __init__(self,label):self.frombuffer=None if label is None else callbacks[label]
                @property
                def uint8(self):argument();return np_original.uint8
            def install(label):ns['np']=Arrays(label)
            async def read():phase();return b'image bytes'
            f.upload.read=read;invoke=lambda:asyncio.run(api.analyze_image(f.upload,'model'))
        elif site=='image_decode':
            callbacks={k:wrap(k,lambda *a:f.image) for k in 'ABC'}
            class Images:
                def __init__(self,label):self.imdecode=None if label is None else callbacks[label]
                @property
                def IMREAD_COLOR(self):argument();return 1
            def install(label):ns['cv2']=Images(label)
            def buffer(*a):
                value=np_original.frombuffer(*a);phase();return value
            ns['np']=SimpleNamespace(frombuffer=buffer,uint8=np_original.uint8)
            invoke=lambda:asyncio.run(api.analyze_image(f.upload,'model'))
        elif site=='video_copy':
            callbacks={k:wrap(k,copy_original) for k in 'ABC'}
            def install(label):ns['shutil']=SimpleNamespace(copyfileobj=None if label is None else callbacks[label])
            original_open=Path.open
            class Opened:
                def __init__(self,handle):self.handle=handle
                def __enter__(self):
                    result=self.handle.__enter__();phase();return result
                def __exit__(self,*a):return self.handle.__exit__(*a)
            def opened(path,*a,**k):
                handle=original_open(path,*a,**k)
                return Opened(handle) if a and a[0]=='wb' else handle
            stack.enter_context(patch.object(Path,'open',opened))
            stream=f.upload.file
            class Upload:
                filename='original.JPG'
                read=f.upload.read
                @property
                def file(self):argument();return stream
            f.upload=Upload();invoke=lambda:asyncio.run(api.analyze_video(f.upload,'model'))
        elif site=='video_capture':
            callbacks={k:wrap(k,lambda *a:f.cap) for k in 'ABC'}
            def install(label):ns['cv2']=SimpleNamespace(VideoCapture=None if label is None else callbacks[label],CAP_PROP_FPS=5)
            armed=[False]
            class CapturedPath(type(Path())):
                def __str__(self):
                    if armed[0]:argument()
                    return super().__str__()
            ns['UPLOAD_DIR']=CapturedPath(f.root)
            def config():phase();armed[0]=True;return f.config
            f.load.side_effect=config;invoke=lambda:asyncio.run(api.analyze_video(f.upload,'model'))
        elif site=='summary_strings':
            callbacks={k:wrap(k,lambda items,**kw:list(items)) for k in 'ABC'}
            def install(label):ns['string_list']=None if label is None else callbacks[label]
            class AI(dict):
                def get(self,key,*a):
                    if key=='error':argument()
                    return super().get(key,*a)
            class Frame(dict):
                reads=0
                def get(self,key,*a):
                    if key=='ai':
                        self.reads+=1
                        if self.reads==1:phase()
                    return super().get(key,*a)
            frames=[Frame(ai=AI(error='err',latency_ms=0),frame_index=0)]
            invoke=lambda:api.video_ai_summary(frames)
        else:raise AssertionError(site)
        install('A');error=None
        try:invoke()
        except BaseException as caught:error=caught
        expected=[] if mode=='missing' else ['A' if mode=='ordinary' else 'B']
        assert [x for x in events if x in 'ABC']==expected,(site,mode,events,repr(error))
        assert 'argument' in events,(site,mode,events,repr(error))
        if mode=='missing':assert type(error) is TypeError,(site,mode,repr(error),events)
        else:assert error is None,(site,mode,repr(error),events)
        assert events.index('prior')<events.index('argument'),events
        assert f.resolver.current_snapshot() is None
        return events

def capture_upload_refresh(api,Fixture,root,site):
    events=[]
    with ExitStack() as stack:
        stack.enter_context(patch.dict(api.__dict__))
        f=Fixture(Path(root)/site);f.bind(api,stack);ns=api.__dict__
        if site=='analyze':
            def b(*a,**k):events.append('B');return f.result
            def a(*args,**kwargs):events.append('A');ns['analyze_bgr']=b;return f.result
            ns['analyze_bgr']=a;expected=['A','B','B']
        elif site=='frame':
            real=api.video_frame_result_payload
            def b(*args):events.append('B');return real(*args)
            def a(*args):events.append('A');ns['video_frame_result_payload']=b;return real(*args)
            ns['video_frame_result_payload']=a;expected=['A','B','B']
        elif site=='summary':
            real=api.video_ai_summary
            def a(*args):events.append('A');return real(*args)
            def b(*args):events.append('B');return real(*args)
            ns['video_ai_summary']=a
            f.cap.release.side_effect=lambda:ns.__setitem__('video_ai_summary',b)
            expected=['B']
        else:raise AssertionError(site)
        error=None
        try:asyncio.run(api.analyze_video(f.upload,'model'))
        except BaseException as caught:error=caught
        assert error is None,(site,repr(error),events)
        assert events==expected,(site,events)
        assert f.resolver.current_snapshot() is None
        return events

class UploadFixture:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.events=[];self.resolver=BindingResolver()
        self.image=np.zeros((3,4,3),dtype=np.uint8);self.frames=[self.image]*7;self.index=0
        self.config={'video':{'sample_every_seconds':1,'max_frames':3}}
        self.result={'passed':True,'annotated_url':'preview','rule':{'missing':[]},'detections':[]}
        def port(name,value):return Mock(side_effect=lambda *a,**kw:self.events.append(name) or value())
        self.ensure=port('ensure',lambda:None);self.permission=port('permission',lambda:None);self.safe=port('safe',lambda:'safe.FILE.MP4')
        self.decode=port('decode',lambda:self.image);self.analyze=port('analyze',lambda:self.result);self.load=port('config',lambda:self.config)
        self.cap=SimpleNamespace(isOpened=port('opened',lambda:True),get=port('fps',lambda:2.0),read=Mock(side_effect=self.read),release=port('release',lambda:None))
        self.video=port('capture',lambda:self.cap);self.cv=SimpleNamespace(imdecode=self.decode,IMREAD_COLOR=1,VideoCapture=self.video,CAP_PROP_FPS=5)
        self.upload=SimpleNamespace(filename='original.JPG',read=AsyncMock(return_value=b'image bytes'),file=io.BytesIO(b'video bytes'))
    def read(self):
        self.events.append('read')
        if self.index>=len(self.frames):return False,None
        value=self.frames[self.index];self.index+=1;return True,value
    def bind(self,api,stack):
        for name,value in {'ensure_dirs':self.ensure,'require_analyze_model_permission':self.permission,'safe_name':self.safe,'UPLOAD_DIR':self.root,'cv2':self.cv,'analyze_bgr':self.analyze,'load_config':self.load,'model_profile_service':self.resolver}.items():stack.enter_context(patch.object(api,name,value))

class UploadContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='upload-baseline-');root=Path(cls.tmp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):self.stack.enter_context(patch(name,side_effect=AssertionError('unexpected external operation')))
        self.f=UploadFixture(Path(self.tmp.name)/self.id().split('.')[-1]);self.f.bind(self.api,self.stack)
    def image(self):return asyncio.run(self.api.analyze_image(self.f.upload,'model'))
    def video(self):return asyncio.run(self.api.analyze_video(self.f.upload,'model'))
    def test_image_decodes_writes_original_bytes_and_returns_same_result(self):
        f=self.f;result=self.image();self.assertIs(result,f.result);self.assertEqual(f.events,['ensure','permission','decode','safe','analyze'])
        f.permission.assert_called_once_with('model');f.upload.read.assert_awaited_once_with();f.safe.assert_called_once_with('original.JPG')
        args=f.decode.call_args.args;self.assertEqual(args[1],1);self.assertEqual(args[0].dtype,np.uint8);self.assertEqual(args[0].tobytes(),b'image bytes')
        path=f.root/'safe.FILE.jpg';self.assertEqual(path.read_bytes(),b'image bytes');self.assertIs(f.analyze.call_args.args[0],f.image)
        self.assertEqual(f.analyze.call_args.args[1:],('safe.FILE','model'));self.assertEqual(f.analyze.call_args.kwargs,{'image_path':path})
    def test_image_suffix_default_and_original_filename_case(self):
        self.f.upload.filename='no_suffix';self.image();self.assertTrue((self.f.root/'safe.FILE.png').exists())
    def test_image_decode_failure_does_not_write_or_analyze(self):
        f=self.f;f.decode.side_effect=None;f.decode.return_value=None
        with self.assertRaises(self.api.HTTPException) as error:self.image()
        self.assertEqual((error.exception.status_code,error.exception.detail),(400,'Could not decode image'));f.safe.assert_not_called();f.analyze.assert_not_called();self.assertEqual(list(f.root.iterdir()),[])
    def test_image_permission_precedes_upload_and_unknown_failure_is_not_retried(self):
        for stage in ('ensure','permission','read','decode','safe','analyze'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=UploadFixture(self.f.root/stage);f.bind(self.api,stack);callback=f.upload.read if stage=='read' else getattr(f,stage);original=callback.side_effect;calls=[0];error=RuntimeError(stage)
                def once(*args,**kwargs):
                    calls[0]+=1
                    if calls[0]==1:raise error
                    return original(*args,**kwargs) if original else b'image bytes'
                callback.side_effect=once
                with self.assertRaises(RuntimeError) as caught:asyncio.run(self.api.analyze_image(f.upload,'model'))
                self.assertIs(caught.exception,error);self.assertEqual(calls,[1])
                if stage in ('ensure','permission'):f.upload.read.assert_not_awaited()
                self.assertEqual((f.root/'safe.FILE.jpg').exists(),stage=='analyze')
    def test_video_samples_stride_and_releases_after_success(self):
        f=self.f;result=self.video();self.assertEqual((f.root/'safe.FILE.MP4').read_bytes(),b'video bytes');f.upload.read.assert_not_awaited()
        self.assertEqual(f.analyze.call_args_list,[call(f.image,'safe.FILE_frame_000000','model'),call(f.image,'safe.FILE_frame_000002','model'),call(f.image,'safe.FILE_frame_000004','model')]);f.cap.release.assert_called_once_with()
        self.assertEqual(result,{'request_id':'safe.FILE','passed':True,'sampled_frames':3,'passed_frames':3,'pass_rate':1.0,'preview_url':'preview','ai':None,'frames':[{'frame_index':i,'timestamp_seconds':float(i/2),'passed':True,'missing':[],'detections':0} for i in (0,2,4)]})
        self.assertEqual(f.resolver.records,[{}]);self.assertIsNone(f.resolver.current_snapshot())
    def test_video_fps_fallback_minimum_stride_and_empty_frames(self):
        f=self.f;f.cap.get.side_effect=None;f.cap.get.return_value=0;f.config['video']={'sample_every_seconds':0,'max_frames':2}
        result=self.video();self.assertEqual([r['frame_index'] for r in result['frames']],[0,1]);self.assertEqual(result['frames'][1]['timestamp_seconds'],0.033)
        f.config['video']['max_frames']=0;result=self.video();self.assertEqual((result['passed'],result['sampled_frames'],result['pass_rate'],result['preview_url']),(False,0,0.0,None))
    def test_video_unopened_keeps_uploaded_file_and_original_error(self):
        f=self.f;f.cap.isOpened.side_effect=None;f.cap.isOpened.return_value=False
        with self.assertRaises(self.api.HTTPException) as caught:self.video()
        self.assertEqual((caught.exception.status_code,caught.exception.detail),(400,'Could not open video'));self.assertTrue((f.root/'safe.FILE.MP4').exists());f.cap.read.assert_not_called();f.cap.release.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())
    def test_video_failures_preserve_original_release_and_snapshot_boundaries(self):
        for stage in ('ensure','permission','safe','load','video','opened','fps','read','analyze','release'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=UploadFixture(self.f.root/stage);f.bind(self.api,stack);callback=getattr(f.cap,{'opened':'isOpened','fps':'get'}.get(stage,stage)) if stage in ('opened','fps','read','release') else getattr(f,stage);original=callback.side_effect;seen=[0];error=RuntimeError(stage)
                def once(*args,**kwargs):
                    seen[0]+=1
                    if seen[0]==1:raise error
                    return original(*args,**kwargs)
                callback.side_effect=once
                with self.assertRaises(RuntimeError) as caught:asyncio.run(self.api.analyze_video(f.upload,'model'))
                self.assertIs(caught.exception,error);self.assertEqual(seen,[1]);self.assertIsNone(f.resolver.current_snapshot());self.assertEqual(f.cap.release.call_count,int(stage=='release'))
    def test_video_ambient_binding_and_missing_resolver(self):
        f=self.f;ambient={'pipeline':{'version':18}};snapshots=[]
        f.analyze.side_effect=lambda *a,**k:snapshots.append(f.resolver.current_snapshot()) or f.result
        with f.resolver.scope(ambient):self.video();self.assertIs(f.resolver.current_snapshot(),ambient)
        self.assertTrue(all(s is ambient for s in snapshots));self.assertEqual(f.resolver.records,[])
        with patch.object(self.api,'model_profile_service',None):
            with self.assertRaises(RuntimeError):self.video()
    def test_video_output_limits_do_not_change_summary_counts(self):
        f=self.f;f.config['video']={'sample_every_seconds':0,'max_frames':205};f.frames=[f.image]*205
        result=self.video();self.assertEqual((len(result['frames']),result['sampled_frames'],result['passed_frames']),(200,205,205));self.assertEqual(f.analyze.call_count,205)
    def test_frame_projection_keeps_ai_aliases_and_compact_native_fields(self):
        rule={'missing':['a']};detections=[{'x':1}];ai={'error':'timeout'};model={'is_ai_detection':True};source={'rule':rule,'detections':detections,'ai':ai,'model':model,'passed':False,'annotated_url':'x'}
        value=self.api.video_frame_result_payload(source,3,2);self.assertIs(value['rule'],rule);self.assertIs(value['model'],model);self.assertIs(value['ai'],ai);self.assertIs(value['detection_items'],detections);self.assertIs(value['missing'],rule['missing']);self.assertEqual(value['timestamp_seconds'],1.5)
        source['ai']={};source['model']={};compact=self.api.video_frame_result_payload(source,0,30);self.assertEqual(set(compact),{'frame_index','timestamp_seconds','passed','missing','detections'})
    def test_frame_projection_malformed_fields_and_zero_fps(self):
        value=self.api.video_frame_result_payload({'rule':None,'detections':{},'ai':'bad','model':[]},1,30);self.assertEqual(value,{'frame_index':1,'timestamp_seconds':0.033,'passed':False,'missing':[],'detections':0})
        with self.assertRaises(ZeroDivisionError):self.api.video_frame_result_payload({},1,0)
    def test_summary_filters_ai_preserves_first_timeout_and_provider_order(self):
        frames=[{'ai':None},{'frame_index':2,'ai':{'timed_out':True,'latency_ms':'5'}},{'frame_index':3,'ai':{'error':'boom','provider_status':'ready','latency_ms':7}}]
        value=self.api.video_ai_summary(frames);self.assertEqual(value,{'frame_count':2,'timed_out':True,'errors':['boom'],'first_error':None,'first_error_frame_index':2,'provider_status':'ready','total_latency_ms':12})
        self.assertIsNone(self.api.video_ai_summary([{}, {'ai':[]}]))
    def test_summary_uses_exact_error_formatter_limits_and_propagates_invalid_latency(self):
        strings=Mock(return_value=['formatted']);frames=[{'frame_index':1,'ai':{'error':'source','latency_ms':1}}]
        with patch.object(self.api,'string_list',strings):value=self.api.video_ai_summary(frames)
        strings.assert_called_once_with(['source'],max_items=8,max_len=180);self.assertIs(value['errors'],strings.return_value)
        frames[0]['ai']['latency_ms']='bad'
        with self.assertRaises(ValueError):self.api.video_ai_summary(frames)


    def test_upload_writes_and_copy_fail_once_preserving_partial_evidence(self):
        for stage in ('image_write','video_copy'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=UploadFixture(self.f.root/stage);f.bind(self.api,stack);seen=[0];error=OSError('partial upload');normal=Path.write_bytes
                if stage=='image_write':
                    def write(path,data):
                        seen[0]+=1
                        if seen[0]==1:normal(path,data[:3]);raise error
                        return normal(path,data)
                    stack.enter_context(patch.object(Path,'write_bytes',write))
                else:
                    normal_copy=self.api.shutil.copyfileobj
                    def copy(source,destination):
                        seen[0]+=1
                        if seen[0]==1:destination.write(source.read(3));raise error
                        return normal_copy(source,destination)
                    stack.enter_context(patch.object(self.api.shutil,'copyfileobj',copy))
                with self.assertRaises(OSError) as caught:asyncio.run((self.api.analyze_image if stage=='image_write' else self.api.analyze_video)(f.upload,'model'))
                self.assertIs(caught.exception,error);self.assertEqual(seen,[1]);f.analyze.assert_not_called();f.video.assert_not_called()
                self.assertEqual((f.root/('safe.FILE.jpg' if stage=='image_write' else 'safe.FILE.MP4')).read_bytes(),b'ima' if stage=='image_write' else b'vid')
                self.assertIsNone(f.resolver.current_snapshot())

    def test_video_end_of_stream_mixed_passes_and_first_preview(self):
        f=self.f;f.frames=[f.image]*3;f.config['video']={'sample_every_seconds':0,'max_frames':9};calls=[0]
        def analyze(*args):
            calls[0]+=1
            return {**f.result,'passed':calls[0]!=2,'annotated_url':None if calls[0]==1 else 'preview'+str(calls[0])}
        f.analyze.side_effect=analyze;value=self.video()
        self.assertEqual((value['passed'],value['sampled_frames'],value['passed_frames'],value['pass_rate'],value['preview_url']),(False,3,2,0.6667,'preview2'))
        self.assertEqual(f.cap.read.call_count,4);f.cap.release.assert_called_once()

    def test_video_invalid_config_preserves_failure_before_release(self):
        for field,value in [('sample_every_seconds','bad'),('max_frames','bad')]:
            with self.subTest(field=field),ExitStack() as stack:
                f=UploadFixture(self.f.root/field);f.bind(self.api,stack);f.config['video'][field]=value
                with self.assertRaises(ValueError):asyncio.run(self.api.analyze_video(f.upload,'model'))
                f.cap.read.assert_not_called();f.cap.release.assert_not_called();f.analyze.assert_not_called();self.assertIsNone(f.resolver.current_snapshot())


    def test_independent_upload_services_keep_account_paths_and_bindings(self):
        from local_inspection_service.detection.upload_ports import UploadAccess,UploadPaths,VideoResults
        from local_inspection_service.detection.image_upload import ImageUpload
        from local_inspection_service.detection.video_upload import VideoUpload
        from local_inspection_service.detection.video_results import VideoSummary,video_frame_result_payload
        from local_inspection_service.model_profiles.snapshots import pinned
        services=[];strings=self.api.string_list;copies=self.api.shutil
        for owner in ('alice','bob'):
            f=UploadFixture(self.f.root/owner);f.result={**f.result,'owner':owner};observed=[]
            def analyze(*args,f=f,observed=observed,**kwargs):observed.append(f.resolver.current_snapshot());return f.result
            access=UploadAccess(f.ensure,f.permission);paths=UploadPaths(lambda f=f:f.safe,lambda f=f:f.root)
            image=ImageUpload(access,paths,lambda:np,lambda f=f:f.cv,analyze);summary=VideoSummary(lambda:strings)
            video=VideoUpload(access,paths,lambda:copies,f.load,lambda f=f:f.cv,analyze,VideoResults(video_frame_result_payload,summary.video_ai_summary))
            self.assertEqual(f.events,[]);self.assertEqual(list(f.root.iterdir()),[])
            invoke=pinned(lambda f=f:f.resolver)(video.analyze_video)
            services.append((f,image,invoke,observed))
        with ExitStack() as stack:
            for name in ('ensure_dirs','require_analyze_model_permission','safe_name','load_config','analyze_bgr','video_frame_result_payload','video_ai_summary'):
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root dependency')))
            stack.enter_context(patch.object(self.api,'cv2',object()));stack.enter_context(patch.object(self.api,'UPLOAD_DIR',object()))
            for f,image,video,observed in services:
                self.assertIs(asyncio.run(image.analyze_image(f.upload,'image-model')),f.result);self.assertIsNone(observed[0])
                value=asyncio.run(video(f.upload,'video-model'));self.assertTrue(value['passed']);self.assertTrue(all(s is not None for s in observed[1:]));self.assertIsNone(f.resolver.current_snapshot())
                self.assertEqual((f.root/'safe.FILE.jpg').read_bytes(),b'image bytes');self.assertEqual((f.root/'safe.FILE.MP4').read_bytes(),b'video bytes')
                self.assertEqual(f.permission.call_args_list,[call('image-model'),call('video-model')])
        self.assertNotEqual(services[0][0].root,services[1][0].root)

    def test_callback_capture_before_arguments_and_after_prior_effects(self):
        for site in ('image_safe','video_safe','array_frombuffer','image_decode','video_copy','video_capture','summary_strings'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode):capture_upload_window(self.api,UploadFixture,self.f.root,site,mode)


    def test_upload_callbacks_refresh_between_frames_and_after_release(self):
        for site in ('analyze','frame','summary'):
            with self.subTest(site=site):capture_upload_refresh(self.api,UploadFixture,self.f.root,site)

    def test_original_mapping_reads_preserve_first_failure_without_retry(self):
        for mode in ('frame_ai','frame_model','summary_error','summary_timeout','video'):
            def exercise(target=None):
                with ExitStack() as stack:
                    f=UploadFixture(self.f.root/(mode+str(target)));f.bind(self.api,stack);events=[];seen={};error=RuntimeError('selected mapping read')
                    class Mapping(dict):
                        def __init__(inner,owner,**values):super().__init__(values);inner.owner=owner
                        def visit(inner,key):
                            pair=(inner.owner,key);seen[pair]=seen.get(pair,0)+1;event=(*pair,seen[pair]);events.append(event)
                            if event==target:raise error
                        def get(inner,key,default=None):inner.visit(key);return super().get(key,default)
                        def __getitem__(inner,key):inner.visit(key);return super().__getitem__(key)
                    if mode.startswith('frame'):
                        result=Mapping('result',rule=Mapping('rule',missing=['a']),detections=[1],model=Mapping('model',is_ai_detection=True),ai=Mapping('ai',**({'error':'x'} if mode=='frame_ai' else {})),passed=True,annotated_url='x')
                        invoke=lambda:self.api.video_frame_result_payload(result,2,30)
                    elif mode.startswith('summary'):
                        frames=[Mapping('frame',ai=Mapping('ai',error='x' if mode=='summary_error' else '',timed_out=True,provider_status='ready',latency_ms=5),frame_index=3)]
                        invoke=lambda:self.api.video_ai_summary(frames)
                    else:
                        f.config=Mapping('config',video=Mapping('video',sample_every_seconds=1,max_frames=2));f.result=Mapping('result',passed=True,annotated_url='x',rule={},detections=[])
                        stack.enter_context(patch.object(self.api,'video_frame_result_payload',side_effect=lambda *a:Mapping('frame',passed=True)))
                        invoke=lambda:asyncio.run(self.api.analyze_video(f.upload,'model'))
                    if target is None:invoke()
                    else:
                        with self.assertRaises(RuntimeError) as caught:invoke()
                        self.assertIs(caught.exception,error);self.assertEqual(events[-1],target);self.assertEqual(events.count(target),1);self.assertIsNone(f.resolver.current_snapshot())
                        if mode=='video':
                            self.assertEqual(f.cap.release.call_count,int(target[0]=='frame'));self.assertEqual((f.root/'safe.FILE.MP4').read_bytes(),b'video bytes')
                    return events
            baseline=exercise()
            for target in baseline:
                with self.subTest(mode=mode,target=target):exercise(target)

    def test_original_array_file_and_projection_callbacks_do_not_retry(self):
        for stage in ('frombuffer','open','frame','summary','strings'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=UploadFixture(self.f.root/stage);f.bind(self.api,stack);seen=[0];error=RuntimeError(stage)
                if stage=='frombuffer':owner=self.api.np;name='frombuffer'
                elif stage=='open':owner=Path;name='open'
                else:owner=self.api;name={'frame':'video_frame_result_payload','summary':'video_ai_summary','strings':'string_list'}[stage]
                normal=getattr(owner,name)
                def once(*args,**kwargs):
                    seen[0]+=1
                    if seen[0]==1:raise error
                    return normal(*args,**kwargs)
                stack.enter_context(patch.object(owner,name,once))
                with self.assertRaises(RuntimeError) as caught:
                    if stage=='strings':self.api.video_ai_summary([{'ai':{'error':'x'}}])
                    else:asyncio.run((self.api.analyze_image if stage=='frombuffer' else self.api.analyze_video)(f.upload,'model'))
                self.assertIs(caught.exception,error);self.assertEqual(seen,[1]);self.assertIsNone(f.resolver.current_snapshot())
                self.assertEqual(f.cap.release.call_count,int(stage=='summary'))

    def test_independent_upload_dependency_getters_fail_without_constructor_io(self):
        from local_inspection_service.detection.upload_ports import UploadAccess,UploadPaths,VideoResults
        from local_inspection_service.detection.image_upload import ImageUpload
        from local_inspection_service.detection.video_upload import VideoUpload
        from local_inspection_service.detection.video_results import VideoSummary,video_frame_result_payload
        cases=[('image',name,count) for name,count in [('directory',1),('name',1),('arrays',1),('arrays',2),('images',1),('images',2)]]
        cases += [('video',name,count) for name,count in [('directory',1),('name',1),('videos',1),('videos',2),('copies',1)]]+[('summary','strings',1)]
        for mode,name,count in cases:
            with self.subTest(mode=mode,name=name,count=count):
                f=UploadFixture(self.f.root/(mode+name+str(count)));seen=[0];error=RuntimeError(mode+' '+name)
                def getter(dependency,value):
                    def read():
                        if dependency==name:
                            seen[0]+=1
                            if seen[0]==count:raise error
                        return value
                    return read
                access=UploadAccess(f.ensure,f.permission);paths=UploadPaths(getter('name',f.safe),getter('directory',f.root));summary=VideoSummary(getter('strings',self.api.string_list))
                image=ImageUpload(access,paths,getter('arrays',np),getter('images',f.cv),f.analyze)
                video=VideoUpload(access,paths,getter('copies',self.api.shutil),f.load,getter('videos',f.cv),f.analyze,VideoResults(video_frame_result_payload,summary.video_ai_summary))
                self.assertEqual(seen,[0]);self.assertEqual(f.events,[])
                with self.assertRaises(RuntimeError) as caught:
                    if mode=='summary':summary.video_ai_summary([{'ai':{'error':'x'}}])
                    else:asyncio.run((image.analyze_image if mode=='image' else video.analyze_video)(f.upload,'model'))
                self.assertIs(caught.exception,error);self.assertEqual(seen,[count]);f.analyze.assert_not_called();f.cap.release.assert_not_called()

    def test_actual_upload_routes_and_plc_guard_follow_moved_implementations(self):
        import ast,copy
        from local_inspection_service.scripts.smoke_plc_frontend_contract import require_detection_upload_boundary
        root=Path(__file__).resolve().parents[1];source=(root/'local_inspection_service/server.py').read_text(encoding='utf-8')
        implementations={name:(root/'local_inspection_service/detection'/name).read_text(encoding='utf-8') for name in ('image_upload.py','video_upload.py','video_results.py','upload_ports.py')}
        require_detection_upload_boundary(source,implementations)
        positions=[]
        for path,name in [('/api/analyze/image','analyze_image'),('/api/analyze/camera','analyze_camera_image'),('/api/analyze/video','analyze_video'),('/api/stream/config','update_stream')]:
            found=[(i,route) for i,route in enumerate(self.api.app.routes) if route.path==path and 'POST' in getattr(route,'methods',set())]
            self.assertEqual(len(found),1);self.assertIs(found[0][1].endpoint,getattr(self.api,name));positions.append(found[0][0])
        self.assertEqual(positions,sorted(positions))
        for filename in implementations:
            with self.subTest(filename=filename):
                with self.assertRaises(AssertionError):require_detection_upload_boundary(source,{**implementations,filename:implementations[filename]+'\nplc_sync = True\n'})
        for change in ('import','shadow','constructor','delegate','binding','decorator','order'):
            with self.subTest(change=change):
                tree=ast.parse(source)
                if change=='import':
                    n=next(n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='detection.image_upload');n.module='wrong_module'
                elif change=='shadow':tree.body.append(ast.parse('ImageUpload = other').body[0])
                elif change in ('constructor','binding'):
                    n=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_image_upload' for t in n.targets))
                    if change=='constructor':n.value.func=ast.Name(id='Other',ctx=ast.Load())
                    else:n.value.args[4].body.func=ast.Name(id='other_analysis',ctx=ast.Load())
                elif change in ('delegate','decorator'):
                    n=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='analyze_video')
                    if change=='delegate':n.body=[ast.Return(value=ast.Dict(keys=[],values=[]))]
                    else:n.decorator_list=n.decorator_list[:1]
                else:
                    indexes=[i for i,n in enumerate(tree.body) if isinstance(n,ast.AsyncFunctionDef) and n.name in ('analyze_image','analyze_video')]
                    tree.body[indexes[0]],tree.body[indexes[1]]=tree.body[indexes[1]],tree.body[indexes[0]]
                ast.fix_missing_locations(tree)
                with self.assertRaises(AssertionError):require_detection_upload_boundary(ast.unparse(tree),implementations)

if __name__=='__main__':unittest.main()

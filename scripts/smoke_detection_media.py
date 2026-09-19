"""Offline media encoding, reference collection and contact-sheet baseline."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch,call
import base64,hashlib,json,os,sys,tempfile,threading,unittest
import cv2
import numpy as np
sys.path.insert(0,str(Path.cwd()))


from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
MEDIA_WINDOWS=('bgr_resize','bgr_encode','path_read','store_resize','store_write','collect_text','tile_full','tile_gray','tile_resize','sheet_text','sheet_full','sheet_read','sheet_text1','sheet_text2','sheet_write')
def capture_media_window(api,Fixture,root,site,mode):
 events=[];armed=[False];phase_done=[False];calls=[0]
 with ExitStack() as stack:
  stack.enter_context(patch.dict(api.__dict__))
  f=Fixture(Path(root)/(site+'-'+mode));real_path_encoder=api.image_path_data_url;f.bind(api,stack)
  ns=api.__dict__;realnp=ns['np'];image=f.image;original_exists=Path.exists;original_mkdir=Path.mkdir
  group='np' if site in ('tile_full','sheet_full') else 'text' if site in ('collect_text','sheet_text') else 'cv2'
  target={'bgr_resize':'resize','bgr_encode':'imencode','path_read':'imread','store_resize':'resize','store_write':'imwrite','tile_full':'full','tile_gray':'cvtColor','tile_resize':'resize','sheet_full':'full','sheet_read':'imread','sheet_text1':'putText','sheet_text2':'putText','sheet_write':'imwrite'}.get(site)
  argument_attr={'bgr_resize':'INTER_AREA','bgr_encode':'IMWRITE_JPEG_QUALITY','path_read':'IMREAD_COLOR','store_resize':'INTER_AREA','store_write':'IMWRITE_JPEG_QUALITY','tile_full':'uint8','tile_gray':'COLOR_GRAY2BGR','tile_resize':'INTER_AREA','sheet_full':'uint8','sheet_read':'IMREAD_UNCHANGED','sheet_text1':'FONT_HERSHEY_SIMPLEX','sheet_text2':'FONT_HERSHEY_SIMPLEX','sheet_write':'IMWRITE_JPEG_QUALITY'}.get(site)
  def phase():
   if phase_done[0]:return
   phase_done[0]=True;armed[0]=True;events.append('prior')
   if mode!='ordinary':install(None if mode=='missing' else 'B')
  def argument():
   if armed[0]:events.append('argument');install('C')
  def callback(label,normal):
   def invoke(*a,**k):
    if armed[0]:events.append(label)
    return normal(*a,**k)
   return invoke
  normal_module=realnp if group=='np' else f.cv
  class Backend:
   def __init__(self,label):self.label=label
   def __getattr__(self,name):
    if name==argument_attr:argument()
    value=getattr(normal_module,name)
    if name==target and armed[0]:return None if self.label is None else callback(self.label,value)
    return value
  def install(label):
   if group=='text':ns['bounded_text']=None if label is None else callback(label,lambda value,limit:str(value)[:limit])
   else:ns[group]=Backend(label)
  def after(mock,fn):
   normal=mock.side_effect or mock._mock_wraps
   def once(*a,**k):
    value=normal(*a,**k) if normal else mock.return_value;fn();return value
   mock.side_effect=once
  if site=='bgr_resize':
   class Limit(float):
    def __float__(self):phase();return 8.0
   invoke=lambda:api.image_bgr_data_url(image,max_side=Limit(8))
  elif site=='bgr_encode':
   after(f.cv.resize,phase);invoke=lambda:api.image_bgr_data_url(image,max_side=8)
  elif site=='path_read':
   invoke=lambda:real_path_encoder(f.path)
  elif site=='store_resize':
   def mkdir(path,*a,**k):
    value=original_mkdir(path,*a,**k)
    if path==f.root/'mcp':phase()
    return value
   stack.enter_context(patch.object(Path,'mkdir',mkdir));invoke=lambda:api.write_mcp_inspection_image(image,'request')
  elif site=='store_write':
   after(f.safe,phase);invoke=lambda:api.write_mcp_inspection_image(image,'request')
  elif site=='collect_text':
   class Payload(dict):
    count=0
    def get(self,key,*a):
     if key=='accessory':
      self.count+=1
      if self.count==2:phase()
     if key=='accessory_id':argument()
     return super().get(key,*a)
   invoke=lambda:api.tool_accessory_reference_collect(Payload(accessory={},accessory_id='id'))
  elif site=='tile_full':invoke=lambda:api.fit_image_into_cell(None,4,3)
  elif site=='tile_gray':
   class Gray(realnp.ndarray):
    @property
    def ndim(self):phase();return realnp.ndarray.ndim.__get__(self)
   image=image[:,:,0].view(Gray);invoke=lambda:api.fit_image_into_cell(image,6,6)
  elif site=='tile_resize':
   class Picture(realnp.ndarray):
    @property
    def shape(self):phase();return realnp.ndarray.shape.__get__(self)
   image=image.view(Picture);invoke=lambda:api.fit_image_into_cell(image,6,6)
  else:
   f.required=f.required[:1]
   if site=='sheet_text':
    class Required(dict):
     def get(self,key,*a):
      if key=='name':argument()
      return super().get(key,*a)
    f.required=[Required(f.required[0])]
    def exists(path):
     value=original_exists(path)
     if path==f.files[1]:phase()
     return value
    stack.enter_context(patch.object(Path,'exists',exists))
   elif site=='sheet_full':
    def exists(path):
     value=original_exists(path)
     if path.parent==f.root/'sheet':phase()
     return value
    stack.enter_context(patch.object(Path,'exists',exists))
   elif site=='sheet_read':
    ns['np']=SimpleNamespace(full=lambda *a,**k:phase() or realnp.full(*a,**k),uint8=realnp.uint8)
   elif site=='sheet_text1':after(f.cv.rectangle,phase)
   elif site=='sheet_text2':after(f.cv.putText,phase)
   elif site=='sheet_write':
    def count():
     calls[0]+=1
     if calls[0]==2:phase()
    after(f.cv.putText,count)
   invoke=lambda:api.build_reference_sheet_descriptor(f.required)
  install('A')
  if site in ('path_read','tile_full'):
   armed[0]=True;events.append('prior')
   if mode=='missing':install(None)
  error=None;result=None
  try:result=invoke()
  except BaseException as caught:error=caught
  expected=[] if mode=='missing' else ['A' if mode=='ordinary' else 'B']
  observed=[x for x in events if x in ('A','B','C')]
  # Resize/putText ports are reused later in these algorithms; only the target first capture is armed.
  if site in ('sheet_text1','sheet_full') and mode!='missing':expected+=['C']
  assert observed==expected,(site,mode,events,repr(error))
  assert 'argument' in events,(site,mode,events,repr(error))
  if mode=='missing':
   if site.startswith('store_'):assert error is None and result is None,(site,repr(error))
   else:assert type(error) is TypeError,(site,repr(error),events)
  else:assert error is None,(site,repr(error),events)
  return events




def capture_media_refresh(api,Fixture,root,site):
 import threading
 events=[]
 with ExitStack() as stack:
  stack.enter_context(patch.dict(api.__dict__))
  f=Fixture(Path(root)/site);f.bind(api,stack);ns=api.__dict__
  if site=='collect_encode':
   real=f.encode
   def b(*a,**k):events.append('B');return real(*a,**k)
   def a(*args,**kwargs):events.append('A');ns['image_path_data_url']=b;return real(*args,**kwargs)
   ns['image_path_data_url']=a;invoke=lambda:api.tool_accessory_reference_collect({});expected=['A','B']
  elif site=='sheet_text':
   real=f.text
   def b(*a,**k):events.append('B');return real(*a,**k)
   def a(*args,**kwargs):events.append('A');ns['bounded_text']=b;return real(*args,**kwargs)
   ns['bounded_text']=a;invoke=lambda:api.build_reference_sheet_descriptor(f.required);expected=['A','B']
  elif site=='sheet_fit':
   real=api.fit_image_into_cell
   def b(*a,**k):events.append('B');return real(*a,**k)
   def a(*args,**kwargs):events.append('A');ns['fit_image_into_cell']=b;return real(*args,**kwargs)
   ns['fit_image_into_cell']=a;invoke=lambda:api.build_reference_sheet_descriptor(f.required);expected=['A','B']
  elif site=='cache_lock':
   def check(kind):
    acquired=[]
    def attempt():
     ok=f.lock.acquire(blocking=False);acquired.append(ok)
     if ok:f.lock.release()
    t=threading.Thread(target=attempt);t.start();t.join(2);assert not t.is_alive()
    events.append((kind,acquired))
   class Records(dict):
    def get(self,*a,**k):check('get');return super().get(*a,**k)
    def __setitem__(self,key,value):check('set');return super().__setitem__(key,value)
   ns['_REFERENCE_SHEET_DESCRIPTOR_CACHE']=Records()
   invoke=lambda:api.build_reference_sheet_descriptor(f.required);expected=[('get',[False]),('set',[False])]
  elif site=='cache_refresh':
   class Records(dict):
    def __init__(self,label):super().__init__();self.label=label
    def get(self,*a,**k):events.append(self.label+'get');return super().get(*a,**k)
    def __setitem__(self,key,value):events.append(self.label+'set');return super().__setitem__(key,value)
   records={label:Records(label) for label in 'ABC'};ns['_REFERENCE_SHEET_DESCRIPTOR_CACHE']=records['A']
   count=[0]
   class Lock:
    def __enter__(self):
     f.lock.acquire();count[0]+=1;ns['_REFERENCE_SHEET_DESCRIPTOR_CACHE']=records['B' if count[0]==1 else 'C']
    def __exit__(self,*a):f.lock.release()
   ns['_REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK']=Lock()
   invoke=lambda:api.build_reference_sheet_descriptor(f.required);expected=['Bget','Cset']
  else:raise AssertionError(site)
  error=None
  try:invoke()
  except BaseException as caught:error=caught
  assert error is None,(site,repr(error),events)
  assert events==expected,(site,events)
  return events


class MediaFixture:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.image=np.full((6,12,3),30,np.uint8);self.path=self.root/'a.png';cv2.imwrite(str(self.path),self.image)
        self.files=[self.path,self.root/'b.png'];cv2.imwrite(str(self.files[1]),np.full((8,4,3),80,np.uint8));self.cache={};self.lock=threading.RLock();self.events=[]
        self.cv=SimpleNamespace(**{name:getattr(cv2,name) for name in ('INTER_AREA','IMREAD_COLOR','IMREAD_UNCHANGED','IMWRITE_JPEG_QUALITY','COLOR_GRAY2BGR','FONT_HERSHEY_SIMPLEX','LINE_AA')})
        for name in ('resize','imread','imwrite','imencode','cvtColor','rectangle','putText'):setattr(self.cv,name,Mock(wraps=getattr(cv2,name)))
        self.text=Mock(side_effect=lambda value,limit:str(value)[:limit]);self.uid=Mock(return_value='fallback-id');self.paths=Mock(return_value=self.files);self.encode=Mock(side_effect=lambda path,**kw:'data:image/jpeg;base64,'+base64.b64encode(str(path).encode()).decode());self.mime=Mock(return_value=('image/jpeg',b'bytes'))
        self.output=Mock(return_value=self.root/'sheet');self.safe=Mock(return_value='safe.name');self.clock=Mock(return_value=123);self.required=[{'accessory_id':'b','name':'Bee','expected_count':2,'profile':{'reference_images':[{'source_path':str(self.files[1]),'sha256':'hash-b'}]}},{'accessory_id':'a','name':'Aye','profile':{'reference_images':[{'source_path':str(self.path),'sha256':'hash-a'}]}}]
    def bind(self,api,stack):
        for name,value in {'cv2':self.cv,'bounded_text':self.text,'accessory_uid':self.uid,'accessory_image_paths':self.paths,'image_path_data_url':self.encode,'data_url_payload':self.mime,'output_write_dir':self.output,'safe_name':self.safe,'time':SimpleNamespace(time_ns=self.clock),'AI_MCP_INSPECTION_IMAGE_DIR':self.root/'mcp','AI_INSPECTION_IMAGE_MAX_SIDE':8,'AI_INSPECTION_IMAGE_QUALITY':79,'AI_REFERENCE_IMAGES_PER_ACCESSORY':2,'AI_REFERENCE_IMAGE_MAX_SIDE':640,'AI_REFERENCE_IMAGE_QUALITY':72,'IMAGE_REFERENCE_SUFFIXES':{'.png','.jpg'},'AI_PROFILE_REFERENCE_MODE':'sheet','AI_PROFILE_REFERENCE_SHEET_QUALITY':83,'AI_PROFILE_REFERENCE_SHEET_MAX_SIDE':1400,'_REFERENCE_SHEET_DESCRIPTOR_CACHE':self.cache,'_REFERENCE_SHEET_DESCRIPTOR_CACHE_LOCK':self.lock}.items():stack.enter_context(patch.object(api,name,value))

class MediaContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env=patch.dict(os.environ);cls.env.start();cls.tmp=tempfile.TemporaryDirectory(prefix='media-baseline-');root=Path(cls.tmp.name);(root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup();cls.env.stop()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):self.stack.enter_context(patch(name,side_effect=AssertionError('unexpected external operation')))
        self.path_encoder=self.api.image_path_data_url;self.f=MediaFixture(Path(self.tmp.name)/self.id().split('.')[-1]);self.f.bind(self.api,self.stack)
    def test_bgr_encoding_resizes_only_when_needed_and_exact_jpeg_bytes(self):
        f=self.f;value=self.api.image_bgr_data_url(f.image,max_side=8,quality=77);resized=cv2.resize(f.image,(8,4),interpolation=cv2.INTER_AREA);ok,expected=cv2.imencode('.jpg',resized,[int(cv2.IMWRITE_JPEG_QUALITY),77]);self.assertTrue(ok)
        self.assertEqual(value,'data:image/jpeg;base64,'+base64.b64encode(expected.tobytes()).decode('ascii'));self.assertEqual(f.cv.resize.call_args.args[1],(8,4));self.assertEqual(f.cv.resize.call_args.kwargs,{'interpolation':cv2.INTER_AREA})
        f.cv.resize.reset_mock();self.api.image_bgr_data_url(f.image,max_side=20);f.cv.resize.assert_not_called();self.assertIs(f.cv.imencode.call_args.args[1],f.image)
    def test_bgr_encoding_false_and_exception_are_distinct(self):
        f=self.f;f.cv.imencode.side_effect=None;f.cv.imencode.return_value=(False,None)
        with self.assertRaises(self.api.AiProviderError) as caught:self.api.image_bgr_data_url(f.image)
        self.assertEqual(str(caught.exception),'Failed to encode image for AI provider')
        error=OSError('encoder');seen=[0]
        def once(*a,**k):
            seen[0]+=1
            if seen[0]==1:raise error
            return True,np.array([1],np.uint8)
        f.cv.imencode.side_effect=once
        with self.assertRaises(OSError) as caught:self.api.image_bgr_data_url(f.image)
        self.assertIs(caught.exception,error);self.assertEqual(seen,[1])
    def test_path_encoding_retains_color_read_and_exact_forwarding(self):
        f=self.f;encode=Mock(return_value='encoded')
        with patch.object(self.api,'image_bgr_data_url',encode):self.assertEqual(self.path_encoder(f.path,max_side=80,quality=66),'encoded')
        f.cv.imread.assert_called_once_with(str(f.path),cv2.IMREAD_COLOR);self.assertEqual(encode.call_args.kwargs,{'max_side':80,'quality':66});np.testing.assert_array_equal(encode.call_args.args[0],f.image)
        f.cv.imread.side_effect=None;f.cv.imread.return_value=None;self.assertIsNone(self.path_encoder(f.path));self.assertEqual(encode.call_count,1)
    def test_inspection_file_name_clock_resize_and_quality(self):
        f=self.f;result=self.api.write_mcp_inspection_image(f.image,'request');digest=hashlib.sha1(b'request:123').hexdigest()[:12]
        self.assertEqual(result,f.root/'mcp'/('safe.name_'+digest+'.jpg'));self.assertTrue(result.exists());self.assertEqual(f.cv.imwrite.call_args.args[2],[int(cv2.IMWRITE_JPEG_QUALITY),79]);self.assertEqual(f.cv.resize.call_args.args[1],(8,4));f.clock.assert_called_once_with();f.safe.assert_called_once_with('request')
    def test_inspection_file_failure_is_suppressed_without_retry(self):
        for stage in ('resize','clock','safe','write'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=MediaFixture(self.f.root/stage);f.bind(self.api,stack);callback={'resize':f.cv.resize,'clock':f.clock,'safe':f.safe,'write':f.cv.imwrite}[stage];normal=callback.side_effect or callback._mock_wraps;seen=[0]
                def once(*a,**k):
                    seen[0]+=1
                    if seen[0]==1:raise RuntimeError(stage)
                    return normal(*a,**k) if normal else ('name' if stage=='safe' else 123)
                callback.side_effect=once;self.assertIsNone(self.api.write_mcp_inspection_image(f.image,'request'));self.assertEqual(seen,[1])
        self.f.cv.imwrite.side_effect=None;self.f.cv.imwrite.return_value=False;self.assertIsNone(self.api.write_mcp_inspection_image(self.f.image,'request'))
    def test_inspection_file_baseexception_is_not_swallowed(self):
        class Cancelled(BaseException):pass
        error=Cancelled();self.f.cv.imwrite.side_effect=error
        with self.assertRaises(Cancelled) as caught:self.api.write_mcp_inspection_image(self.f.image,'request')
        self.assertIs(caught.exception,error)
    def test_fit_white_missing_empty_gray_and_alpha_contracts(self):
        fit=self.api.fit_image_into_cell
        np.testing.assert_array_equal(fit(None,4,3),np.full((3,4,3),255,np.uint8));np.testing.assert_array_equal(fit(np.zeros((0,1,3),np.uint8),4,3),np.full((3,4,3),255,np.uint8))
        np.testing.assert_array_equal(fit(np.full((2,2),60,np.uint8),2,2),np.full((2,2,3),60,np.uint8))
        image=np.array([[[0,0,0,0],[100,120,140,255]]],np.uint8);np.testing.assert_array_equal(fit(image,2,1),np.array([[[255,255,255],[100,120,140]]],np.uint8))
    def test_fit_centers_rounded_dimensions_and_leaves_input_unchanged(self):
        f=self.f;before=f.image.copy();result=self.api.fit_image_into_cell(f.image,6,6);np.testing.assert_array_equal(f.image,before);self.assertEqual(result.shape,(6,6,3));np.testing.assert_array_equal(result[1:4],np.full((3,6,3),30,np.uint8));self.assertTrue(np.all(result[0]==255));self.assertTrue(np.all(result[4:]==255))
    def test_reference_collection_deduplicates_then_encodes_and_limits_valid_paths(self):
        f=self.f;payload={'accessory_id':'explicit','reference_image_paths':[str(f.path),str(f.path),str(f.files[1])],'max_images':2,'max_side':900,'quality':80};value=self.api.tool_accessory_reference_collect(payload)
        self.assertEqual(value['reference_count'],2);self.assertEqual([r['ordinal'] for r in value['references']],[1,2]);self.assertEqual([r['source_path'] for r in value['references']],[str(f.path),str(f.files[1])]);self.assertTrue(all(r['accessory_id']=='explicit' and r['mime_type']=='image/jpeg' and r['detail']=='low' for r in value['references']))
        self.assertEqual(f.encode.call_args_list,[call(f.path,max_side=900,quality=80),call(f.files[1],max_side=900,quality=80)]);f.paths.assert_not_called();f.uid.assert_not_called()
    def test_reference_collection_zero_limit_retains_original_post_append_check(self):
        f=self.f;value=self.api.tool_accessory_reference_collect({'max_images':0});self.assertEqual((value['reference_count'],value['max_images']),(1,0));f.paths.assert_called_once_with({});f.uid.assert_called_once_with({})
    def test_reference_collection_clamps_and_falls_back_invalid_policy(self):
        f=self.f
        for values,expected in [({'max_images':99,'max_side':0,'quality':100},(16,64,95)),({'max_images':'bad','max_side':None,'quality':{}},(2,640,72))]:
            with self.subTest(values=values):
                f.encode.reset_mock();value=self.api.tool_accessory_reference_collect(values);self.assertEqual(value['max_images'],expected[0]);self.assertEqual(f.encode.call_args.kwargs,{'max_side':expected[1],'quality':expected[2]})
    def test_reference_collection_skips_failed_decode_and_propagates_encoder_error_once(self):
        f=self.f;f.encode.side_effect=lambda path,**kw:None if path==f.path else 'data:valid';value=self.api.tool_accessory_reference_collect({});self.assertEqual(value['reference_count'],1);self.assertEqual(value['references'][0]['source_path'],str(f.files[1]))
        error=OSError('decode');seen=[0]
        def once(*a,**k):
            seen[0]+=1
            if seen[0]==1:raise error
            return 'data:valid'
        f.encode.side_effect=once
        with self.assertRaises(OSError) as caught:self.api.tool_accessory_reference_collect({})
        self.assertIs(caught.exception,error);self.assertEqual(seen,[1])
    def test_sheet_sorts_identity_digest_layout_and_shared_cached_items(self):
        f=self.f;value=self.api.build_reference_sheet_descriptor(f.required);items=value['sheet_items'];self.assertEqual([i['accessory_id'] for i in items],['a','b']);self.assertEqual([i['expected_count'] for i in items],[1,2])
        digest=hashlib.sha256(json.dumps({'mode':'sheet','items':[{'accessory_id':'a','sha256':'hash-a'},{'accessory_id':'b','sha256':'hash-b'}]},sort_keys=True,ensure_ascii=False).encode()).hexdigest();path=f.root/'sheet'/('reference_sheet_'+digest[:16]+'.jpg')
        self.assertEqual(value,{'accessory_id':'__reference_sheet__','data_url':'data:image/jpeg;base64,'+base64.b64encode(str(path).encode()).decode(),'detail':'low','source_path':str(path),'mode':'sheet','sheet_items':items});self.assertTrue(path.exists());self.assertEqual(f.cv.imwrite.call_args.args[1].shape,(754,1192,3));self.assertEqual(f.cv.imwrite.call_args.args[2],[int(cv2.IMWRITE_JPEG_QUALITY),83]);self.assertEqual(f.cv.putText.call_count,4)
        self.assertIsNot(value,f.cache[digest]);self.assertIs(value['sheet_items'],f.cache[digest]['sheet_items']);f.cv.imwrite.reset_mock();f.encode.reset_mock();hit=self.api.build_reference_sheet_descriptor(list(reversed(f.required)));self.assertEqual(hit,value);self.assertIsNot(hit,f.cache[digest]);self.assertIs(hit['sheet_items'],items);f.cv.imwrite.assert_not_called();f.encode.assert_not_called()
    def test_sheet_empty_invalid_or_first_missing_reference_does_not_create_output(self):
        f=self.f;required=[{'profile':None},{'profile':{'reference_images':[{'source_path':str(f.root/'missing.png')},{'source_path':str(f.path)}]}}]
        self.assertIsNone(self.api.build_reference_sheet_descriptor(required));f.output.assert_not_called();f.cv.imwrite.assert_not_called()
    def test_sheet_reads_missing_hash_and_reuses_existing_file_without_rendering(self):
        f=self.f;f.required[0]['profile']['reference_images'][0].pop('sha256');value=self.api.build_reference_sheet_descriptor(f.required);item=value['sheet_items'][1];self.assertEqual(item['sha256'],hashlib.sha256(f.files[1].read_bytes()).hexdigest());f.cache.clear();f.cv.imwrite.reset_mock();f.cv.imread.reset_mock();again=self.api.build_reference_sheet_descriptor(f.required);self.assertEqual(again,value);f.cv.imwrite.assert_not_called();f.cv.imread.assert_not_called()
    def test_sheet_false_write_still_encodes_and_missing_data_is_not_cached(self):
        f=self.f;f.cv.imwrite.side_effect=None;f.cv.imwrite.return_value=False;f.encode.side_effect=None;f.encode.return_value=None
        self.assertIsNone(self.api.build_reference_sheet_descriptor(f.required));f.encode.assert_called_once();self.assertEqual(f.cache,{})
    def test_sheet_cache_hit_requires_same_output_path(self):
        f=self.f;first=self.api.build_reference_sheet_descriptor(f.required);f.output.return_value=f.root/'other_owner';second=self.api.build_reference_sheet_descriptor(f.required);self.assertNotEqual(first['source_path'],second['source_path']);self.assertEqual(f.cv.imwrite.call_count,2);self.assertEqual(len(f.cache),1)


    def test_sheet_four_items_use_three_columns_and_two_rows(self):
        f=self.f;required=[{'accessory_id':str(i),'profile':{'reference_images':[{'source_path':str(f.path),'sha256':str(i)}]}} for i in range(4)]
        result=self.api.build_reference_sheet_descriptor(required);self.assertEqual(len(result['sheet_items']),4);self.assertEqual(f.cv.imwrite.call_args.args[1].shape,(1484,1776,3));self.assertEqual(f.cv.imread.call_count,4)

    def test_sheet_existing_digest_keeps_original_cached_metadata(self):
        f=self.f;first=self.api.build_reference_sheet_descriptor(f.required);f.required[1]['name']='renamed';f.required[1]['expected_count']=7
        second=self.api.build_reference_sheet_descriptor(f.required);self.assertEqual(second,first);self.assertEqual(second['sheet_items'][0]['name'],'Aye');self.assertEqual(second['sheet_items'][0]['expected_count'],1)

    def test_sheet_rendering_or_encoding_errors_leave_partial_evidence_without_retry(self):
        for stage in ('read','fit','write','encode'):
            with self.subTest(stage=stage),ExitStack() as stack:
                f=MediaFixture(self.f.root/stage);f.bind(self.api,stack);error=RuntimeError(stage);seen=[0]
                callback={'read':f.cv.imread,'fit':Mock(wraps=self.api.fit_image_into_cell),'write':f.cv.imwrite,'encode':f.encode}[stage];normal=callback.side_effect or callback._mock_wraps
                if stage=='fit':stack.enter_context(patch.object(self.api,'fit_image_into_cell',callback))
                def once(*args,**kwargs):
                    seen[0]+=1
                    if seen[0]==1:raise error
                    return normal(*args,**kwargs)
                callback.side_effect=once
                with self.assertRaises(RuntimeError) as caught:self.api.build_reference_sheet_descriptor(f.required)
                self.assertIs(caught.exception,error);self.assertEqual(seen,[1]);self.assertEqual(f.cache,{})
                self.assertEqual(bool(list((f.root/'sheet').glob('*.jpg'))),stage=='encode')


    def test_independent_media_compositions_own_paths_and_descriptor_caches(self):
        from local_inspection_service.detection.media_ports import InspectionImagePolicy,ReferenceCollectionPolicy,ReferenceSheetPolicy,ReferenceSheetCache,ReferenceSheetImages
        from local_inspection_service.detection.image_encoding import ImageEncoding
        from local_inspection_service.detection.inspection_image_store import InspectionImageStore
        from local_inspection_service.detection.reference_images import ReferenceCollection,ReferenceTileRenderer
        from local_inspection_service.detection.reference_sheet import ReferenceSheet
        error_type=self.api.AiProviderError
        def build(f):
            encoding=ImageEncoding(lambda:f.cv,error_type,lambda image,**kwargs:encoding.image_bgr_data_url(image,**kwargs))
            storage=InspectionImageStore(lambda:f.cv,InspectionImagePolicy(lambda:f.root/'mcp',lambda:8,lambda:79),f.clock,f.safe)
            collection=ReferenceCollection(lambda:f.text,f.uid,f.paths,encoding.image_path_data_url,f.mime,ReferenceCollectionPolicy(lambda:2,lambda:640,lambda:72))
            tiles=ReferenceTileRenderer(lambda:f.cv,lambda:np)
            sheet=ReferenceSheet(lambda:f.text,f.output,ReferenceSheetPolicy(lambda:{'.png','.jpg'},lambda:'sheet',lambda:83,lambda:1400),ReferenceSheetCache(lambda:f.lock,lambda:f.cache),ReferenceSheetImages(lambda:f.cv,lambda:np,tiles.fit_image_into_cell,lambda:encoding.image_path_data_url))
            return encoding,storage,collection,tiles,sheet
        services=[]
        for owner in ('alice','bob'):
            f=MediaFixture(self.f.root/owner);services.append((f,*build(f)));self.assertEqual(f.cache,{})
            for name in ('resize','imread','imwrite','imencode','cvtColor','rectangle','putText'):getattr(f.cv,name).assert_not_called()
            f.clock.assert_not_called();f.output.assert_not_called()
        with ExitStack() as stack:
            for name in ('image_bgr_data_url','image_path_data_url','write_mcp_inspection_image','tool_accessory_reference_collect','fit_image_into_cell','build_reference_sheet_descriptor','output_write_dir','safe_name','bounded_text','accessory_uid','accessory_image_paths','data_url_payload'):
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root callback')))
            stack.enter_context(patch.object(self.api,'cv2',object()));stack.enter_context(patch.object(self.api,'_REFERENCE_SHEET_DESCRIPTOR_CACHE',object()))
            results=[]
            for f,encoding,storage,collection,tiles,sheet in services:
                self.assertTrue(encoding.image_bgr_data_url(f.image).startswith('data:image/jpeg;base64,'));self.assertTrue(encoding.image_path_data_url(f.path).startswith('data:image/jpeg;base64,'))
                self.assertEqual(storage.write_mcp_inspection_image(f.image,'req').parent,f.root/'mcp');self.assertEqual(collection.tool_accessory_reference_collect({})['reference_count'],2);self.assertEqual(tiles.fit_image_into_cell(f.image,8,8).shape,(8,8,3))
                first=sheet.build_reference_sheet_descriptor(f.required);writes=f.cv.imwrite.call_count;second=sheet.build_reference_sheet_descriptor(f.required)
                self.assertEqual(first,second);self.assertEqual(f.cv.imwrite.call_count,writes);self.assertEqual(len(f.cache),1);results.append(first)
            self.assertNotEqual(results[0]['source_path'],results[1]['source_path']);self.assertIsNot(services[0][0].cache,services[1][0].cache)

    def test_dependency_capture_precedes_argument_side_effects(self):
        with patch.object(self.api,'image_path_data_url',self.path_encoder):
            for site in MEDIA_WINDOWS:
                for mode in (('ordinary','missing') if site in ('path_read','tile_full') else ('ordinary','prior','missing')):
                    with self.subTest(site=site,mode=mode):
                        capture_media_window(self.api,MediaFixture,self.f.root,site,mode)

    def test_mcp_registry_retains_actual_reference_collection_adapter(self):
        self.assertEqual(set(self.api.AI_MCP_TOOL_HANDLERS),{'accessory.profile.generate','accessory.reference.collect','vision.inspect.presence','provider.gemini.generate_json'})
        self.assertIs(self.api.AI_MCP_TOOL_HANDLERS['accessory.reference.collect'],self.api.tool_accessory_reference_collect)


    def _media_fault_matrix(self, kind):
        from dataclasses import is_dataclass, replace
        scenarios=('bgr','bgr_false','path','store','collect','collect_invalid','tile_gray','tile_alpha','sheet','sheet_fallback','sheet_hit')
        for scenario in scenarios:
            def run(target=None):
                trace=[];counts={};error=RuntimeError('boundary failure');f=MediaFixture(self.f.root/kind/scenario/('baseline' if target is None else str(target)))
                def wrap(label,fn):
                    def invoke(*a,**kw):
                        occurrence=counts.get(label,0)+1;counts[label]=occurrence;key=(label,occurrence);trace.append(key)
                        if key==target:raise error
                        return fn(*a,**kw)
                    return invoke
                class Record(dict):
                    def __init__(self,value,label):super().__init__(value);self.label=label
                    def get(self,key,*default):return wrap(self.label+'.get.'+str(key),super().get)(key,*default)
                    def __setitem__(self,key,value):return wrap(self.label+'.write',super().__setitem__)(key,value)
                def records(value,label):
                    if isinstance(value,dict):return Record({k:records(v,label+'.'+str(k)) for k,v in value.items()},label)
                    if isinstance(value,list):return [records(v,label+'.'+str(i)) for i,v in enumerate(value)]
                    return value
                with ExitStack() as stack:
                    f.bind(self.api,stack)
                    payload={'accessory':{}}
                    if scenario=='collect_invalid':payload.update(max_images='bad',max_side=None,quality={})
                    if scenario=='sheet_fallback':
                        for item in f.required:
                            item.pop('name',None);item['profile']['name']='fallback';item['profile']['reference_images'][0].pop('sha256')
                    if scenario=='sheet_hit':self.api.build_reference_sheet_descriptor(f.required)
                    if scenario=='bgr_false':f.cv.imencode.side_effect=None;f.cv.imencode.return_value=(False,None)
                    if kind=='mapping':
                        payload=records(payload,'payload');f.required=records(f.required,'required')
                        cache=records(f.cache,'cache');stack.enter_context(patch.object(self.api,'_REFERENCE_SHEET_DESCRIPTOR_CACHE',cache))
                    elif kind=='boundary':
                        for name in ('resize','imread','imwrite','imencode','cvtColor','rectangle','putText'):
                            setattr(f.cv,name,wrap('cv.'+name,getattr(f.cv,name)))
                        arrays=SimpleNamespace(full=wrap('np.full',np.full),full_like=wrap('np.full_like',np.full_like),uint8=np.uint8,float32=np.float32)
                        stack.enter_context(patch.object(self.api,'np',arrays))
                        for name in ('bounded_text','accessory_uid','accessory_image_paths','image_path_data_url','data_url_payload','output_write_dir','safe_name','fit_image_into_cell','image_bgr_data_url','AiProviderError'):
                            stack.enter_context(patch.object(self.api,name,wrap(name,getattr(self.api,name))))
                        stack.enter_context(patch.object(self.api.time,'time_ns',wrap('clock',self.api.time.time_ns)))
                        for name in ('exists','read_bytes','mkdir'):
                            stack.enter_context(patch.object(Path,name,wrap('path.'+name,getattr(Path,name))))
                    else:
                        def instrument(value,label):
                            if is_dataclass(value):return replace(value,**{k:instrument(v,label+'.'+k) for k,v in vars(value).items()})
                            if callable(value):return wrap(label,value)
                            return value
                        for name in ('_image_encoding','_inspection_image_store','_reference_collection','_reference_tile_renderer','_reference_sheet'):
                            service=getattr(self.api,name)
                            for key,value in vars(service).items():stack.enter_context(patch.object(service,key,instrument(value,name+'.'+key)))
                    invoke={
                        'bgr':lambda:self.api.image_bgr_data_url(f.image,max_side=8),
                        'bgr_false':lambda:self.api.image_bgr_data_url(f.image),
                        'path':lambda:self.path_encoder(f.path),
                        'store':lambda:self.api.write_mcp_inspection_image(f.image,'request'),
                        'collect':lambda:self.api.tool_accessory_reference_collect(payload),
                        'collect_invalid':lambda:self.api.tool_accessory_reference_collect(payload),
                        'tile_gray':lambda:self.api.fit_image_into_cell(f.image[:,:,0],6,6),
                        'tile_alpha':lambda:self.api.fit_image_into_cell(np.dstack((f.image,np.full(f.image.shape[:2],120,np.uint8))),6,6),
                        'sheet':lambda:self.api.build_reference_sheet_descriptor(f.required),
                        'sheet_fallback':lambda:self.api.build_reference_sheet_descriptor(f.required),
                        'sheet_hit':lambda:self.api.build_reference_sheet_descriptor(f.required),
                    }[scenario]
                    caught=None;result=None
                    try:result=invoke()
                    except BaseException as exc:caught=exc
                    if target is None:
                        if scenario=='bgr_false':self.assertIsInstance(caught,original_error)
                        else:self.assertIsNone(caught)
                    elif scenario=='store':self.assertIsNone(caught);self.assertIsNone(result)
                    else:self.assertIs(caught,error)
                    if target is not None:
                        self.assertEqual(counts[target[0]],target[1]);self.assertEqual(trace[-1],target)
                    return trace
            original_error=self.api.AiProviderError
            baseline=run()
            for target in baseline:
                with self.subTest(kind=kind,scenario=scenario,target=target):run(target)

    def test_external_boundary_first_error_is_not_retried(self):
        self._media_fault_matrix('boundary')

    def test_mapping_first_error_is_not_retried(self):
        self._media_fault_matrix('mapping')

    def test_independent_dependency_first_error_is_not_retried(self):
        self._media_fault_matrix('dependency')

    def test_callbacks_refresh_and_cache_access_remains_under_lock(self):
        for site in ('collect_encode','sheet_text','sheet_fit','cache_lock','cache_refresh'):
            with self.subTest(site=site):capture_media_refresh(self.api,MediaFixture,self.f.root,site)

if __name__=='__main__':unittest.main()

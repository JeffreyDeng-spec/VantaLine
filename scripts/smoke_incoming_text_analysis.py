"""OCR initialization, image evidence and Beta single-flight contracts; synthetic only."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from local_inspection_service.text_inspection import incoming_analysis as analysis
from local_inspection_service.text_inspection import beta_comparison as beta
from local_inspection_service.text_inspection.beta_api import BetaAccess, register
from local_inspection_service.incoming_text_inspection import TextObservation
from local_inspection_service import text_compare_beta as comparison_engine
ROOT_CHECK='--root' in sys.argv
if ROOT_CHECK:sys.argv.remove('--root')
try:import fitz
except ImportError:fitz=None


def picture(size=300):
    pixels=np.full((size,size,3),(20,80,160),np.uint8);ok,data=cv2.imencode('.png',pixels);assert ok;return data.tobytes()


class Upload:
    def __init__(self,label,data=b'image',content_type='image/png',events=None):
        self.label,self.data,self.content_type,self.events=label,data,content_type,events if events is not None else []
    async def read(self,size=-1):self.events.append(('read',self.label,size));return self.data


class AnalysisContracts(unittest.TestCase):
    def test_engine_initialization_parameters_failure_retry_and_instance_isolation(self):
        model=object();prepare=Mock();initialization_lock=[]
        def build():
            def probe():
                acquired=instance.lock.acquire(blocking=False);initialization_lock.append(acquired)
                if acquired:instance.lock.release()
            thread=threading.Thread(target=probe);thread.start();thread.join(2)
            self.assertFalse(thread.is_alive())
            return model
        factory=Mock(side_effect=build)
        instance=analysis.IncomingOCREngine(prepare,factory)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:instance.get(),range(2)))
        self.assertEqual(results,[model,model]);prepare.assert_called_once();factory.assert_called_once()
        self.assertEqual(initialization_lock,[False])
        other=analysis.IncomingOCREngine(lambda:None,lambda:object());self.assertIsNot(other.get(),model)
        prepare=Mock(side_effect=[RuntimeError('prepare'),None,None]);factory=Mock(side_effect=[RuntimeError('construct'),model]);instance=analysis.IncomingOCREngine(prepare,factory)
        for reason in ['prepare','construct']:
            with self.assertRaisesRegex(RuntimeError,reason):instance.get()
            self.assertIsNone(instance.instance)
        self.assertIs(instance.get(),model);self.assertEqual(prepare.call_count,3);self.assertEqual(factory.call_count,2)
        paddle=types.ModuleType('paddleocr');paddle.PaddleOCR=Mock(return_value=model)
        with patch.dict(sys.modules,{'paddleocr':paddle}):self.assertIs(analysis.create_paddle_ocr(),model)
        paddle.PaddleOCR.assert_called_once_with(text_detection_model_name='PP-OCRv6_medium_det',text_recognition_model_name='PP-OCRv6_medium_rec',use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=True)
    def test_mapping_observations_color_order_and_bad_fields(self):
        direct={'res':{'rec_texts':['nested']}};self.assertIs(analysis.result_mapping(direct),direct)
        for value in [types.SimpleNamespace(json='{"res":{"x":1}}'),types.SimpleNamespace(json=lambda:{'res':{'x':1}})]:self.assertEqual(analysis.result_mapping(value),{'x':1})
        self.assertEqual(analysis.result_mapping(types.SimpleNamespace(json='broken')), {})
        with self.assertRaisesRegex(RuntimeError,'json'):analysis.result_mapping(types.SimpleNamespace(json=Mock(side_effect=RuntimeError('json'))))
        image=np.full((2,2,3),(10,20,30),np.uint8);model=Mock();model.predict.return_value=[{'rec_texts':['',' ',None,'text'],'rec_scores':[.1,.2,.3,.4],'rec_polys':[[],[['bad']],[[1,2]],[[3,4],[5,6]]]}, {'rec_texts':['ignored']}]
        result=analysis.observations(image,lambda:model)
        self.assertEqual([r.text for r in result],[' ','None','text']);self.assertEqual(result[0].polygon,());self.assertEqual(result[-1].polygon,((3.,4.),(5.,6.)))
        self.assertEqual(model.predict.call_args.args[0][0,0].tolist(),[30,20,10])
        model.predict.return_value=[{'rec_texts':['x'],'rec_scores':['bad']}]
        with self.assertRaises(ValueError):analysis.observations(image,lambda:model)
        model.predict.return_value=[];self.assertEqual(analysis.observations(image,lambda:model),[])
        # Initialization lock must not cover model inference.
        instance=analysis.IncomingOCREngine(lambda:None,lambda:model);locked=[]
        def predict(_):
            def probe():
                acquired=instance.lock.acquire(blocking=False);locked.append(acquired)
                if acquired:instance.lock.release()
            thread=threading.Thread(target=probe);thread.start();thread.join(2);return []
        model.predict.side_effect=predict;analysis.observations(image,instance.get);self.assertEqual(locked,[True])
    def test_corroboration_critical_crop_translation_and_duplicate_field(self):
        image=np.zeros((100,200,3),np.uint8)
        rules=[{'field_id':'skip','importance':'normal','region_normalized':{}},
            {'field_id':'field','importance':'critical','region_normalized':{'x':.1,'y':.2,'width':.2,'height':.3}},
            {'field_id':'empty','importance':'critical','region_normalized':{'x':2,'y':2,'width':.1,'height':.1}}]
        observe=Mock(return_value=[TextObservation('x',.9,((1,2),),True)])
        result=analysis.corroboration(image,rules,observe)
        observe.assert_called_once();self.assertEqual(observe.call_args.args[0].shape,(38,48,3))
        self.assertEqual(result['field'][0].polygon,((17,18),));self.assertFalse(result['field'][0].corroborated);self.assertEqual(result['empty'],[]);self.assertNotIn('skip',result)
        duplicate=[rules[1],{**rules[2],'field_id':'field'}];self.assertEqual(analysis.corroboration(image,duplicate,observe)['field'],[])
    def test_field_absence_threshold_and_one_pass_evidence(self):
        rule={'region_normalized':{'x':0,'y':0,'width':1,'height':1},'case_sensitive':True,'ignore_whitespace':False}
        image=np.zeros((10,10,3),np.uint8)
        for similarity,sharpness,expected in [(0.419,85,True),(.42,85,False),(.1,84.9,False),(None,85,False)]:
            laplacian=Mock();laplacian.var.return_value=sharpness
            with patch.object(analysis,'observations_for_rule',return_value=[]),patch.object(analysis,'local_visual_similarity',return_value=similarity),patch.object(analysis.cv2,'Laplacian',return_value=laplacian):
                result=analysis.field_observation(rule,[],[],image,image)
            if expected:self.assertEqual(result,TextObservation('',1.0,(),True))
            else:self.assertIsNone(result)
        first=[TextObservation('A',.9,((1,2),))]
        with patch.object(analysis,'observations_for_rule',side_effect=[first,[]]):result=analysis.field_observation(rule,first,[],image,image)
        self.assertEqual(result.confidence,0);self.assertFalse(result.corroborated);self.assertEqual(result.polygon,((1,2),))
    def test_raster_reference_magic_size_and_decode_failures(self):
        image,suffix=analysis.decode_reference(picture(),'unknown.bin');self.assertEqual(image.shape,(300,300,3));self.assertEqual(suffix,'.png')
        for data,name in [(b'','empty.png'),(b'not a PDF','file.pdf'),(b'broken','file.jpg'),(picture(199),'small.png')]:
            with self.assertRaises(HTTPException) as caught:analysis.decode_reference(data,name)
            self.assertEqual(caught.exception.status_code,400)
        with patch.object(analysis.cv2,'imdecode',return_value=types.SimpleNamespace(shape=(1,40_000_001,3))):
            with self.assertRaises(HTTPException):analysis.decode_reference(picture(),'large.png')
    @unittest.skipUnless(fitz is not None,'requires production PyMuPDF; run this group on Linux')
    def test_pdf_reference_single_page_and_original_failure_boundaries(self):
        document=fitz.open();document.new_page(width=100,height=50);contents=document.tobytes();document.close()
        image,suffix=analysis.decode_reference(contents,'unknown.bin');self.assertEqual(image.shape[:2],(100,200));self.assertEqual(suffix,'.pdf')
        with patch.object(analysis.cv2,'imdecode',return_value=None):self.assertEqual(analysis.decode_reference(contents,'x'),(None,'.pdf'))
        document=fitz.open();document.new_page();document.new_page();contents=document.tobytes();document.close()
        with self.assertRaises(HTTPException) as caught:analysis.decode_reference(contents,'x')
        self.assertEqual(caught.exception.status_code,400)
        fake=Mock();fake.page_count=1;fake.__getitem__=Mock(return_value=Mock(get_pixmap=Mock(side_effect=OSError('render'))))
        with patch.object(fitz,'open',return_value=fake):
            with self.assertRaises(HTTPException) as caught:analysis.decode_reference(b'%PDF-fixture','x')
        self.assertEqual(caught.exception.detail,'无法解析标准稿 PDF');fake.close.assert_not_called()
    def test_beta_concurrent_single_flight_and_captured_observer(self):
        first=Mock(return_value=[]);second=Mock(return_value=[]);current=[first]
        service=beta.BetaComparison(beta.BetaPolicy(lambda:3600,lambda:16_000_000,lambda:32*1024*1024),lambda:current[0])
        calls=[];locks=[]
        def compare(reference,captured,identifier,observe):
            calls.append(identifier);observe(reference);current[0]=second;observe(captured)
            def probe():
                acquired=service.lock.acquire(blocking=False);locks.append(acquired)
                if acquired:service.lock.release()
            thread=threading.Thread(target=probe);thread.start();thread.join(2);return {'comparison_id':identifier,'text':'中文'}
        blob=picture()
        with patch.object(comparison_engine,'compare_images',side_effect=compare):
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:service.run('alice','same',blob,blob),range(2)))
            self.assertIs(results[0],results[1]);self.assertEqual(calls,['same']);self.assertEqual(locks,[False]);self.assertEqual(first.call_count,2);second.assert_not_called()
            service.run('bob','same',blob,blob);self.assertEqual(len(calls),2);self.assertEqual(second.call_count,2)
            with self.assertRaises(HTTPException) as caught:service.run('alice','same',b'broken',blob)
            self.assertEqual(caught.exception.status_code,409);self.assertEqual(len(calls),2)
    def test_beta_ttl_budget_result_identity_and_failure_cache(self):
        limits={'ttl':3600,'bytes':10000};service=beta.BetaComparison(beta.BetaPolicy(lambda:limits['ttl'],lambda:16_000_000,lambda:limits['bytes']),lambda:lambda image:[])
        blob=picture();result={'text':'中文'}
        with patch.object(comparison_engine,'compare_images',return_value=result) as compare,patch.object(beta.time,'monotonic',return_value=100):
            self.assertIs(service.run('alice','id',blob,blob),result)
        size=len(json.dumps(result,ensure_ascii=False).encode('utf-8'));self.assertEqual(service.cache[('alice','id')]['size'],size)
        result['later']='mutation';limits['bytes']=0
        with patch.object(beta.time,'monotonic',return_value=3700),patch.object(comparison_engine,'compare_images') as compare:
            self.assertIs(service.run('alice','id',blob,blob),result);compare.assert_not_called()
        self.assertEqual(service.cache[('alice','id')]['created_at'],100);self.assertEqual(service.cache[('alice','id')]['size'],size)
        with patch.object(beta.time,'monotonic',return_value=3700.1),patch.object(comparison_engine,'compare_images',return_value={'new':True}) as compare:
            self.assertEqual(service.run('alice','id',blob,blob),{'new':True});compare.assert_called_once()
        self.assertEqual(service.cache,{})
        limits['bytes']=10000
        with patch.object(comparison_engine,'compare_images',side_effect=RuntimeError('ocr')) as compare:
            first=service.run('alice','failure',blob,blob);self.assertEqual(first['error_code'],'RuntimeError');self.assertIs(service.run('alice','failure',blob,blob),first);compare.assert_called_once()
        with patch.object(comparison_engine,'compare_images',return_value={'bad':object()}):
            with self.assertRaises(TypeError):service.run('alice','serialization',blob,blob)
        self.assertNotIn(('alice','serialization'),service.cache)
        with self.assertRaises(HTTPException):service.run('alice','decode',b'bad',blob)
        self.assertNotIn(('alice','decode'),service.cache)
    def test_beta_api_read_order_permissions_and_contextvar_thread_dispatch(self):
        context=ContextVar('identity',default='default');events=[];owner=lambda:events.append(('owner',)) or {'id':context.get()}
        def permission(name,**kwargs):events.append(('permission',))
        def run(user,identifier,reference,captured):return {'user':user,'context':context.get(),'thread':threading.get_ident()}
        handler=register(FastAPI(),BetaAccess(permission,owner),lambda:10,lambda:run)
        async def invoke():
            token=context.set('scoped-account')
            try:return await handler(Upload('reference',events=events),Upload('captured',events=events),' comparison-01 ')
            finally:context.reset(token)
        result=asyncio.run(invoke());self.assertEqual(result['user'],'scoped-account');self.assertEqual(result['context'],'scoped-account');self.assertNotEqual(result['thread'],threading.get_ident())
        self.assertEqual(events,[('permission',),('read','reference',-1),('read','captured',-1),('owner',)])
        events.clear()
        with self.assertRaises(HTTPException):asyncio.run(handler(Upload('reference',b'',events=events),Upload('captured',events=events),'comparison-01'))
        self.assertEqual(events,[('permission',),('read','reference',-1),('read','captured',-1)])
        events.clear()
        with self.assertRaises(HTTPException):asyncio.run(handler(Upload('reference',content_type='invalid',events=events),Upload('captured',events=events),'comparison-01'))
        self.assertEqual(events,[('permission',)])
    @unittest.skipUnless(ROOT_CHECK,'use --root for application composition')
    def test_root_owns_process_state_and_keeps_dynamic_observer(self):
        with tempfile.TemporaryDirectory(prefix='incoming-analysis-') as directory:
            (Path(directory)/'local_inspection_service/static').mkdir(parents=True)
            os.environ.update(LOCAL_INSPECTION_ROOT=directory,VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
            from local_inspection_service import server
            self.assertIs(server.decode_incoming_reference,analysis.decode_reference);self.assertIs(server._field_observation,analysis.field_observation)
            self.assertIs(server._incoming_text_ocr_lock,server._incoming_ocr_engine.lock)
            self.assertIs(server._text_compare_beta_cache,server._beta_comparison.cache);self.assertIs(server._text_compare_beta_cache_lock,server._beta_comparison.lock)
            callback=Mock(return_value=[])
            with patch.object(server,'incoming_text_ocr_observations',callback):
                self.assertIs(server._beta_comparison.observer(),callback)
                server.incoming_text_corroboration_observations(np.zeros((20,20,3),np.uint8),[{'field_id':'x','importance':'critical','region_normalized':{'x':0,'y':0,'width':1,'height':1}}])
                callback.assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)

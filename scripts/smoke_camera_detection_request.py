"""Camera request orchestration without model or physical PLC calls."""
import ast,asyncio,hashlib,os,sys,tempfile,unittest
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock,Mock
import cv2
import numpy as np
from fastapi import File,Form,HTTPException,Request,UploadFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from canonical_application_source_contract import read_checked_application_source
from local_inspection_service.plc_fx_ascii import PlcConfigError
BASELINE=os.environ.get('VANTALINE_CAMERA_DETECTION_BASELINE_SOURCE')
def create(b):
 if BASELINE:
  node=next(n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body if isinstance(n,ast.AsyncFunctionDef) and n.name=='analyze_camera_image');node.decorator_list=[]
  ns=dict(b,Any=Any,HTTPException=HTTPException,File=File,Form=Form,Request=Request,UploadFile=UploadFile,Path=Path,hashlib=hashlib,np=np,cv2=cv2,PlcConfigError=PlcConfigError);exec(compile(ast.Module(body=[node],type_ignores=[]),BASELINE,'exec'),ns);return SimpleNamespace(analyze_camera_image=ns['analyze_camera_image']),ns
 from local_inspection_service.detection.camera_request import CameraDetectionRequest
 from local_inspection_service.detection.camera_request_ports import CameraRequestAccess,CameraDispatchEvidence,CameraImageExecution
 def ports(cls):return cls(**{f.name:lambda name=f.name:b[name] for f in fields(cls)})
 return CameraDetectionRequest(ports(CameraRequestAccess),ports(CameraDispatchEvidence),ports(CameraImageExecution)),b
class Contracts(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.events=[];self.station={'id':'station-a'};self.dispatch={'dispatch_id':'dispatch-a'};self.payload=b'not an image';self.file=SimpleNamespace(filename='IMAGE.JPG',read=AsyncMock(side_effect=self.read));self.writes=[];self.finished=[];self.result={'passed':True};self.created=True
  b=dict(ensure_dirs=self.mark('ensure'),require_analyze_model_permission=self.mark('permission'),require_plc_web_serial_station=lambda request:self.station,plc_web_serial_begin_camera_detection=self.begin,plc_web_serial_finish_camera_detection=self.finish,plc_web_serial_dispatch_public=lambda d:dict(d),UPLOAD_DIR=Path(self.temp.name),_business_files=SimpleNamespace(write_bytes=lambda p,v:self.writes.append((p,v))),safe_name=lambda s:s.replace('/','_'),analyze_bgr=lambda *a,**kw:self.result)
  self.s,self.b=create(b)
 def mark(self,name):
  def fn(*a,**k):self.events.append((name,a,k))
  return fn
 async def read(self):self.events.append(('read',));return self.payload
 def begin(self,*args):self.events.append(('begin',args));return self.dispatch,self.created
 def finish(self,*args):self.finished.append(args);return {'dispatch_id':'dispatch-a','result':args[3]}
 async def run_camera(self):return await self.s.analyze_camera_image(object(),self.file,' model-a ','lease-a','camera/a')
 def valid_image(self):self.payload=cv2.imencode('.png',np.zeros((2,3,3),dtype=np.uint8))[1].tobytes()
 async def test_success_evidence_before_decode_model_and_finish(self):
  self.valid_image();out=await self.run_camera();self.assertEqual([e[0] for e in self.events],['ensure','permission','read','begin']);self.assertEqual(self.events[-1][1],('station-a','lease-a','camera/a','model-a',hashlib.sha256(self.payload).hexdigest()));self.assertEqual(self.writes,[(Path(self.temp.name)/'camera_camera_a.jpg',self.payload)]);self.assertEqual(self.finished,[('station-a','dispatch-a','lease-a',self.result)]);self.assertEqual(out,{'passed':True,'plc_sync':{'dispatch_id':'dispatch-a','result':self.result}})
 async def test_duplicate_completed_returns_without_decode_or_write(self):
  self.created=False;stored={'passed':False,'nested':[]};self.dispatch['result']=stored;out=await self.run_camera();self.assertEqual(out['passed'],False);self.assertIs(out['nested'],stored['nested']);self.assertEqual(self.writes,[]);self.assertEqual(self.finished,[])
 async def test_duplicate_pending_returns_conflict(self):
  self.created=False
  with self.assertRaises(HTTPException) as err:await self.run_camera()
  self.assertEqual((err.exception.status_code,err.exception.detail),(409,'plc_camera_request_in_progress'));self.assertEqual(self.finished,[])
 async def test_begin_conflict_and_other_error_identity(self):
  error=PlcConfigError('lease unavailable');self.b['plc_web_serial_begin_camera_detection']=Mock(side_effect=error)
  with self.assertRaises(HTTPException) as err:await self.run_camera()
  self.assertEqual(err.exception.status_code,409);self.assertIs(err.exception.__cause__,error)
  sentinel=RuntimeError('unknown');self.b['plc_web_serial_begin_camera_detection']=Mock(side_effect=sentinel)
  with self.assertRaises(RuntimeError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.assertEqual(self.finished,[])
 async def test_permission_and_station_denied_precede_upload_read(self):
  self.b['require_analyze_model_permission']=Mock(side_effect=HTTPException(403,'model'))
  with self.assertRaises(HTTPException):await self.run_camera()
  self.file.read.assert_not_awaited();self.b['require_analyze_model_permission']=self.mark('permission');self.b['require_plc_web_serial_station']=Mock(side_effect=HTTPException(403,'station'))
  with self.assertRaises(HTTPException):await self.run_camera()
  self.file.read.assert_not_awaited();self.assertEqual(self.finished,[])
 async def test_decode_failure_settles_once_before_http_error(self):
  with self.assertRaises(HTTPException) as err:await self.run_camera()
  self.assertEqual(err.exception.status_code,400);self.assertEqual(self.finished,[('station-a','dispatch-a','lease-a',None,'image_decode_failed')]);self.assertEqual(self.writes,[])
 async def test_decode_settlement_error_preserved_not_retried(self):
  sentinel=RuntimeError('settlement');self.b['plc_web_serial_finish_camera_detection']=Mock(side_effect=sentinel)
  with self.assertRaises(RuntimeError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.b['plc_web_serial_finish_camera_detection'].assert_called_once()
 async def test_write_and_model_failure_best_effort_finish(self):
  self.valid_image();sentinel=OSError('write');self.b['_business_files'].write_bytes=Mock(side_effect=sentinel);self.b['analyze_bgr']=Mock(side_effect=AssertionError('no analysis'))
  with self.assertRaises(OSError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.assertEqual(self.finished[-1][-1],'OSError');self.b['analyze_bgr'].assert_not_called()
  self.b['_business_files'].write_bytes=lambda p,v:self.writes.append((p,v));sentinel=ValueError('model');self.b['analyze_bgr']=Mock(side_effect=sentinel);self.b['plc_web_serial_finish_camera_detection']=Mock(side_effect=RuntimeError('finish also failed'))
  with self.assertRaises(ValueError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.assertEqual(len(self.writes),1);self.b['analyze_bgr'].assert_called_once();self.b['plc_web_serial_finish_camera_detection'].assert_called_once()
 async def test_success_settlement_failure_records_error_no_model_replay(self):
  self.valid_image();sentinel=RuntimeError('unknown write');self.b['analyze_bgr']=Mock(return_value=self.result);self.b['plc_web_serial_finish_camera_detection']=Mock(side_effect=[sentinel,RuntimeError('second failed')])
  with self.assertRaises(RuntimeError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.b['analyze_bgr'].assert_called_once();self.assertEqual(self.b['plc_web_serial_finish_camera_detection'].call_count,2);self.assertEqual(self.b['plc_web_serial_finish_camera_detection'].call_args.args,('station-a','dispatch-a','lease-a',None,'RuntimeError'))
 async def test_publication_failure_keeps_result_and_records_error(self):
  self.valid_image();sentinel=TypeError('public');self.b['plc_web_serial_dispatch_public']=Mock(side_effect=sentinel)
  with self.assertRaises(TypeError) as err:await self.run_camera()
  self.assertIs(err.exception,sentinel);self.assertEqual(len(self.finished),2);self.assertIs(self.finished[0][3],self.result);self.assertEqual(self.finished[1][-1],'TypeError')
 async def test_late_dependency_after_await_and_pretry_filename_failure(self):
  async def read():self.b['plc_web_serial_begin_camera_detection']=Mock(side_effect=RuntimeError('late begin'));return self.payload
  self.file.read=AsyncMock(side_effect=read)
  with self.assertRaisesRegex(RuntimeError,'late begin'):await self.run_camera()
  self.b['plc_web_serial_begin_camera_detection']=self.begin;self.file.read=AsyncMock(side_effect=self.read);self.valid_image();self.file.filename=None
  with self.assertRaises(TypeError):await self.run_camera()
  self.assertEqual(self.finished,[]);self.assertEqual(self.writes,[])
 @unittest.skipIf(bool(BASELINE),'candidate assembly only')
 async def test_actual_wiring_and_no_entry_import(self):
  tree=ast.parse(read_checked_application_source(ROOT / 'local_inspection_service/server.py'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_camera_detection_request' for t in n.targets));count=0
  for group in binding.keywords:
   for kw in group.value.keywords:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id);count+=1
  self.assertEqual(count,10)
if __name__=='__main__':unittest.main()

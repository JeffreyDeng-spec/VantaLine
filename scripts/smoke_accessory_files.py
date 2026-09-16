"""Real HTTP file-edit baseline with disposable images and provider substitutes."""
import copy
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from fastapi.testclient import TestClient


class FileContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="accessory-files-")
        cls.root = Path(cls.temporary.name)
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server
        cls.admin = TestClient(server.app, base_url='https://testserver')
        assert cls.admin.post('/api/auth/bootstrap', json={'username':'fixture-admin','password':'fixture-password-only'}).status_code==200
        cls.users, cls.clients = {}, {}
        for name in ('alice','bob'):
            result=cls.admin.post('/api/auth/users',json={'username':name,'password':'fixture-password-only','role':'user','permissions':['accessory_library']})
            assert result.status_code==200, result.text
            cls.users[name]=result.json()['user']
            client=TestClient(server.app,base_url='https://testserver',raise_server_exceptions=False)
            assert client.post('/api/auth/login',json={'username':name,'password':'fixture-password-only'}).status_code==200
            cls.clients[name]=client
        cls.png=cv2.imencode('.png',np.full((80,100,3),127,dtype=np.uint8))[1].tobytes()

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients.values(): client.close()
        cls.admin.close()
        cls.temporary.cleanup()

    def setUp(self):
        self.state={'accessories':[],'training':{'selected_accessory_ids':[]}}
        self.events=[]
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        def save(item, config=None):
            self.events.append('save')
            self.state=copy.deepcopy(config)
            return dict(item)
        def refresh(item, *, force_profile=True):
            self.events.append(('refresh',force_profile))
        def detail(item):
            self.events.append('detail')
            return {'gallery':[{'source_path':path} for path in item.get('source_files',[])]}
        def generate(item, *, allow_provider=True):
            self.assertTrue(allow_provider)
            self.events.append('generate')
        self.stack.enter_context(patch.object(self.server,'load_config',side_effect=lambda:copy.deepcopy(self.state)))
        self.stack.enter_context(patch.object(self.server,'save_accessory_item',side_effect=save))
        self.stack.enter_context(patch.object(self.server,'refresh_accessory_assets_after_source_change',side_effect=refresh))
        self.stack.enter_context(patch.object(self.server,'save_ai_profile_cache',side_effect=lambda payload:self.events.append(('cache',payload))))
        self.stack.enter_context(patch.object(self.server,'accessory_detail_payload',side_effect=detail))
        self.stack.enter_context(patch.object(self.server,'generate_accessory_ai_profile',side_effect=generate))
        self.stack.enter_context(patch.object(self.server,'fallback_accessory_ai_profile',return_value={'fallback':'synthetic'}))
        self.stack.enter_context(patch.object(self.server,'clean_sprite_assets',return_value=[{'fixture':True}]))

    def seed(self, name, kind='object', *, outside=False):
        base=self.root/'outside' if outside else self.server.UPLOAD_DIR/'accessories'/name
        base.mkdir(parents=True,exist_ok=True)
        path=base/(name+'.png')
        path.write_bytes(self.png)
        item={'id':name,'name':name,'class_id':0 if kind=='object' else 1,'material_type':kind,
              'owner_user_id':self.users['alice']['id'],'source_files':[str(path)],
              'shared_with_user_ids':[self.users['bob']['id']]}
        self.state['accessories']=[item]
        return path,item

    def test_upload_authorization_text_limits_partial_files_and_order(self):
        client=self.clients['alice']
        path,item=self.seed('upload')
        response=self.clients['bob'].post('/api/accessories/upload/files',files={'files':('denied.png',self.png,'image/png')})
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.events,[])
        self.assertEqual(list(path.parent.glob('*_denied.png')),[])
        self.assertEqual(client.post('/api/accessories/upload/files').json(),{'detail':'No files uploaded'})
        self.assertEqual(client.post('/api/accessories/missing/files',files={'files':('a.png',self.png)}).status_code,404)
        response=client.post('/api/accessories/upload/files',files=[('files',('partial.png',self.png,'image/png')),('files',('bad.txt',b'fixture','text/plain'))])
        self.assertEqual(response.status_code,400)
        self.assertEqual(len(list(path.parent.glob('*_partial.png'))),1)
        self.assertEqual(self.state['accessories'][0]['source_files'],[str(path)])
        self.assertEqual(self.events,[])
        response=client.post('/api/accessories/upload/files',files={'files':('valid.PNG',self.png,'image/png')})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.events[:3],[('refresh',True),('cache',{'entries':{}}),'save'])
        self.assertTrue(self.state['accessories'][0]['source_files'][-1].endswith('_valid.png'))
        text,item=self.seed('text-limit','text')
        self.events.clear()
        response=client.post('/api/accessories/text-limit/files',files=[('files',('one.png',self.png)),('files',('two.png',self.png))])
        self.assertEqual((response.status_code,response.json()),(400,{'detail':'文字类配件最多上传 2 张图片'}))
        self.assertEqual(list(text.parent.glob('*_one.png')),[])
        response=client.post('/api/accessories/text-limit/files',files={'files':('movie.mp4',b'fixture')})
        self.assertEqual(response.json(),{'detail':'文字类配件只能上传图片，不能上传视频或其它文件'})
        response=client.post('/api/accessories/text-limit/files',files={'files':('second.png',self.png)})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.state['accessories'][0]['original_source_files'],[self.state['accessories'][0]['source_files'][-1]])
        self.assertTrue(self.state['accessories'][0]['original_source_files'][0].endswith('_second.png'))

    def test_crop_pixels_clamp_unique_names_and_validation(self):
        client=self.clients['alice']
        path,item=self.seed('crop','text')
        corners=[{'x':-10,'y':-10},{'x':110,'y':0},{'x':100,'y':100},{'x':0,'y':110}]
        payload={'source_path':str(path),'corners':corners}
        self.assertEqual(self.clients['bob'].post('/api/accessories/crop/text-crop',json=payload).status_code,404)
        self.assertEqual(self.events,[])
        self.assertEqual(client.post('/api/accessories/crop/text-crop',json={**payload,'corners':corners[:3]}).json(),{'detail':'corners must contain tl,tr,br,bl'})
        tiny=[{'x':0,'y':0},{'x':1,'y':0},{'x':1,'y':1},{'x':0,'y':1}]
        self.assertEqual(client.post('/api/accessories/crop/text-crop',json={**payload,'corners':tiny}).json(),{'detail':'Crop area is too small'})
        result=client.post('/api/accessories/crop/text-crop',json=payload)
        self.assertEqual(result.status_code,200,result.text)
        output=Path(result.json()['source_path'])
        self.assertEqual(output.name,'crop_manual_rectified.png')
        self.assertEqual(cv2.imread(str(output)).shape,(80,100,3))
        cropped=cv2.imread(str(output))
        self.assertTrue(np.all(cropped[:-1,:-1]==127))
        self.assertTrue(np.all(cropped[-1,:]==0))
        self.assertTrue(np.all(cropped[:,-1]==0))
        self.assertEqual(self.events[:3],[('refresh',True),('cache',{'entries':{}}),'save'])
        second=client.post('/api/accessories/crop/text-crop',json=payload)
        self.assertTrue(second.json()['source_path'].endswith('_manual_rectified_1.png'))
        response=client.post('/api/accessories/crop/text-crop',json={**payload,'source_path':str(output)})
        self.assertEqual(response.json(),{'detail':'This text image is already manually cropped'})
        with patch('cv2.imwrite',return_value=False):
            response=client.post('/api/accessories/crop/text-crop',json=payload)
        self.assertEqual((response.status_code,response.json()),(500,{'detail':'Failed to save cropped image'}))

    def test_crop_preserves_asymmetric_corner_orientation(self):
        path, item = self.seed('crop-colour', 'text')
        pixels = np.empty((80, 100, 3), dtype=np.uint8)
        pixels[:40, :50] = (10, 20, 30)
        pixels[:40, 50:] = (40, 50, 60)
        pixels[40:, :50] = (70, 80, 90)
        pixels[40:, 50:] = (100, 110, 120)
        self.assertTrue(cv2.imwrite(str(path), pixels))
        response = self.clients['alice'].post('/api/accessories/crop-colour/text-crop', json={
            'source_path': str(path),
            'corners': [{'x': 0, 'y': 0}, {'x': 100, 'y': 0},
                        {'x': 100, 'y': 100}, {'x': 0, 'y': 100}],
        })
        self.assertEqual(response.status_code, 200, response.text)
        cropped = cv2.imread(response.json()['source_path'])
        self.assertEqual(cropped.shape, (80, 100, 3))
        self.assertEqual(cropped[10, 10].tolist(), [10, 20, 30])
        self.assertEqual(cropped[10, 80].tolist(), [40, 50, 60])
        self.assertEqual(cropped[60, 10].tolist(), [70, 80, 90])
        self.assertEqual(cropped[60, 80].tolist(), [100, 110, 120])

    def test_reference_provider_failure_preserves_selection_and_save_order(self):
        path,item=self.seed('reference')
        client=self.clients['alice']
        endpoint='/api/accessories/reference/ai-reference'
        self.assertEqual(self.clients['bob'].post(endpoint,json={'source_path':str(path)}).status_code,404)
        self.assertEqual(self.events,[])
        self.assertEqual(client.post(endpoint,json={'source_path':' '}).json(),{'detail':'source_path is required'})
        self.assertEqual(client.post(endpoint,json={'source_path':str(path.with_name('unregistered.png'))}).status_code,404)
        self.events.clear()
        def failure(*args,**kwargs):
            self.assertEqual(kwargs,{'allow_provider':True})
            self.events.append('generate_failed')
            raise RuntimeError('synthetic provider failure '+('x'*200))
        with patch.object(self.server,'generate_accessory_ai_profile',side_effect=failure):
            response=client.post(endpoint,json={'source_path':' '+str(path)+' '})
        self.assertEqual(response.status_code,200,response.text)
        saved=self.state['accessories'][0]
        self.assertEqual(saved['ai_profile_reference_files'],[str(path)])
        self.assertEqual(saved['ai_profile'],{'fallback':'synthetic'})
        self.assertEqual(saved['ai_profile_status']['status'],'fallback')
        self.assertTrue(saved['ai_profile_status']['message'].startswith('AI profile provider failed; using selected local reference. '))
        self.assertLess(len(saved['ai_profile_status']['message']),200)
        self.assertEqual(self.events[:4],['detail','generate_failed',('cache',{'entries':{}}),'save'])

    def test_refresh_and_reference_outer_failures_keep_partial_effects(self):
        client=self.clients['alice']
        def failure(*args,**kwargs):
            self.events.append('refresh_failed')
            raise RuntimeError('synthetic source refresh failure')
        path,item=self.seed('upload-refresh-fail')
        with patch.object(self.server,'refresh_accessory_assets_after_source_change',side_effect=failure):
            result=client.post('/api/accessories/upload-refresh-fail/files',files={'files':('new.png',self.png)})
        self.assertEqual(result.status_code,500)
        self.assertEqual(self.events,['refresh_failed'])
        self.assertEqual(len(list(path.parent.glob('*_new.png'))),1)
        self.assertEqual(self.state['accessories'][0]['source_files'],[str(path)])
        path,item=self.seed('crop-refresh-fail','text')
        self.events.clear()
        payload={'source_path':str(path),'corners':[{'x':0,'y':0},{'x':100,'y':0},{'x':100,'y':100},{'x':0,'y':100}]}
        with patch.object(self.server,'refresh_accessory_assets_after_source_change',side_effect=failure):
            result=client.post('/api/accessories/crop-refresh-fail/text-crop',json=payload)
        self.assertEqual(result.status_code,500)
        self.assertTrue(path.with_name('crop-refresh-fail_manual_rectified.png').exists())
        self.assertEqual(self.events,['refresh_failed'])
        self.assertEqual(self.state['accessories'][0]['source_files'],[str(path)])
        path,item=self.seed('delete-refresh-fail')
        self.events.clear()
        with patch.object(self.server,'refresh_accessory_assets_after_source_change',side_effect=failure):
            result=client.request('DELETE','/api/accessories/delete-refresh-fail/files',json={'source_path':str(path)})
        self.assertEqual(result.status_code,500)
        self.assertFalse(path.exists())
        self.assertEqual(self.events,['refresh_failed'])
        self.assertEqual(self.state['accessories'][0]['source_files'],[str(path)])
        path,item=self.seed('reference-outer-fail')
        endpoint='/api/accessories/reference-outer-fail/ai-reference'
        self.events.clear()
        with patch.object(self.server,'fallback_accessory_ai_profile',side_effect=RuntimeError('synthetic fallback failure')):
            result=client.post(endpoint,json={'source_path':str(path)})
        self.assertEqual(result.status_code,500)
        self.assertEqual(self.events,['detail'])
        self.assertNotIn('ai_profile_reference_files',self.state['accessories'][0])
        self.events.clear()
        with patch.object(self.server,'save_ai_profile_cache',side_effect=RuntimeError('synthetic cache failure')):
            result=client.post(endpoint,json={'source_path':str(path)})
        self.assertEqual(result.status_code,500)
        self.assertEqual(self.events,['detail','generate'])
        self.assertNotIn('ai_profile_reference_files',self.state['accessories'][0])

    def test_delete_registered_paths_data_boundary_pose_and_unlink_failure(self):
        client=self.clients['alice']
        path,item=self.seed('delete')
        endpoint='/api/accessories/delete/files'
        self.assertEqual(self.clients['bob'].request('DELETE',endpoint,json={'source_path':str(path)}).status_code,404)
        self.assertTrue(path.exists())
        self.assertEqual(self.events,[])
        self.assertEqual(client.request('DELETE',endpoint,json={'source_path':str(path.with_name('unknown.png'))}).status_code,404)
        result=client.request('DELETE',endpoint,json={'source_path':str(path)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(path.exists())
        self.assertEqual(self.events[:3],[('refresh',True),('cache',{'entries':{}}),'save'])
        outside,item=self.seed('outside-delete',outside=True)
        result=client.request('DELETE','/api/accessories/outside-delete/files',json={'source_path':str(outside)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(outside.exists())
        self.assertEqual(self.state['accessories'][0]['source_files'],[])
        path,item=self.seed('unlink-failure')
        with patch.object(Path,'unlink',side_effect=PermissionError('synthetic unlink failure')):
            result=client.request('DELETE','/api/accessories/unlink-failure/files',json={'source_path':str(path)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(path.exists())
        path,item=self.seed('pose-delete')
        pose=path.with_name('pose.png');pose.write_bytes(self.png)
        item.update(codex_image_jobs=[{'output_path':str(pose),'job_id':'first'},{'output_path':'other','job_id':'second'}],
                    normalized_assets=[{'path':'derived','source_pose_collection':str(pose)},{'path':'keep'}])
        self.events.clear()
        result=client.request('DELETE','/api/accessories/pose-delete/files',json={'source_path':str(pose)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertFalse(pose.exists())
        saved=self.state['accessories'][0]
        self.assertEqual(saved['codex_image_job']['job_id'],'second')
        self.assertEqual(saved['normalized_assets'],[{'path':'keep'}])
        self.assertEqual(saved['clean_sprite_status'],'ready')
        self.assertEqual(self.events[:1],['save'])
        self.assertFalse(any(isinstance(event,tuple) and event[0] in ('refresh','cache') for event in self.events))
        path,item=self.seed('legacy-pose')
        pose=path.with_name('legacy-pose-output.png');pose.write_bytes(self.png)
        item['codex_image_job']={'output_path':str(pose),'job_id':'legacy'}
        result=client.request('DELETE','/api/accessories/legacy-pose/files',json={'source_path':str(pose)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.state['accessories'][0]['codex_image_job']['output_path'],str(pose))
        self.assertFalse(pose.exists())
        path,item=self.seed('source-and-pose')
        item['codex_image_jobs']=[{'output_path':str(path),'job_id':'both'}]
        self.events.clear()
        result=client.request('DELETE','/api/accessories/source-and-pose/files',json={'source_path':str(path)})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.events[:3],[('refresh',True),('cache',{'entries':{}}),'save'])
        self.assertEqual(self.state['accessories'][0]['codex_image_jobs'],[])


if __name__=='__main__':
    unittest.main()

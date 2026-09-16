"""Gallery HTTP and image-byte baselines with disposable local media only."""
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


class GalleryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='accessory-gallery-')
        cls.root = Path(cls.temporary.name)
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root), VANTALINE_DATA_STORE='json',
                          VANTALINE_LABEL_INSPECTION_ENABLED='false', LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
        from local_inspection_service import server
        cls.server = server
        cls.admin = TestClient(server.app, base_url='https://testserver')
        assert cls.admin.post('/api/auth/bootstrap', json={'username':'fixture-admin','password':'fixture-password-only'}).status_code == 200
        cls.clients, cls.users = {}, {}
        for name in ('alice','bob'):
            response = cls.admin.post('/api/auth/users',json={'username':name,'password':'fixture-password-only','role':'user','permissions':['accessory_library']})
            assert response.status_code == 200
            cls.users[name] = response.json()['user']
            client = TestClient(server.app, base_url='https://testserver', raise_server_exceptions=False)
            assert client.post('/api/auth/login',json={'username':name,'password':'fixture-password-only'}).status_code == 200
            cls.clients[name] = client

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients.values(): client.close()
        cls.admin.close()
        cls.temporary.cleanup()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state = {'accessories':[]}
        self.stack.enter_context(patch.object(self.server,'load_config',side_effect=lambda:copy.deepcopy(self.state)))

    def image(self, name, pixels=None):
        path = self.server.OUTPUT_DIR/'gallery-fixtures'/(name+'.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(cv2.imwrite(str(path), np.full((12,20,3),70,dtype=np.uint8) if pixels is None else pixels))
        return path

    def seed(self, identifier, kind='object', **fields):
        source = self.image(identifier+'-source')
        item = {'id':identifier, 'class_id':0 if kind=='object' else 1, 'name':identifier,
                'material_type':kind,'source_files':[str(source)],'original_source_files':[str(source)],'owner_user_id':self.users['alice']['id'],
                'created_at':111,'updated_at':222,'codex_image_private':'synthetic-private',
                'pose_collection_prompt':'synthetic-prompt','preprocess':'Codex CLI ImageWorker Pose Collection'}
        item.update(fields)
        self.state['accessories'] = [item]
        return source, item

    def detail(self, identifier, client='alice'):
        return self.clients[client].get('/api/accessories/'+identifier+'/detail')

    def test_preview_alpha_grayscale_dimensions_and_unchecked_write_result(self):
        pixels = np.zeros((6,8,4),dtype=np.uint8)
        pixels[:,:,:3] = (20,40,60)
        pixels[:,0:3,3] = 0
        pixels[:,3:6,3] = 128
        pixels[:,6:,3] = 255
        src = self.image('alpha',pixels)
        target = self.server.OUTPUT_DIR/'preview-alpha/result.png'
        result = self.server.write_gallery_preview(src,target)
        image = cv2.imread(str(target))
        self.assertEqual((result['width'],result['height']),(8,6))
        self.assertEqual(image[2,1].tolist(),[245,245,245])
        self.assertEqual(image[2,4].tolist(),[132,142,152])
        self.assertEqual(image[2,7].tolist(),[20,40,60])
        gray = self.image('gray',np.full((10,20),83,dtype=np.uint8))
        resized = self.server.OUTPUT_DIR/'preview-gray/result.png'
        result = self.server.write_gallery_preview(gray,resized,max_side=8)
        self.assertEqual((result['width'],result['height']),(8,4))
        self.assertTrue(np.all(cv2.imread(str(resized))==83))
        bad = self.server.OUTPUT_DIR/'bad-preview.png'
        bad.write_text('synthetic invalid image',encoding='utf-8')
        self.assertIsNone(self.server.write_gallery_preview(bad,self.server.OUTPUT_DIR/'unreadable/result.png'))
        self.assertFalse((self.server.OUTPUT_DIR/'unreadable').exists())
        with patch('cv2.imwrite',return_value=False):
            result = self.server.write_gallery_preview(src,self.server.OUTPUT_DIR/'failed-write/result.png')
        self.assertEqual((result['width'],result['height']),(8,6))
        self.assertFalse((self.server.OUTPUT_DIR/'failed-write/result.png').exists())

    def test_http_order_deduplication_metadata_and_default_reference(self):
        source,item = self.seed('gallery-order')
        pose, sprite, derived = [self.image(name) for name in ('pose-order','sprite-order','derived-order')]
        item['source_files'].append(str(source))
        item['codex_image_jobs'] = [{'output_path':str(pose),'label':'Fixture pose'}, {'output_path':str(pose),'label':'Duplicate'}]
        asset = {'path':str(sprite),'pose_family':'upright','pose_position':'top','source_long_side_px':99,
                 'source_long_short_ratio':2.5,'task_id':'fixture-task','render_footprint_mm':[10,20],
                 'normalized_bbox_xyxy':[1,2,3,4],'edge_alpha_pass':True}
        with patch.object(self.server,'clean_sprite_assets',return_value=[{'path':str(source)},asset]), \
             patch.object(self.server,'accessory_image_paths',return_value=[source,pose,sprite,derived]):
            response = self.detail('gallery-order')
        self.assertEqual(response.status_code,200,response.text)
        result = response.json()
        gallery = result['gallery']
        self.assertEqual([entry['kind'] for entry in gallery],['source','pose_collection','clean_object_sprite','derived'])
        self.assertEqual([entry['ai_reference'] for entry in gallery],[True,False,False,False])
        self.assertEqual([entry['source_path'] for entry in gallery],[str(source),str(pose),str(sprite),str(derived)])
        self.assertEqual(gallery[2]['label'],'无背景 sprite 2')
        for field,value in asset.items():
            if field!='path': self.assertEqual(gallery[2][field],value)
        for entry in gallery:
            self.assertEqual((entry['created_at'],entry['updated_at']),(111,222))
        self.assertFalse(any(key.startswith(('codex_image','pose_collection_prompt')) for key in result['item']))
        self.assertIn('codex_image_private',item)

    def test_authorization_precedes_preview_side_effects_and_shared_read_remains(self):
        source,item = self.seed('gallery-access')
        before = set(self.server.OUTPUT_DIR.rglob('source_01.png'))
        denied = self.detail('gallery-access','bob')
        self.assertEqual(denied.status_code,404)
        self.assertEqual(set(self.server.OUTPUT_DIR.rglob('source_01.png')),before)
        item['shared_with_user_ids'] = [self.users['bob']['id']]
        allowed = self.detail('gallery-access','bob')
        self.assertEqual(allowed.status_code,200,allowed.text)
        self.assertEqual(allowed.json()['gallery'][0]['source_path'],str(source))
        self.assertEqual(allowed.json()['item']['source_files'],[])
        self.assertEqual(allowed.json()['item']['original_source_files'],[])
        self.assertEqual(allowed.json()['item']['preprocess'],'本地生成 生成任务 多角度视图')
        owner = self.detail('gallery-access')
        self.assertEqual(owner.json()['item']['source_files'],[])
        admin = self.admin.get('/api/accessories/gallery-access/detail')
        self.assertEqual(admin.status_code,200,admin.text)
        self.assertEqual(admin.json()['item']['source_files'],[source.as_posix()])
        self.assertEqual(admin.json()['item']['original_source_files'],[source.as_posix()])
        self.assertEqual(item['source_files'],[str(source)])
        self.assertEqual(item['original_source_files'],[str(source)])
        self.assertEqual(item['preprocess'],'Codex CLI ImageWorker Pose Collection')
        self.assertGreater(len(set(self.server.OUTPUT_DIR.rglob('source_01.png'))),len(before))
        self.assertEqual(self.detail('not-present').status_code,404)

    def test_text_kind_explicit_reference_and_clean_sprite_cap(self):
        source,item = self.seed('gallery-text','text')
        pose = self.image('text-pose')
        item['ai_profile_reference_files'] = [str(pose)]
        item['codex_image_jobs'] = [{'output_path':str(pose)}]
        with patch.object(self.server,'clean_sprite_assets',return_value=[]), \
             patch.object(self.server,'accessory_image_paths',return_value=[source,pose]):
            response = self.detail('gallery-text')
        gallery = response.json()['gallery']
        self.assertEqual([entry['kind'] for entry in gallery],['source','normalized'])
        self.assertEqual([entry['ai_reference'] for entry in gallery],[False,True])
        self.assertEqual(gallery[0]['label'],'文档照片')
        cap_source, cap_item = self.seed('gallery-cap')
        assets = [{'path':str(self.image('cap-'+str(index)))} for index in range(21)]
        with patch.object(self.server,'clean_sprite_assets',return_value=assets), \
             patch.object(self.server,'accessory_image_paths',return_value=[]):
            response = self.detail('gallery-cap')
        self.assertEqual(response.status_code,200,response.text)
        clean = [entry for entry in response.json()['gallery'] if entry['kind']=='clean_object_sprite']
        self.assertEqual(len(clean),18)
        self.assertEqual(clean[-1]['source_path'],assets[17]['path'])
        assets[0] = {'path':str(cap_source)}
        with patch.object(self.server,'clean_sprite_assets',return_value=assets), \
             patch.object(self.server,'accessory_image_paths',return_value=[]):
            response = self.detail('gallery-cap')
        clean = [entry for entry in response.json()['gallery'] if entry['kind']=='clean_object_sprite']
        self.assertEqual(len(clean),17)
        self.assertEqual(clean[-1]['source_path'],assets[17]['path'])
        self.assertNotIn(assets[18]['path'],[entry['source_path'] for entry in clean])

    def test_preview_exception_keeps_earlier_generated_file(self):
        source,item = self.seed('gallery-failure')
        second = self.image('gallery-failure-second')
        item['source_files'].append(str(second))
        original = cv2.imread
        def read(path, flags):
            if path==str(second): raise OSError('synthetic second preview read failure')
            return original(path, flags)
        with patch('cv2.imread',side_effect=read):
            response = self.detail('gallery-failure')
        self.assertEqual(response.status_code,500)
        self.assertTrue(list(self.server.OUTPUT_DIR.rglob('gallery-failure/source_01.png')))
        self.assertFalse(list(self.server.OUTPUT_DIR.rglob('gallery-failure/source_02.png')))


if __name__ == '__main__':
    unittest.main()

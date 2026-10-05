"""Sprite behavior replay using synthetic arrays and file adapters only."""
import ast
from collections import defaultdict
from dataclasses import fields
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
import time
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch, Mock
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASELINE = os.environ.get('VANTALINE_AUTO_SPRITES_BASELINE_SOURCE')
NAMES = ('auto_optimize_load_sprite', 'auto_optimize_sprite_records_for_sample',
         'auto_optimize_resolve_artifact_path', 'auto_optimize_backfill_missing_sprites_for_sample',
         'auto_optimize_public_sprite_pool', 'auto_optimize_sprite_visible_size',
         'auto_optimize_source_to_canvas_scale', 'auto_optimize_canonical_sprite_sizes',
         'auto_optimize_sprite_target_size')

def create(bindings):
    if BASELINE:
        nodes = [n for n in ast.parse(Path(BASELINE).read_text(encoding='utf-8-sig')).body
                 if isinstance(n, ast.FunctionDef) and n.name in NAMES]
        assert len(nodes) == len(NAMES)
        ns = dict(bindings, Any=Any, Path=Path, PurePosixPath=PurePosixPath, cv2=cv2,
                  np=np, time=time, defaultdict=defaultdict)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), BASELINE, 'exec'), ns)
        return SimpleNamespace(**{name: ns[name] for name in NAMES}), ns
    from local_inspection_service.training.auto_optimization_sprites import AutoOptimizationSprites
    from local_inspection_service.training.auto_optimization_sprites_ports import SpriteFiles, SpriteGeometry
    def ports(cls): return cls(**{f.name: lambda name=f.name: bindings[name] for f in fields(cls)})
    service = AutoOptimizationSprites(ports(SpriteFiles), ports(SpriteGeometry))
    bindings.update({name: getattr(service, name) for name in NAMES})
    return service, bindings

class SpriteContract(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); images = {}; events = []
        def read(path, flag): events.append(('read', Path(path).name, flag)); return images.get(Path(path).name)
        def bbox(mask, *, threshold):
            y, x = np.where(mask > threshold)
            return [int(x.min()), int(y.min()), int(x.max())+1, int(y.max())+1] if len(x) else [0,0,0,0]
        def write(**kwargs): events.append(('sprite', kwargs)); return {'url':'public', 'raw_url':'raw'}
        bindings = {'resolve_service_path':lambda value: root/str(value), '_image_files':SimpleNamespace(imread=read),
                    'OUTPUT_DIR':root/'outputs', 'STATIC_DIR':root/'static',
                    'output_write_dir_for_owner':lambda category, owner: root/category/owner,
                    'safe_record_id':lambda value:value.replace('/','_'),
                    'auto_optimize_write_sprite_artifact':write, 'public_path_sanitized':lambda value:{**value,'sanitized':True},
                    'alpha_bbox':bbox, 'AUTO_OPTIMIZE_SYNTHETIC_CANVAS_SIZE':(1280,900),
                    'AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE':3.0}
        service, bindings = create(bindings)
        return SimpleNamespace(root=root, images=images, events=events, service=service, bindings=bindings)

    def test_load_shape_copy_and_alpha(self):
        f=self.fixture(); call=f.service.auto_optimize_load_sprite
        self.assertIsNone(call({'path':'missing'}))
        for value in (np.zeros((0,0,3),np.uint8),np.zeros((2,3),np.uint8)):
            f.images['a']=value; self.assertIsNone(call({'raw_path':'a'}))
        for channels in (3,4):
            value=np.full((2,3,channels),17,np.uint8);f.images['a']=value
            color,mask=call({'path':'a','raw_path':'missing'})
            self.assertEqual(color.shape,(2,3,3));self.assertTrue(np.all(mask==(17 if channels==4 else 255)))
            color[:]=0;mask[:]=0;self.assertTrue(np.all(value==17))

    def test_records_and_public_limit_keep_order(self):
        f=self.fixture();sample={'sample_id':'s','record_id':'r','source_image':{'path':'source'},'label_status':'trainable',
            'labels':[None,{}, {'accessory_id':'a','sprite':{'path':'one','label':'sprite label'}},
                      {'sprite':{'raw_path':'two','accessory_id':'b'}}, {'sprite':{'path':'skip'}}]}
        records=f.service.auto_optimize_sprite_records_for_sample(sample)
        self.assertEqual([v['accessory_id'] for v in records],['a','b']);self.assertEqual(records[0]['label'],'sprite label')
        self.assertEqual(records[1]['source_image_path'],'source')
        state={'samples':[None,{'label_status':'review','labels':sample['labels']},sample]}
        self.assertEqual(f.service.auto_optimize_public_sprite_pool(state,1),[{**records[0],'sanitized':True}])
        self.assertEqual(f.service.auto_optimize_public_sprite_pool(state,0),[])
        self.assertEqual(len(f.service.auto_optimize_public_sprite_pool(state,-1)),1)

    def test_path_query_prefix_and_fallback(self):
        f=self.fixture();call=f.service.auto_optimize_resolve_artifact_path
        self.assertEqual(call(''),Path(''));self.assertEqual(call(' /outputs/a.png?q=1 '),(f.root/'outputs/a.png').resolve())
        self.assertEqual(call('/static/b.png?x'),(f.root/'static/b.png').resolve())
        self.assertEqual(call('relative?x'),f.root/'relative')
        f.bindings['resolve_service_path']=lambda value:Path('changed')
        self.assertEqual(call('relative'),Path('changed'))

    def test_backfill_threshold_bbox_owner_and_metadata(self):
        f=self.fixture();f.images['source']=np.full((4,5,3),21,np.uint8);mask=np.zeros((4,5,3),np.uint8);mask[1,1]=8;mask[2,2]=9;f.images['mask']=mask
        label={'accessory_id':'a','bbox_xyxy':[-3,-2,99,99],'mask_meta':{}}
        sample={'sample_id':'s','owner_user_id':'sample-owner','source_image':{'url':'source'},'label_artifacts':{'color_mask_url':'mask'},
                'labels':[None,{'sprite':{'path':'exists'}},{'bbox_xyxy':[1]},label]}
        with patch.object(time,'time',return_value=123):
            self.assertEqual(f.service.auto_optimize_backfill_missing_sprites_for_sample('task',{'owner_user_id':'state-owner'},sample),1)
        self.assertEqual(sample['sprite_backfilled_at'],123);self.assertEqual(sample['sprite_backfill_count'],1)
        written=[e[1] for e in f.events if e[0]=='sprite'][0]
        self.assertEqual(written['artifact_dir'],f.root/'auto_optimize_masks/state-owner/task')
        self.assertEqual(written['bbox'],[0,0,5,4]);self.assertEqual(int(written['full_mask'].sum()),255)
        self.assertEqual(label['mask_meta']['processing_artifacts']['transparent_sprite_url'],'public')
        self.assertEqual(int(mask[1,1,0]),8)

    def test_backfill_no_work_unreadable_and_partial_failure(self):
        f=self.fixture();call=f.service.auto_optimize_backfill_missing_sprites_for_sample
        self.assertEqual(call('t',{},{}),0);self.assertEqual(f.events,[])
        sample={'source_image':{'path':'src'},'label_artifacts':{'mask_url':'mask'},'labels':[{'bbox_xyxy':[0,0,2,2]}]}
        self.assertEqual(call('t',{},sample),0);self.assertNotIn('sprite_backfilled_at',sample)
        f.images.update(src=np.ones((2,2,3),np.uint8),mask=np.full((1,1,3),255,np.uint8))
        def fail(**kwargs):raise OSError('synthetic write failure')
        f.bindings['auto_optimize_write_sprite_artifact']=fail
        with self.assertRaises(OSError):call('t',{},sample)
        self.assertNotIn('sprite',sample['labels'][0]);self.assertNotIn('sprite_backfilled_at',sample)

    def test_backfill_retains_earlier_mutation_when_later_write_fails(self):
        f=self.fixture();f.images.update(src=np.ones((2,2,3),np.uint8),mask=np.full((2,2,3),255,np.uint8))
        sample={'source_image':{'path':'src'},'label_artifacts':{'mask_url':'mask'},
                'labels':[{'bbox_xyxy':[0,0,2,2]},{'bbox_xyxy':[0,0,2,2]}]}
        calls=[]
        def write(**kwargs):
            calls.append(kwargs)
            if len(calls)==2: raise OSError('second artifact failure')
            return {'url':'first'}
        f.bindings['auto_optimize_write_sprite_artifact']=write
        with self.assertRaises(OSError):f.service.auto_optimize_backfill_missing_sprites_for_sample('t',{},sample)
        self.assertEqual(sample['labels'][0]['sprite'],{'url':'first'})
        self.assertNotIn('sprite',sample['labels'][1]);self.assertNotIn('sprite_backfilled_at',sample)

    def test_scale_cache_bounds_and_missing(self):
        f=self.fixture();call=f.service.auto_optimize_source_to_canvas_scale;cache={}
        self.assertEqual(call('',cache),1.);self.assertEqual(cache,{})
        self.assertEqual(call('missing',cache),1.);f.images['missing']=np.zeros((10,10,3),np.uint8)
        self.assertEqual(call('missing',cache),1.);self.assertEqual(len(f.events),1)
        self.assertEqual(call('missing',{}),3.)
        f.images['large']=np.zeros((1000,2000,3),np.uint8);self.assertEqual(call('large',{}),.64)
        f.bindings['AUTO_OPTIMIZE_SYNTHETIC_MAX_UPSCALE']=1.2;self.assertEqual(call('missing',{}),1.2)

    def test_canonical_dedupe_median_and_orientation(self):
        f=self.fixture();f.images['a']=np.full((10,30,4),255,np.uint8);f.images['b']=np.full((40,20,4),255,np.uint8)
        records=[{'path':'a','accessory_id':'x'},{'path':'a','accessory_id':'x'}, {'path':'b','accessory_id':'x'},None,{}]
        result=f.service.auto_optimize_canonical_sprite_sizes({},records)
        self.assertEqual(result,{'x':{'long':35,'short':18,'source_count':2}})
        call=f.service.auto_optimize_sprite_target_size
        self.assertEqual(call(np.zeros((2,2),np.uint8)),(18,18))
        self.assertEqual(call(np.full((40,20),255,np.uint8),result['x']),(18,35))
        self.assertEqual(call(np.full((10,30),255,np.uint8)),(30,18))

    @unittest.skipIf(BASELINE,'candidate-only composition')
    def test_actual_root_getters_and_forwarders(self):
        from scripts.verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        service=server._auto_optimization_sprites
        for group in (service.files,service.geometry):
            for field in fields(group):self.assertIs(getattr(group,field.name)(),getattr(server,field.name))
        import inspect
        for name in NAMES:
            signature=inspect.signature(getattr(server,name));args=[object() for p in signature.parameters.values() if p.default is inspect.Parameter.empty]
            mock=Mock(return_value=object())
            with patch.object(server,'_auto_optimization_sprites',SimpleNamespace(**{name:mock})):
                self.assertIs(getattr(server,name)(*args),mock.return_value)
            expected=list(args)+[p.default for p in signature.parameters.values() if p.default is not inspect.Parameter.empty]
            mock.assert_called_once_with(*expected)

if __name__=='__main__':unittest.main()

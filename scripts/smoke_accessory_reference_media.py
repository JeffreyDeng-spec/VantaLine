"""Synthetic reference frame selection, media cleanup and thumbnail contracts."""
import ast
from dataclasses import fields
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock,patch
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
BASELINE=os.environ.get('VANTALINE_ACCESSORY_REFERENCE_MEDIA_BASELINE_SOURCE')
NAMES=('frame_detail_score','frame_histogram','extract_video_reference_frames','write_thumbnail')


def create(bindings):
    source=Path(BASELINE) if BASELINE else ROOT/'local_inspection_service/server.py'
    tree=ast.parse(source.read_text(encoding='utf-8-sig'));nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in NAMES];assert len(nodes)==4
    constant=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MAX_VIDEO_REFERENCE_FRAMES' for t in n.targets))
    bindings.update(Any=Any,Path=Path,np=np,cv2=cv2)
    if not BASELINE:
        from local_inspection_service.accessories.reference_media import AccessoryReferenceMedia
        from local_inspection_service.accessories.reference_media_ports import ReferenceMediaDependencies
        bindings['_accessory_reference_media']=AccessoryReferenceMedia(ReferenceMediaDependencies(**{f.name:lambda name=f.name:bindings[name] for f in fields(ReferenceMediaDependencies)}))
    exec(compile(ast.Module(body=[constant,*nodes],type_ignores=[]),str(source),'exec'),bindings)
    return SimpleNamespace(**{n:bindings[n] for n in NAMES}),bindings


class ReferenceMediaContract(unittest.TestCase):
    def fixture(self):
        files=SimpleNamespace(imwrite=Mock(return_value=True));b={'_image_files':files,'public_output_url':lambda p:'synthetic:'+p.name};service,b=create(b)
        return SimpleNamespace(s=service,b=b,files=files)

    def capture(self,count=5,fps=1,opened=True,frames=None):
        if frames is None:frames=[np.full((4,4,3),i,dtype=np.uint8) for i in range(count)]
        iterator=iter(frames)
        return SimpleNamespace(isOpened=Mock(return_value=opened),get=Mock(side_effect=lambda key:fps if key==cv2.CAP_PROP_FPS else count),read=Mock(side_effect=lambda:((True,x) if (x:=next(iterator,None)) is not None else (False,None))),release=Mock())

    def test_real_score_histogram_and_input_immutability(self):
        f=self.fixture();frame=np.full((12,16,3),135,dtype=np.uint8);before=frame.copy()
        self.assertAlmostEqual(f.s.frame_detail_score(frame),0,places=4)
        hist=f.s.frame_histogram(frame);self.assertEqual(hist.shape,(576,));self.assertEqual(hist.dtype,np.float32);self.assertAlmostEqual(float(hist.sum()),1);np.testing.assert_array_equal(frame,before)
        self.assertLess(f.s.frame_detail_score(np.zeros_like(frame)),-269)

    def test_selected_frames_order_metadata_and_false_writer(self):
        f=self.fixture();cap=self.capture();f.b['frame_detail_score']=lambda frame:float(frame[0,0,0]);f.b['frame_histogram']=lambda frame:np.ones(4,dtype=np.float32)/4;f.files.imwrite.return_value=False
        with tempfile.TemporaryDirectory(prefix='reference-contract-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
            output=Path(directory)/'new';rows=f.s.extract_video_reference_frames(Path('source.mp4'),output,2)
            self.assertTrue(output.is_dir());self.assertEqual([r['frame_index'] for r in rows],[0,4]);self.assertEqual([r['time_seconds'] for r in rows],[0.0,4.0]);self.assertEqual([r['detail_score'] for r in rows],[0.0,4.0])
            self.assertEqual(Path(rows[0]['path']).name,'source_reference_frame_01.jpg');self.assertEqual(rows[0]['source_video'],'source.mp4')
            self.assertEqual(f.files.imwrite.call_count,2);self.assertEqual(f.files.imwrite.call_args.args[2],[int(cv2.IMWRITE_JPEG_QUALITY),94]);self.assertEqual(int(f.files.imwrite.call_args.args[1][0,0,0]),4)
        cap.release.assert_called_once()

    def test_stride_default_and_unknown_length_bound(self):
        f=self.fixture();cap=self.capture(count=144,fps=30);score=Mock(side_effect=lambda a:float(a[0,0,0]));f.b['frame_detail_score']=score;f.b['frame_histogram']=lambda a:np.ones(4,dtype=np.float32)
        with tempfile.TemporaryDirectory(prefix='reference-stride-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
            rows=f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory));self.assertEqual(len(rows),6);self.assertEqual(score.call_count,72);self.assertTrue(all(row['frame_index']%2==0 for row in rows))
        f=self.fixture();frames=(np.zeros((2,2,3),dtype=np.uint8) for _ in range(2000));cap=self.capture(count=0,fps=0,frames=frames);score=Mock(return_value=1.0);f.b['frame_detail_score']=score;f.b['frame_histogram']=lambda a:np.ones(4,dtype=np.float32)
        with tempfile.TemporaryDirectory(prefix='reference-unknown-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
            f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory),1)
        self.assertEqual(cap.read.call_count,1801);self.assertEqual(score.call_count,121);cap.release.assert_called_once()

    def test_unopened_empty_and_zero_limit_original_boundaries(self):
        for opened,frames in [(False,[]),(True,[])]:
            f=self.fixture();cap=self.capture(opened=opened,frames=frames)
            with tempfile.TemporaryDirectory(prefix='reference-empty-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
                self.assertEqual(f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory)),[])
            self.assertEqual(cap.release.call_count,int(opened));f.files.imwrite.assert_not_called()
        f=self.fixture();cap=self.capture(count=1);f.b['frame_detail_score']=lambda a:1;f.b['frame_histogram']=lambda a:np.ones(4,dtype=np.float32)
        with tempfile.TemporaryDirectory(prefix='reference-zero-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
            with self.assertRaises(ZeroDivisionError):f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory),0)
        cap.release.assert_called_once()

    def test_decoder_and_writer_errors_release_without_retry(self):
        for failure_at in ('decode','write'):
            f=self.fixture();cap=self.capture();error=OSError(failure_at);f.b['frame_detail_score']=lambda a:1;f.b['frame_histogram']=lambda a:np.ones(4,dtype=np.float32)
            if failure_at=='decode':cap.read.side_effect=error
            else:f.files.imwrite.side_effect=error
            with tempfile.TemporaryDirectory(prefix='reference-error-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):
                with self.assertRaises(OSError) as caught:f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory),2)
            self.assertIs(caught.exception,error);cap.release.assert_called_once();self.assertEqual(f.files.imwrite.call_count,int(failure_at=='write'))

    def test_thumbnail_pixels_and_late_publication(self):
        f=self.fixture();image=np.full((2,4,3),17,dtype=np.uint8);f.files.imwrite.return_value=False
        result=f.s.write_thumbnail(image,Path('thumb.png'),size=8);self.assertEqual(result,{'url':'synthetic:thumb.png','angle':0.0,'width':8,'height':8})
        rendered=f.files.imwrite.call_args.args[1];np.testing.assert_array_equal(rendered[3:5,2:6],image);np.testing.assert_array_equal(rendered[0,0],[238,240,242]);np.testing.assert_array_equal(image,np.full((2,4,3),17,dtype=np.uint8))
        failure=RuntimeError('url unavailable')
        def write(*args):f.b['public_output_url']=Mock(side_effect=failure);return True
        f.files.imwrite.side_effect=write
        with self.assertRaises(RuntimeError) as caught:f.s.write_thumbnail(image,Path('thumb.png'))
        self.assertIs(caught.exception,failure);self.assertEqual(f.files.imwrite.call_count,2)

    def test_late_scoring_histogram_and_writer_lookup(self):
        f=self.fixture();cap=self.capture(count=1);replacement=SimpleNamespace(imwrite=Mock(return_value=True));events=[]
        def score(frame):
            events.append('score');f.b['frame_histogram']=lambda a:events.append('hist') or np.ones(4,dtype=np.float32);f.b['_image_files']=replacement;return 1
        f.b['frame_detail_score']=score;f.b['frame_histogram']=Mock(side_effect=AssertionError('stale histogram'))
        with tempfile.TemporaryDirectory(prefix='reference-late-') as directory,patch.object(cv2,'VideoCapture',return_value=cap):f.s.extract_video_reference_frames(Path('source.mp4'),Path(directory))
        self.assertEqual(events,['score','hist']);replacement.imwrite.assert_called_once();f.files.imwrite.assert_not_called()

    @unittest.skipIf(bool(BASELINE),'candidate wiring only')
    def test_wiring_and_light_import(self):
        tree=ast.parse((ROOT/'local_inspection_service/server.py').read_text(encoding='utf-8'));binding=next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_accessory_reference_media' for t in n.targets));getters=binding.args[0].keywords;self.assertEqual(len(getters),4)
        for kw in getters:self.assertIsInstance(kw.value,ast.Lambda);self.assertEqual(kw.arg,kw.value.body.id)
        for name in NAMES:
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(len(node.body),1);self.assertIsInstance(node.body[0],ast.Return);self.assertEqual(node.body[0].value.func.attr,name)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='extract_video_reference_frames');self.assertEqual(ast.unparse(node.args.defaults[0]),'MAX_VIDEO_REFERENCE_FRAMES')
        subprocess.run([sys.executable,'-B','-c','import sys; import local_inspection_service.accessories.reference_media; assert "local_inspection_service.server" not in sys.modules'],cwd=ROOT,check=True)


if __name__=='__main__':unittest.main()

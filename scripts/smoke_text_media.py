"""Owned media, PDF-cache and image-transform contracts using synthetic bytes."""
import copy
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cv2
import fitz
import numpy as np
from PIL import Image
from fastapi import HTTPException
from local_inspection_service.text_inspection.media import TextMedia, TextMediaRecords
from local_inspection_service.text_inspection import images

ROOT='--root' in sys.argv
sys.argv=[a for a in sys.argv if a!='--root']

def digest(data):return hashlib.sha256(data).hexdigest()
def picture(fmt='PNG',size=(200,100),mode='RGB',**options):
    output=io.BytesIO(); Image.new(mode,size,(12,45,78,0) if mode=='RGBA' else (12,45,78)).save(output,format=fmt,**options)
    return output.getvalue()


class Fixture:
    def __init__(self,case):
        temporary=tempfile.TemporaryDirectory();case.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.standard={}; self.owned=Mock(side_effect=lambda kind,identity,owner:copy.deepcopy(self.standard) if owner=='alice' else None)
        self.save=Mock(return_value=True)
        self.media=TextMedia(lambda:self.root,digest,TextMediaRecords(self.owned,self.save))
    def pdf(self):
        document=fitz.open();document.new_page(width=200,height=100).insert_text((20,40),'synthetic reference')
        source=document.tobytes();document.close()
        path=self.media.media_path('alice','standard','source.pdf');self.media.write(path,source)
        self.standard=dict(id='standard',source_path=str(path),source_sha256=digest(source))
        return dict(id='asset',standard_id='standard',asset_kind='manual_page',ordinal=1)


class MediaContracts(unittest.TestCase):
    def http_error(self,status,call):
        with self.assertRaises(HTTPException) as caught:call()
        self.assertEqual(caught.exception.status_code,status)

    def test_owned_paths_hash_size_and_atomic_replace_failure(self):
        f=Fixture(self);path=f.media.media_path('alice','standard','fixture.bin');f.media.write(path,b'original')
        self.assertEqual(f.media.read_verified(str(path),'alice','standard',expected_sha256=digest(b'original'),max_bytes=8),b'original')
        self.http_error(404,lambda:f.media.read_verified(str(path),'bob','standard'))
        self.http_error(409,lambda:f.media.read_verified(str(path),'alice','standard',max_bytes=7))
        self.http_error(409,lambda:f.media.read_verified(str(path),'alice','standard',expected_sha256='wrong'))
        self.http_error(400,lambda:f.media.media_path('alice','standard','../escape'))
        self.http_error(400,lambda:f.media.media_path('alice','standard','..'))
        self.assertEqual(f.media.read_verified(str(path),'alice','standard'),b'original')
        with patch('local_inspection_service.text_inspection.media.os.replace',side_effect=PermissionError('fixture locked')):
            with self.assertRaises(PermissionError):f.media.write(path,b'replacement')
        self.assertEqual(path.read_bytes(),b'original')
        leftovers=list(path.parent.glob('.*.tmp'));self.assertEqual(len(leftovers),1);self.assertEqual(leftovers[0].read_bytes(),b'replacement')
        path.write_bytes(b'');self.http_error(409,lambda:f.media.read_verified(str(path),'alice','standard'))

    def test_symlinks_follow_existing_resolved_target_rule(self):
        f=Fixture(self);inside=f.media.media_path('alice','standard','inside.bin');f.media.write(inside,b'owned')
        link=inside.with_name('link.bin');outside=f.root/'outside.bin';outside.write_bytes(b'outside')
        try:link.symlink_to(inside)
        except OSError as error:self.skipTest('symlink creation unavailable: '+type(error).__name__)
        self.assertEqual(f.media.read_verified(str(link),'alice','standard'),b'owned')
        link.unlink();link.symlink_to(outside)
        self.http_error(404,lambda:f.media.read_verified(str(link),'alice','standard'))

    def test_real_pdf_cache_identity_and_no_rerender_on_cache_failure(self):
        f=Fixture(self);asset=f.pdf();f.save.return_value=False
        contents=f.media.asset_bytes(asset,'alice');self.assertEqual(Image.open(io.BytesIO(contents)).size,(300,150))
        self.assertEqual(asset['sha256'],digest(contents));self.assertEqual(Path(asset['media_path']).read_bytes(),contents)
        f.save.assert_called_once();self.assertIs(f.save.call_args.args[1],asset)
        f.owned.reset_mock();f.owned.side_effect=AssertionError('cached asset must not reload source')
        f.standard['source_sha256']='source changed';self.assertEqual(f.media.asset_bytes(asset,'alice'),contents)
        asset['sha256']='bad';self.http_error(409,lambda:f.media.asset_bytes(asset,'alice'))
        Path(asset['media_path']).unlink();self.http_error(404,lambda:f.media.asset_bytes(asset,'alice'));f.owned.assert_not_called()
        self.http_error(404,lambda:f.media.asset_bytes({'asset_kind':'label_candidate'},'alice'))

    def test_pdf_closes_on_validation_and_render_failure_and_keeps_save_evidence(self):
        for mode in ['ordinal','pixels','load','render','encode']:
            with self.subTest(mode=mode):
                f=Fixture(self);asset=f.pdf();document=Mock();document.page_count=1
                page=Mock();page.rect=fitz.Rect(0,0,10000,10000) if mode=='pixels' else fitz.Rect(0,0,200,100)
                document.load_page.return_value=page
                if mode=='ordinal':asset['ordinal']=0
                if mode=='load':document.load_page.side_effect=RuntimeError('load')
                if mode=='render':page.get_pixmap.side_effect=RuntimeError('render')
                if mode=='encode':page.get_pixmap.return_value.tobytes.side_effect=RuntimeError('encode')
                with patch('fitz.open',return_value=document), self.assertRaises((HTTPException,RuntimeError)):
                    f.media.asset_bytes(asset,'alice')
                document.close.assert_called_once();f.save.assert_not_called();self.assertNotIn('media_path',asset)
                if mode=='pixels':page.get_pixmap.assert_not_called()
        f=Fixture(self);asset=f.pdf();before=copy.deepcopy(asset)
        with patch.object(f.media,'write',side_effect=RuntimeError('write failed')):
            with self.assertRaisesRegex(RuntimeError,'write failed'):f.media.asset_bytes(asset,'alice')
        self.assertEqual(asset,before);f.save.assert_not_called()
        f.save.side_effect=RuntimeError('save failed')
        with self.assertRaisesRegex(RuntimeError,'save failed'):f.media.asset_bytes(asset,'alice')
        self.assertTrue(Path(asset['media_path']).is_file());self.assertEqual(digest(Path(asset['media_path']).read_bytes()),asset['sha256'])

    def test_image_passthrough_exif_transparency_and_fallback(self):
        exif=Image.Exif();exif[274]=6
        for fmt,mode,options in [('PNG','RGBA',{}),('JPEG','RGB',{'exif':exif}),('WEBP','RGB',{})]:
            blob=picture(fmt,mode=mode,**options);result=images.prepare_image(blob,max_bytes=len(blob))
            self.assertIs(result[0],blob);self.assertEqual(result[-1],fmt)
        blob=picture('BMP');result=images.prepare_image(blob)
        self.assertTrue(result[0].startswith(b'\xff\xd8'));self.assertEqual(result[1:],('image/jpeg','.jpg','BMP'))
        blob=picture('PNG',mode='RGBA');decode=cv2.imdecode;calls=[]
        def first_fails(*args,**kwargs):
            calls.append(1);return None if len(calls)==1 else decode(*args,**kwargs)
        with patch.object(images.cv2,'imdecode',side_effect=first_fails):result=images.prepare_image(blob)
        self.assertEqual(len(calls),2);self.assertEqual(result[-1],'PNG')
        self.assertGreater(min(Image.open(io.BytesIO(result[0])).getpixel((50,50))),245)
        with patch.object(images.cv2,'imdecode',return_value=None):self.http_error(400,lambda:images.prepare_image(blob))
        for bad in [b'',b'broken',picture(size=(99,100))]:self.http_error(400,lambda:images.prepare_image(bad))
        self.http_error(400,lambda:images.prepare_image(blob,max_bytes=len(blob)-1))

    def test_provider_copy_and_annotation_contract(self):
        exif=Image.Exif();exif[274]=6;blob=picture('JPEG',size=(200,100),exif=exif)
        result=images.prepare_provider_image(blob,'caller-mime',max_side=200,jpeg_quality=90)
        self.assertEqual(result,(blob,'caller-mime','JPEG'))
        result=images.prepare_provider_image(blob,'caller-mime',max_side=100,jpeg_quality=90)
        self.assertEqual(Image.open(io.BytesIO(result[0])).size,(50,100));self.assertEqual(result[1:],('image/jpeg','JPEG'))
        transparent=picture(size=(400,200),mode='RGBA')
        result=images.prepare_provider_image(transparent,'image/png',max_side=100,jpeg_quality=90)
        self.assertGreater(min(Image.open(io.BytesIO(result[0])).getpixel((50,25))),245)
        self.http_error(400,lambda:images.prepare_provider_image(b'broken','image/jpeg',max_side=100,jpeg_quality=90))
        with patch.object(images.cv2,'putText',wraps=cv2.putText) as label:
            annotated=images.annotate(picture(),[{'box':[]},{'box':[.1,.1,.5,.5]}])
        self.assertTrue(annotated.startswith(b'\xff\xd8'));self.assertEqual(label.call_args.args[1],'2')
        with self.assertRaises(ValueError):images.annotate(b'broken',[])
        with self.assertRaises(ValueError):images.annotate(picture(),[{'box':[float('nan'),0,1,1]}])
        self.assertEqual(images.data_url(b'\x89PNG'),'data:image/png;base64,iVBORw==')
        self.assertEqual(images.data_url(b'fixture','image/webp'),'data:image/webp;base64,Zml4dHVyZQ==')
        self.assertEqual(images.data_url(b'fixture'),'data:image/jpeg;base64,Zml4dHVyZQ==')
        self.assertEqual(images.similarity(picture(),picture()),1.0)
        self.assertEqual(images.similarity(b'broken',picture()),0.0)

    @unittest.skipUnless(ROOT,'requires full application runtime')
    def test_application_composition_and_live_resize_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'local_inspection_service/static').mkdir(parents=True)
            os.environ.update(LOCAL_INSPECTION_ROOT=folder,VANTALINE_DATA_STORE='json',VANTALINE_LABEL_INSPECTION_ENABLED='false',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0')
            from local_inspection_service import server
            self.assertIs(server._text_v2_prepare_image,images.prepare_image);self.assertIs(server._text_v2_annotate,images.annotate)
            self.assertIs(server._text_v2_data_url,images.data_url);self.assertIs(server._text_v2_similarity,images.similarity)
            self.assertEqual(server._text_media.directory(),server.TEXT_INSPECTION_MEDIA_DIR)
            blob=picture()
            with patch.object(server,'TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE',200):
                self.assertEqual(server._text_v2_prepare_provider_image(blob,'image/png')[0],blob)
            with patch.object(server,'TEXT_INSPECTION_PROVIDER_IMAGE_MAX_SIDE',100), patch.object(server,'TEXT_INSPECTION_PROVIDER_IMAGE_JPEG_QUALITY',35):
                resized=server._text_v2_prepare_provider_image(blob,'image/png')[0]
                self.assertEqual(Image.open(io.BytesIO(resized)).size,(100,50))
                self.assertEqual(resized,images.prepare_provider_image(blob,'image/png',max_side=100,jpeg_quality=35)[0])
            with patch.object(server,'_text_v2_owned',return_value=None) as owned:
                self.http_error(404,lambda:server._text_v2_asset_bytes({'asset_kind':'manual_page','standard_id':'missing'},'alice'))
                owned.assert_called_once_with('standards','missing','alice')


if __name__=='__main__':unittest.main(verbosity=2)

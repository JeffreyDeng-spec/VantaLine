"""Offline classifier contract; no semantic-accuracy or release claim."""
import io
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from local_inspection_service import document_label_classifier as c

class Contract(unittest.TestCase):
    def test_categories(self):
        for category in c.CATEGORIES:
            value=c.validate({'category':category,'reason':'visible evidence'})
            self.assertEqual(value['status'],'candidate' if category=='label_design' else 'needs_confirmation' if category=='uncertain' else 'excluded')

    def test_strict_output(self):
        for value in ({},[],{'category':'yes','reason':'x'}, {'category':'label_design','reason':''},
                      {'category':'label_design','reason':'x','box':[0,0,1,1]}):
            with self.assertRaises((ValueError,TypeError)):c.validate(value)

    def test_preview(self):
        image=Image.new('RGBA',(2000,1000),(0,0,0,0));out=io.BytesIO();image.save(out,'PNG')
        with Image.open(io.BytesIO(c.prepare_image(out.getvalue()))) as preview:
            self.assertEqual(preview.size,(1600,800));self.assertEqual(preview.getpixel((0,0)),(255,255,255))
        with self.assertRaises(ValueError):c.prepare_image(b'')

    def test_one_call_and_no_crop(self):
        calls=[]
        def transport(request,settings,timeout):
            calls.append(1);payload=json.loads(request.data)
            self.assertTrue(settings['single_attempt']);self.assertEqual(len(payload['messages'][1]['content']),2)
            return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'category':'label_design','reason':'sticker'})}}]}).encode())
        result,_=c.classify_once(b'image',[],{'model':'fixture','base_url':'https://invalid.test','api_key':'private-key'},transport)
        self.assertEqual(result['status'],'candidate');self.assertEqual(len(calls),1);self.assertNotIn('box',result)

    def test_unknown_no_retry(self):
        calls=[]
        def transport(*args,**kwargs):calls.append(1);raise TimeoutError('private-key')
        result,diagnostic=c.classify_once(b'image',[],{'model':'fixture','base_url':'https://invalid.test','api_key':'private-key'},transport)
        self.assertEqual(len(calls),1);self.assertEqual(result['status'],'needs_confirmation')
        self.assertNotIn('private-key',json.dumps(diagnostic))

    def test_redaction(self):
        value=c.evidence(json.dumps({'secret':'s','note':'Bearer abc https://private.test/?key=secret','nested':json.dumps({'api_key':'abc'})}),'abc')
        encoded=json.dumps(value)
        self.assertNotIn('private.test',encoded);self.assertNotIn('abc',encoded)

if __name__=='__main__':unittest.main()

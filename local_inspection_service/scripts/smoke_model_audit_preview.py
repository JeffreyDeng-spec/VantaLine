"""Offline audit, structured JSON and display-only preview regressions."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from local_inspection_service import model_call_audit, evidence_preview, qwen_evidence_jobs as jobs


class Tests(unittest.TestCase):
    def test_audit_immutable_redacted(self):
        with tempfile.TemporaryDirectory() as folder:
            record = dict(id='r', owner_user_id='a', standard_id='s', diagnostics={'phase':'mapping'})
            saved = []
            s = SimpleNamespace(_text_v2_media_path=lambda *args: Path(folder)/args[-1],
                _text_v2_write=lambda p,b: p.write_bytes(b))
            emit = model_call_audit.recorder(s, record, 'mapping', lambda phase: saved.append(phase), 'secret-fixture')
            emit('request', {'text':'secret-fixture data:image/png;base64,YWJjZA=='})
            file = record['diagnostics']['model_audits'][0]['files']['request']
            raw = Path(file['path']).read_bytes()
            self.assertNotIn(b'secret-fixture',raw)
            self.assertNotIn(b'YWJjZA==',raw)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),file['sha256'])
            with self.assertRaises(ValueError): emit('request',{})
            self.assertGreaterEqual(len(saved),2)

    def test_preview_source_unchanged(self):
        image = Image.new('RGBA',(4096,3072),(50,80,120,100))
        before = image.tobytes()
        blob, metadata = evidence_preview.create(image)
        self.assertEqual(image.tobytes(),before)
        self.assertEqual(Image.open(io.BytesIO(blob)).size,(1600,1200))
        self.assertTrue(metadata['display_only'])
        self.assertLess(len(blob),200000)

    def test_structured_and_failure_evidence(self):
        settings = dict(model='qwen3-vl-flash',api_key='fixture',base_url='https://dashscope.aliyuncs.com')
        # Reproduced failure: complete HTTP/stop response missing the root brace.
        for content in ['{"mappings":[]', 'not json', '{"mappings":[]}']:
            body=json.dumps({'output':{'choices':[{'finish_reason':'stop','message':{'content':[{'text':content}]}}]}}).encode()
            response=SimpleNamespace(status_code=200,iter_content=lambda n:iter([body]),close=lambda:None)
            events={}
            with patch('requests.post',return_value=response) as post:
                if content != '{"mappings":[]}':
                    with self.assertRaises(jobs.ocr.EvidenceError) as raised:
                        jobs.llm(settings,{},5,audit=lambda k,v:events.update({k:v}))
                    self.assertIn('position',raised.exception.diagnostics['parse_error'])
                else:
                    proposal,_=jobs.llm(settings,{},5,audit=lambda k,v:events.update({k:v}))
                    self.assertEqual(proposal,{'mappings':[]})
                self.assertEqual(post.call_args.kwargs['json']['parameters']['response_format'],{'type':'json_object'})
                self.assertEqual(post.call_count,1)
                self.assertEqual(events['response']['body'],body.decode())
                self.assertIn('parse',events)


if __name__ == '__main__': unittest.main()

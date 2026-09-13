"""Offline protocol fixtures, NOT real OCR accuracy/performance acceptance."""
import copy
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image
from local_inspection_service import evidence_matching as matching
from local_inspection_service import qwen_ocr_evidence as ocr
from local_inspection_service import qwen_evidence_jobs as jobs


def response(words=None):
    return {"output":{"choices":[{"finish_reason":"stop","message":{"content":[{"ocr_result":{
        "words_info":words if words is not None else [{"text":"20V Max", "location":[10,10,90,10,90,30,10,30]}]
    }}]}}]},"usage":{"input_tokens":100,"output_tokens":20}}


def element(text, kind="text", identity="e1"):
    return dict(id=identity, type=kind, text=text, state="keep", clean_box=[.1,.1,.7,.2])


def observation(text, identity="o1", box=None, kind="text"):
    return dict(id=identity, type=kind, text=text, box=box or [.1,.1,.4,.12], confidence=None, provenance="qwen_ocr")


class ProtocolTests(unittest.TestCase):
    def test_region_text_is_image_only_bounded_and_coarse(self):
        raw = {'output': {'choices': [{'finish_reason': 'stop', 'message': {'content': [{'text': 'Battery Pack'}]}}]}}
        calls = []
        class Reply:
            status_code = 200
            def iter_content(self, size): yield json.dumps(raw).encode()
            def close(self): pass
        def post(*args, **kwargs):
            calls.append(kwargs)
            return Reply()
        def run():
            return ocr.recognize(dict(provider='qwen', api_key='secret', base_url='https://dashscope.aliyuncs.com'),
                b'image', (120,40), 1, post, region_text=True)
        obs, diag = run()
        self.assertEqual(calls[0]['json']['parameters']['ocr_options']['task'], 'text_recognition')
        self.assertEqual(list(calls[0]['json']['input']['messages'][0]['content'][0])[0], 'image')
        self.assertEqual(obs[0]['polygon'], [[0,0],[120,0],[120,40],[0,40]])
        self.assertIsNone(obs[0]['confidence'])
        self.assertIn('not_word', diag['coordinate_precision'])
        raw['output']['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ocr.EvidenceError): run()
        raw['output']['choices'][0]['finish_reason'] = 'stop'
        raw['output']['choices'][0]['message']['content'][0]['text'] = ''
        self.assertEqual(run()[0], [])

    def test_invalid_mapping_json_retains_safe_usage(self):
        raw={'output':{'choices':[{'finish_reason':'stop','message':{'content':[{'text':'not json, private text'}]}}]},
             'usage':{'input_tokens':111,'output_tokens':22,'api_key':'never-store'}}
        class Reply:
            status_code=200
            def iter_content(self,size):yield json.dumps(raw).encode()
            def close(self):pass
        with patch('requests.post',return_value=Reply()) as post:
            with self.assertRaisesRegex(ocr.EvidenceError,'mapping_invalid_json') as caught:
                jobs.llm(dict(base_url='https://dashscope.aliyuncs.com',api_key='secret',model='qwen3-vl-flash'),{},1)
        self.assertEqual(post.call_count,1)
        self.assertEqual(caught.exception.diagnostics['usage'],{'input_tokens':111,'output_tokens':22})
        for private in ('never-store','private text','secret'):
            self.assertNotIn(private,json.dumps(caught.exception.diagnostics))

    def test_presence_empty_and_partial_evidence_never_invent_matches(self):
        def recognize(raw):
            class Reply:
                status_code=200
                def iter_content(self,size):yield json.dumps(raw).encode()
                def close(self):pass
            return ocr.recognize(dict(provider='qwen',api_key='secret',base_url='https://dashscope.aliyuncs.com'),
                b'img',(100,100),1,lambda *a,**kw:Reply(),presence_evidence=True)
        obs,diag=recognize(response([]))
        self.assertEqual(obs,[]);self.assertTrue(diag['empty_scan']);self.assertTrue(diag['scan_complete'])
        rows=matching.direct([element('MODEL: A20')],obs)
        self.assertEqual(rows[0]['state'],'review')
        request=matching.candidates(rows,obs)
        self.assertEqual(request['elements'],[]);self.assertEqual(request['no_evidence_element_ids'],['e1'])
        bad={'text':'irrelevant','location':[0,90,90,90,90,110,0,110]}
        good={'text':'20V','location':[10,10,60,10,60,30,10,30]}
        obs,diag=recognize(response([bad,good]))
        self.assertFalse(diag['scan_complete']);self.assertFalse(diag['empty_scan'])
        self.assertEqual(diag['validation_policy'],ocr.PRESENCE_VERSION)
        self.assertEqual(diag['rejected_words'][0]['index'],0)
        self.assertEqual(matching.direct([element('20V')],obs)[0]['state'],'matched')
        self.assertEqual(matching.direct([element('120V')],obs)[0]['state'],'review')
        malformed=response([]);malformed['output']['choices'][0]['finish_reason']='length'
        for raw in (malformed,response([bad]),response([good]*(ocr.MAX_WORDS+1)),{}):
            with self.subTest(raw_type=str(raw)[:100]),self.assertRaises(ocr.EvidenceError):recognize(raw)

    def test_experimental_rotation_is_explicit_and_keeps_original_coordinates(self):
        self.assertFalse(ocr.payload(b'img')['input']['messages'][0]['content'][0]['enable_rotate'])
        calls=[]
        raw=response([{'text':'Battery','location':[10,10,40,10,40,160,10,160]}])
        class Reply:
            status_code=200
            def iter_content(self,size):yield json.dumps(raw).encode()
            def close(self):pass
        def post(*args,**kwargs):calls.append(kwargs['json']);return Reply()
        obs,diag=ocr.recognize(dict(provider='qwen',api_key='secret',base_url='https://dashscope.aliyuncs.com'),
            b'img',(80,200),1,post,auto_rotate=True)
        self.assertTrue(calls[0]['input']['messages'][0]['content'][0]['enable_rotate'])
        self.assertEqual(obs[0]['polygon'],[(10,10),(40,10),(40,160),(10,160)])
        self.assertTrue(diag['auto_rotate'])
        for invalid in (1,'true',None):
            with self.assertRaisesRegex(ocr.EvidenceError,'rotation_option'):ocr.payload(b'img',auto_rotate=invalid)

    def test_tile_subset_keeps_only_valid_rows_and_never_truncation(self):
        raw=response([{'text':'120V','location':[0,0,110,0,110,20,0,20]},
                      {'text':'20V','location':[10,10,60,10,60,30,10,30]}])
        with self.assertRaises(ocr.EvidenceError):ocr.normalize(raw,(100,100))
        valid,rejected=ocr.validated_subset(raw,(100,100))
        self.assertEqual([v['text'] for v in valid],['20V'])
        self.assertEqual(valid[0]['order'],1)
        self.assertEqual(rejected,[{'index':0,'reason':'ocr_coordinates_outside_original'}])
        self.assertEqual(valid[0]['polygon'],[(10,10),(60,10),(60,30),(10,30)])
        raw['output']['choices'][0]['finish_reason']='length'
        with self.assertRaises(ocr.EvidenceError):ocr.validated_subset(raw,(100,100))

    def test_truncated_response_keeps_safe_usage_without_content(self):
        raw = response()
        raw['output']['choices'][0]['finish_reason'] = 'length'
        raw['usage']['api_key'] = 'secret-never-store'
        class Reply:
            status_code = 200
            def iter_content(self, size): yield json.dumps(raw).encode()
            def close(self): pass
        with self.assertRaises(ocr.EvidenceError) as caught:
            ocr.recognize(dict(provider='qwen', api_key='secret', base_url='https://dashscope.aliyuncs.com'), b'img', (100,100), 1, lambda *a, **kw: Reply())
        diagnostic = caught.exception.diagnostics
        self.assertEqual(diagnostic['finish_reason'], 'length')
        self.assertEqual(diagnostic['usage']['output_tokens'], 20)
        self.assertNotIn('secret', json.dumps(diagnostic))
        self.assertNotIn('20V', json.dumps(diagnostic))

    def test_bounded_transport_without_resize_or_source_mutation(self):
        import random
        source = Image.frombytes('RGB', (128,128), random.Random(7).randbytes(128*128*3))
        original = source.tobytes()
        with patch.object(ocr, 'MAX_BASE64_BYTES', 60000):
            blob, transform = ocr.prepare(source)
            self.assertTrue(transform['lossy'])
            self.assertEqual(transform['encoding'], 'jpeg')
            self.assertEqual(Image.open(io.BytesIO(blob)).size, source.size)
            self.assertLessEqual(transform['base64_bytes'], 60000)
            self.assertTrue(ocr.payload(blob)['input']['messages'][0]['content'][0]['image'].startswith('data:image/jpeg;base64,'))
        self.assertEqual(source.tobytes(), original)
        with patch.object(ocr, 'MAX_BASE64_BYTES', 10):
            with self.assertRaisesRegex(ocr.EvidenceError, 'transport_capacity'):
                ocr.prepare(source)
            with self.assertRaisesRegex(ocr.EvidenceError, 'transport_capacity'):
                ocr.payload(b'x' * 9)

    def test_explicit_model_no_standard_input(self):
        data, transform=ocr.prepare(Image.new("RGBA",(100,100),(0,0,0,0)))
        self.assertEqual(Image.open(io.BytesIO(data)).getpixel((0,0)),(255,255,255))
        body=ocr.payload(data)
        self.assertEqual(body["model"],"qwen-vl-ocr-2025-11-20")
        self.assertEqual(body["parameters"]["ocr_options"]["task"],"advanced_recognition")
        self.assertEqual(list(body["input"]["messages"][0]["content"][0]),["image","min_pixels","max_pixels","enable_rotate"])
        self.assertEqual(body["input"]["messages"][0]["content"][0]["min_pixels"], 3072)
        self.assertEqual(transform["source_size"],transform["input_size"])

    def test_coordinates_scores_stable_ids(self):
        observed=ocr.normalize(response(),(100,100))
        self.assertIsNone(observed[0]["confidence"])
        self.assertEqual(observed[0]["box"],[.1,.1,.9,.3])
        self.assertEqual(observed,ocr.normalize(response(),(100,100)))

    def test_duplicate_text_distinct_locations_retained(self):
        words=[{"text":"20V","location":[10,10,40,10,40,20,10,20]},
               {"text":"20V","location":[10,30,40,30,40,40,10,40]}]
        data=ocr.normalize(response(words),(100,100))
        self.assertEqual(len(data),2); self.assertNotEqual(data[0]["id"],data[1]["id"])

    def test_reject_truncation_empty_schema_and_invalid_polygons(self):
        bad=[]
        r=response();r["output"]["choices"][0]["finish_reason"]="length";bad.append(r)
        bad.extend([{},response([]),response([{"text":"x","location":[0,0,0,0,0,0,0,0]}]),
                    response([{"text":"x","location":[0,0,110,0,110,20,0,20]}]),
                    response([{"text":"x","location":[0,0,float("nan"),0,10,20,0,20]}]),
                    response([{"text":"x","location":[0,0,10,20,0,20,10,0]}])])
        for fixture in bad:
            with self.subTest(fixture=fixture),self.assertRaises(ocr.EvidenceError):ocr.normalize(fixture,(100,100))

    def test_score_not_fabricated_or_rescaled(self):
        for score in [95,True,"0.99",float("inf")]:
            with self.subTest(score=score),self.assertRaises(ocr.EvidenceError):
                ocr.normalize(response([{"text":"x","location":[0,0,10,0,10,20,0,20],"confidence":score}]),(100,100))

    def test_approved_endpoint_only(self):
        for url in ["http://dashscope.aliyuncs.com", "https://dashscope.aliyuncs.com.evil.test", "https://evil.test", "https://a:b@dashscope.aliyuncs.com", "https://dashscope.aliyuncs.com:444"]:
            with self.subTest(url=url),self.assertRaises(ocr.EvidenceError):ocr.endpoint(url)
        self.assertTrue(ocr.endpoint("https://ws-test.cn-beijing.maas.aliyuncs.com/compatible-mode/v1").startswith("https://ws-test."))

    def test_one_call_no_redirect_retry_or_raw_error(self):
        calls=[]
        class Reply:
            status_code=403
            def iter_content(self,n): return iter([b'{"error":"forbidden"}'])
            def close(self):pass
        def post(*a,**kw):calls.append(kw);return Reply()
        with self.assertRaisesRegex(ocr.EvidenceError,"ocr_http_403"):
            ocr.recognize(dict(provider="qwen",api_key="secret",base_url="https://dashscope.aliyuncs.com"),b"img",(100,100),3,post)
        self.assertEqual(len(calls),1);self.assertFalse(calls[0]["allow_redirects"])


class MatchingTests(unittest.TestCase):
    def independent_fixture(self):
        obs = [observation("Battery", "a", [.1,.1,.3,.12]),
               observation("Pack", "b", [.31,.1,.4,.12]),
               observation("120V", "c", [.1,.3,.4,.32])]
        rows = matching.direct([element("Battery Pack"), element("20V", identity="e2")], obs)
        request = matching.candidates(rows, obs)
        good = dict(element_id="e1", spans=[matching.span(obs[0],0,7), matching.span(obs[1],0,4)])
        bad = dict(element_id="e2", spans=[matching.span(obs[2],1,4)])
        return rows, request, good, bad

    def test_independent_valid_evidence_survives_invalid_sibling(self):
        for reverse in (False, True):
            rows, request, good, bad = self.independent_fixture()
            mappings = [bad, good] if reverse else [good, bad]
            result, diagnostic = matching.validate_independently(dict(mappings=mappings), request, rows)
            self.assertEqual([r['state'] for r in result], ['matched', 'review'])
            self.assertEqual(diagnostic['validated_response']['mappings'], [good])
            self.assertEqual(diagnostic['rejected_mappings'][0]['reason'], 'partial_token_boundary')

    def test_independent_duplicate_target_rejects_both_orders(self):
        for reverse in (False, True):
            rows, request, good, bad = self.independent_fixture()
            duplicate = copy.deepcopy(good); duplicate['spans'][0]['end'] = 999
            mappings = [duplicate, good, bad] if reverse else [good, duplicate, bad]
            result, diagnostic = matching.validate_independently(dict(mappings=mappings), request, rows)
            self.assertEqual([r['state'] for r in result], ['review', 'review'])
            self.assertEqual(sum(r['reason']=='duplicate_mapping_target' for r in diagnostic['rejected_mappings']), 2)

    def test_independent_malformed_siblings_are_not_facts(self):
        for malformed in (None, [], {'element_id': []}, {'element_id':'unknown'},
                          {'element_id':'e2', 'spans':[{'evidence_id':[], 'start':0, 'end':4}]}):
            rows, request, good, _ = self.independent_fixture()
            result, diagnostic = matching.validate_independently(dict(mappings=[good, malformed]), request, rows)
            self.assertEqual([r['state'] for r in result], ['matched', 'review'])
            self.assertEqual(len(diagnostic['rejected_mappings']), 1)
        for malformed in ({}, {'mappings':{}, 'extra':True}, {'mappings':[{}]*41}):
            rows, request, _, _ = self.independent_fixture(); before = copy.deepcopy(rows)
            with self.assertRaises(ValueError):matching.validate_independently(malformed, request, rows)
            self.assertEqual(rows, before)

    def test_independent_valid_difference_and_settled_protection(self):
        rows, request, good, bad = self.independent_fixture()
        bad['spans'][0]['start'] = 0
        result, _ = matching.validate_independently(dict(mappings=[good,bad]), request, rows)
        self.assertEqual([r['state'] for r in result], ['matched','difference'])
        self.assertEqual(result[1]['observed_text'],'120V')
        before = copy.deepcopy(rows)
        _, diagnostic = matching.validate_independently(dict(mappings=[good]), request, rows)
        self.assertEqual(rows, before)
        self.assertEqual(diagnostic['rejected_mappings'][0]['reason'], 'already_settled_mapping_target')

    def test_valid_reference_does_not_make_unrelated_text_a_difference(self):
        obs = [observation("20V Max Li-ion Battery")]
        rows = matching.direct([element("read and understand the instruction manual.")],obs)
        request = matching.candidates(rows,obs)
        proposal = dict(mappings=[dict(element_id="e1",spans=[matching.span(obs[0],0,len(obs[0]['text']))])])
        rows, _ = matching.validate_independently(proposal,request,rows)
        self.assertEqual(rows[0]['state'],'review')
        self.assertEqual(rows[0]['reason'],'unrelated_candidate_requires_review')
        self.assertEqual(rows[0]['observed_text'],obs[0]['text'])

    def test_prose_separator_whitespace_preserves_source_spans(self):
        expected = "For more information,call +86 571 2809 3524"
        actual = "  For more information,  call +86 571 2809 3524  "
        start, end = matching.token_spans(expected, actual)[0]
        self.assertEqual(actual[start:end], actual.strip())
        self.assertEqual(matching.normalized(actual[start:end]), expected)
        self.assertEqual(matching.direct([element(expected)], [observation(actual)])[0]['state'], 'matched')
        for text in ["MODEL: X1", "MODEL : X1", "MODEL:\nX1"]:
            self.assertEqual(matching.normalized(text), "MODEL:X1")

    def test_spacing_does_not_erase_content_or_numeric_boundaries(self):
        for expected, actual in [("1,5V", "1, 5V"), ("12:30", "12: 30"),
                                 ("1.5V", "1. 5V"), ("20V", "120V"),
                                 ("20 V", "20V"), ("NOT", "NO T"),
                                 ("a,b", "ab"), ("A:B", "A;B")]:
            with self.subTest(expected=expected, actual=actual):
                self.assertFalse(matching.token_spans(expected, actual))
        self.assertEqual(matching.token_spans("", "anything"), [])

    def test_strict_text(self):
        cases=[("20V","120V",False),("MODEL: X1","MODEL: X2",False),("Do NOT heat.","Do heat.",False),
               ("Made in China","Made In China",False),("1.5V","15V",False),("20V","20v",False),
               ("Store indoors.","Store indoors",False),("Li-ion Battery Pack","Li-ion\nBattery   Pack",True),
               ("20V","20V Max",True),("X1","XX1",False)]
        for expected,actual,ok in cases:
            with self.subTest(expected=expected,actual=actual):
                self.assertEqual(matching.direct([element(expected)],[observation(actual)])[0]["state"]=="matched",ok)

    def test_one_exact_occurrence_satisfies_despite_conflicting_repeats(self):
        rows=matching.direct([element("20V")],[observation("20V"),observation("120V Max","o2")])
        self.assertEqual(rows[0]["state"],"matched");self.assertTrue(rows[0]["conflicts"])
        self.assertEqual(rows[0]["evidence"][0]["evidence_id"],"o1")
        self.assertFalse(matching.candidates(rows,[])['elements'])

    def test_repeats_order_and_missing_element(self):
        obs=[observation("120V","wrong"),observation("20V","correct"),observation("20v","case")]
        for order in (obs,list(reversed(obs))):
            rows=matching.direct([element("20V"),element("MODEL: X1",identity="e2")],order)
            self.assertEqual([r['state'] for r in rows],['matched','review'])
        self.assertEqual(matching.direct([element("20V")],obs[:1])[0]['state'],'review')

    def test_local_exact_combination_overrides_other_instance_difference(self):
        obs=[observation("20V Max","bad"),observation("20V","a",[.1,.1,.2,.12]),
             observation("Pack","b",[.21,.1,.3,.12]),observation("120V Pack","conflict")]
        rows=matching.direct([element("20V Pack")],obs)
        self.assertTrue(rows[0]['conflicts'])
        proposal={'mappings':[{'element_id':'e1','spans':[{'evidence_id':'a','start':0,'end':3},
            {'evidence_id':'b','start':0,'end':4}]}]}
        self.assertEqual(matching.validate(proposal,matching.candidates(rows,obs),rows)[0]['state'],'matched')

    def test_payload_code_not_vlm_text(self):
        value=observation("url",kind="code")
        self.assertEqual(matching.direct([element("url","code")],[value])[0]["state"],"review")
        value["provenance"]="local_decoder"
        self.assertEqual(matching.direct([element("url","code")],[value])[0]["state"],"matched")
        self.assertFalse(matching.candidates(matching.direct([element("url","code")],[]),[]) ["elements"])

    def test_unicode_original_character_spans(self):
        self.assertEqual(matching.token_spans("20V Max","  20V\n  Max  "),[(2,11)])
        self.assertEqual(matching.token_spans("型号 X1","图案 型号\nX1 结束"),[(3,8)])

    def prepared(self):
        obs=[observation("Battery","o1",[.1,.1,.3,.12]),observation("Pack","o2",[.31,.1,.4,.12])]
        rows=matching.direct([element("Battery Pack")],obs)
        request=matching.candidates(rows,obs)
        proposal={"mappings":[{"element_id":"e1","spans":[{"evidence_id":"o1","start":0,"end":7},{"evidence_id":"o2","start":0,"end":4}]}]}
        return rows,request,proposal

    def test_local_combination(self):
        rows,request,proposal=self.prepared()
        self.assertEqual(matching.validate(proposal,request,rows)[0]["state"],"matched")

    def test_forged_id_and_generated_text(self):
        for modification in [lambda p:p["mappings"][0].update(element_id="e999"),
                lambda p:p["mappings"][0].update(observed_text="Battery Pack"),
                lambda p:p["mappings"][0]["spans"][0].update(evidence_id="invented"),
                lambda p:p["mappings"][0]["spans"][0].update(start=True),
                lambda p:p["mappings"][0]["spans"].reverse(),
                lambda p:p["mappings"].append(copy.deepcopy(p["mappings"][0]))]:
            rows,request,proposal=self.prepared();original=copy.deepcopy(rows);modification(proposal)
            with self.assertRaises(ValueError):matching.validate(proposal,request,rows)
            self.assertEqual(rows,original)

    def test_distant_combination_rejected(self):
        rows,request,proposal=self.prepared()
        request["evidence"][1]["box"]=[.8,.8,.9,.82]
        with self.assertRaisesRegex(ValueError,"nonlocal"):matching.validate(proposal,request,rows)

    def test_reuse_characters_rejected(self):
        rows,request,proposal=self.prepared()
        proposal["mappings"][0]["spans"][1]=copy.deepcopy(proposal["mappings"][0]["spans"][0])
        with self.assertRaisesRegex(ValueError,"reused"):matching.validate(proposal,request,rows)

    def test_partial_number_rejected(self):
        rows=matching.direct([element("20V")],[observation("120V")]);request=matching.candidates(rows,[observation("120V")])
        # A forged proposal may not promote a conflict to a match either.
        with self.assertRaises(ValueError):matching.validate({"mappings":[{"element_id":"e1","spans":[{"evidence_id":"o1","start":1,"end":4}]}]},request,rows)

    def test_cannot_skip_not(self):
        obs=observation("Do NOT heat.");rows=matching.direct([element("Do heat.")],[obs]);request=matching.candidates(rows,[obs])
        with self.assertRaisesRegex(ValueError,"skipped"):
            matching.validate({"mappings":[{"element_id":"e1","spans":[{"evidence_id":"o1","start":0,"end":2},{"evidence_id":"o1","start":7,"end":12}]}]},request,rows)

    def test_capacity_explicit(self):
        rows=matching.direct([element("missing "+str(i),identity="e"+str(i)) for i in range(42)],[])
        request=matching.candidates(rows,[observation('unrelated text')])
        self.assertEqual(len(request["elements"]),40);self.assertEqual(len(request["omitted_element_ids"]),2)

    def test_graphics_and_empty_never_match(self):
        self.assertEqual(matching.direct([element("","text"),element("logo","graphic","e2")],[observation("logo")])[0]["state"],"review")
        self.assertFalse(matching.direct([],[]))

    def test_injection_is_data_not_schema(self):
        rows,request,proposal=self.prepared()
        self.assertNotIn("image",json.dumps(request))
        with self.assertRaises(ValueError):matching.validate({"decision":"MATCH","mappings":[]},request,rows)


if __name__=="__main__":unittest.main()

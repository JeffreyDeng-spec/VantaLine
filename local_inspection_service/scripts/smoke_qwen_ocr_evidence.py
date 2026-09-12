"""Offline protocol fixtures, NOT real OCR accuracy/performance acceptance."""
import copy
import io
import json
import unittest

from PIL import Image
from local_inspection_service import evidence_matching as matching
from local_inspection_service import qwen_ocr_evidence as ocr


def response(words=None):
    return {"output":{"choices":[{"finish_reason":"stop","message":{"content":[{"ocr_result":{
        "words_info":words if words is not None else [{"text":"20V Max", "location":[10,10,90,10,90,30,10,30]}]
    }}]}}]},"usage":{"input_tokens":100,"output_tokens":20}}


def element(text, kind="text", identity="e1"):
    return dict(id=identity, type=kind, text=text, state="keep", clean_box=[.1,.1,.7,.2])


def observation(text, identity="o1", box=None, kind="text"):
    return dict(id=identity, type=kind, text=text, box=box or [.1,.1,.4,.12], confidence=None, provenance="qwen_ocr")


class ProtocolTests(unittest.TestCase):
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
            def close(self):pass
        def post(*a,**kw):calls.append(kw);return Reply()
        with self.assertRaisesRegex(ocr.EvidenceError,"ocr_http_403"):
            ocr.recognize(dict(provider="qwen",api_key="secret",base_url="https://dashscope.aliyuncs.com"),b"img",(100,100),3,post)
        self.assertEqual(len(calls),1);self.assertFalse(calls[0]["allow_redirects"])


class MatchingTests(unittest.TestCase):
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
        request=matching.candidates(rows,[])
        self.assertEqual(len(request["elements"]),40);self.assertEqual(len(request["omitted_element_ids"]),2)

    def test_graphics_and_empty_never_match(self):
        self.assertEqual(matching.direct([element("","text"),element("logo","graphic","e2")],[observation("logo")])[0]["state"],"review")
        self.assertFalse(matching.direct([],[]))

    def test_injection_is_data_not_schema(self):
        rows,request,proposal=self.prepared()
        self.assertNotIn("image",json.dumps(request))
        with self.assertRaises(ValueError):matching.validate({"decision":"MATCH","mappings":[]},request,rows)


if __name__=="__main__":unittest.main()

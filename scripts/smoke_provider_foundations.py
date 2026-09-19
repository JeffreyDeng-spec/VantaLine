"""Offline provider error and JSON/data-URL boundary contracts."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from contextlib import ExitStack
from unittest.mock import Mock, patch, call

sys.path.insert(0, str(Path.cwd()))


import io,json,urllib.error
from unittest.mock import patch

def capture_provider_foundation(api, site, mode='ordinary'):
    events=[]
    with patch.dict(api.__dict__):
        if site=='normalize':
            original_loads=json.loads
            def callback(label):
                def invoke(value):events.append(label);return value
                return invoke
            a,b,c=(callback(x) for x in 'ABC')
            api.normalize_ai_json_root=a
            def candidates(text):
                if mode=='prior':api.normalize_ai_json_root=b
                if mode=='missing':api.normalize_ai_json_root=None
                return ['{}']
            api.ai_json_text_candidates=candidates
            def loads(value):
                events.append('loads');api.normalize_ai_json_root=c
                return original_loads(value)
            caught=None;result=None
            with patch.object(json,'loads',loads):
                try:result=api.parse_ai_json_object('input')
                except BaseException as exc:caught=exc
            if mode=='missing':
                assert type(caught) is TypeError,(caught,events)
                assert events==['loads'],events
            else:
                assert caught is None,(caught,events)
                assert result=={},result
                assert events==['loads','B' if mode=='prior' else 'A'],events
            return {'events':events,'error':type(caught).__name__ if caught else None}
        if site=='formatter_refresh':
            def b(text,limit):events.append('B');return str(text)
            def a(text,limit):events.append('A');api.bounded_text=b;return str(text)
            api.bounded_text=a
            result=api.provider_http_error('prefix',urllib.error.HTTPError('https://fixture.invalid',503,'bad',{},io.BytesIO(b'detail')))
            assert events==['A','B'],events
            assert str(result)=='AI provider overloaded: HTTP 503 detail',result
            return {'events':events,'message':str(result)}
        status=int(site.split('_')[1])
        name,prior_index,effect_index={401:('AiProviderAuthError',2,3),503:('AiProviderOverloaded',3,4),400:('AiProviderConfigError',4,5),500:('AiProviderError',5,6),418:('AiProviderNonRetryableError',5,6)}[status]
        cls=getattr(api,name)
        def factory(label):
            def create(message,**kwargs):events.append(label);return cls(message,**kwargs)
            return create
        a,b,c=(factory(x) for x in 'ABC');setattr(api,name,a)
        class Http(urllib.error.HTTPError):
            def __getattribute__(self,key):
                if key=='code':
                    n=object.__getattribute__(self,'reads')+1;object.__setattr__(self,'reads',n);events.append('code'+str(n))
                    if n==prior_index:
                        if mode=='prior':setattr(api,name,b)
                        if mode=='missing':setattr(api,name,None)
                    if n==effect_index:setattr(api,name,c)
                return super().__getattribute__(key)
        http=Http('https://fixture.invalid',status,'bad',{},io.BytesIO(b'detail'));http.reads=0
        api.bounded_text=lambda text,limit:str(text)
        caught=None;result=None
        try:result=api.provider_http_error('prefix',http)
        except BaseException as exc:caught=exc
        if mode=='missing':
            assert type(caught) is TypeError,(site,caught,events)
            assert not any(e in 'ABC' for e in events),events
        else:
            assert caught is None,(site,caught,events)
            assert events[-1]==('B' if mode=='prior' else 'A'),events
            assert result.http_status==status,result
        assert 'code'+str(effect_index) in events,events
        return {'events':events,'error':type(caught).__name__ if caught else None}


class ProviderFoundationContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ)
        cls.env.start()
        cls.tmp = tempfile.TemporaryDirectory(prefix='provider-foundation-')
        root = Path(cls.tmp.name)
        (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        cls.env.stop()

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen', 'subprocess.Popen', 'os.kill'):
            self.stack.enter_context(patch(name, side_effect=AssertionError('external operation forbidden')))

    def test_error_defaults_and_inheritance(self):
        a = self.api
        for cls, parent in ((a.AiProviderError, RuntimeError), (a.AiProviderNonRetryableError, a.AiProviderError),
                            (a.AiProviderConfigError, a.AiProviderNonRetryableError), (a.AiProviderAuthError, a.AiProviderNonRetryableError),
                            (a.AiProviderTimeout, a.AiProviderError), (a.AiProviderOverloaded, a.AiProviderError)):
            with self.subTest(cls=cls.__name__):
                err = cls('message')
                self.assertIsInstance(err, parent)
                self.assertEqual(err.args, ('message',))
                self.assertEqual(err.__dict__, dict(usage_metadata={}, failed_usage_metadata=[], attempts=None,
                    retry_count=None, previous_errors=[], http_status=None, fallback_model='', fallback_reason=''))

    def test_error_metadata_aliases_and_empty_replacements(self):
        usage = {'tokens': 1}; failed = [{'tokens': 2}]; previous = ['prior']
        err = self.api.AiProviderError('x', usage_metadata=usage, failed_usage_metadata=failed, previous_errors=previous,
                                      attempts=3, retry_count=2, http_status=503, fallback_model='m', fallback_reason='busy')
        self.assertIs(err.usage_metadata, usage); self.assertIs(err.failed_usage_metadata, failed); self.assertIs(err.previous_errors, previous)
        self.assertEqual((err.attempts, err.retry_count, err.http_status, err.fallback_model, err.fallback_reason), (3, 2, 503, 'm', 'busy'))
        empty = {}; empty_list = []
        other = self.api.AiProviderError(usage_metadata=empty, failed_usage_metadata=empty_list, previous_errors=empty_list)
        self.assertIsNot(other.usage_metadata, empty); self.assertIsNot(other.failed_usage_metadata, empty_list); self.assertIsNot(other.previous_errors, empty_list)

    def test_http_status_classification_and_single_body_read(self):
        a = self.api
        expected = {401:a.AiProviderAuthError,403:a.AiProviderAuthError,429:a.AiProviderOverloaded,503:a.AiProviderOverloaded,
                    400:a.AiProviderConfigError,404:a.AiProviderConfigError,408:a.AiProviderError,500:a.AiProviderError,
                    502:a.AiProviderError,504:a.AiProviderError,418:a.AiProviderNonRetryableError,200:a.AiProviderNonRetryableError}
        for status, cls in expected.items():
            with self.subTest(status=status):
                http = urllib.error.HTTPError('https://example.invalid',status,'error',{},io.BytesIO(b'detail'))
                reader = Mock(wraps=http.read)
                with patch.object(http,'read',reader): result = a.provider_http_error('prefix',http)
                self.assertIs(type(result),cls); self.assertEqual(result.http_status,status); reader.assert_called_once_with()
                prefix = 'AI provider overloaded' if status in (429,503) else 'prefix'
                self.assertEqual(str(result),f'{prefix}: HTTP {status} detail')

    def test_http_decode_replace_and_truncation_order(self):
        http = urllib.error.HTTPError('https://example.invalid',503,'error',{},io.BytesIO(b'\xff'+b'x'*400))
        formatter = Mock(side_effect=lambda text,limit:str(text)[:limit])
        with patch.object(self.api,'bounded_text',formatter): result = self.api.provider_http_error('prefix',http)
        self.assertEqual(formatter.call_args_list,[call('\ufffd'+'x'*239,180)]*2)
        self.assertEqual(str(result),'AI provider overloaded: HTTP 503 '+'\ufffd'+'x'*179)

    def test_http_read_error_propagates_without_retry(self):
        error = OSError('read failed'); calls = []
        def read():
            calls.append(1)
            if len(calls)==1: raise error
            return b'ok'
        http = urllib.error.HTTPError('https://example.invalid',500,'error',{},None)
        with patch.object(http,'read',read,create=True),self.assertRaises(OSError) as caught:self.api.provider_http_error('prefix',http)
        self.assertIs(caught.exception,error); self.assertEqual(calls,[1])

    def test_normalize_preserves_dictionary_identity(self):
        value = {'a':[]}; self.assertIs(self.api.normalize_ai_json_root(value),value)
        self.assertIs(self.api.normalize_ai_json_root([value]),value)

    def test_normalize_detection_lists_keeps_original_items(self):
        item = {'accessory_id':'a'}; result = self.api.normalize_ai_json_root([None,item,2])
        self.assertEqual(result,{'detections':[item],'rule':{'counts':{}}}); self.assertIs(result['detections'][0],item)
        self.assertEqual(self.api.normalize_ai_json_root([{'accessory_id':'a'}])['rule'],{'counts':{}})

    def test_normalize_unsupported_roots(self):
        for value in (None,1,'x',[],[None],[{},2],[{},{}]):
            with self.subTest(value=value):self.assertIsNone(self.api.normalize_ai_json_root(value))

    def test_candidates_empty_and_whitespace(self):
        for value in ('','  ',None,0):self.assertEqual(self.api.ai_json_text_candidates(value),[])
        self.assertEqual(self.api.ai_json_text_candidates('  {"x":1}  '),['{"x":1}'])

    def test_candidates_fences_preserve_priority_and_duplicates(self):
        text='before ```json {"a":1} ``` then ```JSON {"b":2} ``` after'
        self.assertEqual(self.api.ai_json_text_candidates(text),['{"b":2}','{"a":1}',text])
        self.assertEqual(self.api.ai_json_text_candidates('```json\n{}\n```'),['{}','```json\n{}\n```'])

    def test_candidates_incomplete_fence_keeps_original(self):
        self.assertEqual(self.api.ai_json_text_candidates('```javascript\n{}'),['{}','```javascript\n{}'])

    def test_parse_direct_and_single_dictionary_list(self):
        self.assertEqual(self.api.parse_ai_json_object('{"a":1}'),{'a':1})
        self.assertEqual(self.api.parse_ai_json_object('[{"a":1}]'),{'a':1})

    def test_parse_embedded_objects_and_invalid_prefix(self):
        self.assertEqual(self.api.parse_ai_json_object('explanation { invalid then {"ok":true} trailing'),{'ok':True})
        self.assertEqual(self.api.parse_ai_json_object('null then {"a":2}'),{'a':2})

    def test_parse_fence_priority_depends_on_leading_fence(self):
        self.assertEqual(self.api.parse_ai_json_object('```json {"a":1} ```\n```json {"a":2} ```'),{'a':1})
        self.assertEqual(self.api.parse_ai_json_object('prefix ```json {"a":1} ```\n```json {"a":2} ```'),{'a':2})

    def test_parse_detection_list(self):
        self.assertEqual(self.api.parse_ai_json_object('[{"accessory_id":"a"},null]'),{'detections':[{'accessory_id':'a'}],'rule':{'counts':{}}})

    def test_parse_failure_message_and_non_json_exception(self):
        for value in ('', '[]', 'true', 'plain text'):
            with self.subTest(value=value),self.assertRaises(self.api.AiProviderError) as caught:self.api.parse_ai_json_object(value)
            self.assertEqual(str(caught.exception),'AI provider did not return a parseable JSON object')
        failure = RuntimeError('decoder failure')
        with patch.object(self.api.json,'loads',side_effect=failure),self.assertRaises(RuntimeError) as caught:self.api.parse_ai_json_object('{}')
        self.assertIs(caught.exception,failure)

    def test_data_url_mime_and_payload_are_not_decoded(self):
        self.assertEqual(self.api.data_url_payload('data:image/png;base64,NOT-BASE64'),('image/png','NOT-BASE64'))
        self.assertEqual(self.api.data_url_payload('data:;base64,a,b'),('image/jpeg','a,b'))
        self.assertEqual(self.api.data_url_payload('image/png;base64,abc'),('image/png','abc'))

    def test_data_url_invalid_values_fail_identically(self):
        for value in ('',None,'data:image/png,abc','data:image/png;base64,'):
            with self.subTest(value=value),self.assertRaises(self.api.AiProviderError) as caught:self.api.data_url_payload(value)
            self.assertEqual(str(caught.exception),'AI image payload was not a base64 data URL')


    def test_error_pickle_old_import_path_and_new_round_trip(self):
        import pickle
        for name in ('AiProviderError','AiProviderNonRetryableError','AiProviderConfigError','AiProviderAuthError','AiProviderTimeout','AiProviderOverloaded'):
            with self.subTest(name=name):
                cls=getattr(self.api,name);error=cls('synthetic',usage_metadata={'tokens':3},previous_errors=['prior'],http_status=503)
                current=pickle.dumps(error,protocol=0)
                legacy=current.replace(b'clocal_inspection_service.model_providers.errors\n',b'clocal_inspection_service.server\n')
                for payload in (current,legacy):
                    restored=pickle.loads(payload);self.assertIs(type(restored),cls);self.assertEqual(restored.args,error.args);self.assertEqual(restored.__dict__,error.__dict__)

    def test_independent_payload_and_http_compositions(self):
        from local_inspection_service.model_providers.payloads import ProviderPayloadParser,normalize_ai_json_root,ai_json_text_candidates
        from local_inspection_service.model_providers.http_errors import ProviderHttpErrors,ProviderErrorTypes
        from local_inspection_service.model_providers.errors import AiProviderError,AiProviderAuthError,AiProviderOverloaded,AiProviderConfigError,AiProviderNonRetryableError
        parser=ProviderPayloadParser(lambda:ai_json_text_candidates,lambda:normalize_ai_json_root,lambda:AiProviderError)
        errors=ProviderErrorTypes(lambda:AiProviderError,lambda:AiProviderAuthError,lambda:AiProviderOverloaded,lambda:AiProviderConfigError,lambda:AiProviderNonRetryableError)
        mapper=ProviderHttpErrors(lambda:(lambda value,limit:str(value)[:limit]),errors)
        with ExitStack() as stack:
            for name in ('normalize_ai_json_root','ai_json_text_candidates','parse_ai_json_object','data_url_payload','provider_http_error','bounded_text'):
                stack.enter_context(patch.object(self.api,name,side_effect=AssertionError('root dependency')))
            for name in ('AiProviderError','AiProviderAuthError','AiProviderOverloaded','AiProviderConfigError','AiProviderNonRetryableError'):
                stack.enter_context(patch.object(self.api,name,None))
            self.assertEqual(parser.parse_ai_json_object('prefix {"x":1}'),{'x':1})
            self.assertEqual(parser.data_url_payload('data:image/png;base64,abc'),('image/png','abc'))
            with self.assertRaises(AiProviderError):parser.parse_ai_json_object('invalid')
            http=urllib.error.HTTPError('https://example.invalid',401,'error',{},io.BytesIO(b'no'))
            result=mapper.provider_http_error('prefix',http);self.assertIs(type(result),AiProviderAuthError);self.assertEqual(result.http_status,401)

    def test_independent_error_module_aliases_are_single_class_objects(self):
        from local_inspection_service.model_providers import errors
        for name in ('AiProviderError','AiProviderNonRetryableError','AiProviderConfigError','AiProviderAuthError','AiProviderTimeout','AiProviderOverloaded'):
            with self.subTest(name=name):
                self.assertIs(getattr(self.api,name),getattr(errors,name))
                self.assertEqual(getattr(errors,name).__module__,'local_inspection_service.model_providers.errors')

    def test_provider_callees_are_captured_before_argument_effects(self):
        for site in ('normalize','http_401','http_503','http_400','http_500','http_418'):
            for mode in ('ordinary','prior','missing'):
                with self.subTest(site=site,mode=mode):capture_provider_foundation(self.api,site,mode)

    def test_overloaded_formatter_refreshes_before_second_message(self):
        capture_provider_foundation(self.api,'formatter_refresh')

    def _first_error_matrix(self,kind):
        from dataclasses import replace
        scenarios=('direct','fallback','invalid','data_url','http_401','http_503','http_400','http_500','http_418')
        original_error=self.api.AiProviderError
        for scenario in scenarios:
            def run(target=None):
                failure=RuntimeError('boundary failure');trace=[];counts={}
                def wrap(label,fn):
                    def invoke(*a,**kw):
                        counts[label]=counts.get(label,0)+1;key=(label,counts[label]);trace.append(key)
                        if key==target:raise failure
                        return fn(*a,**kw)
                    return invoke
                with ExitStack() as stack:
                    if kind=='boundary':
                        for name in ('ai_json_text_candidates','normalize_ai_json_root','bounded_text','AiProviderError','AiProviderAuthError','AiProviderOverloaded','AiProviderConfigError','AiProviderNonRetryableError'):
                            stack.enter_context(patch.object(self.api,name,wrap(name,getattr(self.api,name))))
                        stack.enter_context(patch.object(self.api.json,'loads',wrap('loads',self.api.json.loads)))
                    else:
                        parser=self.api._provider_payloads;mapper=self.api._provider_http_errors
                        for name in ('candidates','normalize','error'):
                            stack.enter_context(patch.object(parser,name,wrap('parser.'+name,getattr(parser,name))))
                        stack.enter_context(patch.object(mapper,'text',wrap('http.text',mapper.text)))
                        stack.enter_context(patch.object(mapper,'errors',replace(mapper.errors,**{name:wrap('http.'+name,value) for name,value in vars(mapper.errors).items()})))
                    caught=None
                    try:
                        if scenario.startswith('http_'):
                            status=int(scenario.split('_')[1]);self.api.provider_http_error('prefix',urllib.error.HTTPError('https://example.invalid',status,'error',{},io.BytesIO(b'detail')))
                        elif scenario=='data_url':self.api.data_url_payload('invalid')
                        else:self.api.parse_ai_json_object({'direct':'{}','fallback':'prefix {}','invalid':'invalid'}[scenario])
                    except BaseException as exc:caught=exc
                    if target is None:
                        if scenario in ('invalid','data_url'):self.assertIsInstance(caught,original_error)
                        else:self.assertIsNone(caught)
                    else:
                        self.assertIs(caught,failure);self.assertEqual(counts[target[0]],target[1]);self.assertEqual(trace[-1],target)
                    return trace
            for target in run():
                with self.subTest(kind=kind,scenario=scenario,target=target):run(target)

    def test_existing_callback_first_errors_are_not_retried(self):
        self._first_error_matrix('boundary')

    def test_independent_dependency_first_errors_are_not_retried(self):
        self._first_error_matrix('dependency')

    def test_json_decode_error_catch_boundary_is_preserved(self):
        import json
        failure=json.JSONDecodeError('synthetic','{}',0);normal=self.api.normalize_ai_json_root;seen=[]
        def first(value):
            seen.append(value)
            if len(seen)==1:raise failure
            return normal(value)
        caught_direct=None;result=None
        with patch.object(self.api,'normalize_ai_json_root',first):
            try:result=self.api.parse_ai_json_object('{}')
            except BaseException as exc:caught_direct=exc
        self.assertIsNone(caught_direct);self.assertEqual(result,{});self.assertEqual(seen,[{},{}])
        seen.clear()
        with patch.object(self.api,'normalize_ai_json_root',first),self.assertRaises(BaseException) as caught:
            self.api.parse_ai_json_object('prefix {}')
        self.assertIs(caught.exception,failure);self.assertIs(type(caught.exception),json.JSONDecodeError);self.assertEqual(seen,[{}])

if __name__=='__main__':unittest.main()

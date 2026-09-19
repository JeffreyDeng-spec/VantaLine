"""Synthetic accounting boundary before adding an instance resolver adapter."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path.cwd()))
from local_inspection_service.model_profiles import audit
from local_inspection_service.model_providers.errors import AiProviderError


class MeteringContracts(unittest.TestCase):
    audit = audit
    instance_mode = True

    def provider(self, action, *, bound=True):
        class Provider:
            def run(self,*args,**kwargs):return self.action(*args,**kwargs)
        provider=Provider()
        provider.settings={'profile_id':'synthetic','api_key':'synthetic-key','proxy_url_raw':'synthetic-proxy'} if bound else {}
        provider.last_usage_metadata={'total_tokens':7}
        provider.recorder=Mock()
        provider.resolver=type('Resolver',(),{})()
        provider.resolver.record_call=provider.recorder
        provider.resolve=Mock(side_effect=lambda:provider.resolver)
        provider.action=Mock(side_effect=action)
        decorator=self.audit.metered_instance(lambda current:current.resolve()) if self.instance_mode else self.audit.metered(provider.resolve)
        Provider.run=decorator(Provider.run)
        return provider

    def assert_record(self,p,ok,usage):
        p.recorder.assert_called_once()
        settings,elapsed,actual_ok,actual_usage=p.recorder.call_args.args
        self.assertIs(settings,p.settings)
        self.assertGreaterEqual(elapsed,0)
        self.assertIs(actual_ok,ok)
        self.assertEqual(actual_usage,usage)

    def test_success_retains_result_and_usage_metadata_priority(self):
        result={'usage_metadata':{'tokens':3},'usage':{'tokens':9}}
        p=self.provider(lambda *a,**kw:result)
        self.assertIs(p.run('prompt',limit=3),result)
        p.action.assert_called_once_with('prompt',limit=3)
        p.resolve.assert_called_once_with()
        self.assert_record(p,True,{'tokens':3})

    def test_dict_usage_fallback_and_non_dict_last_usage(self):
        for result,usage in (({'usage':{'tokens':2}},{'tokens':2}),({},{}),(({},12),{'total_tokens':7}),(None,{'total_tokens':7})):
            with self.subTest(result=result):
                p=self.provider(lambda:result);self.assertIs(p.run(),result);self.assert_record(p,True,usage)

    def test_unbound_legacy_call_never_resolves_or_records(self):
        p=self.provider(lambda:'ok',bound=False)
        p.resolver=None
        self.assertEqual(p.run(),'ok');p.resolve.assert_not_called();p.recorder.assert_not_called()

    def test_missing_resolver_fails_before_provider(self):
        p=self.provider(lambda:'must not run');p.resolver=None
        with self.assertRaises(RuntimeError) as caught:p.run()
        self.assertEqual(str(caught.exception),'Model profile resolver is not configured')
        p.action.assert_not_called();p.recorder.assert_not_called();p.resolve.assert_called_once_with()

    def test_resolver_failure_is_not_retried(self):
        p=self.provider(lambda:'must not run');failure=RuntimeError('resolver unavailable');seen=[]
        def get():
            seen.append(1)
            if len(seen)==1:raise failure
            return p.resolver
        p.resolve.side_effect=get
        with self.assertRaises(RuntimeError) as caught:p.run()
        self.assertIs(caught.exception,failure);self.assertEqual(seen,[1]);p.action.assert_not_called();p.recorder.assert_not_called()

    def test_accounting_failure_does_not_repeat_successful_call(self):
        p=self.provider(lambda:{'usage':{'tokens':2}});p.recorder.side_effect=RuntimeError('ledger unavailable')
        with self.assertLogs(self.audit.__name__,level='WARNING') as logs:result=p.run()
        self.assertEqual(result,{'usage':{'tokens':2}});p.action.assert_called_once_with();p.recorder.assert_called_once()
        self.assertEqual(logs.output,['WARNING:'+self.audit.__name__+':Model usage accounting unavailable'])

    def test_failure_redaction_retains_identity_and_accounts_once(self):
        error=AiProviderError('synthetic-key synthetic-proxy',usage_metadata={'value':'synthetic-key'},failed_usage_metadata=[{'x':'synthetic-proxy'}],previous_errors=['synthetic-key'])
        error.response_preview='synthetic-key'
        def fail():raise error
        p=self.provider(fail)
        with self.assertRaises(AiProviderError) as caught:p.run()
        self.assertIs(caught.exception,error);self.assertEqual(str(error),'[REDACTED] [REDACTED]')
        self.assertEqual(error.response_preview,'[REDACTED]');self.assertEqual(error.previous_errors,['[REDACTED]'])
        self.assertEqual(error.usage_metadata,{'value':'[REDACTED]'});self.assertEqual(error.failed_usage_metadata,[{'x':'[REDACTED]'}])
        p.action.assert_called_once_with();self.assert_record(p,False,{'total_tokens':7})

    def test_http_status_overrides_error_message(self):
        error=AiProviderError('unsafe detail',http_status=503)
        def fail():raise error
        p=self.provider(fail)
        with self.assertRaises(AiProviderError) as caught:p.run()
        self.assertIs(caught.exception,error);self.assertEqual(str(error),'模型服务返回 HTTP 503')
        self.assert_record(p,False,{'total_tokens':7})

    def test_unbound_exception_is_not_rewritten(self):
        error=AiProviderError('synthetic-key')
        def fail():raise error
        p=self.provider(fail,bound=False)
        with self.assertRaises(AiProviderError) as caught:p.run()
        self.assertIs(caught.exception,error);self.assertEqual(str(error),'synthetic-key');p.resolve.assert_not_called();p.recorder.assert_not_called()

    def test_cancellation_is_recorded_without_swallowing_or_redacting(self):
        class Cancelled(BaseException):pass
        error=Cancelled('synthetic-key')
        def fail():raise error
        p=self.provider(fail)
        with self.assertRaises(Cancelled) as caught:p.run()
        self.assertIs(caught.exception,error);self.assertEqual(str(error),'synthetic-key');self.assert_record(p,False,{'total_tokens':7})

    def test_settings_are_captured_before_transport_mutates_instance(self):
        p=self.provider(lambda:None);old=p.settings
        def call():p.settings={'profile_id':'different'};return {'usage':{'tokens':1}}
        p.action.side_effect=call;p.run()
        self.assertIs(p.recorder.call_args.args[0],old);self.assertIsNot(p.recorder.call_args.args[0],p.settings)

    def test_wrapper_metadata_and_single_underlying_call(self):
        p=self.provider(lambda:'value')
        self.assertEqual(p.run.__name__,'run');self.assertEqual(p.run.__wrapped__.__name__,'run')
        self.assertEqual(p.run(),'value');p.action.assert_called_once_with()


    def test_independent_same_class_instances_use_separate_resolvers_concurrently(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier=Barrier(2)
        class Provider:
            def __init__(self,name):
                self.settings={'profile_id':name};self.last_usage_metadata={'instance':name};self.recorder=Mock()
                self.resolver=type('Resolver',(),{})();self.resolver.record_call=self.recorder
            def run(self):barrier.wait(timeout=5);return self.settings['profile_id']
        Provider.run=self.audit.metered_instance(lambda instance:instance.resolver)(Provider.run)
        first,second=Provider('first'),Provider('second')
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(first.run);b=pool.submit(second.run)
            self.assertEqual((a.result(timeout=10),b.result(timeout=10)),('first','second'))
        for instance in (first,second):
            instance.recorder.assert_called_once();self.assertIs(instance.recorder.call_args.args[0],instance.settings)
            self.assertEqual(instance.recorder.call_args.args[3],instance.last_usage_metadata)

    def test_independent_instance_resolver_is_refreshed_each_call(self):
        p=self.provider(lambda:'ok');first=p.recorder
        self.assertEqual(p.run(),'ok')
        second=Mock();p.resolver=type('Resolver',(),{})();p.resolver.record_call=second
        self.assertEqual(p.run(),'ok');first.assert_called_once();second.assert_called_once();self.assertEqual(p.resolve.call_count,2)

    def test_independent_current_call_keeps_recorder_when_resolver_changes(self):
        p=self.provider(lambda:None);first=p.recorder;second=Mock()
        def transport():
            p.resolver=type('Resolver',(),{})();p.resolver.record_call=second
            return 'result'
        p.action.side_effect=transport
        self.assertEqual(p.run(),'result');first.assert_called_once();second.assert_not_called()
        self.assertEqual(p.run(),'result');first.assert_called_once();second.assert_called_once()
        self.assertEqual(p.resolve.call_count,2);self.assertEqual(p.action.call_count,2)

    def test_independent_nested_same_class_instances_keep_recorders(self):
        class Provider:
            def __init__(self,name):
                self.settings={'profile_id':name};self.last_usage_metadata={'instance':name}
                self.record=Mock();self.resolver=type('Resolver',(),{})();self.resolver.record_call=self.record;self.child=None
            def run(self):
                if self.child:self.child.run()
                return self.settings['profile_id']
        Provider.run=self.audit.metered_instance(lambda instance:instance.resolver)(Provider.run)
        outer,inner=Provider('outer'),Provider('inner');outer.child=inner
        self.assertEqual(outer.run(),'outer')
        for instance in (outer,inner):
            instance.record.assert_called_once();self.assertIs(instance.record.call_args.args[0],instance.settings)
            self.assertEqual(instance.record.call_args.args[2:],(True,instance.last_usage_metadata))

if __name__=='__main__':unittest.main()

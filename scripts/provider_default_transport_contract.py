"""Exercise the actual default transport graph without network or paid calls."""
import io
import json
import urllib.error
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch


def assert_default_transport(case, kind):
    from local_inspection_service import server
    from scripts.model_profile_test_ports import patch_profile_service
    owner = server._provider_configuration
    parser = server._provider_payloads
    errors = server._provider_http_errors
    graph = server._provider_transports
    provider_type = (server.OpenAICompatibleAiProvider if kind == 'openai'
                     else server.GeminiAiProvider)
    case.assertIs(provider_type, getattr(graph, kind))
    settings = dict(configured=True, provider=kind, model='synthetic-model',
                    base_url='https://fixture.invalid/v1/', api_key='synthetic-key',
                    timeout_seconds=13.5, profile_id='synthetic-profile')
    usage = {'total_tokens': 7} if kind == 'openai' else {'totalTokenCount': 7}
    body = (dict(choices=[dict(message=dict(content='{"answer":42}'),
                              finish_reason='stop')], usage=usage)
            if kind == 'openai' else
            dict(candidates=[dict(content=dict(parts=[dict(text='{"answer":42}')]),
                                  finishReason='STOP')], usageMetadata=usage))
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(body).encode()
    opener = Mock(return_value=response)
    record = Mock()
    with ExitStack() as stack:
        for name in ('requests.sessions.Session.request', 'urllib.request.urlopen',
                     'subprocess.Popen', 'os.kill'):
            stack.enter_context(patch(name, side_effect=AssertionError('external operation forbidden')))
        stack.enter_context(patch_profile_service(server, SimpleNamespace(record_call=record)))

        def owned_open(receiver, *args, **kwargs):
            case.assertIs(receiver, owner)
            return opener(*args, **kwargs)

        stack.enter_context(patch.object(type(owner), 'ai_urlopen', autospec=True,
                                        side_effect=owned_open))
        original_parse = type(parser).parse_ai_json_object
        original_error = type(errors).provider_http_error

        def owned_parse(receiver, *args, **kwargs):
            case.assertIs(receiver, parser)
            return original_parse(receiver, *args, **kwargs)

        def owned_error(receiver, *args, **kwargs):
            case.assertIs(receiver, errors)
            return original_error(receiver, *args, **kwargs)

        parsed = stack.enter_context(patch.object(type(parser), 'parse_ai_json_object',
                                                  autospec=True, side_effect=owned_parse))
        classified = stack.enter_context(patch.object(type(errors), 'provider_http_error',
                                                      autospec=True, side_effect=owned_error))
        provider = provider_type(settings)
        case.assertIs(provider.io, getattr(server, '_' + kind + '_transport_io'))
        case.assertIs(provider.errors, getattr(server, '_' + kind + '_transport_errors'))
        case.assertIs(provider.resolve, getattr(graph, kind + '_resolver'))
        case.assertEqual(provider.generate_json('system', [dict(type='text', text='user')])[0],
                         {'answer': 42})
        parsed.assert_called_once_with(parser, '{"answer":42}')
        opener.assert_called_once()
        request, actual_settings = opener.call_args.args
        case.assertIs(actual_settings, settings)
        case.assertEqual(request.method, 'POST')
        case.assertTrue(request.full_url.startswith('https://fixture.invalid/'))
        case.assertEqual(opener.call_args.kwargs, {'timeout': 13.5})
        payload = json.loads(request.data)
        case.assertEqual(payload['messages'][0]['content'] if kind == 'openai'
                         else payload['systemInstruction']['parts'][0]['text'], 'system')
        record.assert_called_once()
        case.assertIs(record.call_args.args[0], settings)
        case.assertEqual(record.call_args.args[2:], (True, usage))

        opener.reset_mock()
        record.reset_mock()
        settings['configured'] = False
        with case.assertRaises(server.AiProviderConfigError):
            provider_type(settings).generate_json('system', [])
        opener.assert_not_called()
        record.assert_called_once()
        case.assertFalse(record.call_args.args[2])

        settings['configured'] = True
        opener.side_effect = urllib.error.HTTPError(
            'https://fixture.invalid/', 401, 'synthetic', {}, io.BytesIO(b'synthetic'))
        record.reset_mock()
        with case.assertRaises(server.AiProviderAuthError) as caught:
            provider_type(settings).generate_json('system', [])
        case.assertEqual(caught.exception.http_status, 401)
        classified.assert_called_once()
        case.assertIs(classified.call_args.args[0], errors)
        record.assert_called_once()
        case.assertFalse(record.call_args.args[2])

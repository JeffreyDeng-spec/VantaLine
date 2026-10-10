"""Actual canonical HTTP endpoint to native receiver witnesses; no PLC I/O."""
from unittest.mock import patch


def assert_http_receivers(test, owner_name, cases):
    from canonical_application_source_contract import verify_actual_sources
    from local_inspection_service.runtime.default_application import default_application
    verify_actual_sources()
    owner = getattr(default_application.plc, owner_name)
    for endpoint_name, method, args in cases:
        with test.subTest(endpoint=endpoint_name):
            matches = [route.endpoint for route in default_application.app.routes
                       if getattr(getattr(route, 'endpoint', None), '__name__', None) == endpoint_name]
            test.assertEqual(len(matches), 1)
            marker = object()
            with patch.object(type(owner), method, autospec=True, return_value=marker) as receiver:
                test.assertIs(matches[0](*args), marker)
                receiver.assert_called_once_with(owner, *args)
                test.assertIs(receiver.call_args.args[0], owner)

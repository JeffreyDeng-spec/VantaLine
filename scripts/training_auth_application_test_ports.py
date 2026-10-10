"""Only the four existing synthetic training capabilities in RBAC smoke."""
from contextlib import ExitStack
from dataclasses import replace
from functools import wraps
from unittest.mock import patch


def with_training_auth_test_ports(api):
    def decorate(main):
        @wraps(main)
        def run(*args,**kwargs):
            from scripts.training_preview_application_test_ports import assert_default_training_preview
            from scripts.training_launch_application_test_ports import assert_default_training_launch
            assert_default_training_preview(api);assert_default_training_launch(api)
            graph=api._default_application.training_pipeline
            import unittest
            from scripts.auto_optimization_test_ports import assert_native_relay
            item, selected, action = object(), object(), object()
            assert_native_relay(unittest.TestCase(), graph._training_launch_submission.enqueue,
                (graph._training_execution, 'enqueue_training_task',
                 (item, selected, action), {}, (item, selected, action), {}))
            preview=graph._training_preview_submission;launch=graph._training_launch_submission
            with ExitStack() as stack:
                for owner in (preview,launch):stack.enter_context(patch.object(owner,'config',replace(owner.config,ensure=lambda:api.ensure_training_assets_for_request)))
                stack.enter_context(patch.object(preview,'draw',lambda:api.draw_training_preview))
                stack.enter_context(patch.object(launch,'enqueue',lambda *args,**kwargs:api.enqueue_training_task(*args,**kwargs)))
                return main(*args,**kwargs)
        return run
    return decorate

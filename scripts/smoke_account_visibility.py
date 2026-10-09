"""Actual account/network graph isolation and permission contracts; synthetic only."""
import ast
from dataclasses import fields, is_dataclass
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException
import smoke_account_projections as projections_test
from local_inspection_service.auth.visibility_composition import (
    AccountVisibility, VisibilityAccess, VisibilityConfiguration, VisibilityOrigins)
from local_inspection_service.auth.account_projection_ports import AccountModels, AccountMedia


class VisibilityContracts(unittest.TestCase):
    def test_default_aliases_and_actual_parent_contract(self):
        import application_integration_source_contract as contract
        source=(contract.ROOT/'local_inspection_service/server.py').read_text()
        current=ast.parse(contract.restore_provider_transports_root(source))
        self.assertEqual(contract.digest(current),contract.ACCOUNT_VISIBILITY['integrated_ast_sha256'])
        parent=ast.parse(contract.restore_account_visibility_root(source))
        self.assertEqual(contract.digest(parent),contract.ACCOUNT_VISIBILITY['parent_ast_sha256'])
        functions=lambda tree:[contract.canonical(node) for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))]
        self.assertEqual(functions(current),functions(parent));self.assertEqual(len(functions(current)),983)
        from verify_backend_contract import capture
        capture()
        from local_inspection_service import server
        graph=server._account_visibility
        self.assertIs(server._public_network_policy,graph.network)
        self.assertIs(server._account_projections,graph.projections)
        for edge in (graph.network.origins.normalize_origin(),graph.network.endpoints.is_private_or_local_host(),
            graph.projections.access.include_internal_runtime_details(),graph.projections.config.scope_config_for_user()):
            self.assertIs(edge.__self__,graph)

    def inputs(self):
        f=projections_test.Contracts().fixture()
        temporary=tempfile.TemporaryDirectory(prefix='account-visibility-')
        self.addCleanup(temporary.cleanup)
        f.b['OUTPUT_DIR']=Path(temporary.name)
        def ports(cls):
            return cls(**{field.name:lambda name=field.name:f.b[name] for field in fields(cls)})
        inputs=dict(access=ports(VisibilityAccess),configuration=ports(VisibilityConfiguration),
            models=ports(AccountModels),media=ports(AccountMedia),
            origins=VisibilityOrigins(lambda:['https://example.invalid'],lambda:r'^https://[^/]+\.local$'),
            masked_url=lambda:lambda value:'masked:'+value)
        return f,inputs

    def graph(self):
        f,inputs=self.inputs();f.graph=AccountVisibility(**inputs);return f

    def test_inert_constructor_fresh_owners_and_final_failure(self):
        f,inputs=self.inputs()
        def poison(*args,**kwargs):raise AssertionError('eager selection')
        def poisoned(value):
            if is_dataclass(value):return type(value)(**{field.name:poisoned(getattr(value,field.name)) for field in fields(value)})
            return poison if callable(value) else value
        inputs={name:poisoned(value) for name,value in inputs.items()}
        a,b=AccountVisibility(**inputs),AccountVisibility(**inputs)
        self.assertIsNot(a.network,b.network);self.assertIsNot(a.projections,b.projections)
        import local_inspection_service.auth.visibility_composition as module
        with patch.object(module,'AccountProjections',side_effect=ValueError('projection constructor')):
            with self.assertRaisesRegex(ValueError,'projection constructor'):AccountVisibility(**inputs)
        self.assertFalse(any(f.b['OUTPUT_DIR'].iterdir()))

    def test_two_account_permissions_redaction_and_paths(self):
        a,b=self.graph(),self.graph();a.user['permissions']={'ai_detection'}
        a.graph.projections.require_analyze_model_permission('ai')
        with self.assertRaises(HTTPException) as error:b.graph.projections.require_analyze_model_permission('ai')
        self.assertEqual(error.exception.status_code,403)
        payload={'model_path':'private','available_models':[{'path':'private','metadata':{'a':1}}]}
        redacted=b.graph.projections.redact_status_payload_for_user(payload,b.user)
        self.assertIsNot(redacted,payload);self.assertNotIn('model_path',redacted)
        self.assertNotIn('path',redacted['available_models'][0]);self.assertEqual(payload['model_path'],'private')
        a.user['admin']=True
        self.assertIs(a.graph.projections.redact_status_payload_for_user(payload,a.user),payload)
        for path,expected in (('/outputs/users/alice/image',True),('/outputs/users/bob/image',False),('/outputs/../../escape',False)):
            self.assertEqual(b.graph.projections.output_path_visible_to_user(path,b.user),expected)
        self.assertEqual(a.graph.network.sanitize_url_for_public_user('http://localhost/private'),'')
        self.assertEqual(b.graph.network.sanitize_url_for_public_user('https://public.invalid/private'),'masked:https://public.invalid/private')

    def test_saved_four_callbacks_select_owner_after_arguments(self):
        a,b=self.graph(),self.graph()
        network=a.graph.network
        normalize=network.origins.normalize_origin()
        def change_normalize():
            a.graph.network=b.graph.network
            return 'https://EXAMPLE.INVALID:443/path'
        with patch.object(type(b.graph.network),'normalize_origin',autospec=True,return_value='new') as called:
            self.assertEqual(normalize(change_normalize()),'new');self.assertIs(called.call_args.args[0],b.graph.network)
        private=network.endpoints.is_private_or_local_host()
        with patch.object(type(b.graph.network),'is_private_or_local_host',autospec=True,return_value=True) as called:
            self.assertTrue(private('example.invalid'));self.assertIs(called.call_args.args[0],b.graph.network)
        a.graph.network=network
        include=a.graph.projections.access.include_internal_runtime_details()
        a.b['user_is_admin']=lambda user:False
        b.b['user_is_admin']=lambda user:True
        def change_runtime_details():
            a.graph.network=b.graph.network
            return b.user
        self.assertTrue(include(change_runtime_details()))
        scope=a.graph.projections.config.scope_config_for_user()
        b.b['training_state_for_user']=lambda *args:{'owner':'b'}
        def change_scope():
            a.graph.projections=b.graph.projections
            return {'accessories':[{'id':'a','owner':'alice'}]}
        result=scope(change_scope(),b.user)
        self.assertEqual(result['training']['owner'],'b')

    def test_config_loader_rebinding_preserves_original_permission_evaluation_order(self):
        a,b=self.graph(),self.graph();a.user['permissions']={'ai_detection'};events=[]
        def load():
            events.append('load');a.graph.projections=b.graph.projections
            return {'accessories':[{'id':'a','owner':'alice'}]}
        a.b['load_config']=load
        a.b['selected_model_spec']=lambda model,config:events.append(('selected',config['training']['owner'])) or {'is_ai_detection':True}
        b.b['training_state_for_user']=lambda *args:events.append('scope-b') or {'owner':'b'}
        a.graph.projections.require_analyze_model_permission('ai')
        self.assertEqual(events,['load','scope-b',('selected','b')])


if __name__=='__main__':unittest.main()

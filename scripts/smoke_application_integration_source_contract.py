"""Positive and adverse checks for immutable assembly replay and real owners."""
import ast
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import application_integration_source_contract as contract


class IntegrationContracts(unittest.TestCase):
    def setUp(self):
        self.source = (contract.ROOT / "local_inspection_service/server.py").read_text()

    def test_current_root_and_actual_owner_bindings_pass_before_replay(self):
        contract.verify_actual_compositions()
        original = contract.restore_integrated_root(self.source)
        self.assertEqual(contract.digest(ast.parse(original)), contract.FIXTURE["parent_ast_sha256"])
        older = contract.restore_business_root(self.source)
        self.assertEqual(contract.digest(ast.parse(older)), contract.BUSINESS["parent_ast_sha256"])

    def test_pose_actual_owners_and_outer_fixture_mutations_fail(self):
        original_read = Path.read_text
        for relative in ("agent/state_composition.py", "agent/planning_composition.py", "agent/pose_execution_composition.py"):
            target = (contract.ROOT / "local_inspection_service" / relative).resolve()
            def read(path, *args, **kwargs):
                value = original_read(path, *args, **kwargs)
                return value + "\nunreviewed_owner = None\n" if path.resolve() == target else value
            with self.subTest(owner=relative), patch.object(Path, "read_text", read), self.assertRaises(AssertionError):
                contract.restore_pose_domain_root(self.source)
        for name in ("POSE_EXECUTION", "POSE_PLANNING", "AGENT_STATE"):
            altered = copy.deepcopy(getattr(contract, name))
            altered["regions"][0]["expected"][0] = "unreviewed_owner = None"
            with self.subTest(fixture=name), patch.object(contract, name, altered), self.assertRaises(AssertionError):
                contract.restore_pose_domain_root(self.source)

    def test_path_configuration_actual_owner_and_delta_are_guarded(self):
        target = (contract.ROOT / "local_inspection_service/runtime/path_configuration_composition.py").resolve()
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            value = original_read(path, *args, **kwargs)
            return value + "\nunreviewed_owner = None\n" if path.resolve() == target else value
        with patch.object(Path, "read_text", read), self.assertRaises(AssertionError):
            contract.restore_path_configuration_root(self.source)
        for mode in ("edit", "delete", "duplicate", "order"):
            altered = copy.deepcopy(contract.PATH_CONFIGURATION)
            if mode == "edit":
                altered["regions"][0]["expected"][0] = "unreviewed_owner = None"
            elif mode == "delete":
                altered["regions"].pop()
            elif mode == "duplicate":
                altered["regions"].append(copy.deepcopy(altered["regions"][-1]))
            else:
                altered["regions"].reverse()
            with self.subTest(mode=mode), patch.object(contract, "PATH_CONFIGURATION", altered), self.assertRaises(AssertionError):
                contract.restore_path_configuration_root(self.source)

    def test_infrastructure_actual_owners_and_delta_are_guarded(self):
        original_read=Path.read_text
        for relative in contract.INFRASTRUCTURE["actual_owner_ast_sha256"]:
            target=(contract.ROOT/relative).resolve()
            def read(path,*args,**kwargs):
                value=original_read(path,*args,**kwargs)
                return value+"\nunreviewed_infrastructure = None\n" if path.resolve()==target else value
            with self.subTest(owner=relative), patch.object(Path,"read_text",read), self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)
        for mode in ("edit","delete","duplicate","order"):
            altered=copy.deepcopy(contract.INFRASTRUCTURE)
            if mode=="edit": altered["regions"][0]["expected"][0]="unreviewed_infrastructure = None"
            elif mode=="delete": altered["regions"].pop()
            elif mode=="duplicate": altered["regions"].append(copy.deepcopy(altered["regions"][-1]))
            else: altered["regions"].reverse()
            with self.subTest(mode=mode), patch.object(contract,"INFRASTRUCTURE",altered), self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)

    def test_exact_partial_replays_remain_guarded_at_every_checkpoint(self):
        fixtures = (contract.REAL_PHOTO_WORKFLOWS, contract.PROVIDER_TRANSPORTS, contract.ACCOUNT_VISIBILITY, contract.TRAINING_PERSISTENCE_GRAPH, contract.INFRASTRUCTURE, contract.PATH_CONFIGURATION, contract.POSE_EXECUTION, contract.POSE_PLANNING, contract.AGENT_STATE, contract.CODEX_ENVIRONMENT, contract.PIPELINE_RUNTIME,
                    contract.PIPELINE_TASKS, contract.PIPELINE_STAGES,
                    contract.AGENT_PIPELINE, contract.PIPELINE_QUERIES,
                    contract.PIPELINE_EXECUTION, contract.PIPELINE_PERSISTENCE,
                    contract.PLC_CAPTURE, contract.PLC_OPERATIONS, contract.PLC_WORKSTATION)
        source = self.source
        for index, fixture in enumerate(fixtures):
            with self.subTest(checkpoint=index):
                restored = contract.restore_plc_domain_root(source)
                self.assertEqual(contract.digest(ast.parse(restored)),
                                 contract.PLC_WORKSTATION["parent_ast_sha256"])
                with self.assertRaises(AssertionError):
                    contract.restore_plc_domain_root(source + "\nunreviewed_owner = None\n")
            source = contract.restore_delta(source, fixture)

    def test_training_completion_actual_owner_and_delta_are_guarded(self):
        original_read=Path.read_text
        for relative in contract.TRAINING_PERSISTENCE_GRAPH['actual_owner_ast_sha256']:
            target=(contract.ROOT/relative).resolve()
            def read(path,*args,**kwargs):
                value=original_read(path,*args,**kwargs)
                return value+'\nunreviewed_completion = None\n' if path.resolve()==target else value
            with patch.object(Path,'read_text',read),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)
        for mode in ('edit','delete','duplicate','order'):
            altered=copy.deepcopy(contract.TRAINING_PERSISTENCE_GRAPH)
            if mode=='edit': altered['regions'][0]['expected'][0]='unreviewed_completion = None'
            elif mode=='delete': altered['regions'].pop()
            elif mode=='duplicate': altered['regions'].append(copy.deepcopy(altered['regions'][-1]))
            else: altered['regions'].reverse()
            with self.subTest(mode=mode),patch.object(contract,'TRAINING_PERSISTENCE_GRAPH',altered),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)

    def test_account_visibility_actual_owner_and_delta_are_guarded(self):
        original_read=Path.read_text
        for relative in contract.ACCOUNT_VISIBILITY['actual_owner_ast_sha256']:
            target=(contract.ROOT/relative).resolve()
            def read(path,*args,**kwargs):
                value=original_read(path,*args,**kwargs)
                return value+'\nunreviewed_visibility = None\n' if path.resolve()==target else value
            with patch.object(Path,'read_text',read),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)
        for mode in ('edit','delete','duplicate','order'):
            altered=copy.deepcopy(contract.ACCOUNT_VISIBILITY)
            if mode=='edit': altered['regions'][0]['expected'][0]='unreviewed_visibility = None'
            elif mode=='delete': altered['regions'].pop()
            elif mode=='duplicate': altered['regions'].append(copy.deepcopy(altered['regions'][-1]))
            else: altered['regions'].reverse()
            with self.subTest(mode=mode),patch.object(contract,'ACCOUNT_VISIBILITY',altered),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)
    def test_provider_transports_actual_owner_and_delta_are_guarded(self):
        self.check_new_factory_boundary('PROVIDER_TRANSPORTS')

    def test_real_photo_workflows_actual_owner_and_delta_are_guarded(self):
        self.check_new_factory_boundary('REAL_PHOTO_WORKFLOWS')

    def check_new_factory_boundary(self, name):
        fixture=getattr(contract,name)
        original_read=Path.read_text
        for relative in fixture['actual_owner_ast_sha256']:
            target=(contract.ROOT/relative).resolve()
            def read(path,*args,**kwargs):
                value=original_read(path,*args,**kwargs)
                return value+'\nunreviewed_factory = None\n' if path.resolve()==target else value
            with patch.object(Path,'read_text',read),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)
        for mode in ('edit','delete','duplicate','order'):
            altered=copy.deepcopy(fixture)
            if mode=='edit':altered['regions'][0]['expected'][0]='unreviewed_factory = None'
            elif mode=='delete':altered['regions'].pop()
            elif mode=='duplicate':altered['regions'].append(copy.deepcopy(altered['regions'][-1]))
            else:altered['regions'].reverse()
            with self.subTest(fixture=name,mode=mode),patch.object(contract,name,altered),self.assertRaises(AssertionError):
                contract.restore_infrastructure_root(self.source)

    def test_partial_replay_still_checks_the_actual_native_owner(self):
        source = contract.restore_delta(contract.restore_delta(contract.restore_pose_domain_root(self.source),
                    contract.CODEX_ENVIRONMENT), contract.PIPELINE_RUNTIME)
        target = (contract.ROOT / "local_inspection_service/pipeline/runtime_composition.py").resolve()
        original_read = Path.read_text
        def read(path, *args, **kwargs):
            value = original_read(path, *args, **kwargs)
            return value + "\nunreviewed_owner = None\n" if path.resolve() == target else value
        with patch.object(Path, "read_text", read), self.assertRaisesRegex(AssertionError, "Actual pipeline runtime"):
            contract.restore_plc_domain_root(source)

    def test_new_missing_duplicate_reordered_and_changed_root_nodes_fail(self):
        for mode in ("new", "missing", "duplicate", "reorder", "wrong-import", "wrong-owner"):
            tree = ast.parse(self.source)
            if mode == "new":
                tree.body.append(ast.parse("unreviewed_owner = None").body[0])
            elif mode == "missing":
                tree.body.pop()
            elif mode == "duplicate":
                tree.body.append(copy.deepcopy(tree.body[-1]))
            elif mode == "reorder":
                tree.body[-1], tree.body[-2] = tree.body[-2], tree.body[-1]
            elif mode == "wrong-import":
                node = next(node for node in tree.body if isinstance(node, ast.ImportFrom)
                            and node.module == "model_providers.configuration_composition")
                node.module = "model_providers.unreviewed_shadow"
            else:
                node = next(node for node in tree.body if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "_provider_configuration"
                                    for target in node.targets))
                node.value = ast.Name(id="unreviewed_provider_owner", ctx=ast.Load())
            with self.subTest(mode=mode), self.assertRaises(AssertionError):
                contract.restore_integrated_root(ast.unparse(tree))

    def test_fixture_region_edit_delete_duplicate_and_order_fail(self):
        for mode in ("edit", "delete", "duplicate", "order"):
            fixture = copy.deepcopy(contract.FIXTURE)
            regions = fixture["regions"]
            if mode == "edit":
                regions[0]["expected"][0] = "unreviewed_owner = None"
            elif mode == "delete":
                regions.pop()
            elif mode == "duplicate":
                regions.append(copy.deepcopy(regions[-1]))
            else:
                regions.reverse()
            with self.subTest(mode=mode), patch.object(contract, "FIXTURE", fixture), self.assertRaises(AssertionError):
                contract.restore_integrated_root(self.source)

    def test_route_and_shutdown_dependency_order_fail(self):
        route_tree = ast.parse(self.source)
        route = next(node for node in ast.walk(route_tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                     and isinstance(node.func.value, ast.Name) and node.func.value.id == "app"
                     and node.args and isinstance(node.args[0], ast.Constant))
        route.args[0].value = "/unreviewed-route"
        with self.assertRaises(AssertionError):
            contract.restore_integrated_root(ast.unparse(route_tree))
        shutdown_tree = ast.parse(self.source)
        shutdown = next(node for node in ast.walk(shutdown_tree) if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name) and node.func.id == "register_web_shutdown")
        steps = shutdown.args[1].elts
        steps[0], steps[1] = steps[1], steps[0]
        with self.assertRaises(AssertionError):
            contract.restore_integrated_root(ast.unparse(shutdown_tree))

    def test_actual_constructor_eager_repository_wrong_owner_and_shadow_import_fail(self):
        target = (contract.ROOT / "local_inspection_service/text_inspection/storage_composition.py").resolve()
        original_read = Path.read_text
        source = original_read(target)
        for before, after in [("runtime_repository=repository", "runtime_repository=repository()"),
                              ("guard=lambda: self.lock", "guard=lambda: other_owner.lock"),
                              ("TextRecordDependencies, TextRecordStore", "TextRecordDependencies, TextRecordStore as OtherStore")]:
            self.assertIn(before, source)
            changed = source.replace(before, after)
            def read(path, *args, **kwargs):
                return changed if path.resolve() == target else original_read(path, *args, **kwargs)
            with self.subTest(change=after), patch.object(Path, "read_text", read), self.assertRaises(AssertionError):
                contract.restore_business_root(self.source)


if __name__ == "__main__":
    unittest.main()

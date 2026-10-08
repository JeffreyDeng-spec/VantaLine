"""Catalog graph isolation, thread identity and actual application bindings."""
import ast
import asyncio
from contextvars import ContextVar
from pathlib import Path
import sys
import tempfile
import threading
from dataclasses import replace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smoke_trained_model_catalog import Fixture
from local_inspection_service.training.catalog_composition import (
    ModelCatalog, ModelRunFiles, ModelPipeline, ModelRegistry,
)
from local_inspection_service.training.model_catalog import TrainingAccessories, TrainingAccess
from local_inspection_service.training.task_lookup import LookupCache, LookupRows
from local_inspection_service.storage.artifacts.files import BusinessFiles


class CatalogCompositionContracts(unittest.TestCase):
    def build(self, fixture, user):
        files=BusinessFiles(runtime_provider=lambda: None)
        factory=Mock(side_effect=lambda path:object())
        graph=ModelCatalog(
            repository=fixture.repository, file_loader=lambda:fixture.file_loader,
            cache=LookupCache(fixture.get,fixture.put),
            rows=LookupRows(lambda rows:[row['raw_json'] for row in rows],lambda path:path.stem,
                lambda task, requested, row:requested==task['task_id']),
            config=fixture.config_load,
            runs=ModelRunFiles(lambda:[fixture.runs],lambda:(lambda name:fixture.root/(name+'.json')),
                fixture.read,lambda:fixture.output,lambda:(lambda path:fixture.root/path)),
            accessories=TrainingAccessories(lambda item:item['id'],lambda item:dict(item),
                lambda:fixture.uses_ocr,lambda:fixture.profiles),
            pipeline=ModelPipeline(fixture.pipeline_load,lambda task:task.get('name',''),lambda:(lambda method:method)),
            access=TrainingAccess(user.get,fixture.visible,lambda:fixture.audit),rules=fixture.rules,
            registry=ModelRegistry(lambda config:[],lambda:{},lambda:'none',lambda feature:None,lambda:factory),
            files=files,
        )
        return graph,files,factory

    def test_constructor_invokes_no_identity_repository_files_or_model_factory(self):
        fail=Mock(side_effect=AssertionError('constructor side effect'))
        ModelCatalog(repository=fail,file_loader=fail,cache=LookupCache(fail,fail),
            rows=LookupRows(fail,fail,fail),config=fail,
            runs=ModelRunFiles(fail,fail,fail,fail,fail),
            accessories=TrainingAccessories(fail,fail,fail,fail),
            pipeline=ModelPipeline(fail,fail,fail),access=TrainingAccess(fail,fail,fail),
            rules=fail,registry=ModelRegistry(fail,fail,fail,fail,fail),files=fail)
        fail.assert_not_called()

    def test_two_owners_same_run_id_separate_model_state_and_catalog_linkage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'a').mkdir();(root/'b').mkdir()
            user=ContextVar('catalog_user',default=None)
            first=Fixture(root/'a');second=Fixture(root/'b')
            for fixture,owner in [(first,'alice'),(second,'bob')]:
                run=fixture.run('same',task={'owner_user_id':owner});(run/'weights').mkdir();(run/'weights/best.pt').write_bytes(b'synthetic')
            a,af,am=self.build(first,user);b,bf,bm=self.build(second,user)
            self.assertIs(a.local.files,af);self.assertIs(a.catalog.business_files,af)
            self.assertIs(b.local.files,bf);self.assertIsNot(a.local.models,b.local.models)
            token=user.set({'id':'alice'})
            try:
                self.assertEqual(len(a.catalog.list_trained_model_specs()),1)
                self.assertEqual(b.catalog.list_trained_model_specs(),[])
                one=a.local.model('trained_same__yolo')
                token_b=user.set({'id':'bob'})
                try: two=b.local.model('trained_same__yolo')
                finally:user.reset(token_b)
                self.assertIsNot(one,two);self.assertIs(a.local.model('trained_same__yolo'),one)
                task={'training_task_id':'same'}
                self.assertEqual(a.pipeline_link.link_pipeline_trained_model(task)['owner_user_id'],'alice')
                self.assertEqual(task['ai_model_id'],'trained_same__yolo')
                self.assertEqual((am.call_count,bm.call_count),(1,1))
            finally:user.reset(token)

    def test_async_thread_entry_uses_each_call_identity_and_connection_factory(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture=Fixture(Path(temporary));user=ContextVar('thread_catalog_user',default=None)
            fixture.run(task={'owner_user_id':'alice'})
            graph,_,_=self.build(fixture,user)
            async def query(owner):
                token=user.set({'id':owner})
                try:
                    result=await asyncio.to_thread(graph.catalog.list_trained_model_specs)
                    finder=await asyncio.to_thread(graph.lookup.training_task_finder)
                    return result,finder
                finally:user.reset(token)
            async def together():return await asyncio.gather(query('alice'),query('bob'))
            a,b=asyncio.run(together())
            self.assertEqual(len(a[0]),1);self.assertEqual(b[0],[])
            self.assertIs(a[1],fixture.file_loader);self.assertIs(b[1],fixture.file_loader)
            self.assertEqual(fixture.repository.call_count,4)
            self.assertIsNone(user.get())

    def test_thread_bound_repository_finder_is_created_and_consumed_in_same_thread(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'a').mkdir();(root/'b').mkdir()
            fixtures={name:Fixture(root/path) for name,path in [('alice','a'),('bob','b')]}
            user=ContextVar('bound_repository_user',default=None);events=[];failures={'alice':True}
            graphs={name:self.build(fixture,user)[0] for name,fixture in fixtures.items()}
            for name,fixture in fixtures.items():
                def repository(_owner=name):
                    owner=user.get()['id'];thread=threading.get_ident()
                    self.assertEqual(owner,_owner);events.append(('factory',owner,thread))
                    class ThreadBoundRepository:
                        def fetch_all(inner,table):
                            self.assertEqual(threading.get_ident(),thread)
                            self.assertEqual(user.get()['id'],owner)
                            self.assertEqual(table,'training_tasks');events.append(('fetch',owner,thread))
                            if failures.get(owner):raise RuntimeError('synthetic owner fetch failure')
                            return [{'raw_json':{'task_id':'shared','owner_user_id':owner}}]
                    return ThreadBoundRepository()
                fixture.repository.side_effect=repository
                original=graphs[name].lookup.rows.decode
                def decode(rows,_owner=name,_original=original):
                    self.assertEqual(user.get()['id'],_owner)
                    events.append(('decode',_owner,threading.get_ident()))
                    return _original(rows)
                graphs[name].lookup.rows=replace(graphs[name].lookup.rows,decode=decode)
            async def query(owner):
                token=user.set({'id':owner})
                try:
                    def consume():
                        finder=graphs[owner].lookup.training_task_finder()
                        return finder(Path('shared.json'))
                    try:return await asyncio.to_thread(consume)
                    except RuntimeError as error:return str(error)
                finally:user.reset(token)
            async def together():return await asyncio.gather(query('alice'),query('bob'))
            a,b=asyncio.run(together())
            self.assertEqual(a,'synthetic owner fetch failure');self.assertEqual(b['owner_user_id'],'bob')
            self.assertEqual(fixtures['alice'].cache,{})
            self.assertEqual([event[0] for event in events if event[1]=='alice'],['factory','fetch'])
            bob=[event for event in events if event[1]=='bob']
            self.assertEqual([event[0] for event in bob],['factory','fetch','decode'])
            self.assertEqual(len({event[2] for event in bob}),1)
            failures['alice']=False
            self.assertEqual(asyncio.run(query('alice'))['owner_user_id'],'alice')
            self.assertEqual(fixtures['bob'].repository.call_count,1)
            self.assertIsNone(user.get())

    def test_owned_catalog_replacement_reaches_selection_cache_listing_and_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture=Fixture(Path(temporary));graph,_,_=self.build(fixture,ContextVar('user',default=None))
            spec={'id':'selected','run_id':'run','path':fixture.root/'model.pt'}
            graph.local.paths['cached']=spec['path'].resolve()
            replacement=Mock(return_value=[spec])
            with patch.object(graph.catalog,'list_trained_model_specs',replacement):
                self.assertIs(graph.selection.selected_model_spec('selected',{}),spec)
                self.assertIn('selected',graph.local.yolo_loaded_model_ids({}))
                self.assertIs(graph.pipeline_link.link_pipeline_trained_model({'training_task_id':'run'}),spec)
            self.assertEqual(replacement.call_count,3)

    def test_actual_entry_constructs_one_graph_and_exports_only_owned_compatibility_aliases(self):
        root=Path(__file__).resolve().parents[1]
        tree=ast.parse((root/'local_inspection_service/server.py').read_text(encoding='utf8'))
        assignments={node.targets[0].id:node.value for node in tree.body if isinstance(node,ast.Assign)
            and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)}
        assembly=assignments['_model_catalog']
        self.assertEqual(ast.unparse(assembly.func),'ModelCatalog')
        self.assertEqual(ast.unparse(next(k.value for k in assembly.keywords if k.arg=='files')),'_business_files')
        for alias,attribute in {'_training_task_lookup':'lookup','_training_links':'links',
                '_trained_model_catalog':'catalog','_model_selection':'selection',
                '_local_models':'local','_pipeline_trained_model_link':'pipeline_link'}.items():
            self.assertEqual(ast.unparse(assignments[alias]),'_model_catalog.'+attribute)
        source=(root/'local_inspection_service/training/catalog_composition.py').read_text()
        own=ast.parse(source)
        self.assertFalse(any(isinstance(n,ast.ImportFrom) and 'server' in (n.module or '') for n in ast.walk(own)))
        for name in ['training_task_finder','pipeline_task_link_for_training_run','list_trained_model_specs','selected_model_spec']:
            self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==name for n in ast.walk(own)))


if __name__=='__main__':unittest.main()

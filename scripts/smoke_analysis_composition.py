"""Composed analysis services with preserved repository and projection contracts."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import fields
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from fastapi import HTTPException
from local_inspection_service.analytics.analysis_composition import AnalysisServices, AnalysisStorage
from local_inspection_service.analytics.analysis_records import AnalysisNormalization
from local_inspection_service.analytics.analysis_service import AnalysisAccess
from local_inspection_service.analytics.analysis_processing import ProcessingDependencies, image_processing_summary
from local_inspection_service.analytics.analysis_scope import ScopeDependencies
from local_inspection_service.analytics.analysis_projection import ProjectionDependencies
from local_inspection_service.analytics.analysis_publication import PublicationDependencies
from local_inspection_service.analytics.analysis_queries import AnalysisQueries, AnalysisPresentation
import smoke_analysis_records as records_contract
import smoke_analysis_projections as projection_contract


def poison_graph(**overrides):
    fail=Mock(side_effect=AssertionError('unexpected external operation'))
    def port(kind):
        return kind(**{f.name: ('default' if f.name in {'default_task_id','default_task_label'} else fail) for f in fields(kind)})
    values=dict(normalization=port(AnalysisNormalization),storage=port(AnalysisStorage),
        access=port(AnalysisAccess),processing=port(ProcessingDependencies),scope=port(ScopeDependencies),
        projection=port(ProjectionDependencies),publication=port(PublicationDependencies),cache_scope=fail,batch_limit=17)
    values.update(overrides)
    graph=AnalysisServices(**values)
    return graph,fail


class ExistingProjectionContracts(projection_contract.AnalysisProjectionTests):
    """Keep every old projection/publication assertion; replace only assembly."""
    def setUp(self):
        super().setUp()
        def allowed(record,user,*,write=False):
            if not user.get('admin') and record['owner_user_id']!=user['id']:
                raise HTTPException(403,'denied')
        self.cache_events=[]
        @contextmanager
        def cache_scope():
            self.cache_events.append('enter')
            try:
                yield
            finally:
                self.cache_events.append('exit')
        self.graph=AnalysisServices(
            normalization=self.repository.normalize.__self__.dependencies,
            storage=AnalysisStorage(self.repository.dependencies.path,self.repository.dependencies.runtime_repository,self.repository.dependencies.ensure_dirs),
            access=AnalysisAccess(lambda user:bool(user.get('admin')),
                lambda record,user,target: ((not target or record['owner_user_id']==target) if user.get('admin') else record['owner_user_id']==user['id']),allowed),
            processing=self.processing.dependencies,scope=self.scope.dependencies,projection=self.views.dependencies,
            publication=self.publisher.dependencies,cache_scope=cache_scope,batch_limit=17)
        self.processing,self.scope,self.views,self.publisher,self.repository=(self.graph.processing,self.graph.scope,self.graph.projection,self.graph.publisher,self.graph.repository)

    def test_queries_preserve_legacy_presentation_and_cache_cleanup(self):
        self.repository.save_data_analysis_records([records_contract.seed('a',timestamp=2),records_contract.seed('b',owner='bob')])
        legacy=AnalysisQueries(self.graph.records,AnalysisPresentation(
            self.graph.queries.presentation.cache_scope,
            lambda record,**kwargs:self.processing.data_analysis_image_processing_items(record,**kwargs),
            lambda record,**kwargs:self.views.public_data_analysis_record(record,**kwargs),
            lambda records,**kwargs:self.views.data_analysis_task_groups(records,**kwargs),
            lambda items:image_processing_summary(items)),batch_limit=17)
        for user in ({'id':'alice'},{'id':'bob'},{'id':'admin','admin':True}):
            for query in ({},{'offset':1,'limit':1},{'task_id':'absent'}):
                self.assertEqual(self.graph.queries.list_records(user,**query),legacy.list_records(user,**query))
        self.assertEqual(self.graph.queries.get_record({'id':'alice'},'a'),legacy.get_record({'id':'alice'},'a'))
        with self.assertRaises(HTTPException) as caught:
            self.graph.queries.get_record({'id':'bob'},'a')
        self.assertEqual(caught.exception.status_code,403)
        self.assertEqual(self.cache_events.count('enter'),self.cache_events.count('exit'))
        failure=RuntimeError('projection failure')
        # Direct presentation methods are retained, while their external ports
        # still belong to the selected domain instance and resolve per operation.
        with patch.object(self.views,'dependencies',Mock(created_at=Mock(side_effect=failure))):
            with self.assertRaises(RuntimeError) as caught:
                self.graph.queries.get_record({'id':'alice'},'a')
        self.assertIs(caught.exception,failure)
        self.assertEqual(self.cache_events[-2:],['enter','exit'])


class Composition(unittest.TestCase):
    def test_ownership_and_no_constructor_operations(self):
        a,fail=poison_graph()
        b,other=poison_graph()
        self.assertFalse(fail.called);self.assertFalse(other.called)
        self.assertIs(a.repository.dependencies.lock(),a.lock)
        self.assertIs(a.repository.normalize.__self__,a.normalizer)
        self.assertIs(a.records.repository,a.repository)
        self.assertIs(a.projection.processing,a.processing)
        self.assertIs(a.projection.scope,a.scope)
        self.assertIs(a.publisher.repository,a.repository)
        self.assertIs(a.publisher.processing,a.processing)
        self.assertIs(a.queries.records,a.records)
        for method,owner in ((a.queries.presentation.processing_items,a.processing),(a.queries.presentation.record,a.projection),(a.queries.presentation.task_groups,a.projection)):
            self.assertIs(method.__self__,owner)
        self.assertIs(a.queries.presentation.processing_summary,image_processing_summary)
        self.assertIsNot(a.lock,b.lock)
        with a.lock:
            self.assertTrue(a.lock.acquire(blocking=False));a.lock.release()
            with ThreadPoolExecutor(1) as pool:
                self.assertFalse(pool.submit(a.lock.acquire,False).result(timeout=5))
        self.assertIs(a.queries.presentation.cache_scope,fail)

    def test_original_json_repository_contract_through_composer(self):
        with patch.object(records_contract,'AnalysisRepository',composed_repository):
            records_contract.json_contract()

    def test_actual_root_graph_and_contract(self):
        from scripts import verify_backend_contract as contract
        snapshot=contract.capture()
        self.assertEqual(contract.encoded(snapshot),contract.BASELINE.read_text(encoding='utf-8'))
        from local_inspection_service import server
        graph=server._analysis
        for suffix,field in {'normalizer':'normalizer','repository':'repository','records':'records','queries':'queries','processing':'processing','scope':'scope','projection':'projection','publisher':'publisher'}.items():
            self.assertIs(getattr(server,'_analysis_'+suffix),getattr(graph,field))
        self.assertFalse(hasattr(server,'_data_analysis_store_lock'))
        for name,actual in (('data_analysis_image_processing_items',graph.queries.presentation.processing_items),
                            ('public_data_analysis_record',graph.queries.presentation.record),
                            ('data_analysis_task_groups',graph.queries.presentation.task_groups),
                            ('image_processing_summary',graph.queries.presentation.processing_summary)):
            self.assertEqual(getattr(server,name),actual)
            with patch.object(server,name,Mock(side_effect=AssertionError('root rebound'))):
                self.assertNotEqual(getattr(server,name),actual)
        failure=RuntimeError('live repository factory')
        with patch.object(server,'runtime_postgres_repository_or_none',Mock(side_effect=failure)):
            with self.assertRaises(RuntimeError) as caught:
                graph.repository.dependencies.runtime_repository()
        self.assertIs(caught.exception,failure)


def composed_repository(dependencies,normalize):
    graph,_=poison_graph(normalization=normalize.__self__.dependencies,
        storage=AnalysisStorage(dependencies.path,dependencies.runtime_repository,dependencies.ensure_dirs))
    return graph.repository


if __name__=='__main__':
    postgres='--postgres' in sys.argv
    if postgres:
        sys.argv.remove('--postgres')
    result=unittest.main(exit=False)
    if not result.result.wasSuccessful():
        sys.exit(1)
    if postgres:
        with patch.object(records_contract,'AnalysisRepository',composed_repository):
            records_contract.postgres_contract(os.environ['VANTALINE_POSTGRES_DSN'])
        print('PASS composed analysis real PostgreSQL access, row upserts and connection cleanup')

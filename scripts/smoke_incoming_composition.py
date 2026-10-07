"""Exercise the actual incoming workflow builder with independent HTTP graphs."""
import asyncio
import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI
from smoke_incoming_text_workflows import Fixture, picture
from local_inspection_service.storage.runtime_records import (
    incoming_text_reference_row, incoming_text_inspection_row, audit_event_row, row_raw_json_list,
)
from local_inspection_service.text_inspection.incoming_composition import IncomingWorkflows
from local_inspection_service.text_inspection.incoming_ports import IncomingOCR, IncomingImaging
from local_inspection_service.text_inspection.incoming_store import IncomingRows
from local_inspection_service.text_inspection.storage_composition import TextStorage, TextStoragePaths, TextStorageJSON


def compose(fixture):
    storage = TextStorage(
        repository=lambda: fixture.repository,
        paths=TextStoragePaths(lambda: fixture.root/'records', fixture.paths),
        rows=IncomingRows(incoming_text_reference_row, incoming_text_inspection_row, audit_event_row, lambda: row_raw_json_list),
        json_io=TextStorageJSON(lambda: lambda path: fixture.state[path.stem], lambda: fixture.write),
        tables=lambda: {},
    )
    graph = IncomingWorkflows(
        storage=storage, access=fixture.access, tasks=fixture.tasks, media=fixture.media,
        ocr=IncomingOCR(lambda image: fixture.observe(image), lambda *args: fixture.corroborate(*args), lambda: fixture.field),
        imaging=IncomingImaging(lambda image: fixture.quality(image), lambda: fixture.rectify,
                               lambda: fixture.similarity, lambda: fixture.annotate),
        files=fixture.files, images=fixture.images,
        public=fixture.catalog.public, verified=lambda: False,
        decode_rows=lambda: row_raw_json_list, capacity=lambda: fixture.capacity,
        audit=lambda: fixture.audit, system_owner=lambda: 'system',
    )
    return storage, graph


class CompositionContracts(unittest.TestCase):
    def test_constructor_does_not_read_storage_or_identity_and_writers_share_lock(self):
        fixture=Fixture(self)
        storage, graph=compose(fixture)
        forbidden=Mock(side_effect=AssertionError('eager dependency'))
        with patch.object(storage.incoming, 'repository', forbidden), patch.object(storage.incoming, 'read_json', forbidden):
            other=IncomingWorkflows(storage=storage, access=replace(fixture.access, user=forbidden),
                tasks=fixture.tasks, media=fixture.media, ocr=graph.execution.ocr,
                imaging=graph.execution.imaging, files=fixture.files, images=fixture.images,
                public=forbidden, verified=forbidden, decode_rows=forbidden,
                capacity=forbidden, audit=forbidden, system_owner=forbidden)
        forbidden.assert_not_called()
        for service in (other.catalog, other.reviews, other.retention):
            self.assertIs(service.writes.guard(), storage.lock)
            self.assertIs(service.files, fixture.files)
        self.assertIs(other.execution.images, fixture.images)
        self.assertIs(other.catalog.images, fixture.images)

    def test_duplicate_entry_points_share_query_and_original_missing_row_decode_order(self):
        fixture=Fixture(self); storage, graph=compose(fixture)
        repository=Mock()
        record={'id':'same','owner_user_id':'alice','task_id':'task','capture_id':'capture'}
        repository.fetch_one_by_columns.return_value={'raw_json':record}
        fixture.repository=repository
        for lookup in (graph.inspections.duplicate, graph.reviews.duplicate):
            repository.reset_mock()
            self.assertEqual(lookup('alice','task','capture'), record)
            repository.fetch_one_by_columns.assert_called_once_with('incoming_text_inspections',
                {'owner_user_id':'alice','task_id':'task','capture_id':'capture'})
        repository.fetch_one_by_columns.return_value=None
        with patch.object(graph.reviews, 'decode_rows', side_effect=AssertionError('decode absent row')):
            self.assertIsNone(graph.reviews.duplicate('alice','task','capture'))
        repository.fetch_one_by_columns.side_effect=RuntimeError('query failed')
        with self.assertRaisesRegex(RuntimeError,'query failed'):
            graph.inspections.duplicate('alice','task','capture')

    def test_two_builder_http_apps_keep_same_ids_owner_and_duplicate_records_separate(self):
        fixtures=[Fixture(self),Fixture(self)]
        graphs=[]; apps=[]
        for fixture, owner in zip(fixtures, ('alice','bob')):
            fixture.task_records[0]['owner_user_id']=owner
            storage,graph=compose(fixture);graphs.append(graph)
            fixture.state['inspections']=[dict(id='same', owner_user_id=owner, task_id='task', capture_id='capture.same', source_sha256=hashlib.sha256(picture()).hexdigest())]
            app=FastAPI()
            graph.register_catalog(app)
            graph.register_inspections(app)
            apps.append(app)
        async def exercise(index, owner):
            fixture=fixtures[index];token=fixture.context.set(owner)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=apps[index]),base_url='http://fixture') as client:
                    response=await client.post('/api/incoming-text/tasks/task/references',
                        data={'version_label':'same'},files={'file':('same.png',picture(),'image/png')})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['owner_user_id'],owner)
                    response=await client.get('/api/incoming-text/tasks/task')
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['references'][0]['owner_user_id'],owner)
                    response=await client.post('/api/incoming-text/tasks/task/inspect',
                        data={'capture_id':'capture.same'},files={'file':('same.png',picture(),'image/png')})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['id'],'same')
                    self.assertEqual(response.json()['owner_user_id'],owner)
                    response=await client.post('/api/incoming-text/tasks/task/inspect',
                        data={'capture_id':'capture.same'},files={'file':('different.png',b'different','image/png')})
                    self.assertEqual(response.status_code,409,response.text)
                    fixture.capacity.assert_not_called()
                    fixture.observe.assert_not_called()
                    fixture.corroborate.assert_not_called()
                self.assertEqual(graphs[index].inspections.duplicate(owner,'task','capture.same')['owner_user_id'],owner)
                self.assertIsNone(graphs[index].reviews.duplicate('bob' if owner=='alice' else 'alice','task','capture.same'))
            finally:fixture.context.reset(token)
        async def both():await asyncio.gather(exercise(0,'alice'),exercise(1,'bob'))
        asyncio.run(both())
        with patch.object(graphs[0].storage.incoming,'read_json',side_effect=OSError('A unavailable')):
            with self.assertRaisesRegex(OSError,'A unavailable'):graphs[0].inspections.duplicate('alice','task','capture.same')
            self.assertEqual(graphs[1].inspections.duplicate('bob','task','capture.same')['owner_user_id'],'bob')
        self.assertIsNot(graphs[0].writes.guard(),graphs[1].writes.guard())

    def test_reviews_selects_decoder_and_list_after_repository_callback(self):
        fixture=Fixture(self);storage,graph=compose(fixture)
        marker={'id':'new','owner_user_id':'alice','task_id':'task','capture_id':'capture'}
        def json_repository():
            graph.reviews.inspections=replace(graph.inspections,all=lambda:[marker])
            return None
        graph.reviews.writes=replace(graph.writes,repository=json_repository)
        self.assertIs(graph.reviews.duplicate('alice','task','capture'),marker)
        repository=Mock();repository.fetch_one_by_columns.return_value={'unparsed':'row'}
        decoded=Mock(return_value=[marker])
        def sql_repository():
            graph.reviews.decode_rows=lambda:decoded
            return repository
        graph.reviews.decode_rows=Mock(side_effect=AssertionError('old decoder'))
        graph.reviews.writes=replace(graph.writes,repository=sql_repository)
        self.assertIs(graph.reviews.duplicate('alice','task','capture'),marker)
        decoded.assert_called_once_with([{'unparsed':'row'}])

    def test_storage_method_replacement_is_selected_after_repository_callback(self):
        fixture=Fixture(self);storage,graph=compose(fixture)
        marker={'id':'replacement','owner_user_id':'alice','task_id':'task','capture_id':'capture'}
        original=storage.incoming.load_incoming_text_inspections
        calls=[]
        def repository():
            calls.append(threading.get_ident())
            storage.incoming.load_incoming_text_inspections=lambda:[marker]
            return None
        with patch.object(storage.incoming,'repository',repository):
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    result=pool.submit(graph.inspections.duplicate,'alice','task','capture').result(timeout=5)
                self.assertIs(result,marker)
                self.assertEqual(len(calls),1)
                self.assertNotEqual(calls[0],threading.get_ident())
            finally:storage.incoming.load_incoming_text_inspections=original


    def test_owned_response_files_selected_only_after_actual_http_authorization(self):
        fixture=Fixture(self);storage,graph=compose(fixture)
        path=fixture.root/'evidence.png';path.write_bytes(picture())
        fixture.state['references']=[dict(id='reference',task_id='task',owner_user_id='alice',source_path=str(path))]
        fixture.state['inspections']=[dict(id='inspection',task_id='task',owner_user_id='alice',source_path=str(path))]
        response_files=Mock()
        response_files.runtime.side_effect=AssertionError('registration resolved storage')
        graph.files=response_files
        app=FastAPI();graph.register_catalog(app);graph.register_inspections(app)
        response_files.runtime.assert_not_called()
        response_files.runtime.side_effect=None;response_files.runtime.return_value=None
        urls=['/api/incoming-text/references/reference/asset/source',
              '/api/incoming-text/inspections/inspection/evidence/source']
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
                token=fixture.context.set('bob')
                try:
                    for url in urls:
                        response=await client.get(url)
                        self.assertEqual(response.status_code,403,response.text)
                    response_files.runtime.assert_not_called()
                finally:fixture.context.reset(token)
                for url in urls:
                    response=await client.get(url)
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.content,picture())
        asyncio.run(exercise())
        self.assertEqual(response_files.runtime.call_count,2)
        for call in response_files.runtime.call_args_list:self.assertEqual(call.args,(path,))


if __name__=='__main__':unittest.main()

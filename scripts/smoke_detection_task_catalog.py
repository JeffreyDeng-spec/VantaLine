"""Synthetic detection task projections and model catalog behavior contracts."""
from contextlib import ExitStack
import asyncio
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def task(identifier='task', owner='alice', **values):
    return dict(id=identifier,name=' Task ',selected_accessory_ids=['a'],required_accessory_counts={'a':2},
                owner_user_id=owner,owner_username=owner,created_at=10,updated_at=20,**values)


def trained(identifier='trained', owner='alice', **values):
    return dict(id='trained-model:'+identifier,task_id=identifier,run_id='run:'+identifier,
                selected_accessory_ids=['a'],required_accessory_counts={'a':3},owner_user_id=owner,**values)


class Fixture:
    def __init__(self):
        self.config={'accessories':[{'id':'a','name':'Current A'},{'id':'b','name':'Current B'}]}
        self.tasks=[]; self.trained=[]; self.events=[]
        self.load_config=Mock(side_effect=lambda:self.config)
        self.load_tasks=Mock(side_effect=lambda:self.tasks)
        self.load_trained=Mock(side_effect=lambda *args:self.trained)
        self.background=Mock(return_value=('',{}))
        self.sanitize=Mock(side_effect=lambda value:{'safe':value['value']})
        self.audit=Mock(side_effect=lambda value:{k:value.get(k,0 if k.endswith('_at') else '')
                            for k in ('created_at','updated_at','owner_user_id','owner_username')})
        self.base={'id':'base','engine':{'version':'fixture'},'label':'base-label'}
        self.owner_name=Mock(return_value='legacy-name')
    def visible(self,record,user,target=None):
        self.events.append((record.get('id'),user['id'],target))
        return record.get('owner_user_id')==user['id'] and (target is None or target==record.get('owner_user_id'))
    def bind(self,api,stack):
        values={'load_config':self.load_config,'load_ai_detection_tasks':self.load_tasks,
                'list_trained_model_specs':self.load_trained,'ai_detection_task_background_record':self.background,
                'public_path_sanitized':self.sanitize,'record_audit_fields':self.audit,
                'accessory_lookup_by_id':lambda config:{item['id']:item for item in config.get('accessories',[])},
                'record_visible_to_user':self.visible,'record_owner_username':self.owner_name,
                'accessory_uid':lambda item:item.get('id') or 'generated','serialize_accessory':lambda item:item,
                'MODEL_REGISTRY':{'base':self.base},'AI_DETECTION_MODEL_ID':'base','AI_DETECTION_LABEL':'AI label',
                'AI_DETECTION_TASK_PREFIX':'task:','LEGACY_OWNER_ID':'legacy','AI_DETECTION_TASKS_PATH':Path('fixture-tasks.json')}
        for name,value in values.items():stack.enter_context(patch.object(api,name,value))


class CatalogContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='detection-catalog-root-')
        root=Path(cls.temp.name); (root/'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root),VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close); self.f=Fixture(); self.f.bind(self.api,self.stack)
        token=self.api._request_user.set(None); self.addCleanup(self.api._request_user.reset,token)
    def test_projection_labels_duplicates_audit_background_and_no_mutation(self):
        f=self.f;api=self.api;value=task(' A! ');value.update(name='',selected_accessory_ids=['a','missing','a','filtered'],
            required_accessory_counts={'a':101,'missing':'bad'},accessory_labels={'a':'old','missing':' Saved '})
        before=copy.deepcopy(value); f.background.return_value=('blue',{'value':'visible','internal':'private'})
        result=api.serialize_ai_detection_task(value,f.config)
        self.assertEqual(result['id'],'a'); self.assertEqual(result['model_id'],'task:a')
        self.assertEqual(result['selected_accessory_ids'],['a','missing','a']);self.assertEqual(result['accessory_count'],3)
        self.assertEqual(result['accessory_names'],['Current A',' Saved ','Current A'])
        self.assertEqual(result['accessory_labels'],{'a':'Current A','missing':' Saved '})
        self.assertEqual(result['missing_accessory_ids'],['missing']); self.assertEqual(result['required_accessory_counts'],{'a':99,'missing':1})
        self.assertEqual(result['name'],'Current A +  Saved  + Current A')
        self.assertEqual(result['environment_background'],{'safe':'visible'});f.background.assert_called_once_with('a')
        self.assertEqual(value,before); f.audit.assert_called_once_with(value)
        value['selected_accessory_ids']=['invalid'];f.background.return_value=('',{})
        result=api.serialize_ai_detection_task(value,f.config);self.assertEqual(result['selected_accessory_ids'],['a','missing'])
        self.assertNotIn('environment_background',result);self.assertEqual(result['owner_user_id'],'alice')
    def test_request_merge_order_normalization_and_validation_errors(self):
        api=self.api; f=self.f
        request=api.AiDetectionTaskRequest(name='  ',required_accessory_counts={'a':3,'b':0},
                                        accessories=[{'accessory_id':'a','required_count':5},{'accessory_id':'b','required_count':101}])
        lookup=lambda config:{item['id']:item for item in config.get('accessories',[])}
        with patch.object(api,'accessory_lookup_by_id',side_effect=lookup) as lookup_call:
            result=api.ai_detection_task_payload_from_request(request,f.config)
            lookup_call.assert_called_once_with(f.config)
        self.assertEqual(result,{'name':'Current A + Current B','selected_accessory_ids':['a','b'],
            'required_accessory_counts':{'a':5,'b':99},'accessory_labels':{'a':'Current A','b':'Current B'},'source':'ai_detection_workbench'})
        for request,detail in [(api.AiDetectionTaskRequest(), 'AI detection task requires at least one accessory'),
                (api.AiDetectionTaskRequest(required_accessory_counts={'z':1,'x':2}), "Unknown accessory IDs: ['z', 'x']")]:
            empty=not request.required_accessory_counts
            with patch.object(api,'accessory_lookup_by_id',side_effect=RuntimeError('lookup before empty validation') if empty else lookup) as lookup_call:
                with self.assertRaises(api.HTTPException) as error: api.ai_detection_task_payload_from_request(request,f.config)
                if empty: lookup_call.assert_not_called()
                else: lookup_call.assert_called_once_with(f.config)
            self.assertEqual(error.exception.status_code,400);self.assertEqual(error.exception.detail,detail)
        f.audit.assert_not_called();f.background.assert_not_called()
    def test_native_specs_visibility_lazy_registry_and_aliases(self):
        api=self.api;f=self.f;invalid=task('');empty=task('empty');empty['required_accessory_counts']={}
        f.tasks=[task('alice'),task('bob','bob'),invalid,empty]
        api._request_user.set({'id':'alice'})
        values=api.list_ai_detection_task_model_specs({},'alice')
        self.assertEqual([v['task_id'] for v in values],['alice']);self.assertEqual(len(f.events),4)
        value=values[0];self.assertEqual(value['label'],'AI label');self.assertEqual(value['metadata_path'],'fixture-tasks.json')
        self.assertEqual(value['task_source'],'ai_detection_task_config');self.assertIs(value['engine'],f.base['engine'])
        self.assertEqual(value['artifact_path'],''); f.load_config.assert_called_once_with()
        api._request_user.set(None);f.events=[]
        self.assertEqual([v['task_id'] for v in api.list_ai_detection_task_model_specs(f.config,'bob')],['alice','bob'])
        self.assertEqual(f.events,[])
        with patch.object(api,'AI_DETECTION_LABEL','new label'),patch.object(api,'AI_DETECTION_TASK_PREFIX','new:'):
            value=api.list_ai_detection_task_model_specs(f.config)[0]
            self.assertEqual(value['label'],'new label');self.assertEqual(value['id'],'new:alice')
    def test_specialized_merges_preserve_native_precedence_and_eager_defaults(self):
        api=self.api;f=self.f;f.tasks=[task('native')]
        first=trained('native');first.update(selected_accessory_ids=['a','b','missing'],required_accessory_counts={'a':150,'b':0,'missing':4},accessory_labels={'missing':'saved'})
        second=trained('native');second.update(selected_accessory_ids=['b'],required_accessory_counts={'b':8})
        other=trained('other');other.update(selected_accessory_ids=['missing'],required_accessory_counts={},accessory_labels={'missing':'Saved other'})
        values=api.list_ai_detection_specialized_model_specs(f.config,[first,second,other])
        self.assertEqual([v['task_id'] for v in values],['native','other'])
        native,other_value=values
        self.assertEqual(native['required_accessory_counts'],{'a':150,'b':8,'missing':4})
        self.assertEqual(native['selected_accessory_ids'],['a','b','missing'])
        self.assertEqual(native['accessory_names'],['Current A','Current B','missing'])
        self.assertEqual(native['accessory_labels'],{'a':'Current A'});self.assertEqual(native['task_source'],'ai_detection_task_config')
        self.assertEqual(native['run_id'],'native');self.assertEqual(native['task_label'],'Task')
        self.assertEqual(other_value['accessory_names'],['Saved other']);self.assertEqual(other_value['required_accessory_counts'],{'missing':1})
        self.assertEqual(f.owner_name.call_count,3);f.load_trained.assert_not_called()
        # Even a pre-existing native task evaluates the full setdefault fallback.
        with patch.object(api,'record_owner_username',side_effect=RuntimeError('eager owner')):
            with self.assertRaisesRegex(RuntimeError,'eager owner'):api.list_ai_detection_specialized_model_specs(f.config,[first])
        bad=trained('native');bad['required_accessory_counts']={'a':'bad'}
        with self.assertRaises(ValueError):api.list_ai_detection_specialized_model_specs(f.config,[bad])
    def test_specialized_none_empty_config_and_skip_rules(self):
        api=self.api;f=self.f;f.trained=[trained('other')]
        result=api.list_ai_detection_specialized_model_specs(None,None);self.assertEqual(len(result),1)
        f.load_trained.assert_called_once_with();self.assertEqual(f.load_config.call_count,1)
        f.load_trained.reset_mock();f.load_config.reset_mock()
        self.assertEqual(api.list_ai_detection_specialized_model_specs(f.config,[]),[])
        f.load_trained.assert_not_called();f.load_config.assert_not_called()
        empty=trained('empty');empty['selected_accessory_ids']=[]
        no_id=trained('');no_id['run_id']=''
        self.assertEqual(api.list_ai_detection_specialized_model_specs(f.config,[empty,no_id]),[])
        spaced=trained(' spaced '); result=api.list_ai_detection_specialized_model_specs(f.config,[spaced])
        self.assertEqual(result[0]['task_id'],' spaced ');self.assertEqual(result[0]['id'],'task: spaced ')
    def test_response_filters_deduplicates_and_preserves_selected_id(self):
        api=self.api;f=self.f;f.tasks=[task('native'),task('private','bob')]
        f.trained=[trained('native'),trained('train'),trained('private-training','bob'),trained('train')]
        api._request_user.set({'id':'alice'})
        result=api.ai_detection_tasks_response(f.config,target_user_id='alice')
        self.assertEqual([r['id'] for r in result['tasks']],['native','train']);self.assertEqual(result['selected_task_id'],'native')
        self.assertEqual(result['tasks'][0]['required_accessory_counts'],{'a':2})
        self.assertEqual(result['tasks'][1]['task_type'],'trained_model_ai')
        self.assertEqual(result['tasks'][1]['model_id'],'task:train');self.assertEqual(result['tasks'][1]['owner_username'],'legacy-name')
        self.assertEqual(api.ai_detection_tasks_response(f.config,selected_id='missing')['selected_task_id'],'missing')
        f.tasks=[];f.trained=[];self.assertEqual(api.ai_detection_tasks_response(f.config),{'tasks':[],'selected_task_id':''})
        # Explicit user controls outer list filtering, while native spec discovery still
        # reads the request ContextVar; preserve the original precedence.
        f.tasks=[task('native'),task('bob','bob')]
        result=api.ai_detection_tasks_response(f.config,user={'id':'bob'})
        self.assertEqual([v['id'] for v in result['tasks']],['bob','native'])
    def test_failure_order_distinct_accessory_indexes_and_partial_merge(self):
        api=self.api;f=self.f
        bad=task();bad['required_accessory_counts']=['invalid']
        with patch.object(api,'accessory_lookup_by_id') as lookup:
            with self.assertRaises(AttributeError):api.serialize_ai_detection_task(bad,f.config)
            f.audit.assert_called_once_with(bad);lookup.assert_not_called();f.background.assert_not_called()
        f.audit.return_value={};f.audit.side_effect=None
        with patch.object(api,'ai_detection_task_model_id',return_value='model') as model_id:
            with self.assertRaises(KeyError):api.serialize_ai_detection_task(task(),f.config)
            model_id.assert_called_once_with('task');f.background.assert_not_called()
        f.audit.side_effect=lambda value:{k:value.get(k,0) for k in ('created_at','updated_at','owner_user_id','owner_username')}
        first={'id':'a','name':'first'};last={'id':'a','name':'last'};config={'accessories':[first,last]}
        with patch.object(api,'accessory_lookup_by_id',return_value={'a':first,'legacy':first}):
            value=task();value.update(selected_accessory_ids=['legacy'],required_accessory_counts={'legacy':1})
            self.assertEqual(api.serialize_ai_detection_task(value,config)['accessory_names'],['first'])
            self.assertEqual(api.list_ai_detection_specialized_model_specs(config,[trained()])[0]['accessory_names'],['last'])
        native={'task_id':'same','selected_accessory_ids':['a'],'accessory_names':['A'],
                'required_accessory_counts':{'a':1},'accessory_labels':{'a':'A'}}
        update=trained('same');update.update(selected_accessory_ids=['b'],required_accessory_counts={'b':4,'unselected':5})
        invalid=trained('same');invalid['required_accessory_counts']={'a':'bad'}
        with patch.object(api._detection_task_catalog,'list_ai_detection_task_model_specs',return_value=[native]):
            with self.assertRaises(ValueError):api.list_ai_detection_specialized_model_specs(f.config,[update,invalid])
        self.assertEqual(native['selected_accessory_ids'],['a','b'])
        self.assertEqual(native['required_accessory_counts'],{'a':1,'b':4,'unselected':5})
        self.assertEqual(native['accessory_names'],['A','Current B']);self.assertEqual(native['accessory_labels'],{'a':'A'})

    def test_contextvar_identity_survives_concurrent_async_thread_handoffs(self):
        api=self.api;f=self.f;f.tasks=[task('alice'),task('bob','bob')]
        async def check():
            async def actor(user):
                token=api._request_user.set({'id':user})
                try:
                    await asyncio.sleep(0)
                    return await asyncio.to_thread(api.list_ai_detection_task_model_specs,f.config)
                finally:api._request_user.reset(token)
            return await asyncio.gather(actor('alice'),actor('bob'))
        first,second=asyncio.run(check())
        self.assertEqual([v['task_id'] for v in first],['alice']);self.assertEqual([v['task_id'] for v in second],['bob'])
        self.assertIsNone(api._request_user.get())


    def test_independent_services_and_late_root_projection(self):
        from local_inspection_service.detection.task_projection import TaskProjection
        from local_inspection_service.detection.task_catalog import TaskCatalog, TaskCatalogSources, TaskCatalogAccess, TaskModelRegistry
        def build(fixture,prefix):
            projection=TaskProjection(lambda config:{item['id']:item for item in config['accessories']},
                fixture.audit,fixture.background,fixture.sanitize,lambda value:prefix+value)
            catalog=TaskCatalog(TaskCatalogSources(fixture.load_config,fixture.load_tasks,fixture.load_trained,
                lambda item:item['id'],lambda item:item),
                TaskCatalogAccess(lambda:None,fixture.visible,fixture.owner_name),
                TaskModelRegistry(lambda:fixture.base,lambda:prefix,lambda:Path(prefix+'tasks.json'),lambda:'legacy',lambda value:prefix+value),
                projection.serialize_ai_detection_task)
            return projection,catalog
        first=self.f;second=Fixture();first.tasks=[task('first')];second.tasks=[task('second')]
        first_projection,first_catalog=build(first,'first:');second_projection,second_catalog=build(second,'second:')
        self.assertEqual(first_catalog.list_ai_detection_task_model_specs()[0]['id'],'first:first')
        self.assertEqual(second_catalog.list_ai_detection_task_model_specs()[0]['id'],'second:second')
        second.tasks[0]['name']='changed'
        self.assertEqual(first_projection.serialize_ai_detection_task(first.tasks[0],first.config)['name'],'Task')
        self.assertEqual(second_projection.serialize_ai_detection_task(second.tasks[0],second.config)['name'],'changed')
        original=self.api.serialize_ai_detection_task(task('root'),first.config)
        original['name']='late projection'
        with patch.object(self.api,'serialize_ai_detection_task',return_value=original) as project:
            self.assertEqual(self.api.list_ai_detection_task_model_specs(first.config)[0]['task_label'],'late projection')
            project.assert_called_once_with(first.tasks[0],first.config)


if __name__=='__main__': unittest.main()

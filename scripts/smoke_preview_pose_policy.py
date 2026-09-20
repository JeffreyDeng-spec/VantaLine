"""Offline contracts for accessory preview pose selection and composition."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch,call
sys.path.insert(0,str(Path.cwd()))
class PreviewPoseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='preview-pose-')))
        (cls.root/'local_inspection_service/static').mkdir(parents=True)
        for name in ('DATABASE_URL','VANTALINE_POSTGRES_DSN','PGDSN'):os.environ.pop(name,None)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(cls.root),VANTALINE_DATA_STORE='json',LOCAL_INSPECTION_AUTO_RESUME_WORKER='0',VANTALINE_LABEL_INSPECTION_ENABLED='false',YOLO_AUTOINSTALL='false')
        for name in ('requests.sessions.Session.request','urllib.request.urlopen','subprocess.Popen','os.kill'):
            cls.lifetime.enter_context(patch(name,side_effect=AssertionError('External operation forbidden')))
        from types import SimpleNamespace
        cls.import_factory=Mock(side_effect=AssertionError('Eager model load forbidden'));cls.import_remove=Mock(side_effect=AssertionError('Eager inference forbidden'))
        cls.lifetime.enter_context(patch.dict(sys.modules,{'rembg':SimpleNamespace(new_session=cls.import_factory,remove=cls.import_remove)}))
        from local_inspection_service import server
        cls.import_factory.assert_not_called();cls.import_remove.assert_not_called()
        cls.api=server
    @classmethod
    def tearDownClass(cls):cls.lifetime.close()
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
    def replace(self,name,**kwargs):return self.stack.enter_context(patch.object(self.api,name,**kwargs))
    def test_normalization_aliases(self):
        for value,expected in [(None,'auto'),('', 'auto'),(' DEFAULT ','auto'),('controlled','auto'),('flat','lying'),('SIDE-FACING','lying'),('lying_only','lying'),('top_view','upright'),('top-view','upright'),('upright_only','upright'),('auto','auto')]:self.assertEqual(self.api.normalize_preview_pose_family_policy(value),expected)
    def test_normalization_error_status_and_original_value(self):
        from fastapi import HTTPException
        for value in ('unknown',' Mixed ',123):
            with self.assertRaises(HTTPException) as seen:self.api.normalize_preview_pose_family_policy(value)
            self.assertEqual(seen.exception.status_code,400);self.assertEqual(seen.exception.detail,f'Unknown preview_pose_family_policy: {value}')
    def test_sprite_family_precedence_and_string_conversion(self):
        for asset,expected in [({},''),({'pose_family':'lying'},'lying'),({'source_pose_family':'top','pose_family':'lying'},'top'),({'source_pose_family':'','pose_family':'lying'},'lying'),({'source_pose_family':0,'pose_family':7},'7')]:self.assertEqual(self.api.sprite_pose_family(asset),expected)
    def test_available_families_double_calls_and_sorted_unique(self):
        item={};assets=[{}, {}, {}];clean=self.replace('clean_sprite_assets',return_value=assets);family=self.replace('sprite_pose_family',side_effect=['gate','z',None,'gate','a'])
        self.assertEqual(self.api.available_object_pose_families(item),['a','z']);self.assertEqual(family.call_count,5);clean.assert_called_once_with(item)
    def test_family_intersection_excludes_text_accessories(self):
        items=[{'kind':'object','families':['lying','upright']},{'kind':'text','families':['z']},{'kind':'object','families':['lying']}]
        self.replace('accessory_material_type',side_effect=lambda item:item['kind']);available=self.replace('available_object_pose_families',side_effect=lambda item:item['families'])
        self.assertEqual(self.api.preview_pose_families_for_policy(items,'auto'),['lying']);self.assertEqual(available.call_args_list,[call(items[0]),call(items[2])])
    def test_no_common_family_returns_none_before_alias_canonicalization(self):
        self.replace('accessory_material_type',return_value='object');self.replace('available_object_pose_families',side_effect=lambda item:item['families']);canonical=self.replace('canonical_pose_family_name',return_value='lying')
        self.assertIsNone(self.api.preview_pose_families_for_policy([],'auto'));self.assertIsNone(self.api.preview_pose_families_for_policy([{'families':['lying']},{'families':['flat']}],'auto'));canonical.assert_not_called()
    def test_lying_and_upright_order_preserves_first_exact_alias(self):
        self.replace('accessory_material_type',return_value='object');available=self.replace('available_object_pose_families',return_value=['side-facing','side','flat','lying','top-view','top','upright'])
        self.assertEqual(self.api.preview_pose_families_for_policy([{}],'lying'),['lying']);self.assertEqual(self.api.preview_pose_families_for_policy([{}],'upright'),['upright'])
        available.return_value=['side-facing','flat','top-view'];self.assertEqual(self.api.preview_pose_families_for_policy([{}],'lying'),['flat']);self.assertEqual(self.api.preview_pose_families_for_policy([{}],'upright'),['top-view'])
    def test_auto_deduplicates_canonical_families_and_keeps_first_alias(self):
        self.replace('accessory_material_type',return_value='object');self.replace('available_object_pose_families',return_value=['flat','side','top','z']);canonical=self.replace('canonical_pose_family_name',side_effect=lambda family:{'flat':'lying','side':'lying','top':'upright'}.get(family))
        self.assertEqual(self.api.preview_pose_families_for_policy([{}],'auto'),['flat','top']);self.assertEqual(canonical.call_args_list,[call('flat'),call('side'),call('top'),call('z')])
    def test_unknown_family_auto_sort_and_policy_mismatch_errors(self):
        from fastapi import HTTPException
        self.replace('accessory_material_type',return_value='object');self.replace('available_object_pose_families',return_value=['z','a']);self.replace('canonical_pose_family_name',return_value=None)
        self.assertEqual(self.api.preview_pose_families_for_policy([{}],'auto'),['a'])
        for policy in ('lying','upright'):
            with self.assertRaises(HTTPException) as seen:self.api.preview_pose_families_for_policy([{}],policy)
            self.assertEqual(seen.exception.status_code,400);self.assertEqual(seen.exception.detail,f'No clean sprites available for preview pose policy: {policy}')
    def test_single_family_projection_nullable_and_first_alias(self):
        many=self.replace('preview_pose_families_for_policy');items=[]
        for value,expected in [(None,None),([],None),(['flat','top'],'flat')]:many.return_value=value;self.assertEqual(self.api.preview_pose_family_for_policy(items,'x'),expected)
        self.assertEqual(many.call_args_list,[call(items,'x')]*3)
    def test_sequence_alternation_count_and_single_policy(self):
        normal=self.replace('normalize_preview_pose_family_policy',return_value='auto');many=self.replace('preview_pose_families_for_policy',return_value=['flat','top']);items=[]
        self.assertEqual(self.api.preview_pose_family_sequence(items,5,'DEFAULT'),['flat','top','flat','top','flat']);normal.assert_called_once_with('DEFAULT');many.assert_called_once_with(items,'auto')
        self.assertEqual(self.api.preview_pose_family_sequence(items,-2),[]);normal.return_value='lying';self.assertEqual(self.api.preview_pose_family_sequence(items,3,'flat'),['flat']*3)
    def test_sequence_missing_returns_none_entries_but_still_resolves_zero_count(self):
        normal=self.replace('normalize_preview_pose_family_policy',return_value='auto');many=self.replace('preview_pose_families_for_policy',return_value=None)
        self.assertEqual(self.api.preview_pose_family_sequence([],3),[None,None,None]);self.assertEqual(self.api.preview_pose_family_sequence([],0),[]);self.assertEqual(normal.call_count,2);self.assertEqual(many.call_count,2)
    def test_sequence_labels_canonical_order_and_fallback(self):
        canonical=self.replace('canonical_pose_family_name',side_effect=lambda value:{'flat':'lying','top':'upright'}.get(value))
        for values,expected in [(['top','flat'],'mixed'),(['flat','z'],'lying'),(['top'],'upright'),(['z'],'z'),([],None),([None],'None')]:self.assertEqual(self.api.preview_pose_family_sequence_label(values),expected)
        self.assertNotIn(call(None),canonical.call_args_list)
    def test_material_predicate_can_replace_next_available_callback(self):
        old=self.replace('available_object_pose_families',return_value=['wrong']);new=Mock(return_value=['lying'])
        def kind(item):self.api.available_object_pose_families=new;return 'object'
        material=self.replace('accessory_material_type',side_effect=kind);self.assertEqual(self.api.preview_pose_families_for_policy([{}],'lying'),['lying']);old.assert_not_called();new.assert_called_once_with({});material.assert_called_once_with({})
    def test_sequence_reselects_many_after_normalization(self):
        old=self.replace('preview_pose_families_for_policy',return_value=['wrong']);new=Mock(return_value=['flat','top'])
        def normalize(policy):self.api.preview_pose_families_for_policy=new;return 'auto'
        self.replace('normalize_preview_pose_family_policy',side_effect=normalize);self.assertEqual(self.api.preview_pose_family_sequence([],3,'x'),['flat','top','flat']);old.assert_not_called();new.assert_called_once_with([],'auto')
    def test_normalization_error_callee_precedes_second_string_conversion(self):
        from fastapi import HTTPException
        events=[];late=Mock(side_effect=lambda **kw:HTTPException(400,'late'));first=self.replace('HTTPException',side_effect=lambda **kw:HTTPException(**kw))
        class Value:
            def __str__(value):
                events.append('str')
                if len(events)==2:self.api.HTTPException=late
                return 'unknown'
        with self.assertRaises(HTTPException) as seen:self.api.normalize_preview_pose_family_policy(Value())
        self.assertEqual(seen.exception.detail,'Unknown preview_pose_family_policy: unknown');self.assertEqual(events,['str','str']);first.assert_called_once_with(status_code=400,detail='Unknown preview_pose_family_policy: unknown');late.assert_not_called()

    def test_many_consumes_all_objects_before_empty_intersection(self):
        error=RuntimeError('second object still evaluated');self.replace('accessory_material_type',return_value='object');available=self.replace('available_object_pose_families',side_effect=[[],error])
        with self.assertRaises(RuntimeError) as seen:self.api.preview_pose_families_for_policy([{'id':1},{'id':2}],'auto')
        self.assertIs(seen.exception,error);self.assertEqual(available.call_args_list,[call({'id':1}),call({'id':2})])
    def test_many_unknown_direct_policy_skips_normalization_and_auto_mixing(self):
        self.replace('accessory_material_type',return_value='object');self.replace('available_object_pose_families',return_value=['lying','upright']);normal=self.replace('normalize_preview_pose_family_policy',return_value='auto');canonical=self.replace('canonical_pose_family_name',side_effect=lambda value:value)
        self.assertEqual(self.api.preview_pose_families_for_policy([{}],'unknown'),['lying']);normal.assert_not_called();canonical.assert_not_called()
    def test_available_reselects_sprite_callback_between_condition_and_value(self):
        sprites=[{'id':1},{'id':2}];clean=self.replace('clean_sprite_assets',return_value=sprites);last=Mock(return_value='a')
        def middle(asset):
            if asset['id']==1:return 'z'
            self.api.sprite_pose_family=last;return 'gate'
        second=Mock(side_effect=middle)
        def start(asset):self.api.sprite_pose_family=second;return 'gate'
        first=self.replace('sprite_pose_family',side_effect=start)
        self.assertEqual(self.api.available_object_pose_families({}),['a','z']);first.assert_called_once_with(sprites[0]);self.assertEqual(second.call_args_list,[call(sprites[0]),call(sprites[1])]);last.assert_called_once_with(sprites[1]);clean.assert_called_once_with({})
    def test_normalize_reselects_error_factory_after_initial_string_conversion(self):
        from fastapi import HTTPException
        old=self.replace('HTTPException',side_effect=lambda **kw:HTTPException(400,'old'));new=Mock(side_effect=lambda **kw:HTTPException(**kw));events=[]
        class Value:
            def __str__(value):events.append('str');self.api.HTTPException=new;return 'unknown'
        with self.assertRaises(HTTPException) as seen:self.api.normalize_preview_pose_family_policy(Value())
        self.assertEqual(seen.exception.detail,'Unknown preview_pose_family_policy: unknown');self.assertEqual(events,['str','str']);old.assert_not_called();new.assert_called_once_with(status_code=400,detail='Unknown preview_pose_family_policy: unknown')
    def test_many_error_factory_selected_before_effectful_format(self):
        from fastapi import HTTPException
        self.replace('accessory_material_type',return_value='object');self.replace('available_object_pose_families',return_value=['upright']);first=self.replace('HTTPException',side_effect=lambda **kw:HTTPException(**kw));late=Mock(side_effect=lambda **kw:HTTPException(400,'late'));events=[]
        class Policy(str):
            def __format__(value,spec):events.append(spec);self.api.HTTPException=late;return 'lying'
        with self.assertRaises(HTTPException) as seen:self.api.preview_pose_families_for_policy([{}],Policy('lying'))
        self.assertEqual(seen.exception.detail,'No clean sprites available for preview pose policy: lying');self.assertEqual(events,['']);first.assert_called_once_with(status_code=400,detail='No clean sprites available for preview pose policy: lying');late.assert_not_called()

    def test_independent_preview_constructor_and_first_second_first(self):
        from local_inspection_service.accessories.pose_policy import PreviewPosePolicy
        from local_inspection_service.accessories.pose_policy_ports import PreviewPoseAssetOperations,PreviewPoseSelectionOperations,PreviewPoseErrors
        names=('assets','material','sprite','available','normalize','many','canonical','make')
        getters={name:Mock(side_effect=AssertionError('constructor resolved dependency')) for name in names}
        PreviewPosePolicy(PreviewPoseAssetOperations(getters['assets'],getters['material'],getters['sprite']),PreviewPoseSelectionOperations(getters['available'],getters['normalize'],getters['many'],getters['canonical']),PreviewPoseErrors(getters['make']))
        for getter in getters.values():getter.assert_not_called()
        poisons=[self.replace(name,side_effect=AssertionError('root dependency forbidden')) for name in ('clean_sprite_assets','accessory_material_type','sprite_pose_family','available_object_pose_families','normalize_preview_pose_family_policy','preview_pose_families_for_policy','canonical_pose_family_name','HTTPException')]
        class PolicyError(Exception):pass
        instances=[]
        for prefix,families in (('A',['flat','top']),('B',['lying','upright'])):
            assets=Mock(return_value=[{'family':family} for family in families]);material=Mock(return_value='object');sprite=Mock(side_effect=lambda asset:asset['family']);available=Mock(return_value=families);normalize=Mock(return_value='auto');many=Mock(return_value=families);canonical=Mock(side_effect=lambda family:{'flat':'lying','top':'upright'}.get(family,family));error=Mock(side_effect=lambda *,status_code,detail,p=prefix:PolicyError(p,status_code,detail))
            service=PreviewPosePolicy(PreviewPoseAssetOperations(lambda fn=assets:fn,lambda fn=material:fn,lambda fn=sprite:fn),PreviewPoseSelectionOperations(lambda fn=available:fn,lambda fn=normalize:fn,lambda fn=many:fn,lambda fn=canonical:fn),PreviewPoseErrors(lambda fn=error:fn))
            instances.append((service,prefix,families,assets,available,many,error))
        for index in (0,1,0):
            service,prefix,families,assets,available,many,error=instances[index];items=[{}]
            self.assertEqual(service.available_object_pose_families(items[0]),families)
            self.assertEqual(service.normalize_preview_pose_family_policy('flat'),'lying')
            self.assertEqual(service.preview_pose_family_for_policy(items,'auto'),families[0]);self.assertIs(many.call_args.args[0],items)
            self.assertEqual(service.preview_pose_families_for_policy(items,'auto'),families)
            self.assertEqual(service.preview_pose_family_sequence(items,3,'DEFAULT'),[families[0],families[1],families[0]])
            self.assertEqual(service.preview_pose_family_sequence_label(families),'mixed')
            with self.assertRaises(PolicyError) as seen:service.normalize_preview_pose_family_policy('invalid')
            self.assertEqual(seen.exception.args,(prefix,400,'Unknown preview_pose_family_policy: invalid'))
            available.return_value=['alien']
            try:
                with self.assertRaises(PolicyError) as seen:service.preview_pose_families_for_policy(items,'lying')
                self.assertEqual(seen.exception.args,(prefix,400,'No clean sprites available for preview pose policy: lying'))
            finally:available.return_value=families
        self.assertEqual([item[3].call_count for item in instances],[2,1]);self.assertEqual([item[5].call_count for item in instances],[4,2]);self.assertEqual([item[6].call_count for item in instances],[4,2])
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()

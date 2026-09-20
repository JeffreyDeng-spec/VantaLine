"""Original pose-grid and selection contracts; synthetic values only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from itertools import chain,repeat
from contextlib import ExitStack
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path.cwd()))
class PosePolicyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lifetime=ExitStack();cls.lifetime.enter_context(patch.dict(os.environ))
        cls.root=Path(cls.lifetime.enter_context(tempfile.TemporaryDirectory(prefix='cutout-runtime-')))
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
    def positions(self):
        positions=tuple('p'+str(i) for i in range(9));self.replace('POSE_COLLECTION_GRID_POSITIONS',new=positions);return positions
    def test_regions_padding_and_row_major_order(self):
        image=np.zeros((90,120,3),np.uint8)
        self.assertEqual(self.api.pose_collection_regions(image,False),[(0,0,40,30),(40,0,80,30),(80,0,120,30),(0,30,40,60),(40,30,80,60),(80,30,120,60),(0,60,40,90),(40,60,80,90),(80,60,120,90)])
        padded=self.api.pose_collection_regions(image);self.assertEqual(len(padded),9);self.assertEqual([padded[i] for i in (0,4,8)],[(0,0,49,37),(31,23,89,67),(71,53,120,90)])
    def test_grid_clipping_and_explicit_roi(self):
        positions=self.positions();roi=(10,20,100,110)
        for point,index in [((-10,-10),0),((10,20),0),((40,20),1),((99,109),8),((1000,1000),8),((55,65),4)]:self.assertEqual(self.api.grid_position_for_center(point,roi),positions[index])
        self.assertEqual(self.api.grid_position_for_center((10,20),(10,20,10,20)),'p0')
    def test_grid_default_is_bound_before_root_roi_reassignment(self):
        self.positions();original=self.api.grid_position_for_center.__defaults__[0];self.replace('BACKGROUND_ROI_PX',new=(-100,-100,-97,-97));center=((original[0]+original[2])//2,(original[1]+original[3])//2)
        self.assertIs(self.api.grid_position_for_center.__defaults__[0],original);self.assertEqual(self.api.grid_position_for_center(center),'p4');self.assertEqual(self.api.grid_position_for_center(center,(-100,-100,-97,-97)),'p8')
    def test_row_column_roundtrip_and_unknown(self):
        positions=self.positions()
        for i,position in enumerate(positions):self.assertEqual(self.api.grid_row_col(position),(i//3,i%3));self.assertEqual(self.api.grid_position_from_row_col(i//3,i%3),position)
        self.assertIsNone(self.api.grid_row_col(None));self.assertIsNone(self.api.grid_row_col('?'));self.assertEqual(self.api.grid_position_from_row_col(-8,99),'p2')
    def test_row_lookup_rereads_positions_after_membership(self):
        class Positions(list):
            def __contains__(value,item):self.api.POSE_COLLECTION_GRID_POSITIONS=['b','a'];return True
        self.replace('POSE_COLLECTION_GRID_POSITIONS',new=Positions(['a','b']));self.assertEqual(self.api.grid_row_col('a'),(0,1))
    def test_cardinal_banker_rounding_and_errors(self):
        for angle,expected in [(0,0),(45,0),(135,180),(225,180),(315,0),(-45,0),(-135,180),(450,90),('90',90)]:self.assertEqual(self.api.normalize_cardinal_rotation_degrees(angle),expected)
        with self.assertRaises(ValueError):self.api.normalize_cardinal_rotation_degrees(float('nan'))
        with self.assertRaises(OverflowError):self.api.normalize_cardinal_rotation_degrees(float('inf'))
    def test_inverse_rotation_positions_and_invalid_early_return(self):
        self.positions()
        for angle,expected in [(0,'p0'),(90,'p2'),(180,'p8'),(270,'p6'),(450,'p2')]:self.assertEqual(self.api.source_position_for_rotated_target('p0',angle),expected)
        for angle in (0,90,180,270):self.assertEqual(self.api.source_position_for_rotated_target('p4',angle),'p4')
        normalize=self.replace('normalize_cardinal_rotation_degrees',side_effect=AssertionError('unneeded normalization'));self.assertIsNone(self.api.source_position_for_rotated_target(None,90));self.assertEqual(self.api.source_position_for_rotated_target('unknown',90),'unknown');normalize.assert_not_called()
    def test_upright_policy_keeps_container_selected_before_random_effect(self):
        initial=['first','second'];self.replace('UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',new=initial);top=self.replace('pose_family_is_top_view',return_value=True);inverse=self.replace('source_position_for_rotated_target');rng=Mock()
        def pick(low,high):self.api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS=['new-first','new-second'];return 1
        rng.integers.side_effect=pick;self.assertEqual(self.api.source_position_for_render_policy('p0',90,None,rng),'second');rng.integers.assert_called_once_with(0,2);top.assert_called_once_with('');inverse.assert_not_called()
    def test_lying_policy_forwards_without_random(self):
        self.replace('pose_family_is_top_view',return_value=False);inverse=self.replace('source_position_for_rotated_target',return_value='chosen');rng=Mock();self.assertEqual(self.api.source_position_for_render_policy('p0',32.5,'lying',rng),'chosen');inverse.assert_called_once_with('p0',32.5);rng.integers.assert_not_called()
    def test_render_policy_rng_precedes_family_and_keeps_raw_angle(self):
        events=[];rng=Mock();rng.uniform.side_effect=lambda *a:events.append('rng') or 44.9;self.replace('pose_family_is_top_view',side_effect=lambda family:events.append('family') or False);normal=self.replace('normalize_cardinal_rotation_degrees',return_value=90)
        result=self.api.object_render_pose_policy('lying',rng);self.assertEqual(events,['rng','family']);rng.uniform.assert_called_once_with(-180.0,180.0);normal.assert_called_once_with(44.9)
        self.assertEqual(result,{'render_pose_policy':'lying_random_planar_rotation','perspective_rotation_degrees':44.9,'placement_angle_degrees':44.9,'desired_lie_direction':'horizontal','desired_facing_direction':'lying_horizontal_44.9deg','source_selection_rule':'inverse_grid_position_for_random_planar_rotation'})
    def test_top_render_policy_skips_cardinal_normalization(self):
        rng=Mock();rng.uniform.return_value=-22.25;self.replace('pose_family_is_top_view',return_value=True);normal=self.replace('normalize_cardinal_rotation_degrees')
        result=self.api.object_render_pose_policy(None,rng);self.assertEqual(result['render_pose_policy'],'upright_random_planar_rotation');self.assertEqual(result['placement_angle_degrees'],-22.25);self.assertIsNone(result['desired_lie_direction']);self.assertEqual(result['desired_facing_direction'],'upright_top_down_-22.2deg');normal.assert_not_called()
    def test_selection_reason_normalization_and_precedence(self):
        self.replace('UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',new=('center','bottom'))
        for target,source,angle,reason in [(None,'center',0,'position_unavailable'),('other','center',0,'upright_restricted_center_or_bottom_center'),('x','x',0,'same_position_0'),('x','y',0,'unrotated_position_remap'),('x','y',180,'opposite_position_180'),('x','x',180,'center_180_no_opposite'),('x','y',90,'inverse_position_90')]:self.assertEqual(self.api.pose_selection_reason(target,source,angle),reason)
        fail=RuntimeError('normalization first');self.replace('normalize_cardinal_rotation_degrees',side_effect=fail)
        with self.assertRaises(RuntimeError) as seen:self.api.pose_selection_reason(None,None,0)
        self.assertIs(seen.exception,fail)
    def test_render_size_hint_filters_skips_invalid_and_clamps_assets(self):
        self.replace('canonical_pose_family_name',side_effect=lambda value:str(value or '').lower());assets=[{'pose_family':'other','render_size_hint_px':[100,100]},{'pose_family':'lying','render_size_hint_px':['bad',20]},{'source_pose_family':'lying','pose_family':'other','render_size_hint_px':[-5,'30']}];self.replace('clean_sprite_assets',return_value=assets);fallback=self.replace('pose_render_footprint_metadata')
        self.assertEqual(self.api.object_pose_render_size_hint({},'LYING'),(16,30));fallback.assert_not_called()
        error=OverflowError('hint overflow')
        class Overflow:
            def __int__(value):raise error
        self.api.clean_sprite_assets.return_value=[{'pose_family':'lying','render_size_hint_px':[Overflow(),20]},{'pose_family':'lying','render_size_hint_px':[40,50]}]
        with self.assertRaises(OverflowError) as seen:self.api.object_pose_render_size_hint({},'LYING')
        self.assertIs(seen.exception,error);fallback.assert_not_called()
    def test_render_size_fallback_keeps_small_values_and_physical_alias(self):
        physical={'width':3};item={'physical_size':physical};self.replace('canonical_pose_family_name',return_value='lying');self.replace('clean_sprite_assets',return_value=[{'pose_family':'lying','render_size_hint_px':(50,50)}]);fallback=self.replace('pose_render_footprint_metadata',return_value={'render_footprint_px':['7',9]})
        self.assertEqual(self.api.object_pose_render_size_hint(item,'lying'),(7,9));self.assertEqual(fallback.call_args.args[:2],('lying',[1,1]));self.assertIs(fallback.call_args.args[2],physical)
    def test_major_axis_list_coercion_and_overflow(self):
        for asset,expected in [({},None),({'source_object_size_px':(3,9)},None),({'source_object_size_px':[3]},None),({'source_object_size_px':['3',9]},9),({'source_object_size_px':['bad',9]},None),({'source_object_size_px':[-5,-2]},-2)]:self.assertEqual(self.api.source_object_major_axis_px(asset),expected)
        with self.assertRaises(OverflowError):self.api.source_object_major_axis_px({'source_object_size_px':[float('inf'),1]})
    def test_candidate_filter_threshold_identity_and_unknown_lengths(self):
        candidates=[{'source_object_size_px':[v,v]} for v in (100,100,100,85,84)]+[{}]
        result=self.api.filter_complete_pose_candidates(candidates,'SIDE');self.assertEqual(result,candidates[:4]+candidates[5:]);self.assertIs(result[0],candidates[0]);self.assertIs(result[-1],candidates[-1]);self.assertIsNot(result,candidates)
        self.assertIs(self.api.filter_complete_pose_candidates(candidates,' lying '),candidates);small=candidates[:3];self.assertIs(self.api.filter_complete_pose_candidates(small,'lying'),small)
    def test_candidate_filter_empty_negative_result_falls_back(self):
        candidates=[{'source_object_size_px':[v,v]} for v in (-100,-100,-100,-100)];self.assertIs(self.api.filter_complete_pose_candidates(candidates,'flat'),candidates)
    def test_family_choice_repeats_callback_and_sorts_unique_values(self):
        sprites=[{}, {}, {}];family=self.replace('sprite_pose_family',side_effect=['condition','z',None,'condition','a']);rng=Mock();rng.integers.return_value=0
        self.assertEqual(self.api.choose_object_pose_family(sprites,rng),'a');self.assertEqual(family.call_count,5);rng.integers.assert_called_once_with(0,2)
        family.side_effect=None;family.return_value=None;rng.reset_mock();self.assertIsNone(self.api.choose_object_pose_family(sprites,rng));rng.integers.assert_not_called()

    def test_upright_separate_container_and_length_reads(self):
        self.replace('UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',new=['old-first','old-second']);self.replace('pose_family_is_top_view',return_value=True);pick=Mock(return_value=1)
        class Rng:
            @property
            def integers(value):
                self.api.UPRIGHT_TOP_VIEW_SOURCE_POSITIONS=['new-first','new-second','new-third'];return pick
        self.assertEqual(self.api.source_position_for_render_policy('p0',90,'top',Rng()),'old-second');pick.assert_called_once_with(0,3)
    def test_render_policy_rereads_callbacks_after_float_and_predicate(self):
        before_top=self.replace('pose_family_is_top_view',return_value=True);before_normal=self.replace('normalize_cardinal_rotation_degrees',return_value=0);normal=Mock(return_value=90)
        def check(family):self.api.normalize_cardinal_rotation_degrees=normal;return False
        top=Mock(side_effect=check)
        class Angle:
            def __float__(value):self.api.pose_family_is_top_view=top;return 44.9
        rng=Mock();rng.uniform.return_value=Angle();result=self.api.object_render_pose_policy('lying',rng)
        self.assertEqual(result['desired_lie_direction'],'horizontal');self.assertEqual(result['placement_angle_degrees'],44.9);top.assert_called_once_with('lying');normal.assert_called_once_with(44.9);before_top.assert_not_called();before_normal.assert_not_called()
    def test_footprint_callee_selected_before_arguments_evaluated_once(self):
        self.replace('canonical_pose_family_name',return_value=None);self.replace('clean_sprite_assets',return_value=[]);first=self.replace('pose_render_footprint_metadata',return_value={'render_footprint_px':[7,9]});late=Mock(return_value={'render_footprint_px':[99,99]});events=[];physical={'width':2}
        class Family:
            def __str__(value):events.append('str');self.api.pose_render_footprint_metadata=late;return 'lying'
        class Item(dict):
            def get(value,key,default=None):events.append(key);return physical
        self.assertEqual(self.api.object_pose_render_size_hint(Item(),Family()),(7,9));self.assertEqual(events,['str','physical_size']);first.assert_called_once_with('lying',[1,1],physical);late.assert_not_called()
    def test_family_comprehension_reselects_callback_between_evaluations(self):
        sprites=[{'id':1},{'id':2}];last=Mock(return_value='a')
        def middle(asset):
            if asset['id']==1:return 'z'
            self.api.sprite_pose_family=last;return 'gate'
        second=Mock(side_effect=middle)
        def start(asset):self.api.sprite_pose_family=second;return 'gate'
        first=self.replace('sprite_pose_family',side_effect=start);rng=Mock();rng.integers.return_value=0
        self.assertEqual(self.api.choose_object_pose_family(sprites,rng),'a');first.assert_called_once_with(sprites[0]);self.assertEqual(second.call_args_list,[unittest.mock.call(sprites[0]),unittest.mock.call(sprites[1])]);last.assert_called_once_with(sprites[1]);rng.integers.assert_called_once_with(0,2)

    def test_independent_grid_policy_constructors_and_first_second_first(self):
        from local_inspection_service.accessories.pose_policy import PoseGridPolicy
        from local_inspection_service.accessories.pose_policy_ports import PoseLayoutValues,PoseRotationOperations,PoseRenderOperations
        getters={name:Mock(side_effect=AssertionError('constructor resolved dependency')) for name in ('grid','upright','normalize','row_col','position','is_top','source')}
        PoseGridPolicy(PoseLayoutValues(getters['grid'],getters['upright']),PoseRotationOperations(getters['normalize'],getters['row_col'],getters['position']),PoseRenderOperations(getters['is_top'],getters['source']))
        for getter in getters.values():getter.assert_not_called()
        poisons=[self.replace(name,side_effect=AssertionError('root dependency forbidden')) for name in ('normalize_cardinal_rotation_degrees','grid_row_col','grid_position_from_row_col','pose_family_is_top_view','source_position_for_rotated_target')]
        self.replace('POSE_COLLECTION_GRID_POSITIONS',new=());self.replace('UPRIGHT_TOP_VIEW_SOURCE_POSITIONS',new=())
        instances=[]
        for prefix in ('A','B'):
            grid=tuple(prefix+str(i) for i in range(9));upright=(prefix+'U0',prefix+'U1')
            normal=Mock(return_value=90);row_col=Mock(return_value=(0,0));position=Mock(side_effect=lambda row,col,p=prefix:p+str(row)+str(col));top=Mock(side_effect=lambda family:family=='top');source=Mock(return_value=prefix+'source')
            service=PoseGridPolicy(PoseLayoutValues(lambda v=grid:v,lambda v=upright:v),PoseRotationOperations(lambda v=normal:v,lambda v=row_col:v,lambda v=position:v),PoseRenderOperations(lambda v=top:v,lambda v=source:v))
            instances.append((service,prefix,normal,row_col,position,top,source))
        for index in (0,1,0):
            service,prefix,normal,row_col,position,top,source=instances[index];rng=Mock();rng.integers.return_value=1;rng.uniform.return_value=22.0
            self.assertEqual(service.grid_position_for_center((45,45),(0,0,90,90)),prefix+'4')
            self.assertEqual(service.grid_row_col(prefix+'1'),(0,1));self.assertEqual(service.grid_position_from_row_col(1,2),prefix+'5')
            self.assertEqual(service.source_position_for_rotated_target('target',15),prefix+'02')
            self.assertEqual(service.source_position_for_render_policy('target',15,'top',rng),prefix+'U1')
            self.assertEqual(service.source_position_for_render_policy('target',15,'lying',rng),prefix+'source')
            result=service.object_render_pose_policy('lying',rng);self.assertEqual(result['desired_lie_direction'],'horizontal');self.assertEqual(result['placement_angle_degrees'],22.0)
            self.assertEqual(service.pose_selection_reason('target','source',15),'inverse_position_90')
        self.assertEqual([item[2].call_count for item in instances],[6,3]);self.assertEqual([item[6].call_count for item in instances],[2,1])
        for poison in poisons:poison.assert_not_called()

    def test_independent_candidate_policy_constructors_and_first_second_first(self):
        from local_inspection_service.accessories.pose_policy import PoseCandidatePolicy
        from local_inspection_service.accessories.pose_policy_ports import PoseAssetOperations,PoseCandidateOperations
        getters={name:Mock(side_effect=AssertionError('constructor resolved dependency')) for name in ('canonical','assets','footprint','major_axis','family')}
        PoseCandidatePolicy(PoseAssetOperations(getters['canonical'],getters['assets'],getters['footprint']),PoseCandidateOperations(getters['major_axis'],getters['family']))
        for getter in getters.values():getter.assert_not_called()
        poisons=[self.replace(name,side_effect=AssertionError('root dependency forbidden')) for name in ('canonical_pose_family_name','clean_sprite_assets','pose_render_footprint_metadata','source_object_major_axis_px','sprite_pose_family')]
        instances=[]
        for delta in (1,2):
            canonical=Mock(side_effect=lambda value:value);assets=Mock(return_value=[{'pose_family':'lying','render_size_hint_px':[-1,30+delta]}]);footprint=Mock(return_value={'render_footprint_px':[7+delta,9]});major=Mock(side_effect=lambda asset:asset.get('axis'));family=Mock(side_effect=lambda asset:asset['family'])
            service=PoseCandidatePolicy(PoseAssetOperations(lambda v=canonical:v,lambda v=assets:v,lambda v=footprint:v),PoseCandidateOperations(lambda v=major:v,lambda v=family:v))
            instances.append((service,delta,canonical,assets,footprint,major,family))
        for index in (0,1,0):
            service,delta,canonical,assets,footprint,major,family=instances[index];rng=Mock();rng.integers.return_value=0
            self.assertEqual(service.object_pose_render_size_hint({},'lying'),(16,30+delta))
            self.assertEqual(service.object_pose_render_size_hint({},'missing'),(7+delta,9))
            candidates=[{'axis':v} for v in (100,100,100,85,84)]
            result=service.filter_complete_pose_candidates(candidates,'side');self.assertEqual(result,candidates[:4]);self.assertIs(result[0],candidates[0])
            self.assertEqual(service.choose_object_pose_family([{'family':'z'+str(delta)},{'family':'a'+str(delta)}],rng),'a'+str(delta))
        self.assertEqual([item[4].call_count for item in instances],[2,1]);self.assertEqual([item[6].call_count for item in instances],[8,4])
        for poison in poisons:poison.assert_not_called()

if __name__=='__main__':unittest.main()

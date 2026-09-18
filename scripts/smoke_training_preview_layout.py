"""Offline preview layout contracts first run against the original application functions."""
from contextlib import ExitStack
import inspect
import itertools
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class PreviewLayoutContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ); cls.environment.start()
        cls.runtime = tempfile.TemporaryDirectory(prefix='preview-layout-root-')
        root = Path(cls.runtime.name); (root / 'local_inspection_service/static').mkdir(parents=True)
        os.environ.update(LOCAL_INSPECTION_ROOT=str(root), VANTALINE_DATA_STORE='json',
                          LOCAL_INSPECTION_AUTO_RESUME_WORKER='0', VANTALINE_LABEL_INSPECTION_ENABLED='false')
        from local_inspection_service import server
        cls.api = server

    @classmethod
    def tearDownClass(cls): cls.runtime.cleanup(); cls.environment.stop()

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for target in ['requests.request', 'subprocess.Popen', 'os.kill']:
            self.stack.enter_context(patch(target, side_effect=AssertionError('unexpected external operation')))

    def replace(self, name, value): return self.stack.enter_context(patch.object(self.api, name, value))

    def test_constrained_range_casts_inclusive_and_bankers_rounding(self):
        f = self.api.constrained_center_range
        self.assertEqual(f('1', '11', '5'), (6, 6))
        self.assertEqual(f(1.9, 12.9, 2.9), (3, 10))
        self.assertEqual(f(0, 5, 9), (2, 2))
        self.assertEqual(f(0, 7, 9), (4, 4))
        self.assertEqual(f(0, 10, -2), (-2, 12))

    def test_random_margin_ceil_inclusive_endpoints_and_axis_order(self):
        class ForbiddenCanvas:
            def __getitem__(self, key): raise AssertionError('normal ROI read canvas')
        self.replace('PREVIEW_CANVAS_SIZE_PX', ForbiddenCanvas())
        rng = Mock(); rng.integers.side_effect = lambda low, high: high - 1
        self.assertEqual(self.api.random_center_inside_background(rng, (21, 11), 0, (0, 0, 100, 100)), (77, 82))
        self.assertEqual(rng.integers.call_args_list, [call(23, 78), call(18, 83)])
        rng.reset_mock(); rng.integers.side_effect = lambda low, high: low
        self.assertEqual(self.api.random_center_inside_background(rng, (20, 10), 45, (0, 0, 100, 100)), (23, 23))
        self.assertEqual(rng.integers.call_args_list, [call(23, 78), call(23, 78)])

    def test_equal_bound_fallback_each_axis_lazy_and_oversized_two_draws(self):
        events = []
        class Canvas:
            def __getitem__(self, key): events.append(key); return [101, 107][key]
        self.replace('PREVIEW_CANVAS_SIZE_PX', Canvas())
        rng = Mock(); rng.integers.side_effect = lambda low, high: low
        self.assertEqual(self.api.random_center_inside_background(rng, (20, 20), 0, (0, 0, 44, 44)), (22, 22))
        self.assertEqual(events, [0, 1]); self.assertEqual(rng.integers.call_args_list, [call(22, 80), call(22, 86)])
        events.clear(); rng.reset_mock()
        self.assertEqual(self.api.random_center_inside_background(rng, (999, 999), 0, (0, 0, 44, 44)), (50, 54))
        self.assertEqual(events, [0, 1]); self.assertEqual(rng.integers.call_args_list, [call(50, 51), call(54, 55)])
        events.clear(); rng.reset_mock()
        self.api.random_center_inside_background(rng, (20, 20), 0, (0, 0, 44, 100))
        self.assertEqual(events, [0])

    def test_public_roi_default_is_captured_and_explicit_none_is_not_default(self):
        original = inspect.signature(self.api.random_center_inside_background).parameters['roi'].default
        self.assertIs(inspect.signature(self.api.choose_object_center_inside_background).parameters['roi'].default, original)
        self.replace('BACKGROUND_ROI_PX', (9999, 9999, 10000, 10000))
        rng = Mock(); rng.integers.side_effect = lambda low, high: low
        self.assertEqual(self.api.random_center_inside_background(rng, (20, 20), 0), (original[0] + 22, original[1] + 22))
        sample = self.replace('random_center_inside_background', Mock(return_value=(1, 2)))
        overlap = self.replace('object_placement_overlap_area', Mock(return_value=0))
        placed = []
        self.api.choose_object_center_inside_background(rng, (20, 20), 0, placed)
        sample.assert_called_once_with(rng, (20, 20), 0, original)
        self.api.choose_object_center_inside_background(rng, (20, 20), 0, placed, None)
        self.assertIsNone(sample.call_args.args[-1]); self.assertEqual(overlap.call_count, 2)
        # Real random helper still rejects an explicit None through the public chooser.
        sample.side_effect = TypeError('cannot unpack non-iterable NoneType object')
        with self.assertRaises(TypeError): self.api.choose_object_center_inside_background(rng, (20, 20), 0, placed, None)

    def test_rotated_geometry_real_intersections_and_none_status_short_circuit(self):
        f = self.api.rotated_rect_tuple
        self.assertEqual(f((-2, 3), (0, -4), '45'), ((-2.0, 3.0), (1.0, 1.0), 45.0))
        a = f((0, 0), (10, 10), 0)
        for center, size, area in [((0, 0), (10, 10), 100), ((5, 0), (10, 10), 50), ((0, 0), (2, 2), 4), ((50, 50), (10, 10), 0)]:
            self.assertAlmostEqual(self.api.rotated_rect_overlap_area(a, f(center, size, 0)), area)
        for result in [(cv2.INTERSECT_NONE, np.ones((3, 1, 2))), (cv2.INTERSECT_FULL, None)]:
            with patch.object(cv2, 'rotatedRectangleIntersection', return_value=result), patch.object(cv2, 'contourArea', side_effect=AssertionError('unexpected area')):
                self.assertEqual(self.api.rotated_rect_overlap_area(a, a), 0.0)
        with patch.object(cv2, 'rotatedRectangleIntersection', return_value=(cv2.INTERSECT_PARTIAL, 'points')), patch.object(cv2, 'contourArea', return_value=-2.5):
            self.assertEqual(self.api.rotated_rect_overlap_area(a, a), 2.5)

    def test_overlap_constructs_once_empty_or_duplicate_order_and_propagates(self):
        rect = object(); make = self.replace('rotated_rect_tuple', Mock(return_value=rect))
        area = self.replace('rotated_rect_overlap_area', Mock(side_effect=[2.0, 3.0, 2.0]))
        a, b = object(), object(); placed = [{'rect': a}, {'rect': b}, {'rect': a}]
        self.assertEqual(self.api.object_placement_overlap_area((1, 2), (3, 4), 5, placed), 7)
        make.assert_called_once_with((1, 2), (3, 4), 5)
        self.assertEqual(area.call_args_list, [call(rect, a), call(rect, b), call(rect, a)])
        make.reset_mock(); area.reset_mock()
        self.assertEqual(self.api.object_placement_overlap_area((1, 2), (3, 4), 5, []), 0)
        make.assert_called_once(); area.assert_not_called()
        with self.assertRaises(KeyError): self.api.object_placement_overlap_area((1, 2), (3, 4), 5, [{}])

    def choose(self, overlaps):
        counter = iter((i, i + 1) for i in range(180))
        random = self.replace('random_center_inside_background', Mock(side_effect=lambda *args: next(counter)))
        area = self.replace('object_placement_overlap_area', Mock(side_effect=overlaps))
        rng = np.random.default_rng(12); placed = [{'rect': 'one'}]; roi = (1, 2, 3, 4)
        result = self.api.choose_object_center_inside_background(rng, (9, 7), 15, placed, roi)
        self.assertEqual(random.call_count, area.call_count)
        for i, (sample_call, area_call) in enumerate(zip(random.call_args_list, area.call_args_list)):
            self.assertIs(sample_call.args[0], rng); self.assertEqual(sample_call.args[1:], ((9, 7), 15, roi))
            self.assertEqual(area_call.args[:3], ((i, i + 1), (9, 7), 15)); self.assertIs(area_call.args[3], placed)
        return result, random.call_count

    def test_search_threshold_first_and_last_attempt_succeed_and_no_more_calls(self):
        for overlap in [-2, 0, 0.5]:
            (center, meta), count = self.choose([overlap])
            self.assertEqual((center, count), ((0, 1), 1))
            self.assertEqual(meta, {'object_non_overlap_attempts': 1, 'object_overlap_area_px': 0.0, 'object_non_overlap_pass': True})
        (center, meta), count = self.choose([0.500001] * 179 + [0.5])
        self.assertEqual((center, count), ((179, 180), 180))
        self.assertEqual(meta, {'object_non_overlap_attempts': 180, 'object_overlap_area_px': 0.0, 'object_non_overlap_pass': True})

    def test_search_exhaustion_keeps_first_tie_and_rounds_only_report(self):
        (center, meta), count = self.choose([2, 1.23456, 1.23456] + [9] * 177)
        self.assertEqual((center, count), ((1, 2), 180))
        self.assertEqual(meta, {'object_non_overlap_attempts': 180, 'object_overlap_area_px': 1.235, 'object_non_overlap_pass': False})
        (center, meta), count = self.choose([0.500001] * 180)
        self.assertEqual((center, count, meta['object_overlap_area_px'], meta['object_non_overlap_pass']), ((0, 1), 180, 0.5, False))

    def test_search_errors_immediate_and_none_roi_real_failure(self):
        rng = Mock()
        with self.assertRaises(TypeError): self.api.random_center_inside_background(rng, (2, 2), 0, None)
        rng.integers.assert_not_called()
        sample = self.replace('random_center_inside_background', Mock(side_effect=RuntimeError('sample')))
        area = self.replace('object_placement_overlap_area', Mock())
        with self.assertRaisesRegex(RuntimeError, 'sample'): self.api.choose_object_center_inside_background(rng, (2, 2), 0, [])
        sample.assert_called_once(); area.assert_not_called()
        sample.side_effect = None; sample.return_value = (1, 2); sample.reset_mock(); area.side_effect = ValueError('area')
        with self.assertRaisesRegex(ValueError, 'area'): self.api.choose_object_center_inside_background(rng, (2, 2), 0, [])
        sample.assert_called_once(); area.assert_called_once()

    def test_box_bankers_rounding_and_polygon_mask_real_pixels(self):
        rect = object(); make = self.replace('rotated_rect_tuple', Mock(return_value=rect))
        with patch.object(cv2, 'boxPoints', return_value=np.array([[0.5, 1.5], [2.5, 3.5], [-0.5, -1.5], [-2.5, -3.5]])) as box:
            self.assertEqual(self.api.placement_box_points((0, 0), (2, 2), 9), [[0, 2], [2, 4], [0, -2], [-2, -4]])
            box.assert_called_once_with(rect); make.assert_called_once_with((0, 0), (2, 2), 9)
        for polygon in [None, [], [[1, 1]], [[0, 0], [3, 3]]]:
            actual = self.api.mask_from_polygon((8, 8), polygon)
            self.assertEqual(actual.dtype, np.uint8); self.assertEqual(actual.shape, (8, 8)); self.assertEqual(int(actual.sum()), 0)
        expected = np.zeros((8, 8), np.uint8); expected[1:5, 1:5] = 255
        np.testing.assert_array_equal(self.api.mask_from_polygon((8, 8), [[1.9, 1.9], [4.9, 1.1], [4.2, 4.8], [1.1, 4.9]]), expected)

    def test_contour_epsilon_clip_only_consecutive_duplicates_and_closure(self):
        contour = np.array([[[0, 0]], [[2, 0]], [[2, 2]]], np.int32)
        points = np.array([[[-1, -1]], [[0, 0]], [[8, 0]], [[8, 9]], [[0, 0]], [[2, 3]], [[-1, -1]]], np.int32)
        with patch.object(cv2, 'arcLength', return_value=400) as arc, patch.object(cv2, 'approxPolyDP', return_value=points) as approx:
            self.assertEqual(self.api.contour_to_polygon(contour, (6, 7)), [[0, 0], [6, 0], [6, 5], [0, 0], [2, 3]])
            arc.assert_called_once_with(contour, True); approx.assert_called_once_with(contour, 400 * 0.0035, True)
            self.api.contour_to_polygon(contour, (6, 7, 3), 0)
            self.assertEqual(approx.call_args.args[1:], (1.0, True))
        with patch.object(cv2, 'approxPolyDP', return_value=np.zeros((3, 1, 2), np.int32)):
            self.assertEqual(self.api.contour_to_polygon(contour, (6, 7)), [])

    def test_contour_fallback_truncates_before_clipping_and_real_rectangle(self):
        contour = np.array([[[1, 1]], [[5, 1]], [[5, 4]], [[1, 4]]], np.int32)
        self.assertEqual(self.api.contour_to_polygon(contour, (8, 8)), [[1, 1], [5, 1], [5, 4], [1, 4]])
        rect = object()
        with patch.object(cv2, 'approxPolyDP', return_value=contour[:2]), patch.object(cv2, 'minAreaRect', return_value=rect) as minimum, patch.object(cv2, 'boxPoints', return_value=np.array([[1.9, 1.9], [5.9, 1.9], [5.9, 4.9], [1.9, 4.9]])) as box:
            self.assertEqual(self.api.contour_to_polygon(contour, (8, 8)), [[1, 1], [5, 1], [5, 4], [1, 4]])
            minimum.assert_called_once_with(contour); box.assert_called_once_with(rect)

    def test_visible_mask_cutoff_min_pixels_and_morphology_order(self):
        with patch.object(cv2, 'morphologyEx', wraps=cv2.morphologyEx) as morph:
            for mask in [None, np.zeros((0, 0), np.uint8), np.full((10, 10), 24, np.uint8)]:
                self.assertEqual(self.api.visible_polygons_from_mask(mask), [])
            mask = np.zeros((10, 10), np.uint8); mask.flat[:11] = 25
            self.assertEqual(self.api.visible_polygons_from_mask(mask), []); morph.assert_not_called()
            mask.flat[11] = 25
            self.api.visible_polygons_from_mask(mask)
            self.assertEqual([c.args[1] for c in morph.call_args_list], [cv2.MORPH_OPEN, cv2.MORPH_CLOSE])
            np.testing.assert_array_equal(morph.call_args_list[0].args[0], (mask > 24).astype(np.uint8) * 255)
            for entry in morph.call_args_list: np.testing.assert_array_equal(entry.args[2], np.ones((3, 3), np.uint8))

    def test_visible_contour_stable_sort_absolute_relative_thresholds_and_empty_conversion(self):
        contours = [object() for _ in range(7)]
        areas = dict(zip(contours, [12, 800, 11.99, 12, 11.999, 13, 800]))
        results = {contours[1]: [], contours[6]: [[6]], contours[5]: [[5]], contours[0]: [[0]], contours[3]: [[3]]}
        converted = self.replace('contour_to_polygon', Mock(side_effect=lambda contour, shape, ratio: results[contour]))
        with patch.object(cv2, 'findContours', return_value=(contours, None)) as find, patch.object(cv2, 'contourArea', side_effect=lambda contour: areas[contour]):
            mask = np.full((10, 10), 255, np.uint8)
            self.assertEqual(self.api.visible_polygons_from_mask(mask, 0.02), [[[6]], [[5]], [[0]], [[3]]])
            self.assertEqual(converted.call_args_list, [call(c, (10, 10), 0.02) for c in [contours[1], contours[6], contours[5], contours[0], contours[3]]])
            self.assertEqual(find.call_args.args[1:], (cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE))
            areas[contours[1]] = 1000
            converted.reset_mock(); self.assertEqual(self.api.visible_polygons_from_mask(mask), [[[6]]])
            self.assertEqual(converted.call_count, 2)

    def test_visible_absolute_area_threshold_is_independent_of_relative_threshold(self):
        small, edge, largest = object(), object(), object()
        areas = {small: 11.99, edge: 12.0, largest: 100.0}
        converted = self.replace('contour_to_polygon', Mock(side_effect=lambda contour, shape, ratio: [[areas[contour]]]))
        with patch.object(cv2, 'findContours', return_value=([small, edge, largest], None)), patch.object(cv2, 'contourArea', side_effect=lambda contour: areas[contour]):
            self.assertEqual(self.api.visible_polygons_from_mask(np.full((20, 20), 255, np.uint8), 0.04), [[[100.0]], [[12.0]]])
            self.assertEqual(converted.call_args_list, [call(largest, (20, 20), 0.04), call(edge, (20, 20), 0.04)])

    def test_visible_real_noise_holes_components_and_first_polygon_alias(self):
        mask = np.zeros((50, 60), np.uint8)
        mask[4:20, 4:24] = 25; mask[8, 8] = 0; mask[30:40, 35:45] = 255; mask[25, 20] = 255
        polygons = self.api.visible_polygons_from_mask(mask)
        self.assertEqual(polygons, [[[4, 4], [4, 19], [23, 19], [23, 4]], [[35, 30], [35, 39], [44, 39], [44, 30]]])
        returned = self.replace('visible_polygons_from_mask', Mock(return_value=polygons))
        self.assertIs(self.api.visible_polygon_from_mask(mask, 0.04), polygons[0])
        self.assertIs(returned.call_args.args[0], mask); self.assertEqual(returned.call_args.args[1], 0.04)
        returned.return_value = []; self.assertEqual(self.api.visible_polygon_from_mask(mask), [])

    def test_polygon_max_distance_all_pairs_and_empty(self):
        for polygon in [None, [], [[1, 2]], [[1, 2], [1, 2]]]: self.assertEqual(self.api.polygon_max_pair_distance_px(polygon), 0.0)
        self.assertEqual(self.api.polygon_max_pair_distance_px([[0, 0], [1, 1], ['3', '4'], [0, 0]]), 5.0)
        self.assertEqual(self.api.polygon_max_pair_distance_px([[-3, -4], [3, 4], [0, 1]]), 10.0)


    def test_callback_capture_after_prior_work_before_argument_effects(self):
        for site in ['x', 'y', 'intersection', 'contour']:
            for mode in ['A', 'B', 'missing']:
                with self.subTest(site=site, mode=mode), ExitStack() as scope:
                    events = []
                    value = (0, 0) if site in ['x', 'y'] else 7.0 if site == 'intersection' else [[1, 1], [2, 1], [2, 2]]
                    callbacks = {name: Mock(return_value=value) for name in ['A', 'B', 'C']}
                    target = 'constrained_center_range' if site in ['x', 'y'] else 'rotated_rect_overlap_area' if site == 'intersection' else 'contour_to_polygon'
                    scope.enter_context(patch.object(self.api, target, callbacks['A']))
                    def prior():
                        events.append('prior'); setattr(self.api, target, None if mode == 'missing' else callbacks[mode])
                    def argument():
                        events.append('argument'); setattr(self.api, target, callbacks['C'])
                    if site in ['x', 'y']:
                        class Canvas:
                            def __getitem__(inner, key): argument(); return 100
                        scope.enter_context(patch.object(self.api, 'PREVIEW_CANVAS_SIZE_PX', Canvas()))
                        original_sin = np.sin
                        def sine(value): prior(); return original_sin(value)
                        scope.enter_context(patch.object(np, 'sin', sine))
                        rng = Mock(); rng.integers.return_value = 0
                        roi = (0, 0, 1, 10000) if site == 'x' else (0, 0, 10000, 1)
                        operation = lambda: self.api.random_center_inside_background(rng, (10, 10), 0, roi)
                    elif site == 'intersection':
                        rect = object()
                        def rectangle(*args): prior(); return rect
                        scope.enter_context(patch.object(self.api, 'rotated_rect_tuple', rectangle))
                        class Placed(dict):
                            def __getitem__(inner, key): argument(); return rect
                        operation = lambda: self.api.object_placement_overlap_area((1, 2), (3, 4), 0, [Placed()])
                    else:
                        class Binary:
                            @property
                            def shape(inner): argument(); return (8, 8)
                        binary = Binary(); contour = object(); area_calls = []
                        def area(value):
                            area_calls.append(value)
                            if len(area_calls) == 3: prior()
                            return 100.0
                        scope.enter_context(patch.object(cv2, 'morphologyEx', return_value=binary))
                        scope.enter_context(patch.object(cv2, 'findContours', return_value=([contour], None)))
                        scope.enter_context(patch.object(cv2, 'contourArea', area))
                        operation = lambda: self.api.visible_polygons_from_mask(np.full((8, 8), 255, np.uint8))
                    if mode == 'missing':
                        with self.assertRaises(TypeError): operation()
                    else: operation()
                    self.assertEqual(events, ['prior', 'argument'])
                    for name, callback in callbacks.items(): self.assertEqual(callback.call_count, int(name == mode))

    def test_callback_binding_refreshes_between_axes_and_list_items(self):
        rng = Mock(); rng.integers.return_value = 0
        second = Mock(return_value=(0, 0)); events = []
        def first(*args):
            events.append('first'); self.api.constrained_center_range = second; return (0, 0)
        self.replace('constrained_center_range', first); self.replace('PREVIEW_CANVAS_SIZE_PX', (100, 100))
        self.api.random_center_inside_background(rng, (10, 10), 0, (0, 0, 1, 1))
        self.assertEqual(events, ['first']); second.assert_called_once_with(0, 100, 17)
        rectangle = object(); self.replace('rotated_rect_tuple', Mock(return_value=rectangle))
        second_area = Mock(return_value=3.0)
        def first_area(*args): self.api.rotated_rect_overlap_area = second_area; return 2.0
        self.replace('rotated_rect_overlap_area', Mock(side_effect=first_area))
        self.assertEqual(self.api.object_placement_overlap_area((0, 0), (2, 2), 0, [{'rect': rectangle}, {'rect': rectangle}]), 5.0)
        second_area.assert_called_once_with(rectangle, rectangle)
        contours = [object(), object()]; one = [[1, 1]]; two = [[2, 2]]; second_contour = Mock(return_value=two)
        def first_contour(*args): self.api.contour_to_polygon = second_contour; return one
        self.replace('contour_to_polygon', Mock(side_effect=first_contour))
        with patch.object(cv2, 'findContours', return_value=(contours, None)), patch.object(cv2, 'contourArea', return_value=100.0):
            actual = self.api.visible_polygons_from_mask(np.full((8, 8), 255, np.uint8))
        self.assertEqual(actual, [one, two]); self.assertIs(actual[0], one); self.assertIs(actual[1], two)
        second_contour.assert_called_once_with(contours[1], (8, 8), 0.0035)

    def test_layout_dependency_first_errors_never_retry(self):
        rng = Mock(); rng.integers.return_value = 0
        rect = ((1.0, 1.0), (2.0, 2.0), 0.0)
        random_operation = self.api.random_center_inside_background
        overlap_operation = self.api.object_placement_overlap_area
        operations = [
            ('constrained_center_range', lambda: random_operation(rng, (10, 10), 0, (0, 0, 1, 1)), [1, 2]),
            ('rotated_rect_tuple', lambda: overlap_operation((0, 0), (2, 2), 0, [{'rect': rect}]), [1]),
            ('rotated_rect_tuple', lambda: self.api.placement_box_points((0, 0), (2, 2), 0), [1]),
            ('rotated_rect_overlap_area', lambda: overlap_operation((0, 0), (2, 2), 0, [{'rect': rect}] * 2), [1, 2]),
            ('random_center_inside_background', lambda: self.api.choose_object_center_inside_background(rng, (2, 2), 0, []), [1, 2, 180]),
            ('object_placement_overlap_area', lambda: self.api.choose_object_center_inside_background(rng, (2, 2), 0, []), [1, 2, 180]),
            ('contour_to_polygon', lambda: self.api.visible_polygons_from_mask(np.full((8, 8), 255, np.uint8)), [1, 2]),
            ('visible_polygons_from_mask', lambda: self.api.visible_polygon_from_mask(np.full((8, 8), 255, np.uint8)), [1]),
        ]
        values = {'constrained_center_range': (0, 0), 'rotated_rect_tuple': rect, 'rotated_rect_overlap_area': 2.0,
                  'random_center_inside_background': (0, 0), 'object_placement_overlap_area': 2.0,
                  'contour_to_polygon': [[1, 1]], 'visible_polygons_from_mask': [[[1, 1]]]}
        for target, operation, indices in operations:
            for index in indices:
                with self.subTest(target=target, index=index), ExitStack() as scope:
                    ports = {}
                    for name, value in values.items():
                        if name == 'visible_polygons_from_mask' and target == 'contour_to_polygon': continue
                        ports[name] = scope.enter_context(patch.object(self.api, name, Mock(return_value=value)))
                    scope.enter_context(patch.object(self.api, 'PREVIEW_CANVAS_SIZE_PX', (100, 100)))
                    scope.enter_context(patch.object(cv2, 'findContours', return_value=([object(), object()], None)))
                    scope.enter_context(patch.object(cv2, 'contourArea', return_value=100.0))
                    port = ports[target]; failure = RuntimeError('first-layout-error')
                    port.side_effect = itertools.chain(itertools.repeat(port.return_value, index - 1), [failure], itertools.repeat(port.return_value))
                    with self.assertRaises(RuntimeError) as caught: operation()
                    self.assertIs(caught.exception, failure); self.assertEqual(port.call_count, index)

    def test_new_layout_getter_errors_propagate_without_retry(self):
        from local_inspection_service.training.preview_placement import PreviewPlacement
        from local_inspection_service.training.preview_masks import PreviewMasks
        rng = Mock(); rng.integers.return_value = 0
        rect = ((1.0, 1.0), (2.0, 2.0), 0.0)
        for name, indices in [('canvas', [1, 2]), ('constrained', [1, 2]), ('intersection', [1, 2]), ('contour', [1, 2])]:
            for index in indices:
                with self.subTest(name=name, index=index), ExitStack() as scope:
                    getters = {'canvas': Mock(return_value=(100, 100)), 'constrained': Mock(return_value=lambda *a: (0, 0)),
                               'intersection': Mock(return_value=lambda *a: 2.0), 'contour': Mock(return_value=lambda *a: [[1, 1]])}
                    service = PreviewPlacement(getters['canvas'], getters['constrained'], lambda *a: rect,
                                               getters['intersection'], lambda *a: (0, 0), lambda *a: 2.0)
                    masks = PreviewMasks(getters['contour'], lambda *a: [])
                    scope.enter_context(patch.object(cv2, 'findContours', return_value=([object(), object()], None)))
                    scope.enter_context(patch.object(cv2, 'contourArea', return_value=100.0))
                    port = getters[name]; failure = RuntimeError('getter-first')
                    port.side_effect = itertools.chain(itertools.repeat(port.return_value, index - 1), [failure], itertools.repeat(port.return_value))
                    with self.assertRaises(RuntimeError) as caught:
                        if name in ['canvas', 'constrained']: service.random_center_inside_background(rng, (10, 10), 0, (0, 0, 1, 1))
                        elif name == 'intersection': service.object_placement_overlap_area((0, 0), (2, 2), 0, [{'rect': rect}] * 2)
                        else: masks.visible_polygons_from_mask(np.full((8, 8), 255, np.uint8))
                    self.assertIs(caught.exception, failure); self.assertEqual(port.call_count, index)

    def test_independent_services_no_constructor_reads_and_no_root_access(self):
        from local_inspection_service.training import preview_geometry as geometry, preview_masks as masks
        from local_inspection_service.training.preview_placement import PreviewPlacement
        for module, names in [(geometry, ['constrained_center_range', 'rotated_rect_tuple', 'rotated_rect_overlap_area', 'polygon_max_pair_distance_px']),
                              (masks, ['mask_from_polygon', 'contour_to_polygon'])]:
            for name in names: self.assertIs(getattr(self.api, name), getattr(module, name))
        canvases, contours, services, filters = [], [], [], []
        def build(size, tag):
            canvas = Mock(return_value=size); canvases.append(canvas)
            service = PreviewPlacement(canvas, lambda: geometry.constrained_center_range, geometry.rotated_rect_tuple,
                                       lambda: geometry.rotated_rect_overlap_area,
                                       lambda rng, size, angle, roi: service.random_center_inside_background(rng, size, angle, roi),
                                       lambda center, size, angle, placed: service.object_placement_overlap_area(center, size, angle, placed))
            contour = Mock(side_effect=lambda value, shape, ratio: masks.contour_to_polygon(value, shape, ratio) + [[tag, tag]])
            contours.append(contour)
            visible = masks.PreviewMasks(lambda: contour, lambda mask, ratio: visible.visible_polygons_from_mask(mask, ratio))
            return service, visible
        for size, tag in [((100, 120), 1), ((200, 240), 2)]:
            service, visible = build(size, tag); services.append(service); filters.append(visible)
        for callback in canvases + contours: callback.assert_not_called()
        for name in ['constrained_center_range', 'rotated_rect_tuple', 'rotated_rect_overlap_area',
                     'random_center_inside_background', 'object_placement_overlap_area', 'contour_to_polygon', 'visible_polygons_from_mask']:
            self.replace(name, Mock(side_effect=AssertionError('independent service accessed root')))
        self.replace('PREVIEW_CANVAS_SIZE_PX', None)
        mask = np.zeros((20, 20), np.uint8); mask[2:10, 3:12] = 255
        for index in [1, 0, 1, 0]:
            result = services[index].choose_object_center_inside_background(np.random.default_rng(1), (1000, 1000), 0, [], (0, 0, 1, 1))
            self.assertEqual(result[0], [(50, 60), (100, 120)][index])
            self.assertEqual(result[1]['object_non_overlap_attempts'], 1)
            self.assertEqual(filters[index].visible_polygon_from_mask(mask), [[3, 2], [3, 9], [11, 9], [11, 2], [index + 1, index + 1]])
        self.assertEqual([c.call_count for c in canvases], [4, 4])
        self.assertEqual([c.call_count for c in contours], [2, 2])


if __name__ == '__main__': unittest.main()

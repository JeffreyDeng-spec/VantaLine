#!/usr/bin/env python3
"""Offline bbox benchmark acceptance; no customer data or provider calls."""
import itertools
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from local_inspection_service.training.bbox_benchmark import assignment, box, evaluate, mask_box, measure, select_samples
from collect_doubao_bbox_benchmark import parse_response, prepare


class BenchmarkTests(unittest.TestCase):
    def test_optimal_assignment_not_greedy(self):
        self.assertEqual(set(assignment([[1000.9, 1000.8], [1000.7, 0]])), {(0, 1), (1, 0)})
        rng = random.Random(17)
        for n in range(1, 5):
            for _ in range(20):
                weights = [[rng.randrange(10) for _ in range(n)] for _ in range(n)]
                actual = sum(weights[i][j] for i, j in assignment(weights))
                expected = max(sum(weights[i][p[i]] for i in range(n)) for p in itertools.permutations(range(n)))
                self.assertEqual(actual, expected)

    def test_wrong_class_duplicate_and_missed(self):
        item = lambda c, b: {'class_id': c, 'bbox': b}
        truth = [item('a', [0, 0, 10, 10]), item('b', [20, 20, 30, 30])]
        prediction = [item('x', [0, 0, 10, 10]), item('x', [0, 0, 10, 10])]
        metrics = measure(truth, prediction, 40, 40)
        self.assertEqual((metrics['wrong_class'], metrics['extra'], metrics['missed']), (1, 1, 1))
        duplicate = measure([truth[0]], [truth[0], truth[0]], 40, 40)
        self.assertEqual((duplicate['matched'], duplicate['extra']), (1, 1))

    def test_mask_geometry_and_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'mask.png'
            image = Image.new('L', (4, 4), 0)
            image.putpixel((1, 2), 9)
            image.putpixel((3, 3), 8)
            image.save(path)
            self.assertEqual(mask_box(path, 20, 20, crop=[10, 10, 14, 14]), [11, 12, 12, 13])
            with self.assertRaises(ValueError):
                mask_box(path, 20, 20)
            Image.new('L', (4, 4), 0).save(path)
            with self.assertRaises(ValueError):
                mask_box(path, 4, 4)
            Image.new('RGB', (4, 4), 'red').save(path)
            with self.assertRaises(ValueError):
                mask_box(path, 4, 4)

    def test_owner_real_source_and_content_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'photo.png'
            Image.new('RGB', (4, 4), 'blue').save(path)
            record = {'image_path': str(path), 'owner_user_id': 'mine', 'source_kind': 'real_photo'}
            records = [{**record, 'created_at': 1}, {**record, 'created_at': 2},
                       {**record, 'owner_user_id': 'other', 'image_path': 'must-not-be-read'},
                       {**record, 'source_kind': 'synthetic', 'image_path': 'must-not-be-read'}]
            selected = select_samples(records, 'mine')
            self.assertEqual(len(selected), 1)
            self.assertEqual(selected[0]['created_at'], 2)

    def test_confirmation_exact_coverage_and_failures(self):
        identity = 'f'*64
        sample = {'image_sha256': identity, 'source_kind':'real_photo', 'width': 10, 'height': 10, 'objects': []}
        reference = {'review_status': 'draft', 'owner_user_id':'mine', 'samples': [sample]}
        outputs = {'mask': [{'image_sha256': identity, 'status': 'completed', 'objects': []}],
                   'doubao': [{'image_sha256': identity, 'status': 'completed', 'objects': []}]}
        with self.assertRaises(ValueError):
            evaluate(reference, outputs)
        reference.update(review_status='human_confirmed', confirmed_by='fixture-human')
        self.assertEqual(evaluate(reference, outputs)['winner'], 'tie')
        sample['source_kind'] = 'synthetic'
        with self.assertRaises(ValueError):
            evaluate(reference, outputs)
        sample['source_kind'] = 'real_photo'
        outputs['doubao'][0]['status'] = 'timeout'
        with self.assertRaises(ValueError):
            evaluate(reference, outputs)
        outputs['doubao'] = []
        with self.assertRaises(ValueError):
            evaluate(reference, outputs)

    def test_coordinates_fail_closed(self):
        for value in ([0, 0, 0, 5], [-1, 0, 5, 5], [0, 0, 11, 5], [0, 0, float('nan'), 5], [False, 0, 5, 5]):
            with self.assertRaises(ValueError):
                box(value, 10, 10)

    def test_blind_provider_input_and_source_integrity(self):
        from local_inspection_service.training.bbox_benchmark import digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'original.png'
            Image.new('RGB', (40, 30), 'blue').save(path)
            sample = {'image_path':str(path),'image_sha256':digest(path), 'source_kind':'real_photo','owner_user_id':'mine'}
            manifest = {'owner_user_id':'mine','classes':[{'class_id':'a','name':'part','definition':'visible only','reference_path':str(path)}], 'samples':[sample]}
            self.assertEqual(len(prepare(manifest)[0]),1)
            sample['objects'] = []
            with self.assertRaises(ValueError):
                prepare(manifest)
            del sample['objects']
            sample['owner_user_id'] = 'other'
            with self.assertRaises(ValueError):
                prepare(manifest)
            sample['owner_user_id'] = 'mine'
            Image.new('RGB', (40, 30), 'red').save(path)
            with self.assertRaises(ValueError):
                prepare(manifest)

    def test_provider_mismatch_truncation_and_coordinate_convention(self):
        import json
        model = 'doubao-seed-2-1-pro-260915'
        response = {'model':model,'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'objects':[{'class_id':'a','bbox':[10,5,30,20]}]})}}]}
        self.assertEqual(parse_response(response,(40,30),model)[0]['bbox'],[10,5,30,20])
        with self.assertRaises(ValueError):
            parse_response(response,(40,30),'doubao-seed-evolving')
        response['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ValueError):
            parse_response(response,(40,30),model)
        response['choices'][0]['finish_reason'] = 'stop'
        response['choices'][0]['message']['content'] = json.dumps({'objects':[{'class_id':'a','bbox':[0,0,1000,1000]}]})
        with self.assertRaises(ValueError):
            parse_response(response,(40,30),model)

    def test_explicit_normalized_mapping_never_guessed(self):
        import json
        model = 'doubao-seed-2-1-pro-260915'
        def response(coords):
            return {'model':model,'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'objects':[{'class_id':'a','bbox':coords}]})}}]}
        # Unequal width and height catch swapped axes and wrong common scale.
        self.assertEqual(parse_response(response([100,200,900,1000]),(640,480),model,'normalized_1000')[0]['bbox'],[64,96,576,480])
        with self.assertRaises(ValueError):
            parse_response(response([100,200,900,1000]),(640,480),model)
        with self.assertRaises(ValueError):
            parse_response(response([0,0,1001,1000]),(640,480),model,'normalized_1000')

    def test_fixed_model_failure_stops_without_second_call(self):
        import json
        from unittest.mock import patch, Mock
        import collect_doubao_bbox_benchmark as client
        from local_inspection_service.training.bbox_benchmark import digest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = []
            for index, color in enumerate(('blue','red')):
                path = root/f'{index}.png'; Image.new('RGB',(40,30),color).save(path)
                samples.append({'image_path':str(path),'image_sha256':digest(path),'source_kind':'real_photo','owner_user_id':'mine'})
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps({'owner_user_id':'mine','classes':[{'class_id':'a','name':'part','definition':'visible','reference_path':samples[0]['image_path']}],'samples':samples}))
            response = Mock(status_code=403)
            response.iter_content.return_value = [b'{"error":"unavailable"}']
            context = Mock(); context.__enter__ = Mock(return_value=response); context.__exit__ = Mock(return_value=False)
            with patch.dict('os.environ',{'ARK_API_KEY':'private-test-secret'}), patch('requests.post',return_value=context) as post, patch.object(sys,'argv',['collector','--manifest',str(manifest),'--model','doubao-seed-2-1-pro-260915','--output-dir',str(root/'output')]):
                self.assertEqual(client.main(),1)
                self.assertEqual(post.call_count,1)
            receipt = (root/'output'/'receipt.json').read_text()
            self.assertNotIn('private-test-secret',receipt)
            self.assertEqual(json.loads(receipt)['calls'][0]['status'],'failed')


if __name__ == '__main__':
    unittest.main()

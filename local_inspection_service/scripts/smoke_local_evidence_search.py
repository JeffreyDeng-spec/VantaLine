"""Strict local character-path fixtures, not OCR accuracy certification."""
import unittest
from unittest.mock import patch
from local_inspection_service import evidence_matching as matching, local_evidence_search as search


def observation(text,identity,box):
    return dict(id=identity,type='text',text=text,box=box)


class LocalSearchTests(unittest.TestCase):
    def run_case(self,expected,obs):
        rows=matching.direct([dict(id='e',type='text',state='keep',text=expected)],obs)
        return search.complete(rows,obs)

    def test_same_line_and_original_spans(self):
        obs=[observation('prefix Battery','a',[0,0,140,20]),observation('Pack suffix','b',[145,0,245,20])]
        rows,diag=self.run_case('Battery Pack',obs)
        self.assertEqual(rows[0]['state'],'matched')
        self.assertEqual(rows[0]['evidence'],[dict(evidence_id='a',start=7,end=14),dict(evidence_id='b',start=0,end=5)])
        self.assertEqual(diag['matched'],['e'])

    def test_wrapped_line(self):
        obs=[observation('Do not','a',[0,0,90,20]),observation('heat.','b',[0,25,70,45])]
        self.assertEqual(self.run_case('Do not heat.',obs)[0][0]['state'],'matched')

    def test_punctuation_spacing(self):
        obs=[observation('MODEL:','a',[0,0,100,20]),observation('X1','b',[105,0,140,20])]
        self.assertEqual(self.run_case('MODEL:X1',obs)[0][0]['state'],'matched')

    def test_skipped_not_same_line(self):
        obs=[observation('Do','a',[0,0,20,20]),observation('NOT','b',[25,0,40,20]),observation('heat.','c',[45,0,90,20])]
        self.assertEqual(self.run_case('Do heat.',obs)[0][0]['state'],'review')

    def test_skipped_word_before_wrap(self):
        obs=[observation('Do','a',[0,0,20,20]),observation('NOT','b',[25,0,60,20]),observation('heat.','c',[0,25,60,45])]
        self.assertEqual(self.run_case('Do heat.',obs)[0][0]['state'],'review')

    def test_strict_unequal_characters_never_promoted(self):
        for expected,first,second in [('20V Pack','120V','Pack'),('20V Pack','20v','Pack'),
                ('functioning properly,','functioning','properly.'),('1.5V Pack','15V','Pack'),
                ('NOT','NO','T'),('MODEL: X1','MODEL:','X2')]:
            obs=[observation(first,'a',[0,0,100,20]),observation(second,'b',[105,0,200,20])]
            with self.subTest(expected=expected):
                self.assertNotEqual(self.run_case(expected,obs)[0][0]['state'],'matched')

    def test_distant_and_reversed(self):
        for box in ([1000,0,1100,20],[-100,0,-5,20]):
            obs=[observation('Battery','a',[0,0,100,20]),observation('Pack','b',box)]
            self.assertEqual(self.run_case('Battery Pack',obs)[0][0]['state'],'review')

    def test_source_observation_order_does_not_define_reading_order(self):
        obs=[observation('Battery','a',[0,0,100,20]),observation('Pack','b',[105,0,150,20])]
        self.assertEqual(self.run_case('Battery Pack',list(reversed(obs)))[0][0]['state'],'matched')

    def test_capacity_reported_no_false_success(self):
        obs=[observation('Battery','a',[0,0,100,20]),observation('Pack','b',[105,0,150,20])]
        with patch.object(search,'MAX_OPERATIONS',1):
            rows,diag=self.run_case('Battery Pack',obs)
        self.assertEqual(rows[0]['state'],'review')
        self.assertIn('e',diag['limited_element_ids'])

    def test_duplicate_evidence_ids_rejected(self):
        rows,diag=self.run_case('Battery Pack',[observation('Battery','a',[0,0,100,20]),observation('Pack','a',[105,0,150,20])])
        self.assertEqual(rows[0]['state'],'review')
        self.assertEqual(diag['reason'],'duplicate_evidence_ids')


if __name__=='__main__':unittest.main()

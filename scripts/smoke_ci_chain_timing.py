"""Timing accounting must include later queues and exclude only authorized waits."""
import unittest
from measure_ci_chain import calculate


def run(t):return {'created_at':f'2026-10-11T00:{t}:00Z'}
def jobs(start,end):return [{'status':'completed','started_at':f'2026-10-11T00:{start}:00Z','completed_at':f'2026-10-11T00:{end}:00Z'}]


class ChainTiming(unittest.TestCase):
    def test_raw_human_queue_and_stages_reconcile(self):
        result=calculate(run('00'),run('13'),run('15'),jobs('01','03'),jobs('14','15'),jobs('16','17'),'2026-10-11T00:13:00Z')
        self.assertEqual(result['raw_seconds'],1020)
        self.assertEqual(result['excluded_human_seconds'],600)
        self.assertEqual(result['excluded_initial_pr_queue_seconds'],60)
        self.assertEqual(result['total_seconds'],360)
        self.assertEqual(result['seconds'],dict(pr_full=120,main=120,release=120,handoff=0))
        self.assertFalse(result['passed_budgets']['total'])

    def test_workflow_handoff_counts(self):
        result=calculate(run('00'),run('14'),run('17'),jobs('01','03'),jobs('14','15'),jobs('17','18'),'2026-10-11T00:13:00Z')
        self.assertEqual(result['seconds']['handoff'],180)
        self.assertEqual(result['total_seconds'],420)

    def test_out_of_order_provider_data_is_rejected(self):
        with self.assertRaises(AssertionError):calculate(run('00'),run('02'),run('04'),jobs('01','03'),jobs('02','04'),jobs('04','05'),'2026-10-11T00:02:00Z')


if __name__=='__main__':unittest.main()

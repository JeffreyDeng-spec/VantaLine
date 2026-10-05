"""Conservative native summary proof without Web, database or model calls."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from local_inspection_service.label_inspection.run_summary import MAX_BYTES, project

BASE = dict(id="run",owner_user_id="alice",task_id="task",kind="run",created_at=1.75,status="completed",decision="MATCH")


def check(value):
    return project(json.dumps(value), "run", "alice", "task")


class SummaryProof(unittest.TestCase):
    def test_normal_and_missing_optional_fields(self):
        self.assertEqual(check(BASE), dict(id="run",created_at=1.75,status="completed",decision="MATCH"))
        for key in ("status", "decision"):
            row = dict(BASE); del row[key]
            result = check(row)
            self.assertNotIn(key,result)
            self.assertIn(key,check({**row,key:None}))
            self.assertIsNone(check({**row,key:None})[key])

    def test_unknown_fields_are_validated_not_silently_skipped(self):
        for value in (None, [], 1, "bad"):
            self.assertIsNone(check({**BASE,"import":value}))
        self.assertIsNotNone(check({**BASE,"import":{"version":"v1","discard":"x"},"quality":{"checked":False},"error":"hidden"}))
        for token in ("NaN", "Infinity", "1e10000", "9"*513):
            text=json.dumps(BASE)[:-1]+',"not_used":'+token+'}'
            self.assertIsNone(project(text,"run","alice","task"))
        value=[]
        for _ in range(65):value=[value]
        self.assertIsNone(check({**BASE,"not_used":value}))

    def test_identity_and_kind_must_match_actual_source(self):
        for key,value in (("id","other"),("owner_user_id","bob"),("task_id","different"),("kind","task")):
            self.assertIsNone(check({**BASE,key:value}))
        for value in ([],None,"JSON-string",123):self.assertIsNone(check(value))

    def test_bounded_order_keys_and_types(self):
        for value in (True,None,"1",[],{},float('inf'),float('nan'),2**53+1):
            self.assertIsNone(check({**BASE,"created_at":value}))
        for value in (-1.25,0,2**53):self.assertIsNotNone(check({**BASE,"created_at":value}))
        for key in ("status","decision"):
            for value in (False,1,[],{},"x"*257):self.assertIsNone(check({**BASE,key:value}))
        row=dict(BASE);del row['created_at'];self.assertIsNone(check(row))

    def test_full_json_bounds_and_failures(self):
        self.assertIsNone(check({**BASE,"unused":"x"*MAX_BYTES}))
        for value in (None,3,"{broken",'"string"'):
            self.assertIsNone(project(value,"run","alice","task"))
        self.assertIsNotNone(check({**BASE,"unused":10**511}))
        self.assertIsNone(check({**BASE,"unused":10**512}))


if __name__=='__main__':unittest.main()

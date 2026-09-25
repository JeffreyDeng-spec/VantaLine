"""Same-environment accepted/candidate legacy-list traversal benchmark."""
import gc
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.smoke_label_run_batch import FakeRepository, baseline_register, list_client
from local_inspection_service.label_inspection import api


class TrackedRecord(dict):
    reads = 0

    def get(self, key, default=None):
        if key == "standard_id":
            TrackedRecord.reads += 1
        return super().get(key, default)


def fixture(count):
    repo = FakeRepository(0)
    repo.legacy_rows = {"standards": [
        {"id": f"s{i:03}", "standard_type": "label", "name": f"Old {i:03}",
         "created_at": i, "updated_at": i}
        for i in range(100)
    ], "records": [], "assets": [], "sessions": [], "pages": [], "beta": []}
    for index in range(count):
        group = 0 if index < count // 10 else 1 + index % 99
        repo.legacy_rows["records"].append(TrackedRecord(
            id=f"r{index:05}", standard_id=f"s{group:03}", standard_type="label",
            created_at=index + 100, status="completed", decision="MATCH",
        ))
    # Production LabelRepository caches each owner/kind read within a request.
    def cached_legacy(owner, kind):
        repo.calls.append(("legacy", owner, kind))
        return repo.legacy_rows[kind] if owner == repo.owner else []
    repo.legacy = cached_legacy
    return repo


def measure(register, count, root):
    gc.collect()
    repo = fixture(count)
    TrackedRecord.reads = 0
    tracemalloc.start()
    start = time.perf_counter()
    items = list_client(register, repo, root)
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(items) == 100
    assert len({x["id"] for x in items}) == 100
    assert sum(x["run_count"] for x in items) == count
    return items, elapsed, peak, TrackedRecord.reads


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def main():
    assert os.environ.get("VANTALINE_LABEL_LIST_BASELINE_SOURCE"), "accepted source required"
    accepted = baseline_register()
    output = []
    with tempfile.TemporaryDirectory() as temp:
        for count in (1000, 10000):
            old_times, new_times, old_peaks, new_peaks, old_scans, new_scans = [], [], [], [], [], []
            root = Path(temp)
            measure(accepted, count, root)
            measure(api.register, count, root)
            for iteration in range(5):
                if iteration % 2:
                    new = measure(api.register, count, root)
                    old = measure(accepted, count, root)
                else:
                    old = measure(accepted, count, root)
                    new = measure(api.register, count, root)
                assert new[0] == old[0], count
                old_times.append(old[1]); new_times.append(new[1])
                old_peaks.append(old[2]); new_peaks.append(new[2])
                old_scans.append(old[3]); new_scans.append(new[3])
            assert max(new_scans) < min(old_scans) // 4
            assert p95(new_times) <= max(p95(old_times) * 1.25, p95(old_times) + 0.25)
            assert max(new_peaks) <= max(max(old_peaks) * 1.5, max(old_peaks) + 8 * 1024 * 1024)
            output.append({
                "records": count, "groups": 100, "samples": 5,
                "old_p95_seconds": round(p95(old_times), 3),
                "new_p95_seconds": round(p95(new_times), 3),
                "old_peak_mib": round(max(old_peaks) / 1048576, 2),
                "new_peak_mib": round(max(new_peaks) / 1048576, 2),
                "old_standard_id_reads": min(old_scans),
                "new_standard_id_reads": max(new_scans),
            })
    print(json.dumps({"label_legacy_index_benchmark": output}, sort_keys=True))


if __name__ == "__main__":
    main()
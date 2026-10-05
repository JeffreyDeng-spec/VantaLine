"""Observations outside acceptance timing; synthetic benchmark use only."""
import gc
import json
import time
import sys
try:
    import resource
except ImportError:  # Windows local checks; hosted acceptance uses Linux.
    resource = None


def preserve_primary(action):
    """Evidence failures fail successful work, but never replace a primary failure."""
    pending = sys.exc_info()[1]
    try:
        return action()
    except BaseException:
        if pending is None:
            raise


def snapshot():
    result = {"python_cpu_seconds": time.process_time(),
              "gc_collections": [item["collections"] for item in gc.get_stats()]}
    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result.update(voluntary_switches=usage.ru_nvcsw,
                      involuntary_switches=usage.ru_nivcsw)
    return result


def difference(before, after):
    return {key: ([right-left for left,right in zip(before[key],value)]
                  if isinstance(value,list) else value-before[key])
            for key,value in after.items()}


def prepared_counters(connection):
    try:
        # Do not emit statement text, parameters, DSNs, or exception messages.
        rows = connection.execute(
            "SELECT name, generic_plans, custom_plans FROM pg_prepared_statements ORDER BY name",
            prepare=False).fetchall()
        return {"phase": "post_failure_before_cleanup", "counters": rows,
                "limitation": "session totals, not per-sample attribution or a timed execution plan"}
    except BaseException as exc:
        return {"phase": "post_failure_before_cleanup", "diagnostic_error_type": type(exc).__name__}


def execute_protocol(measure, reports):
    # The protocol is fixed: no CLI repetition reduction, retry or pooled percentile.
    plan = [("AA",0,1000,(0,))] + [
        ("AB",repetition,size,(0,.5,1))
        for repetition in (1,2,3) for size in (1000,10000)]
    accounting = [dict(mode=mode,repetition=repetition,tasks=size,ratios=ratios,status="not_run")
                  for mode,repetition,size,ratios in plan]
    try:
        for index,(mode,repetition,size,ratios) in enumerate(plan):
            accounting[index]["status"] = "running"
            try:
                offset = len(reports)
                measure(mode,repetition,size,ratios,reports)
                actual = [(item["mode"],item["repetition"],item["tasks"],item["synthetic_run_cache_ratio"])
                          for item in reports[offset:]]
                expected = [(mode,repetition,size,ratio) for ratio in ratios]
                assert actual == expected, "missing, duplicate, reordered or mislabeled benchmark cases"
            except BaseException:
                accounting[index]["status"] = "failed"
                raise
            accounting[index]["status"] = "passed"
    finally:
        summary = {"protocol": "label-reader-repeated-v1", "planned_ab_cases": 18,
                   "planned_aa_cases": 1, "groups": accounting}
        reports.append(summary)
        preserve_primary(lambda: print(json.dumps(summary),flush=True))

"""Full first-page native SQL statistics versus the frozen fdb3ce9 endpoint."""
import argparse
import json
from pathlib import Path
from benchmark_label_summary_reads import measure_fixture
from label_benchmark_evidence import preserve_primary
from smoke_label_history_statistics import StatisticsFixture, parent_register

COMPARISON = "native SQL statistics versus frozen fdb3ce9 endpoint"
BASELINE_SHA256 = "ce5b2beaacf9b6d16957ed22470b2cec36da30596ad1fccab6f60cd4bf2bb086"


def measure(mode,repetition,size,depth,ratios,reports):
    measure_fixture(mode,repetition,size,ratios,reports,fixture_type=StatisticsFixture,
                    comparison=COMPARISON,history_depth=depth,baseline_sha256=BASELINE_SHA256)


def execute_history_protocol(measure,reports):
    # Fixed complete repetitions; no CLI reduction, retries or pooled percentiles.
    plan=[("AA",0,1000,None,(0,))]+[
        ("AB",repetition,size,depth,(0,.5,1))
        for repetition in (1,2,3) for size,depth in ((1000,None),(10000,None),(1000,20))]
    accounting=[dict(mode=mode,repetition=repetition,tasks=size,synthetic_history_depth=depth,
                     ratios=ratios,comparison=COMPARISON,baseline_sha256=BASELINE_SHA256,status="not_run")
                for mode,repetition,size,depth,ratios in plan]
    try:
        for index,(mode,repetition,size,depth,ratios) in enumerate(plan):
            accounting[index]['status']='running'
            try:
                offset=len(reports)
                measure(mode,repetition,size,depth,ratios,reports)
                actual=[(r['mode'],r['repetition'],r['tasks'],r['synthetic_history_depth'],
                         r['synthetic_run_cache_ratio'],r['comparison'],r['baseline_sha256'])
                        for r in reports[offset:]]
                expected=[(mode,repetition,size,depth,ratio,COMPARISON,BASELINE_SHA256) for ratio in ratios]
                assert actual==expected,'missing, duplicate, reordered or mislabeled history benchmark cases'
            except BaseException:
                accounting[index]['status']='failed'
                raise
            accounting[index]['status']='passed'
    finally:
        summary=dict(protocol='label-history-repeated-v1',planned_ab_cases=27,planned_aa_cases=1,groups=accounting)
        reports.append(summary)
        preserve_primary(lambda:print(json.dumps(summary),flush=True))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report');args=parser.parse_args()
    reports=[]
    try:
        parent_register()  # Frozen original endpoint AST compilation is outside samples.
        execute_history_protocol(measure,reports)
    finally:
        if args.report:
            def save_report():
                with Path(args.report).open('x',encoding='utf8') as output:json.dump(reports,output,indent=2)
            preserve_primary(save_report)
    print('PASS history A/A plus three complete nine-case repetitions; unchanged query/memory/latency guards')


if __name__=='__main__':main()

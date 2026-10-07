"""Single dispatch-only attribution study. Never a release acceptance runner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

BASE = 'c08d1e92d7a2904b0a488a1384cd25dec1f6c07a'
CANDIDATE = 'fe0c88de246631b8df4445f0fb0120cd151855df'
parser=argparse.ArgumentParser()
parser.add_argument('--base-root',required=True)
parser.add_argument('--candidate-root',required=True)
parser.add_argument('--output-directory',required=True)
args=parser.parse_args()
directory=Path(args.output_directory).resolve()
directory.mkdir(parents=True,exist_ok=False)
script=Path(__file__).with_name('diagnose_label_phases.py')
prelude=Path(__file__).with_name('hosted_phase_diagnostic_prelude.json')
steps=json.loads(prelude.read_text())['steps']
plan=[('base_1',Path(args.base_root).resolve(),BASE),
      ('candidate_1',Path(args.candidate_root).resolve(),CANDIDATE),
      ('candidate_2',Path(args.candidate_root).resolve(),CANDIDATE),
      ('base_2',Path(args.base_root).resolve(),BASE)]
cases=[dict(label=label,sha=sha,status='not_run') for label,root,sha in plan]
accounting=dict(scope='DIAGNOSTIC ONLY; both prior PR273 NoGos remain',
    order=[label for label,root,sha in plan],cases=cases,
    script_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
    runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    prelude_sha256=hashlib.sha256(prelude.read_bytes()).hexdigest(),
    interpretation='Instrumented phases and observer are not original acceptance samples; first error stops remaining cases, no repeats')
checkpoint_index=0
def checkpoint(reason):
    global checkpoint_index
    accounting['checkpoint_reason']=reason
    accounting['checkpoint_epoch']=time.time()
    with (directory/f'accounting_{checkpoint_index:03}.json').open('x') as output:json.dump(accounting,output,indent=2)
    checkpoint_index+=1
def state(root):
    value=dict(tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=root,text=True).strip(),tracked=subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=root,text=True),all_untracked=subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True))
    assert not value['tracked'],'tracked worktree changed'
    return value
checkpoint('initial fixed plan before any prelude')
primary=None
try:
    for case,(label,root,sha) in zip(cases,plan):
        assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==sha
        case['before_prelude']=state(root)
        case['status']='prelude';case['started_epoch']=time.time();checkpoint('prelude starting')
        with (directory/(label+'_prelude.log')).open('x') as output:
            for index,command in enumerate(steps):
                case['prelude_step']=index;checkpoint('prelude block starting')
                output.write(json.dumps(dict(step=index,command=command))+'\n');output.flush()
                subprocess.run(['bash','-eo','pipefail','-c',command],cwd=root,stdout=output,stderr=subprocess.STDOUT,check=True)
        case['before_diagnostic']=state(root)
        case['status']='measuring';checkpoint('diagnostic starting')
        with (directory/(label+'_diagnostic.log')).open('x') as output:
            subprocess.run([sys.executable,'-B',str(script),'--root',str(root),'--expected-sha',sha,
                '--label',label,'--output',str(directory/(label+'_report.json'))],
                cwd=root,stdout=output,stderr=subprocess.STDOUT,check=True)
        case['after_diagnostic']=state(root)
        report=json.loads((directory/(label+'_report.json')).read_text())
        assert not report.get('metadata_errors') and not report.get('observer_errors')
        assert len(report['reports'])==2 and len(report['samples'])==152 and len(report['cleanups'])==154
        case['status']='completed';case['ended_epoch']=time.time();checkpoint('case completed')
except BaseException as error:
    primary=error
    if 'case' in globals():
        case.update(status='failed',failed_phase=case['status'],error_type=type(error).__name__,ended_epoch=time.time())
        try:checkpoint('case failed')
        except BaseException:pass
    raise
finally:
    try:
        accounting['files']=[dict(path=p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in directory.iterdir() if p.is_file()]
        with (directory/'accounting.json').open('x') as output:json.dump(accounting,output,indent=2)
    except BaseException:
        if primary is None:raise
        print('Diagnostic accounting output also failed; original exception retained',file=sys.stderr)
print('Completed one fixed mirrored diagnostic study; no release verdict')

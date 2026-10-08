"""Held-out local YOLO evaluation; unsupported classes have no invented metrics."""
import json
from pathlib import Path
import subprocess
import sys

SCRIPT='''import json, sys
from ultralytics import YOLO
value=YOLO(sys.argv[1]).val(data=sys.argv[2],split="test",augment=False,plots=False,workers=0,device=sys.argv[4])
box=value.box
rows={str(int(c)):{"precision":float(box.p[i]),"recall":float(box.r[i]),"ap50":float(box.ap50[i]),"ap75":float(box.all_ap[i,5]),"ap50_95":float(box.ap[i])} for i,c in enumerate(box.ap_class_index)}
open(sys.argv[3],"w").write(json.dumps(rows,allow_nan=False))
'''


def evaluate(task,run_dir,yaml_path,device):
    root=Path(run_dir);script=root/'evaluate_test.py';output=root/'test_metrics.json'
    script.write_text(SCRIPT,encoding='utf-8')
    with (root/'test.log').open('w') as log:
        subprocess.run([sys.executable,str(script),str(root/'weights'/'best.pt'),str(yaml_path),str(output),str(device)],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
    if output.stat().st_size>65536:raise ValueError('held-out metrics exceed bound')
    rows=json.loads(output.read_text());result={}
    for index,cid in enumerate(task['selected_accessory_ids']):
        unavailable=cid in task['unsupported_by_real_data'] or not task['split_class_instance_counts']['test'].get(cid)
        if unavailable:
            result[cid]={'status':'unavailable','metrics':None,'reason':'unsupported_by_real_data' if cid in task['unsupported_by_real_data'] else 'no_test_instances'}
        else:
            metrics=rows.get(str(index))
            if not metrics:raise ValueError('held-out class metrics missing')
            result[cid]={'status':'evaluated','metrics':metrics}
    return result

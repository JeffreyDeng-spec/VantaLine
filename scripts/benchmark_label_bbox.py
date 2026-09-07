"""Nine-image, at-most-once commissioning runner; output stays outside Git.

The SSH bridge loads the existing production resolver once, keeps credentials in
remote memory, sends at most nine requests, and writes no server code or media.
"""
import argparse
import base64
import hashlib
import io
import json
import selectors
import shlex
import subprocess
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageDraw
from local_inspection_service import label_bbox as b, label_extraction as g

BRIDGE = r'''
import os,sys,subprocess,json,time
pid=subprocess.check_output(['systemctl','show',SERVICE,'-p','MainPID','--value'],text=True).strip()
os.environ.update(dict(x.split('=',1) for x in open('/proc/'+pid+'/environ').read().split('\0') if '=' in x))
sys.path.insert(0,RELEASE)
from local_inspection_service import server
settings=server.ai_detection_settings()
assert settings.get('configured') and settings.get('provider')=='qwen'
assert server.TEXT_INSPECTION_EXTERNAL_VLM_ENABLED
def emit(value):print('BBOX:'+json.dumps(value),flush=True)
emit({'model':settings['model'],'provider':settings['provider'],'configured':True,'timeout_seconds':180})
for number,line in enumerate(sys.stdin):
    if number>=9:break
    payload=json.loads(line);assert payload['model']==settings['model']
    request=server.urllib.request.Request(settings['base_url'],data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+settings['api_key'],'Content-Type':'application/json'},method='POST')
    start=time.monotonic()
    try:
        with server.ai_urlopen(request,settings,timeout=180) as response:body=response.read(1048577)
        if len(body)>1048576:raise ValueError('response_too_large')
        text=body.decode(errors='replace').replace(settings['api_key'],'<redacted>')
        emit({'ok':True,'body':text,'elapsed_ms':round((time.monotonic()-start)*1000)})
    except Exception as exc:
        emit({'ok':False,'error_type':type(exc).__name__,'http_status':getattr(exc,'code',None),'outcome_unknown':not hasattr(exc,'code'),'elapsed_ms':round((time.monotonic()-start)*1000)})
'''


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('--ssh-host',required=True);ap.add_argument('--ssh-key',required=True)
    ap.add_argument('--remote-python',required=True);ap.add_argument('--release',required=True);ap.add_argument('--service',default='vantaline')
    args=ap.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    # Entire rounds are immutable. Resume/review reads existing files, never calls.
    claim=out/'round.json'
    with claim.open('x') as f:json.dump({'method':b.VERSION,'max_requests':9,'started_at':time.time()},f)
    code='SERVICE='+repr(args.service)+'\nRELEASE='+repr(args.release)+'\n'+BRIDGE
    encoded=base64.b64encode(code.encode()).decode()
    command='sudo '+shlex.quote(args.remote_python)+' -u -c '+shlex.quote("import base64;exec(base64.b64decode("+repr(encoded)+"))")
    process=subprocess.Popen(['ssh','-i',args.ssh_key,'-o','BatchMode=yes','-o','ConnectTimeout=20',args.ssh_host,command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ)
    def receive(timeout=230):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if not selector.select(max(0,deadline-time.monotonic())):break
            line=process.stdout.readline()
            if not line:raise RuntimeError('bridge_closed')
            if line.startswith('BBOX:'):return json.loads(line[5:])
        raise TimeoutError('bridge_outcome_unknown')
    try:
        settings=receive();save(out/'settings.json',settings);print(json.dumps(settings),flush=True)
        for number in range(1,10):
            directory=out/str(number);directory.mkdir()
            source=Path(args.input)/f'{number}.jpg';raw=source.read_bytes();original=g.normalized_image(raw)
            image=Image.open(io.BytesIO(original)).convert('RGB')
            data,meta=b.prepare(original)
            (directory/'model-input.jpg').write_bytes(data);(directory/'prompt.txt').write_text(b.PROMPT)
            save(directory/'input.json',{**meta,'source_path':str(source),'source_sha256':hashlib.sha256(raw).hexdigest(),'normalized_sha256':hashlib.sha256(original).hexdigest(),'model':settings['model']})
            save(directory/'attempt.json',{'started_at':time.time(),'max_attempts':1,'status':'attempting'})
            process.stdin.write(json.dumps(b.payload(data,settings['model']))+'\n');process.stdin.flush()
            response=receive()
            body=response.pop('body','');response['response']=b.evidence(body)
            save(directory/'response.json',response)
            verdict={'status':'needs_visual_review','physical_boundary':'unverified','actual_currency_charge':None}
            try:
                if not response['ok']:raise ValueError('provider_failed')
                result,rect=b.parse(body)
                cropped,points,quality=b.crop_rectangle(original,rect)
                (directory/'crop.png').write_bytes(cropped)
                x,y,w,h=quality['bbox']
                assert np.array_equal(np.asarray(Image.open(io.BytesIO(cropped))),np.asarray(image)[y:y+h,x:x+w])
                save(directory/'geometry.json',{**quality,'points':points,'parsed_result':result,'original_pixels_equal':True})
                overlay=image.copy();draw=ImageDraw.Draw(overlay);draw.rectangle((x,y,x+w-1,y+h-1),outline='red',width=max(2,round(image.width/900)))
                overlay.save(directory/'overlay.jpg',quality=92)
                pad=max(20,round(max(w,h)*.15));overlay.crop((max(0,x-pad),max(0,y-pad),min(image.width,x+w+pad),min(image.height,y+h+pad))).save(directory/'overlay-detail.png')
            except ValueError as exc:verdict={'status':'failed','reason':str(exc),'actual_currency_charge':None}
            save(directory/'review.json',verdict)
            print(json.dumps({'image':number,'status':verdict['status'],'elapsed_ms':response.get('elapsed_ms')},ensure_ascii=False),flush=True)
    finally:
        process.stdin.close();selector.close()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.terminate()


if __name__=='__main__':main()

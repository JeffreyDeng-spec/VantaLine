"""Read saved CI output only. Numeric/protocol checks never confer CI/release Go."""
import argparse, hashlib, json, math, re
from pathlib import Path

BASELINE='ce5b2beaacf9b6d16957ed22470b2cec36da30596ad1fccab6f60cd4bf2bb086'
MANUAL='52b31c4afe4ba42d2bd0ee9a5b1111fe3b5390b3e528848ce557e795c0d4227e'
MIB=1048576
def require(condition, message):
    if not condition: raise ValueError(message)
def number(x): return type(x) in (int,float) and math.isfinite(x) and x>=0
def samples(a,n):
    require(isinstance(a,list) and len(a)==n and all(number(v) for v in a),f'invalid {n}-sample series')
    return a
def p95(a,n): return sorted(samples(a,n))[math.ceil(.95*n)-1]
def close(a,b): require(number(a) and number(b) and abs(a-b)<=1e-12*max(1,abs(a),abs(b)),f'derived value differs: {a!r}/{b!r}')
def one(rows,predicate,description):
    values=[x for x in rows if predicate(x)]
    require(len(values)==1,f'{description}: expected once, got {len(values)}')
    return values[0]
def read(path):
    path=Path(path); data=path.read_bytes(); text=data.decode('utf-8-sig'); lines=[]; objects=[]
    try: value=json.loads(text)
    except ValueError: value=None
    if isinstance(value,list): objects=value
    else:
        for n,line in enumerate(text.splitlines(),1):
            line=re.sub(r'^\d{4}-\d\d-\d\dT\S+Z\s+','',line)
            line=re.sub(r'\x1b\[[0-9;]*m','',line);lines.append(line)
            try: obj=json.loads(line)
            except ValueError: continue
            if isinstance(obj,dict):objects.append(obj)
    require(all(isinstance(x,dict) for x in objects),'non-object report entry')
    return objects,{'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},lines
def standard_case(x,peaks=False):
    require(x['samples']==31,'sample count is not31')
    old,new=p95(x['old_seconds'],31),p95(x['new_seconds'],31)
    close(old,x['old_p95_seconds']);close(new,x['new_p95_seconds'])
    op,np=x['old_peak_bytes'],x['new_peak_bytes'];require(number(op) and number(np),'invalid peak')
    if peaks:
        close(max(samples(x['old_peak_samples'],3)),op);close(max(samples(x['new_peak_samples'],3)),np)
    latency=max(old*1.25,old+.01);memory=max(op*1.25,op+MIB)
    close(latency,x['latency_limit']);close(memory,x['memory_limit'])
    require(new<=latency,'P95 regression');require(np<=memory,'peak-memory regression')
    for field in ('old_observations','new_observations'):
        observations=x[field];require(len(observations)==31,'missing CPU/GC diagnostic observations')
        for obs in observations:
            require(number(obs['python_cpu_seconds']) and len(obs['gc_collections'])==3 and all(number(v) for v in obs['gc_collections']),'bad CPU/GC observation')
    return {'key':{k:x[k] for k in ('mode','repetition','tasks','shape','synthetic_history_depth','synthetic_run_cache_ratio') if k in x},'old_p95':old,'new_p95':new,'latency_limit':latency,'old_peak':op,'new_peak':np,'memory_limit':memory,'raw_memory_samples':3 if peaks else None}
def original(rows):
    result={};nraw=0
    for kind,comparison,workloads in [('history','native SQL statistics versus frozen fdb3ce9 endpoint',[(1000,None),(10000,None),(1000,20)]),('reader','cached payloads versus c798 parent reader',[(1000,None),(10000,None)])]:
        cases=[x for x in rows if x.get('comparison')==comparison]
        expected=[('AA',0,1000,None,0)]+[('AB',r,size,depth,ratio) for r in (1,2,3) for size,depth in workloads for ratio in (0,.5,1)]
        key=lambda x:(x['mode'],x['repetition'],x['tasks'],x['synthetic_history_depth'],x['synthetic_run_cache_ratio'])
        require([key(x) for x in cases]==expected,f'{kind} missing/duplicate/reordered case')
        checked=[]
        for x in cases:
            require(x['baseline_sha256']==(BASELINE if kind=='history' else None) and x['synthetic_quality_bytes']==8192,'baseline/quality changed')
            checked.append(standard_case(x))
            for name in ('old_queries','new_queries'):
                q=x[name];require(len(q)==2 and all(type(v)==int and v>=0 for v in q) and q[1]==math.ceil(x['tasks']/64) and q[0]<=q[1]+12,'reader batch/query bound')
            counts=(20000,0) if x['synthetic_history_depth']==20 else (1003,142) if x['tasks']==1000 else (10029,1421)
            require((x['synthetic_run_count'],x['synthetic_empty_tasks'])==counts,'synthetic population changed')
        ledger=one(rows,lambda x:x.get('protocol')==f'label-{kind}-repeated-v1',kind+' ledger')
        require((ledger['planned_aa_cases'],ledger['planned_ab_cases'])==(1,len(expected)-1),'ledger count changed')
        require(all(g['status']=='passed' for g in ledger['groups']),'incomplete/failed ledger')
        require([(g['mode'],g['repetition'],g['tasks'],g.get('synthetic_history_depth'),ratio) for g in ledger['groups'] for ratio in g['ratios']]==expected,'ledger wrong group/order')
        result[kind]=checked;nraw+=len(checked)
    publication=one(rows,lambda x:x.get('p95_method')=='nearest-rank ceil(.95*n)-1','publisher full raw report')['cases']
    require([x['quality_fixture_bytes'] for x in publication]==[256,8192,204800],'publisher population/order')
    checked=[]
    for x in publication:
        values={side:{k:p95(a,31) for k,a in x['samples_seconds'][side].items()} for side in ('before','after')}
        require(all(set(v)=={'settlement','publication','worker_total','competing_claim'} for v in values.values()),'publisher metrics missing')
        for side in values:
            for k,v in values[side].items():close(v,x['p95_seconds'][side][k])
        limits={'publication':.05,**{k:max(values['before'][k]*1.25,values['before'][k]+.005) for k in ('settlement','competing_claim')}}
        require(all(values['after'][k]<=v for k,v in limits.items()),'publisher threshold')
        checked.append({'bytes':x['quality_fixture_bytes'],'p95':values,'limits':limits,'worker_total_guard':False})
    result['publisher']=checked;nraw+=len(checked)
    inherited=[x for x in rows if x.get('benchmark_case') in ('label_run_batch','label_run_payload')]
    require([(x['benchmark_case'],x['tasks']) for x in inherited]==[(k,n) for k in ('label_run_batch','label_run_payload') for n in (1000,10000)],'batch/payload raw order/count')
    checked=[]
    for x in inherited:
        old,new=p95(x['old_seconds'],5),p95(x['new_seconds'],5)
        op,np=max(samples(x['old_peak_bytes'],5)),max(samples(x['new_peak_bytes'],5))
        close(old,x['old_p95_seconds']);close(new,x['new_p95_seconds'])
        latency=max(old*1.25,old+.25);memory=max(op*(1.5 if x['benchmark_case']=='label_run_batch' else 1.25),op+8*MIB)
        close(latency,x['p95_limit_seconds']);close(memory,x['peak_limit_bytes'])
        require(new<=latency and np<=memory,'batch/payload threshold')
        require(x['sample_order']==['old-new','new-old','old-new','new-old','old-new'],'batch sample order')
        if x['benchmark_case']=='label_run_payload':require(x['new_wire_bytes']<x['old_wire_bytes']*.4,'payload wire guard')
        checked.append({'case':x['benchmark_case'],'tasks':x['tasks'],'old_p95':old,'new_p95':new,'latency_limit':latency,'new_peak':np,'memory_limit':memory})
    result['batch_payload']=checked;nraw+=len(checked)
    rounded=one(rows,lambda x:'label_legacy_index_benchmark' in x,'legacy index rounded report')['label_legacy_index_benchmark']
    require([x['records'] for x in rounded]==[1000,10000],'rounded legacy cases')
    result['rounded_legacy']=[]
    for x in rounded:
        require(x['groups']==100 and x['samples']==5,'rounded legacy population/samples')
        require(x['new_standard_id_reads']<x['old_standard_id_reads']//4,'legacy scan guard')
        latency_certain=x['new_p95_seconds']+.0005<=max(max(0,x['old_p95_seconds']-.0005)*1.25,max(0,x['old_p95_seconds']-.0005)+.25)
        memory_certain=x['new_peak_mib']+.005<=max(max(0,x['old_peak_mib']-.005)*1.5,max(0,x['old_peak_mib']-.005)+8)
        require(latency_certain and memory_certain,'rounded legacy interval cannot certify guard; inspect exact source harness result separately, never invent raw samples')
        result['rounded_legacy'].append({**x,'rounding_interval_proves_guard':latency_certain and memory_certain,'raw_samples_available':False,'limitation':'If interval is inconclusive, source harness success is needed; cannot reconstruct raw5 samples from rounded output.'})
    require(nraw==54,'raw case count must be54')
    result['count']={'raw':nraw,'rounded':len(rounded)}
    return result
def beta(rows):
    cases=[x for x in rows if 'projection_contract' in x and 'old_seconds' in x]
    expected=[('AA',0,1000,'large')]+[('AB',r,n,s) for r in (1,2,3) for n,s in ((1000,'small'),(1000,'large'),(10000,'large'),(1000,'fallback'),(10000,'mixed'))]
    key=lambda x:(x['mode'],x['repetition'],x['tasks'],x['shape'])
    require([key(x) for x in cases]==expected,'Beta missing/duplicate/reordered cases')
    checks=[]
    for x in cases:
        require(x['projection_contract']==3 and x['baseline_sha256']==BASELINE,'Beta source contract')
        require(x['compacted_rows']==(0 if x['shape']=='small' else x['tasks']),'Beta population')
        checks.append(standard_case(x,True))
        old=samples(x['old_queries'],31);new=samples(x['new_queries'],31)
        require(all(type(q)==int for q in old+new),'non-integer query count')
        require(len(set(old))==len(set(new))==1 and max(new)<=12,'Beta query bound/constant count')
        require(new[0]==old[0]+(0 if x['mode']=='AA' else 2),'Beta known readiness-query delta')
        for name,expected_probe in [('old_legacy_probes',{'catalog':0,'eligibility':0}),('new_legacy_probes',{'catalog':0,'eligibility':0} if x['mode']=='AA' else {'catalog':1,'eligibility':1})]:
            require(len(x[name])==31 and all(p==expected_probe for p in x[name]),'Beta probe accounting')
    ledger=one(rows,lambda x:x.get('protocol')=='beta-list-summaries-v1','Beta ledger')
    require(ledger['planned_cases']==16 and [key(x) for x in ledger['cases']]==expected and all(x['status']=='passed' for x in ledger['cases']),'Beta ledger incomplete')
    return checks
def manual(rows,ready):
    cases=[x for x in rows if x.get('fixture')=='ManualFixture']
    expected=[('AA',0,1000)]+[('AB',r,n) for r in (1,2,3) for n in (1000,10000)]
    key=lambda x:(x['mode'],x['repetition'],x['tasks'])
    require([key(x) for x in cases]==expected,'manual missing/duplicate/reordered cases')
    checks=[]
    for x in cases:
        require(x['manual_baseline_sha256']==MANUAL and x['tasks_baseline_sha256']==BASELINE,'manual baselines changed')
        require(x['comparison']=='manual full first page versus frozen tasks and complete manual helper','manual comparison changed')
        require(x['populations']=={name:x['tasks'] for name in ('standards','sessions','pages','assets')},'manual populations')
        require(x['derived_published'] is ready,'manual ready/dirty mismatch')
        require(x['old_queries']==10 and x['new_queries']==(10 if x['mode']=='AA' else 7 if ready else 12),'manual query counts')
        checks.append(standard_case(x,True))
    ledger=one(rows,lambda x:x.get('protocol')=='manual-history-repeated-v1','manual ledger')
    require((ledger['planned_aa_cases'],ledger['planned_ab_cases'])==(1,6) and [key(x) for x in ledger['groups']]==expected and all(x['status']=='passed' for x in ledger['groups']),'manual ledger incomplete')
    return checks
def storage(rows):
    xs=[(i,x) for i,x in enumerate(rows) if 'ordinary_disk_database' in x and 'benchmark_database' in x and 'container' in x]
    require(len(xs)==2,'must contain both initial and final complete storage snapshots')
    indices=[i for i,x in enumerate(rows) if 'old_seconds' in x or 'p95_method' in x or 'label_legacy_index_benchmark' in x]
    require(indices and xs[0][0]<min(indices)<=max(indices)<xs[1][0],'storage does not surround complete benchmarks')
    identities=[]
    for _,x in xs:
        identities.append((x['ordinary_disk_database']['system_identifier'],x['benchmark_database']['system_identifier']))
        require(identities[-1][0]!=identities[-1][1],'database instances are not distinct')
        for key in ('ordinary_disk_database','benchmark_database'):
            db=x[key];settings=db['settings']
            require(int(settings['server_version_num'])//10000==16,'Postgres version')
            require(all(settings[k]=='on' for k in ('fsync','synchronous_commit','full_page_writes')),'durability setting weakened')
            require(settings['data_directory']=='/var/lib/postgresql/data' and not settings['temp_tablespaces'],'database location changed')
            require(db['tablespaces']==[['pg_default',''],['pg_global','']],'external tablespace')
        normal=x['ordinary_storage'];require(not normal['tmpfs'] and normal['filesystem_type']!='tmpfs' and normal['wal_path']=='/var/lib/postgresql/data/pg_wal' and normal['oom_killed'] is False,'ordinary database storage altered')
        c=x['container'];require(c['tmpfs']=={'/var/lib/postgresql/data':'rw,noexec,nosuid,size=2147483648'},'benchmark tmpfs mismatch')
        require(c['memory_limit_bytes']==c['memory_swap_limit_bytes']==c['actual_memory_limit_bytes']==3221225472,'cgroup limit')
        require(c['oom_killed'] is False and c['filesystem_capacity_bytes']==2147483648,'OOM/capacity')
        require(0<c['container_peak_memory_bytes']<=3221225472,'memory peak')
        require(all(0<=c[k]<=2147483648 for k in ('filesystem_used_bytes','filesystem_available_bytes')),'filesystem capacity')
        lines=c['mount_wal_capacity_and_cgroup_evidence'].splitlines();events={p[0]:int(p[1]) for line in lines if len(p:=line.split())==2 and p[0] in ('max','oom','oom_kill','oom_group_kill')}
        require({'max','oom','oom_kill'}<=events.keys() and all(v==0 for v in events.values()) and lines[-1]=='0','missing/failed cgroup event/swap evidence')
        require([int(n) for n in lines[lines.index('FILESYSTEM_BYTES')+2].split()]==[c['filesystem_capacity_bytes'],c['filesystem_used_bytes'],c['filesystem_available_bytes']],'raw filesystem telemetry differs from summary')
        require(int(lines[lines.index('MEMORY_PEAK_BYTES')+1])==c['container_peak_memory_bytes'],'raw peak differs from summary')
        require(int(lines[lines.index('MEMORY_MAX_BYTES')+1])==c['actual_memory_limit_bytes'],'raw memory limit differs from summary')
    require(identities[0]==identities[1],'initial/final database system identifiers changed')
    return {'snapshots':2,'distinct_instances_stable':True,'records':[x for _,x in xs]}
def scan(lines):
    return {name:[{'line':i+1,'text':line} for i,line in enumerate(lines) if re.search(pattern,line)] for name,pattern in {'errors_requiring_context':r'Traceback \(most recent call last\)|^FAILED\b|^FAIL:|##\[error\]|No space left on device','pg_negative_lines_requiring_classification':r'\b(ERROR|FATAL|PANIC):','skip_lines_requiring_classification':r'^OK \(skipped=|\.\.\. skipped '}.items()}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',type=Path,required=True);parser.add_argument('--manual-ready',type=Path,required=True);parser.add_argument('--manual-dirty',type=Path,required=True);parser.add_argument('--manual-job-log',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();result={'numeric_protocol_acceptance':False,'overall_second_go':False,'requires':'Separate exact-head completed9-job metadata, functional/negative/skip review, raw/artifact consistency and immutable release gates.'}
    try:
        rows,bind,lines=read(a.backend);result['backend_input']=bind;result['original54plus2']=original(rows);result['beta16']=beta(rows);result['initial_final_storage']=storage(rows);result['backend_diagnostics']=scan(lines)
        manualrows,bind,lines=read(a.manual_job_log);result['manual_job_input']=bind;result['manual_diagnostics']=scan(lines)
        for key,path,ready in [('ready',a.manual_ready,True),('dirty',a.manual_dirty,False)]:
            report,bind,_=read(path);result[key+'_input']=bind;result['manual_'+key]=manual(report,ready)
            rawcases=[x for x in manualrows if x.get('fixture')=='ManualFixture' and x.get('derived_published') is ready]
            require(rawcases==[x for x in report if x.get('fixture')=='ManualFixture'],'manual job raw differs from artifact')
        ledgers=[x for x in manualrows if x.get('protocol')=='manual-history-repeated-v1']
        require(len(ledgers)==2,'manual raw missing/duplicate final ledgers')
        require(ledgers==[one(read(p)[0],lambda x:x.get('protocol')=='manual-history-repeated-v1','artifact ledger') for p in (a.manual_ready,a.manual_dirty)],'manual raw/artifact ledger order mismatch')
        result['numeric_protocol_acceptance']=True
    except Exception as exc:
        result['failure_type']=type(exc).__name__;result['failure']=str(exc)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'output':str(a.output),'bytes':a.output.stat().st_size,'sha256':hashlib.sha256(a.output.read_bytes()).hexdigest(),'numeric_protocol_acceptance':result['numeric_protocol_acceptance'],'overall_second_go':False,'failure':result.get('failure')},ensure_ascii=False))
    return 0 if result['numeric_protocol_acceptance'] else 1
if __name__=='__main__':raise SystemExit(main())

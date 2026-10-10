"""Immutable, task-scoped Ark prefix cache; never chain one photograph's answer."""
import json
import re
import time
from .real_photo_annotation import INPUT_POLICY, PROMPT, image_content
from .real_photo_contracts import MODEL, VERSION, digest, objects

TTL = 3600
MARGIN = 180  # Do not begin a paid annotation near cache expiration.
CACHE_PROTOCOL = 'ark-reference-prefix-v1'


def cache_key(state):
    return digest({'owner': state['owner_user_id'], 'task': state['task_id'],
                   'classes': state['classes'], 'profiles': state['profiles'],
                   'model': MODEL, 'prompt': digest(PROMPT), 'input_policy': INPUT_POLICY,
                   'cache_protocol': CACHE_PROTOCOL})


def usable(state, now=None):
    value = state.get('reference_cache') or {}
    return (value.get('status') == 'ready' and value.get('key') == cache_key(state)
            and value.get('expires_at', 0) > (time.time() if now is None else now) + MARGIN)


def schedule_cache(repo, state, cursor):
    """Only known expiration creates another attempt; uncertain outcomes block."""
    if not state['enabled'] or usable(state):
        return
    cursor.execute(f"SELECT raw_json FROM {repo.table('jobs')} WHERE owner_user_id=%s AND task_id=%s AND kind='annotate' AND status='queued' AND raw_json->>'epoch'=%s",
                   (state['owner_user_id'], state['task_id'], state['epoch']))
    pending = repo.rows(cursor)
    if not pending or (state.get('pause_reason') and not any(j['inputs'].get('explicit') for j in pending)):
        return
    key = cache_key(state)
    previous = state.get('reference_cache') or {}
    if previous.get('key') == key and previous.get('status') in {'queued', 'failed', 'interrupted'}:
        return
    identifier = digest({'key': key, 'epoch': state['epoch'], 'generation': previous.get('generation', 0)+1})
    job = repo.enqueue(cursor, state, 'reference_cache', 'reference-cache:'+identifier,
                       {'classes': state['classes'], 'profiles': state['profiles'], 'cache_key': key,
                        'explicit': any(j['inputs'].get('explicit') for j in pending)})
    state['reference_cache'] = {'key': key, 'job_id': job['id'], 'status': 'queued',
                                'generation': previous.get('generation', 0)+1}


def failure(exc, receipt, stage):
    known = {'ConnectionError','ProxyError','SSLError','ConnectTimeout','ReadTimeout',
             'ReadTimeoutError','Timeout','ProtocolError','RemoteDisconnected','MaxRetryError',
             'NewConnectionError','NameResolutionError','ConnectionResetError','BrokenPipeError',
             'JSONDecodeError','ValueError','OSError','TimeoutError'}
    pending=[exc]; seen=set(); names=[]; errnos=[]
    while pending and len(seen)<16:
        error=pending.pop()
        if id(error) in seen:continue
        seen.add(id(error)); name=type(error).__name__
        if name in known and name not in names:names.append(name)
        number=getattr(error,'errno',None)
        if type(number) is int and number in {32,54,60,61,104,110,111} and number not in errnos:errnos.append(number)
        pending.extend(v for v in (error.__cause__,error.__context__,getattr(error,'reason',None),*error.args) if isinstance(v,BaseException))
    receipt.update(failure_stage=stage,failure_types=names,failure_errnos=errnos)
    return {'status':'failed','objects':[],'error_code':stage+'_failed',
            'error_type':type(exc).__name__ if type(exc).__name__ in known else 'ProviderFailure','receipt':receipt}


def request(body, settings, transport, receipt, validate):
    if settings.get('provider')!='doubao' or settings.get('model')!=MODEL or not settings.get('configured'):
        raise ValueError('fixed bbox model must be explicitly configured')
    body.update(model=MODEL, thinking={'type':'disabled'}, stream=False)
    encoded=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
    if len(encoded)>(32 if 'previous_response_id' not in body else 10)*1024*1024:
        raise ValueError('compressed request exceeds byte bound')
    receipt.update(model=MODEL,prompt_version=VERSION,prompt_sha256=digest(PROMPT),
                   input_policy_version=INPUT_POLICY,cache_protocol=CACHE_PROTOCOL,request_bytes=len(encoded),usage={})
    stage='transport'
    try:
        status, raw=transport(body,settings)
        stage='response_validation'
        receipt.update(http_status=status,response_sha256=digest(raw.encode()),response=raw[:1024*1024])
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError('provider object required')
        receipt['usage']=value.get('usage') or {}
        if status!=200 or value.get('model')!=MODEL or value.get('status')!='completed' or value.get('error') or value.get('incomplete_details'):
            raise ValueError('incomplete provider response or model mismatch')
        return {**validate(value),'status':'completed','receipt':receipt}
    except Exception as exc:
        return failure(exc,receipt,stage)


def create_prefix(classes, settings, read_reference, transport):
    content=[{'type':'input_text','text':PROMPT}]; references=[]
    for c in classes:
        part, meta=image_content(read_reference(c),max_edge=1024)
        if meta['source_sha256']!=c['reference_sha256']:raise ValueError('reference changed after snapshot')
        content.extend([{'type':'input_text','text':json.dumps({k:c[k] for k in ('class_id','name','definition')},ensure_ascii=False)},
                        {'type':'input_image','image_url':part['image_url']['url'],'detail':'high'}])
        references.append({'class_id':c['class_id'],**meta})
    expires=int(time.time())+TTL
    def validate(value):
        identifier=value.get('id')
        if not isinstance(identifier,str) or not re.fullmatch(r'resp_[A-Za-z0-9_-]{1,240}',identifier):
            raise ValueError('invalid cache response identity')
        end=value.get('expire_at',expires)
        if type(end) is not int or not time.time()+MARGIN<end<=expires:
            raise ValueError('invalid cache expiry')
        if value.get('usage',{}).get('output_tokens')!=0:
            raise ValueError('prefix must not generate an answer')
        return {'response_id':identifier,'expires_at':end,'references':references}
    return request({'input':[{'role':'user','content':content}], 'store':True,
                    'caching':{'type':'enabled','prefix':True},'expire_at':expires},
                   settings,transport,{'references':references},validate)


def annotate_cached(image, classes, cache, settings, read_reference, transport):
    if cache.get('expires_at',0)<=time.time()+MARGIN:raise ValueError('reference cache expired')
    # Even a cache hit verifies the frozen source hashes, without encoding/uploading refs.
    for c in classes:
        if digest(read_reference(c))!=c['reference_sha256']:raise ValueError('cached reference changed')
    part,meta=image_content(image,max_edge=2048)
    def validate(value):
        output=value.get('output')
        if not isinstance(output,list) or len(output)!=1:raise ValueError('one output message required')
        message=output[0]
        if message.get('type')!='message' or message.get('role')!='assistant' or message.get('status')!='completed':
            raise ValueError('incomplete localization message')
        content=message.get('content')
        if not isinstance(content,list) or len(content)!=1 or content[0].get('type')!='output_text':
            raise ValueError('localization refusal or ambiguous response')
        parsed=json.loads(content[0]['text'])
        if not isinstance(parsed,dict) or set(parsed)!={'objects'}:raise ValueError('invalid localization schema')
        return {'objects':objects(parsed['objects'],{c['class_id'] for c in classes},meta['width'],meta['height'],normalized=True)}
    return request({'previous_response_id':cache['response_id'],'input':[{'role':'user','content':[
                      {'type':'input_text','text':'仅标注这张新的实拍原图，使用前缀中的类别定义、参考图和坐标协议。'},
                      {'type':'input_image','image_url':part['image_url']['url'],'detail':'high'}]}],
                    'store':True,'caching':{'type':'enabled'},'expire_at':cache['expires_at'],
                    'temperature':0,'max_output_tokens':4096,
                    'text':{'format':{'type':'json_object'}}},settings,transport,
                   {'input':meta,'references':cache['references'],'reference_cache_key':cache['key'],
                    'reference_cache_reused':True,'uploaded_image_count':1},validate)

"""Single-attempt label transport with explicit provider completion validation."""
import json
import time
from urllib.parse import quote


def invoke(body, settings):
    import requests
    provider = settings['provider']
    payload = dict(body, model=settings['model'])
    payload.pop('thinking', None)
    headers = {'Content-Type':'application/json'}
    url = settings['base_url']
    if provider == 'gemini':
        parts = []
        for message in body['messages']:
            for part in message['content']:
                if part['type'] == 'text':
                    parts.append({'text':part['text']})
                else:
                    head, data = part['image_url']['url'].split(',',1)
                    parts.append({'inlineData':{'mimeType':head[5:].split(';')[0],'data':data}})
        payload = {'contents':[{'role':'user','parts':parts}], 'generationConfig':{'temperature':body['temperature'],'maxOutputTokens':body['max_tokens'],'responseMimeType':'application/json'}}
        url = url.rstrip('/')+'/models/'+quote(settings['model'],safe='')+':generateContent'
        headers['x-goog-api-key'] = settings['api_key']
    else:
        headers['Authorization'] = 'Bearer '+settings['api_key']
        payload['response_format'] = {'type':'json_object'}
        if provider == 'doubao':
            payload['thinking'] = {'type':'disabled'}
        elif provider == 'qwen':
            payload['enable_thinking'] = False
        else:
            raise ValueError('标签模型服务商不兼容')
    start = time.monotonic()
    timeout = min(180, float(settings['timeout_seconds']))
    proxy = settings.get('proxy_url_raw')
    with requests.post(url,proxies={'http':proxy,'https':proxy} if proxy else None,json=payload,headers=headers,timeout=(min(10,timeout),timeout),allow_redirects=False,stream=True) as response:
        data = bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data)>1024*1024 or time.monotonic()-start>timeout:
                raise ValueError('模型响应超时或超过容量限制')
        raw = data.decode('utf8',errors='replace').replace(settings['api_key'],'[REDACTED]')
        if provider != 'gemini' or response.status_code != 200:
            return response.status_code,raw
        value = json.loads(raw)
        candidates = value.get('candidates') or []
        if len(candidates)!=1 or candidates[0].get('finishReason')!='STOP':
            raise ValueError('模型响应不完整，无法判定')
        text = ''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
        usage = value.get('usageMetadata',{})
        return 200,json.dumps({'choices':[{'finish_reason':'stop','message':{'content':text}}], 'usage':usage,'provider_response':value},ensure_ascii=False)

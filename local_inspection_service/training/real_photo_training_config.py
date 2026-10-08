"""Freeze executor/base weights without storing signed download URLs or credentials."""
import hashlib
import re
from pathlib import Path
from .real_photo_contracts import digest
from .runpod_submission import (RUNPOD_YOLO_BASE_MODEL_ENV, RUNPOD_YOLO_BASE_MODEL_SHA256_ENV,
                               RUNPOD_YOLO_BASE_MODEL_URL_ENV, RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV)


def file_hash(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def freeze(mode,base,device,environment):
    if mode=='runpod':
        url=str(environment.get(RUNPOD_YOLO_BASE_MODEL_URL_ENV) or '').strip()
        identifier=digest(url.encode()) if url else str(environment.get(RUNPOD_YOLO_BASE_MODEL_ENV) or '/models/vantaline-yolo-base.pt').strip()
        sha=str(environment.get(RUNPOD_YOLO_BASE_MODEL_URL_SHA256_ENV if url else RUNPOD_YOLO_BASE_MODEL_SHA256_ENV) or '').strip()
        if not re.fullmatch('[0-9a-fA-F]{64}',sha):raise ValueError('real-photo RunPod training requires pinned base weights SHA256')
        value={'executor':mode,'base_identifier':identifier,'base_is_url':bool(url),'base_sha256':sha.lower(),
               'device':str(environment.get('VANTALINE_RUNPOD_YOLO_DEVICE') or '').strip()}
    elif mode=='local':
        path=Path(base())
        if not path.is_file():raise ValueError('real-photo local training requires existing pinned weights')
        value={'executor':mode,'base_identifier':str(path),'base_sha256':file_hash(path),'device':str(device())}
    else:raise ValueError('real-photo executor must be local or RunPod')
    return {**value,'epochs':80,'image_size':640,'augmentation':'existing_yolo_train_only'}


def validate_local(config,path,device):
    if config['executor']!='local' or str(path)!=config['base_identifier'] or file_hash(path)!=config['base_sha256'] or str(device)!=config['device']:
        raise ValueError('frozen real-photo training configuration changed')


def validate_runpod(config,payload):
    identifier=digest(payload['base_model_url'].encode()) if payload.get('base_model_url') else payload.get('base_model')
    if config['executor']!='runpod' or identifier!=config['base_identifier'] or payload.get('base_model_sha256','').lower()!=config['base_sha256'] or str(payload.get('device') or '')!=config['device'] or payload['epochs']!=config['epochs'] or payload['imgsz']!=config['image_size']:
        raise ValueError('frozen real-photo RunPod configuration changed')

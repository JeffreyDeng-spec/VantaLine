import pytest
from local_inspection_service.training.real_photo_training_config import freeze,validate_local,validate_runpod


def test_local_weights_drift_is_blocked(tmp_path):
    path=tmp_path/'base.pt';path.write_bytes(b'first weights')
    config=freeze('local',lambda:str(path),lambda:'cpu',{})
    validate_local(config,str(path),'cpu')
    path.write_bytes(b'changed weights')
    with pytest.raises(ValueError):validate_local(config,str(path),'cpu')


def test_runpod_requires_pin_and_does_not_persist_download_url():
    env={'VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL':'https://example.test/private?secret=value'}
    with pytest.raises(ValueError):freeze('runpod',None,None,env)
    env['VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL_SHA256']='a'*64
    config=freeze('runpod',None,None,env)
    assert 'secret' not in str(config)
    payload={'base_model_url':env['VANTALINE_RUNPOD_YOLO_BASE_MODEL_URL'],'base_model_sha256':'a'*64,'epochs':80,'imgsz':640}
    validate_runpod(config,payload)
    payload['base_model_sha256']='b'*64
    with pytest.raises(ValueError):validate_runpod(config,payload)

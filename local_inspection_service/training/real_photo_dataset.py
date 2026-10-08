"""Publish a frozen, group-split YOLO dataset from accepted original pixels only."""
from pathlib import Path
import time
from .real_photo_annotation import canonical
from .real_photo_contracts import approved, digest, encode, objects, split_samples


def build(job, files, output):
    inputs=job['inputs'];samples=inputs['samples'];classes=inputs['classes']
    state={'samples':samples,'classes':classes}
    if len(approved(state))!=len(samples) or len(samples)<20:
        raise ValueError('only current accepted real photos may enter training')
    if split_samples(samples,inputs['splits'])!=inputs['splits']:
        raise ValueError('split snapshot changed')
    ids=[c['class_id'] for c in classes];index={cid:i for i,cid in enumerate(ids)}
    root=Path(output)/('real_dataset_'+job['fingerprint'][:32]);records=[]
    class_counts={split:{cid:0 for cid in ids} for split in ('train','val','test')}
    for s in samples:
        if s.get('source_kind')!='real_photo':raise ValueError('real originals required')
        raw=files.read_bytes(s['source_path'],max_bytes=32*1024*1024)
        clean,meta=canonical(raw)
        if meta['source_sha256']!=s['image_sha256'] or meta!=s['geometry']:
            raise ValueError('frozen original geometry changed')
        labels=objects(s['annotation']['objects'],set(ids),meta['width'],meta['height'])
        split=inputs['splits'][s['source_group']]
        stem=s['image_sha256'];image=root/'images'/split/(stem+'.png');label=root/'labels'/split/(stem+'.txt')
        # Directories are virtual in COS; local test/development needs parents.
        if files.runtime(image) is None:image.parent.mkdir(parents=True,exist_ok=True);label.parent.mkdir(parents=True,exist_ok=True)
        files.write_bytes(image,clean)
        rows=[]
        for obj in labels:
            class_counts[split][obj['class_id']]+=1
            x1,y1,x2,y2=obj['bbox'];w,h=meta['width'],meta['height']
            rows.append(f"{index[obj['class_id']]} {(x1+x2)/2/w:.10f} {(y1+y2)/2/h:.10f} {(x2-x1)/w:.10f} {(y2-y1)/h:.10f}")
        files.write_text(label,'\n'.join(rows)+('\n' if rows else ''),encoding='utf-8')
        records.append({'image':str(image),'labels':str(label),'split':split,'source_sample_id':s['sample_id'],
                        'image_sha256':s['image_sha256'],'source_group':s['source_group'],
                        'annotation_version':s['annotation']['version'],'review_key':s['review']['key'],
                        'review_job_id':s['review']['job_id'],'label_count':len(rows),'sample_type':'real_photo'})
    yaml=root/'dataset.yaml';manifest=root/'manifest.json'
    # Keep a block path line for the existing RunPod relocation contract.
    files.write_text(yaml,'path: '+encode(str(root))+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames: '+encode([c['name'] for c in classes])+'\n',encoding='utf-8')
    value={'id':root.name,'strategy':'real_photo_vlm','owner_user_id':job['owner_user_id'],'task_id':job['task_id'],
           'created_at':int(time.time()),'display_name':'实拍回流数据集','mode':'yolo','model_variant':'yolo',
           'sample_count':len(records),'real_source_count':len({s['image_sha256'] for s in samples}),
           'synthetic_sample_count':0,'generated_negative_sample_count':0,
           'selected_accessory_ids':ids,'class_accessory_map':index,'accessory_class_map':{str(v):k for k,v in index.items()},
           'class_names':[c['name'] for c in classes],'dataset_dir':str(root),'dataset_yaml':str(yaml),
           'manifest_path':str(manifest),'samples':records,'split_assignments':inputs['splits'],
           'unsupported_by_real_data':inputs['unsupported_by_real_data'],'model_profiles':inputs['profiles'],
           'snapshot_fingerprint':job['fingerprint'],'training_job_id':'train_real_'+job['fingerprint'][:32],
           'split_class_instance_counts':class_counts,
           'training_configuration':inputs.get('training_configuration',{}),
           'augmentation_policy':'existing_yolo_train_only'}
    files.write_text(manifest,encode(value),encoding='utf-8')
    return value

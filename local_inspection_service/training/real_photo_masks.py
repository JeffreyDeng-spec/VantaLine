"""Explicit user-requested mask attachment; never changes boxes/reviews/admission."""
import threading
from .real_photo_annotation import image_content, canonical
from .real_photo_contracts import digest, encode
from .real_photo_dispatch import Dispatcher


class MaskDispatcher(Dispatcher):
    def __init__(self,ports,profiles,provider):
        super().__init__(ports);self.profiles=profiles;self.provider=provider

    def tick(self):
        from .real_photo_api import accounts
        claimed=self.operation(lambda r:r.claim(accounts(),{'mask'},'image','real-photo-mask-v1'))
        if not claimed:return
        job,token=claimed;stop=threading.Event()
        def pulse():
            while not stop.wait(5):
                try:
                    if not self.operation(lambda r:r.pulse(job['id'],token)):return
                except Exception:return
        thread=threading.Thread(target=pulse,daemon=True);thread.start()
        try:
            files=self.ports.files();s=job['inputs']['sample']
            raw=files.read_bytes(s['source_path'],max_bytes=32*1024*1024)
            if digest(raw)!=s['image_sha256']:raise ValueError('original changed')
            content=[];input_bytes=0
            for c in job['inputs']['classes']:
                reference=files.read_bytes(c['reference_path'],max_bytes=32*1024*1024)
                if digest(reference)!=c['reference_sha256']:raise ValueError('reference changed')
                part,_=image_content(reference);input_bytes+=len(part['image_url']['url'])
                if input_bytes>48*1024*1024:raise ValueError('mask references exceed byte bound')
                content += [{'type':'text','text':encode({k:c[k] for k in ('class_id','name','definition')})},part]
            part,meta=image_content(raw);content.append(part)
            if input_bytes+len(part['image_url']['url'])>48*1024*1024:raise ValueError('mask input exceeds byte bound')
            settings=self.profiles().resolve('image',job['inputs']['image_profile'])
            provider=self.provider(settings)
            if not self.operation(lambda r:r.pulse(job['id'],token)):raise ValueError('mask request cancelled')
            self.operation(lambda r:r.receipt(job['id'],job['attempt_id'],{'external_call_started':True}))
            result=provider.generate_image('前面的图是任务类别参考；只为最后的实拍图输出附加黑白 mask：可见任务目标为白，其他区域为黑。保持原图尺寸、方向与位置，不补充遮挡部分，不输出框或合成场景。',content,model=settings['model'])
            data=result['bytes'];clean,mask_meta=canonical(data)
            path=self.ports.output(job['owner_user_id'])/('mask_'+job['id']+'.png')
            if files.runtime(path) is None:path.parent.mkdir(parents=True,exist_ok=True)
            files.write_bytes(path,clean)
            attachment={'job_id':job['id'],'source_sha256':s['image_sha256'],'path':str(path),
                        'mask_sha256':digest(clean),'model_profile':job['inputs']['image_profile'],
                        'annotation_version':s.get('annotation',{}).get('version'),'geometry':mask_meta,
                        'mapping_status':'same_size_unverified' if (meta['width'],meta['height'])==(mask_meta['width'],mask_meta['height']) else 'dimension_mismatch',
                        'training_admission_effect':'none','usage':result.get('usage') or result.get('usage_metadata') or {}}
            self.operation(lambda r:r.receipt(job['id'],job['attempt_id'],{'usage':attachment['usage'],'evidence':attachment}))
            def finish(repo):
                def apply(state,current,c):
                    sample=next(x for x in state['samples'] if x['sample_id']==s['sample_id'])
                    sample.setdefault('masks',[]).append(attachment)
                return repo.finish(job['id'],token,attachment,apply)
            self.operation(finish)
        except Exception as exc:
            try:self.operation(lambda r:r.finish(job['id'],token,{'error_type':type(exc).__name__},lambda *a:None,success=False))
            except Exception:pass
        finally:stop.set();thread.join(timeout=6)

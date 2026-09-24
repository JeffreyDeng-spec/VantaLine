"""One stage transition with caller-owned tasks, assets, and job submitters."""
import threading
from typing import Any

from .stage_advance_ports import StageAdvanceAssets, StageAdvanceJobs, StageAdvancePolicy, StageAdvanceRuntime


class PipelineStageAdvancer:
    def __init__(self, policy: StageAdvancePolicy, assets: StageAdvanceAssets,
                 jobs: StageAdvanceJobs, runtime: StageAdvanceRuntime) -> None:
        self.policy = policy
        self.assets = assets
        self.jobs = jobs
        self.runtime = runtime

    def advance(self, task: dict[str, Any], cancel_event: 'threading.Event | None'=None) -> None:
        task_id = str(task.get('id') or '')

        def _check_cancel() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise self.policy.cancelled_error()()

        def _step(note: str, pct: int) -> None:
            """Record a sub-step on the snapshot and mirror it to the stored record so
        the UI shows live advance progress; also a cancellation checkpoint."""
            _check_cancel()
            task['job_note'] = note
            task['progress'] = int(pct)
            self.runtime.persist_progress()(task_id, job_note=note, progress=int(pct), status='running')
        stage = str(task.get('stage') or 'draft')
        accessory_ids = list(task.get('accessory_ids') or [])
        params = dict(task.get('params') or {})
        advance_t0 = self.runtime.monotonic()()
        self.runtime.print()(f'[pipeline.advance] task={task_id} stage={stage} begin', flush=True)
        _check_cancel()
        if stage == 'draft':
            if not accessory_ids:
                raise self.policy.http_error()(status_code=400, detail='流水线任务还没有选择配件')
            detection_method = self.policy.detection_method()(str(task.get('detection_method') or params.get('train_mode') or ''))
            task['detection_method'] = detection_method
            if detection_method == 'ai':
                config = self.assets.load_config()()
                self.assets.activate_ai()(task, config)
                return
            if detection_method == 'locate':
                params['route'] = 'locate'
                params.pop('train_mode', None)
                task.update({'stage': 'library', 'status': 'completed', 'progress': 100, 'params': params, 'linked_view': 'locateAnything', 'last_error': ''})
                task['updated_at'] = int(self.runtime.clock()())
                return
            if 'sample_count' not in params:
                pregenerated = self.policy.consume_recommendation()(task, 'samples')
                if pregenerated is not None:
                    params.update(pregenerated)
                else:
                    recommendation = self.policy.recommend()('samples', accessory_ids)
                    params.update(recommendation['params'])
                    task['agent_reason'] = recommendation['reason']
                    task['agent_source'] = recommendation['source']
            params['train_mode'] = detection_method
            config = self.assets.load_config()()
            accessory_ids = self.policy.canonical_accessories()(config, accessory_ids)
            task['accessory_ids'] = accessory_ids
            _step('准备实拍高亮抠图与背景底板…', 10)
            if not self.assets.prepare()(task, config):
                task['params'] = params
                orchestration = self.policy.orchestration()(task)
                if task.get('status') == 'needs_user_action' and (not isinstance(orchestration.get('pause'), dict)):
                    reason = str(task.get('last_error') or task.get('job_note') or 'Agent/MCP requires user action before sample generation.')
                    self.policy.pause()(task, orchestration, stage=str(orchestration.get('active_stage') or 'pose_image_generation'), reason=reason, suggested_actions=['retry_pose_image_generation', 'replan', 'cancel'])
                    task['params'] = params
                return
            _step('写入实拍抠图素材…', 35)
            pose_assets_changed = self.assets.materialize()(task, config)
            _step('规范化训练素材…', 55)
            try:
                assets_changed = self.assets.normalize()(config, accessory_ids)
            except self.policy.http_error() as exc:
                self.assets.save_config()(config)
                if exc.status_code == 409:
                    detail = str(exc.detail)[:240]
                    task.update({'stage': 'draft', 'status': 'pending', 'progress': 0, 'params': params, 'last_error': detail, 'job_note': '规范化/参考图生成中，完成后再次生成样本。', 'updated_at': int(self.runtime.clock()())})
                    return
                raise
            if assets_changed or pose_assets_changed:
                self.assets.save_config()(config)
            _step('创建样本生成任务…', 80)
            job = self.jobs.sample_generation()(self.jobs.request_type()(selected_accessory_ids=accessory_ids, sample_count=int(params.get('sample_count') or 200), train_mode=str(params.get('train_mode') or 'yolo_ocr'), background_set_id=params.get('background_set_id') or task.get('background_set_id'), pipeline_task_id=task_id, pipeline_task_name=self.jobs.task_name()(task)))
            task.update({'stage': 'samples', 'status': 'running', 'progress': 0, 'params': params, 'samples_task_id': job['job_id'], 'dataset_id': job['job_id'], 'last_error': '', 'job_note': ''})
            self.jobs.log_samples()(task, job)
            self.runtime.print()(f'[pipeline.advance] task={task_id} draft->samples ok elapsed_ms={int((self.runtime.monotonic()() - advance_t0) * 1000)}', flush=True)
        elif stage == 'samples':
            if task.get('status') != 'completed':
                raise self.policy.http_error()(status_code=409, detail='样本还没有生成完成,暂时不能进入训练')
            if not self.policy.training_quality()(task):
                return
            if 'epochs' not in params:
                pregenerated = self.policy.consume_recommendation()(task, 'training')
                if pregenerated is not None:
                    params.update(pregenerated)
                else:
                    recommendation = self.policy.recommend()('training', accessory_ids, int(params.get('sample_count') or 0) or None)
                    params.update(recommendation['params'])
                    task['agent_reason'] = recommendation['reason']
                    task['agent_source'] = recommendation['source']
            _step('启动模型训练任务…', 80)
            job = self.jobs.training()(self.jobs.request_type()(selected_accessory_ids=accessory_ids, dataset_id=str(task.get('dataset_id') or ''), epochs=int(params.get('epochs') or 40), image_size=int(params.get('image_size') or 640), train_mode=str(params.get('train_mode') or 'yolo_ocr'), pipeline_task_id=task_id, pipeline_task_name=self.jobs.task_name()(task)))
            task.update({'stage': 'training', 'status': 'running', 'progress': 0, 'params': params, 'training_task_id': job['job_id'], 'last_error': ''})
            self.jobs.log_training()(task, job)
        elif stage == 'training':
            if task.get('status') != 'completed':
                raise self.policy.http_error()(status_code=409, detail='模型还没有训练完成,暂时不能进入模型库')
            _step('登记训练模型…', 90)
            task.update({'stage': 'library', 'status': 'completed', 'last_error': '', 'job_note': ''})
            self.policy.link_model()(task)
        else:
            raise self.policy.http_error()(status_code=409, detail='任务已经在模型库阶段')
        task['updated_at'] = int(self.runtime.clock()())
        self.runtime.print()(f"[pipeline.advance] task={task_id} stage={stage}->{task.get('stage')} done elapsed_ms={int((self.runtime.monotonic()() - advance_t0) * 1000)}", flush=True)

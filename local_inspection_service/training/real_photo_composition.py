"""Owned feedback/training bridge, with explicit identity and dispatcher lifetime."""
from collections.abc import Callable
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from ..schemas.training import TrainingStartRequest
from ..storage.artifacts.files import BusinessFiles
from .dispatcher_runtime import DispatcherRuntime
from .real_photo_api import FeedbackPorts, FeedbackService, compose
from .real_photo_dispatch import DispatchPorts, Dispatcher
from .real_photo_masks import MaskDispatcher

Record = dict[str, Any]


@dataclass(frozen=True)
class FeedbackInputs:
    repository: Callable[[], Any]
    user: Callable[[], Record]
    tasks: Callable[[], list[Record]]
    authorize: Callable[..., Any]
    config: Callable[[Record], Record]
    references: Callable[[Record], list]
    read: Callable[[str], bytes]
    profiles: Callable[[], Any]
    legacy_state: Callable[[str], Record]
    model_task: Callable[[str, Record], str]


@dataclass(frozen=True)
class TrainingInputs:
    auth_store: Callable[[], Record]
    find_user: Callable[[], Callable[[Record, str], Record | None]]
    identity: ContextVar
    load_config: Callable[[], Record]
    scope_config: Callable[[], Callable[[Record, Record], Record]]
    selected_accessories: Callable[[], Callable[[Record, list[str]], list[Record]]]
    request_type: Callable[[], type[TrainingStartRequest]]
    enqueue: Callable[[], Callable[..., Record]]


@dataclass(frozen=True)
class FeedbackArtifacts:
    files: Callable[[], BusinessFiles]
    output: Callable[[], Callable[[str, str], Path]]


@dataclass(frozen=True)
class LegacyFeedback:
    guard: Callable[[], AbstractContextManager]
    load: Callable[[], Callable[[str], Record]]
    save: Callable[[], Callable[[Record], None]]


class RealPhotoTrainingBridge:
    """Keep original immutable evidence and identity scopes around submission."""

    def __init__(self, *, feedback: Callable[[], FeedbackService],
                 training: TrainingInputs, artifacts: FeedbackArtifacts,
                 legacy: LegacyFeedback, metadata: Callable[[Record], Record]):
        self.feedback, self.training = feedback, training
        self.artifacts, self.legacy = artifacts, legacy
        self.metadata = metadata

    def freeze_original(self, user, data, sha):
        path = self.artifacts.output()('real_photo_feedback', user['id']) / (sha + '.source')
        if not self.artifacts.files().is_file(path):
            self.artifacts.files().write_bytes(path, data)
        elif self.artifacts.files().read_bytes(path) != data:
            raise ValueError('immutable real photo conflict')
        return str(path)

    def disable_legacy(self, task_id):
        with self.legacy.guard():
            state = self.legacy.load()(task_id)
            if any(s.get('label_status') in {'labeling', 'rendering'} for s in state.get('samples', [])):
                raise HTTPException(409, '历史标注正在执行，请等待当前调用结算后切换实拍回流')
            state['settings'] = {**(state.get('settings') or {}), 'enabled': False, 'auto_promote': False}
            self.legacy.save()(state)

    def training_metadata(self, job):
        owner = self.training.find_user()(self.training.auth_store(), job['owner_user_id'])
        if not owner or not owner.get('active', True):
            raise ValueError('training owner account is unavailable')
        token = self.training.identity.set(owner)
        try:
            _, task = self.feedback().task(job['task_id'])
            if self.feedback().classes(task, owner) != job['inputs']['classes']:
                raise ValueError('frozen task category/reference version changed')
            counts = task.get('required_accessory_counts') or {}
            return {'feedback_task_id': job['task_id'], 'required_accessory_counts': {
                c['class_id']: max(0, int(counts.get(c['class_id'], 1))) for c in job['inputs']['classes']}}
        finally:
            self.training.identity.reset(token)

    def submit_training(self, job, dataset):
        owner = self.training.find_user()(self.training.auth_store(), job['owner_user_id'])
        if not owner or not owner.get('active', True):
            raise ValueError('training owner account is unavailable')
        token = self.training.identity.set(owner)
        try:
            if self.metadata(job) != dataset['training_metadata']:
                raise ValueError('frozen task rule snapshot changed')
            config = self.training.scope_config()(self.training.load_config(), owner)
            selected = self.training.selected_accessories()(config, dataset['selected_accessory_ids'])
            if {s['id'] for s in selected} != set(dataset['selected_accessory_ids']):
                raise ValueError('frozen task classes no longer available')
            by_id = {s['id']: s for s in selected}
            selected = [by_id[cid] for cid in dataset['selected_accessory_ids']]
            request = self.training.request_type()(
                selected_accessory_ids=dataset['selected_accessory_ids'],
                sample_count=dataset['sample_count'], train_mode='yolo', dataset_id=dataset['id'])
            return self.training.enqueue()(request, selected, 'train_model', dataset)
        finally:
            self.training.identity.reset(token)


class RealPhotoWorkflows:
    """An inert business graph; registration and native startup are separate."""

    def __init__(self, *, feedback: FeedbackInputs, training: TrainingInputs,
                 artifacts: FeedbackArtifacts, legacy: LegacyFeedback,
                 training_record: Callable[[str], Record | None],
                 configuration: Callable[[], Record],
                 image_provider: Callable[[Record], Any],
                 scope: Callable[[], AbstractContextManager],
                 accounts: Callable[[], set[str]], training_enabled: Callable[[], bool]):
        self.accounts, self.training_enabled = accounts, training_enabled
        self.bridge = RealPhotoTrainingBridge(
            feedback=lambda: self.feedback, training=training, artifacts=artifacts,
            legacy=legacy, metadata=self.training_metadata)
        self.feedback = FeedbackService(FeedbackPorts(
            repository=feedback.repository, user=feedback.user, tasks=feedback.tasks,
            authorize=feedback.authorize, config=feedback.config,
            references=feedback.references, read=feedback.read, profiles=feedback.profiles,
            legacy_state=feedback.legacy_state, model_task=feedback.model_task,
            freeze=self.freeze_original, legacy_disable=self.disable_legacy,
        ))
        self.dispatcher = Dispatcher(DispatchPorts(
            repository=feedback.repository, files=artifacts.files,
            output=lambda owner: artifacts.output()('real_photo_datasets', owner),
            submit=self.submit_training, training=training_record,
            configuration=configuration, metadata=self.training_metadata,
        ))
        self.mask_dispatcher = MaskDispatcher(self.dispatcher.ports, feedback.profiles, image_provider)
        self.runtime = DispatcherRuntime(scope=scope)

    def freeze_original(self, user, data, sha):
        return self.bridge.freeze_original(user, data, sha)

    def disable_legacy(self, task_id):
        return self.bridge.disable_legacy(task_id)

    def training_metadata(self, job):
        return self.bridge.training_metadata(job)

    def submit_training(self, job, dataset):
        return self.bridge.submit_training(job, dataset)

    def register(self, app: FastAPI) -> FeedbackService:
        return compose(app, self.feedback)

    def start(self):
        if not self.accounts():
            return
        self.runtime.start(self.mask_dispatcher.tick,
                           self.dispatcher.tick if self.training_enabled() else None)

    def stop(self):
        self.runtime.stop()

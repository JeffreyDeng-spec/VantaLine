"""Ordinary uploaded-video sampling and analysis; no camera dispatch."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
from fastapi import UploadFile, HTTPException
from .analysis_ports import AnalysisCall
from .upload_ports import UploadAccess, UploadPaths, VideoBackend, FileCopy, VideoResults, VideoFiles, Record
from ..training.real_photo_provenance import group

class VideoUpload:
    def __init__(self, access: UploadAccess, paths: UploadPaths, copies: Callable[[], FileCopy],
                 config: Callable[[], Record], videos: Callable[[], VideoBackend], analyze: AnalysisCall,
                 results: VideoResults, *, files: VideoFiles):
        self.access, self.paths, self.copies = access, paths, copies
        self.config, self.videos, self.analyze, self.results = config, videos, analyze, results
        if files is None:
            raise TypeError("files is required")
        self.files = files

    async def analyze_video(self, file: UploadFile, model_id: str | None) -> dict[str, Any]:
        self.access.ensure()
        self.access.permit(model_id)
        upload_name = self.paths.name()(file.filename)
        video_path = self.paths.directory() / upload_name
        if self.files.runtime(video_path) is not None:
            self.files.copy_stream(video_path, file.file, self.copies().copyfileobj)
            with self.files.local_file(video_path) as local_video:
                return self._analyze_cos_video(local_video, upload_name, model_id)
        with video_path.open('wb') as f:
            self.copies().copyfileobj(file.file, f)
        config = self.config()
        cap = self.videos().VideoCapture(str(video_path))
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail='Could not open video')
        fps = cap.get(self.videos().CAP_PROP_FPS) or 30.0
        stride = max(1, int(fps * float(config['video']['sample_every_seconds'])))
        max_frames = int(config['video']['max_frames'])
        frames = []
        idx = 0
        sampled = 0
        first_preview_url = None
        while sampled < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                request_id = f'{Path(upload_name).stem}_frame_{idx:06d}'
                with group('source_video:'+upload_name):
                    result = self.analyze(frame, request_id, model_id)
                if first_preview_url is None:
                    first_preview_url = result['annotated_url']
                frames.append(self.results.frame(result, idx, fps))
                sampled += 1
            idx += 1
        cap.release()
        passed_frames = sum((1 for frame in frames if frame['passed']))
        overall = len(frames) > 0 and passed_frames == len(frames)
        ai_summary = self.results.summary(frames)
        result = {'request_id': Path(upload_name).stem, 'passed': overall, 'sampled_frames': len(frames), 'passed_frames': passed_frames, 'pass_rate': round(passed_frames / len(frames), 4) if frames else 0.0, 'preview_url': first_preview_url, 'ai': ai_summary, 'frames': frames[:200]}
        return result

    def _analyze_cos_video(self, local_video, upload_name, model_id):
        config = self.config()
        cap = self.videos().VideoCapture(str(local_video))
        try:
            if not cap.isOpened():
                raise HTTPException(status_code=400, detail='Could not open video')
            fps = cap.get(self.videos().CAP_PROP_FPS) or 30.0
            stride = max(1, int(fps * float(config['video']['sample_every_seconds'])))
            max_frames = int(config['video']['max_frames'])
            frames, idx, sampled, first_preview_url = [], 0, 0, None
            while sampled < max_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                if idx % stride == 0:
                    request_id = f'{Path(upload_name).stem}_frame_{idx:06d}'
                    with group('source_video:'+upload_name):
                        result = self.analyze(frame, request_id, model_id)
                    if first_preview_url is None:
                        first_preview_url = result['annotated_url']
                    frames.append(self.results.frame(result, idx, fps))
                    sampled += 1
                idx += 1
        finally:
            cap.release()
        passed_frames = sum(1 for frame in frames if frame['passed'])
        return {'request_id': Path(upload_name).stem, 'passed': len(frames) > 0 and passed_frames == len(frames),
                'sampled_frames': len(frames), 'passed_frames': passed_frames,
                'pass_rate': round(passed_frames / len(frames), 4) if frames else 0.0,
                'preview_url': first_preview_url, 'ai': self.results.summary(frames), 'frames': frames[:200]}

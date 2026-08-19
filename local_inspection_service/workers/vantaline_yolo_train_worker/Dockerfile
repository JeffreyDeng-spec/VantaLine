FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VANTALINE_RUNPOD_YOLO_WORK_ROOT=/workspace/vantaline-yolo-worker \
    VANTALINE_RUNPOD_YOLO_BASE_MODEL=/models/vantaline-yolo-base.pt \
    VANTALINE_RUNPOD_YOLO_MAX_CONCURRENCY=1 \
    VANTALINE_RUNPOD_YOLO_JOB_TIMEOUT_SECONDS=7200 \
    VANTALINE_RUNPOD_YOLO_RETURN_INLINE_MAX_BYTES=52428800

WORKDIR /workspace/vantaline-yolo-train-worker

COPY requirements.txt .
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

COPY handler.py .

CMD ["python", "-u", "handler.py"]

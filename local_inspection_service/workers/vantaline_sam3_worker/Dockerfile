FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ENV PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY handler.py provision.py .
CMD ["python", "-u", "handler.py"]

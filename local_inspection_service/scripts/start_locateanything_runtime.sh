#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV="${LOCATEANYTHING_VENV:-$ROOT/.venv_locateanything}"
HF_HOME_DIR="${HF_HOME:-/mnt/f/CodexHome/.cache/huggingface}"
SNAPSHOT_ROOT="$HF_HOME_DIR/hub/models--nvidia--LocateAnything-3B/snapshots"
DEFAULT_MODEL_ID=""

if [[ -d "$SNAPSHOT_ROOT" ]]; then
  DEFAULT_MODEL_ID="$(find "$SNAPSHOT_ROOT" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1)"
fi

MODEL_ID="${LOCATEANYTHING_MODEL_ID:-$DEFAULT_MODEL_ID}"
LOG_DIR="${LOCATEANYTHING_LOG_DIR:-$ROOT/.locateanything_logs}"

if [[ -z "$MODEL_ID" || ! -e "$MODEL_ID/config.json" ]]; then
  echo "LocateAnything snapshot not found under $SNAPSHOT_ROOT" >&2
  echo "Download nvidia/LocateAnything-3B before starting this runtime." >&2
  exit 1
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Python environment not found: $VENV" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
systemctl --user stop vantaline-locateanything-8000 >/dev/null 2>&1 || true

systemd-run \
  --user \
  --unit=vantaline-locateanything-8000 \
  --same-dir \
  --collect \
  --property=WorkingDirectory="$ROOT" \
  --property=StandardOutput=append:"$LOG_DIR/runtime.log" \
  --property=StandardError=append:"$LOG_DIR/runtime.log" \
  env \
  HF_HOME="$HF_HOME_DIR" \
  HF_HUB_DISABLE_TELEMETRY=1 \
  HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}" \
  TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}" \
  PYTHONPATH="$ROOT" \
  LOCATEANYTHING_MODEL_ID="$MODEL_ID" \
  LOCATEANYTHING_HOST="${LOCATEANYTHING_HOST:-127.0.0.1}" \
  LOCATEANYTHING_PORT="${LOCATEANYTHING_PORT:-8000}" \
  LOCATEANYTHING_DEVICE="${LOCATEANYTHING_DEVICE:-cuda}" \
  LOCATEANYTHING_DTYPE="${LOCATEANYTHING_DTYPE:-bfloat16}" \
  LOCATEANYTHING_QUANTIZATION="${LOCATEANYTHING_QUANTIZATION:-4bit}" \
  PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}" \
  "$VENV/bin/python" \
  "$ROOT/local_inspection_service/scripts/locateanything_server.py"

"""Run the active legacy pipeline decision assertions with offline dependencies."""
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    original_mkdtemp = tempfile.mkdtemp
    with tempfile.TemporaryDirectory(prefix="pipeline-decision-contract-") as root, ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {
            "LOCAL_INSPECTION_ROOT": root,
            "VANTALINE_DATA_STORE": "json",
            "LOCAL_INSPECTION_AUTO_RESUME_WORKER": "0",
            "VANTALINE_LABEL_INSPECTION_ENABLED": "false",
            "YOLO_AUTOINSTALL": "false",
        }))
        # CI may inherit PostgreSQL settings; this decision-only contract must be offline.
        os.environ.pop("VANTALINE_POSTGRES_DSN", None)
        os.environ.pop("DATABASE_URL", None)
        def private_directory(*args, **kwargs):
            kwargs["dir"] = root
            return original_mkdtemp(*args, **kwargs)
        stack.enter_context(patch("tempfile.mkdtemp", side_effect=private_directory))
        for name in ("requests.sessions.Session.request", "urllib.request.urlopen",
                     "subprocess.Popen", "socket.create_connection", "socket.socket.connect"):
            stack.enter_context(patch(name, side_effect=AssertionError("External operation forbidden in decision contract")))
        from local_inspection_service.scripts.smoke_phase3d_pipeline import assert_agent_pipeline_decision_helpers
        assert_agent_pipeline_decision_helpers()
    print("PASS active pipeline decision contracts (full legacy workflow not run)")


if __name__ == "__main__":
    main()

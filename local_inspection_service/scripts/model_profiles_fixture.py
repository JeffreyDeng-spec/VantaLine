"""Explicit legacy-config fixture for JSON business tests; registry tests use PostgreSQL."""
from contextlib import nullcontext
from types import SimpleNamespace
from local_inspection_service.model_profiles.service import PURPOSES

def install(server):
    snapshot=lambda:{purpose:None for purpose in PURPOSES}
    server.model_profile_service=SimpleNamespace(
        resolve=lambda purpose,reference=None:server._legacy_image_generation_settings() if purpose=='image' else server._legacy_load_agent_config() if purpose=='training_assistant' else server._legacy_ai_detection_settings(),
        snapshot=snapshot,snapshot_for_record=lambda record:snapshot(),scope=lambda value=None:nullcontext(),record_call=lambda *args:None)

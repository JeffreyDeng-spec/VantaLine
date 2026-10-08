"""Frozen c25e1bb stream handler body; HTTP decorator intentionally excluded."""
from typing import Any
from local_inspection_service.schemas.configuration import StreamConfig

def update_stream(config_in: StreamConfig) -> dict[str, Any]:
    config = load_config()
    config["stream"] = {
        "enabled": config_in.enabled,
        "source": config_in.source,
        "url": config_in.url,
        "status": "reserved_for_camera_or_rtsp_input",
    }
    save_config(config)
    return {"status": "saved", "stream": config["stream"]}

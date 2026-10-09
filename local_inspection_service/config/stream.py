"""Stream configuration persistence with caller-owned config capabilities."""
from collections.abc import Callable
from typing import Any
from ..schemas.configuration import StreamConfig

Record = dict[str, Any]


class StreamConfiguration:
    def __init__(self, load: Callable[[], Record], save: Callable[[Record], Any]):
        if load is None or save is None:
            raise TypeError("Stream configuration load and save capabilities are required")
        self.load, self.save = load, save

    def update(self, config_in: StreamConfig) -> Record:
        config = self.load()
        config["stream"] = {
            "enabled": config_in.enabled,
            "source": config_in.source,
            "url": config_in.url,
            "status": "reserved_for_camera_or_rtsp_input",
        }
        self.save(config)
        return {"status": "saved", "stream": config["stream"]}

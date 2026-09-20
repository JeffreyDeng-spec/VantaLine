"""Explicit pose chroma policy service without application imports."""
from typing import Any
from .pose_materialization_ports import PoseChromaSources


class PoseChromaPolicy:
    def __init__(self, chroma: PoseChromaSources) -> None:
        self._chroma = chroma

    def choose_agent_mcp_chroma_screen(self, item: dict[str, Any]) -> dict[str, Any]:
        green_fraction = self._chroma.fraction()(item, "green")
        if green_fraction <= self._chroma.threshold():
            screen = self._chroma.screen()("green")
            screen["reference_chroma_fraction"] = round(float(green_fraction), 6)
            return screen
        blue_fraction = self._chroma.fraction()(item, "blue")
        red_fraction = self._chroma.fraction()(item, "red")
        chosen = "blue" if blue_fraction <= self._chroma.threshold() else "red"
        if chosen == "red" and red_fraction > self._chroma.threshold():
            chosen = "blue"
        screen = self._chroma.screen()(chosen)
        screen["reference_green_fraction"] = round(float(green_fraction), 6)
        screen["reference_blue_fraction"] = round(float(blue_fraction), 6)
        screen["reference_red_fraction"] = round(float(red_fraction), 6)
        return screen

"""Provider JSON, data-URL and image payload codecs without application imports."""
from collections.abc import Callable
from typing import Any, Protocol
from pathlib import Path
import base64
import binascii
import mimetypes
import json
import re

def normalize_ai_json_root(parsed: Any) -> dict[str, Any] | None:
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        dict_items = [item for item in parsed if isinstance(item, dict)]
        if dict_items and all("accessory_id" in item for item in dict_items):
            return {"detections": dict_items, "rule": {"counts": {}}}
        if len(dict_items) == 1 and len(parsed) == 1:
            return dict_items[0]
    return None

def ai_json_text_candidates(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    for match in re.finditer(r"```(?:json|JSON)?\s*([\s\S]*?)\s*```", raw):
        fenced = match.group(1).strip()
        if fenced:
            candidates.insert(0, fenced)
    if raw.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", raw)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
        if stripped and stripped not in candidates:
            candidates.insert(0, stripped)
    return candidates

class ProviderPayloadParser:
    def __init__(self, candidates: Callable[[], Callable[[str], list[str]]],
                 normalize: Callable[[], Callable[[Any], dict[str, Any] | None]],
                 error: Callable[[], type[Exception]]):
        self.candidates, self.normalize, self.error = candidates, normalize, error

    def parse_ai_json_object(self, text: str) -> dict[str, Any]:
        decoder = json.JSONDecoder()
        for candidate in self.candidates()(text):
            try:
                normalized = self.normalize()(json.loads(candidate))
                if normalized is not None:
                    return normalized
            except json.JSONDecodeError:
                pass
            for index, char in enumerate(candidate):
                if char not in '{[':
                    continue
                try:
                    parsed, _ = decoder.raw_decode(candidate[index:])
                except json.JSONDecodeError:
                    continue
                normalized = self.normalize()(parsed)
                if normalized is not None:
                    return normalized
        raise self.error()('AI provider did not return a parseable JSON object')

    def data_url_payload(self, data_url: str) -> tuple[str, str]:
        header, _, payload = str(data_url or '').partition(',')
        if not payload or ';base64' not in header:
            raise self.error()('AI image payload was not a base64 data URL')
        mime_type = header.removeprefix('data:').split(';', 1)[0] or 'image/jpeg'
        return (mime_type, payload)

class BinaryReader(Protocol):
    def read_bytes(self, path: Path) -> bytes: ...


def decode_b64_image(value: Any) -> bytes | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("data:"):
        _, _, text = text.partition(",")
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error):
        return None



class ImagePayloadCodec:
    def __init__(self, files: Callable[[], BinaryReader],
                 decoder: Callable[[], Callable[[Any], bytes | None]],
                 candidates: Callable[[], Callable[[Any], list[dict[str, Any]]]]) -> None:
        self.files, self.decoder, self.candidates = files, decoder, candidates

    def image_file_payload(self, path: Path) -> dict[str, str]:
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        return {
            "name": path.name,
            "mime_type": mime_type,
            "data": base64.b64encode(self.files().read_bytes(path)).decode("ascii"),
        }


    def windows_worker_image_response_bytes(self, payload: dict[str, Any]) -> bytes:
        for key in ("b64_json", "base64", "image_base64"):
            image_bytes = self.decoder()(payload.get(key))
            if image_bytes:
                return image_bytes
        for item in self.candidates()(payload):
            for key in ("b64_json", "base64", "image_base64"):
                image_bytes = self.decoder()(item.get(key))
                if image_bytes:
                    return image_bytes
        raise RuntimeError("Windows Worker image fallback response did not include base64 PNG bytes.")

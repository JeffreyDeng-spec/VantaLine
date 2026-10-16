"""Freeze literal business errors; dynamic provider/file exceptions stay private."""
import ast
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_inspection_service.privacy.presentation import SENSITIVE

TARGET = ROOT / "local_inspection_service/privacy/public_errors.json"
PRIVATE_PATH = re.compile(r"(?:^|\s)(?:/|[A-Za-z]:[\\/])|\.(?:pt|pth|onnx|bin|ckpt|safetensors|gguf|weights)\b", re.I)
INTERNAL_DETAIL = re.compile(r"api[_ -]?key|base[_ -]?url|proxy|provider|backbone|architecture|traceback|密钥|供应商|模型配置|权重", re.I)


def expected():
    # Reviewed fixed business text emitted by the bounded text-image limit.
    values = {"文字类配件最多上传 2 张图片", "文字类配件只能上传图片，不能上传视频或其它文件"}
    for source in (ROOT / "local_inspection_service").rglob("*.py"):
        if "scripts" in source.relative_to(ROOT / "local_inspection_service").parts:
            continue
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if not name.endswith(("Error", "Exception")):
                continue
            for item in [*node.args, *(part.value for part in node.keywords if part.arg == "detail")]:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    value = item.value
                    if value and not SENSITIVE.search(value) and not PRIVATE_PATH.search(value) and not INTERNAL_DETAIL.search(value):
                        values.add(value)
    return json.dumps(sorted(values), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    output = expected()
    if "--check" in sys.argv:
        assert TARGET.read_text(encoding="utf-8") == output, "Stale public business error contract"
    else:
        TARGET.write_text(output, encoding="utf-8")
    print("Public business error contract passed")

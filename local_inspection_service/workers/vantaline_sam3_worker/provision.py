"""Explicit one-time weight provisioning; never called by the inference worker."""
import hashlib
import os
from handler import MODEL_DIR, REVISION, WEIGHTS_SHA256


def provision():
    token = os.environ["HF_TOKEN"]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "processor_config.json", "model.safetensors"):
        destination = MODEL_DIR / name
        if destination.exists():
            if name != "model.safetensors":
                continue
            with destination.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest == WEIGHTS_SHA256:
                continue
            raise RuntimeError("existing_weights_checksum_mismatch")
        os.environ["HF_HUB_OFFLINE"] = "0"
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download("facebook/sam3", name, revision=REVISION,
                                    token=token, local_dir=str(MODEL_DIR))
        if name == "model.safetensors":
            with open(downloaded, "rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != WEIGHTS_SHA256:
                    raise RuntimeError("download_checksum_mismatch")
    print("SAM3 provisioning complete; weights verified", flush=True)


if __name__ == "__main__":
    import runpod
    def bootstrap(event):
        if event.get("input") != {"action": "provision_sam3"}:
            return {"ok": False, "error": "invalid_bootstrap_request"}
        try:
            provision()
            return {"ok": True, "revision": REVISION, "weights_sha256": WEIGHTS_SHA256}
        except Exception as exc:
            return {"ok": False, "error": type(exc).__name__}
    runpod.serverless.start({"handler": bootstrap})

#!/usr/bin/env python3
"""Build a small external POI bundle; no downloads happen during user imports.

Only Maven Central HTTPS artifacts; verify published checksums (SHA-512 where
available, legacy SHA-1 otherwise), then record SHA-256 for deployment validation.
The produced manifest pins every downloaded jar and the compiled helper.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parents[1]
ARTIFACTS = [
    ("org.apache.poi", "poi", "5.5.1"), ("org.apache.poi", "poi-scratchpad", "5.5.1"),
    ("commons-codec", "commons-codec", "1.20.0"), ("org.apache.commons", "commons-collections4", "4.5.0"),
    ("org.apache.commons", "commons-math3", "3.6.1"), ("commons-io", "commons-io", "2.21.0"),
    ("com.zaxxer", "SparseBitSet", "1.3"), ("org.apache.logging.log4j", "log4j-api", "2.24.3")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    jars = output / "lib"; jars.mkdir(exist_ok=True)
    hashes = {}
    locked = json.loads((ROOT / "local_inspection_service/workers/doc_image_extractor/dependencies.json").read_text())
    for group, name, version in ARTIFACTS:
        filename = f"{name}-{version}.jar"
        url = f"https://repo.maven.apache.org/maven2/{group.replace('.', '/')}/{name}/{version}/{filename}"
        algorithm = "sha512"
        try:
            response = urllib.request.urlopen(url + ".sha512", timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code != 404: raise
            algorithm = "sha1"
            response = urllib.request.urlopen(url + ".sha1", timeout=30)
        with response:
            expected = response.read(4096).decode().split()[0].lower()
        if len(expected) != (128 if algorithm == "sha512" else 40) or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("invalid upstream checksum")
        target = jars / filename
        if not target.exists() or hashlib.new(algorithm, target.read_bytes()).hexdigest() != expected:
            with urllib.request.urlopen(url, timeout=60) as response: data = response.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024 or hashlib.new(algorithm, data).hexdigest() != expected:
                raise ValueError("jar checksum failed")
            target.write_bytes(data)
        hashes[f"lib/{filename}"] = hashlib.sha256(target.read_bytes()).hexdigest()
        if hashes[f"lib/{filename}"] != locked[f"lib/{filename}"]:
            raise ValueError("dependency differs from checked-in SHA-256 lock")
        print(filename, target.stat().st_size, flush=True)
    source = ROOT / "local_inspection_service/workers/doc_image_extractor/DocImages.java"
    classes = output / "classes"; classes.mkdir(exist_ok=True)
    subprocess.run(["javac", "--release", "11", "-cp", str(jars / "*"), "-d", str(classes), str(source)], check=True)
    subprocess.run(["jar", "--create", "--file", str(output / "doc-images.jar"), "-C", str(classes), "."], check=True)
    hashes["doc-images.jar"] = hashlib.sha256((output / "doc-images.jar").read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({"version": "doc-images-v1", "poi": "5.5.1", "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "files": hashes}, indent=2))
    print("Bundle built:", output)


if __name__ == "__main__": main()

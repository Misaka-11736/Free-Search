"""Explicit online preparation; runtime never calls this script."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MODELS = json.loads((ROOT / "packaging/models.lock.json").read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", default=list(MODELS))
    args = parser.parse_args()
    os.environ["HF_HOME"] = str(ROOT / "private" / "hf-cache")
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import snapshot_download
    manifest_path = ROOT / "models" / "manifest.json"
    manifest_path.parent.mkdir(exist_ok=True)
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name in args.names:
        info = MODELS[name]
        repo = info["repository"]
        patterns = [p.replace("\\", "/") for p in info["files"]]
        print(f"Downloading {name}: {repo}@{info['revision']}", flush=True)
        target = ROOT / "models" / name
        snapshot_download(repo, revision=info["revision"], local_dir=target,
                          allow_patterns=patterns, max_workers=2)
        for relative, expected in info["files"].items():
            with (target / relative).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Downloaded checksum mismatch: {name}/{relative}")
        shutil.copytree(ROOT / "docs/third_party/models" / name, target, dirs_exist_ok=True)
        manifest[name] = info
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Ready: {name}", flush=True)


if __name__ == "__main__":
    main()

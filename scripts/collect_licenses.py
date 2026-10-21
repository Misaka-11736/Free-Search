"""Collect installed licenses and notices without importing ML libraries or downloading.

Usage: .venv/Scripts/python scripts/collect_licenses.py --output dist/licenses
The manifest records all installed distributions, including those without license text.
Upstream supplements in docs/third_party are copied with their provenance records.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
LICENSE_NAME = re.compile(r"^(licen[sc]e|notice|copying|copyright|authors)(?:[._-].*)?$", re.I)


def is_notice(path: Path) -> bool:
    return ((LICENSE_NAME.match(path.name) is not None or any(
                part.lower() in {"licenses", "license", "licences"} for part in path.parts[:-1]))
            and path.suffix.lower() not in {".py", ".pyc", ".pyd", ".dll", ".so"})


def collect(output: Path, model_dir: Path) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"distributions": [], "models": [], "files": [], "unresolved": []}

    def copy(source: Path, relative: Path, origin: str):
        # Distribution RECORD paths may contain ../; preserve names without traversal.
        relative = Path(*[part for part in relative.parts if part not in {"..", "."}])
        target = output / relative
        if not target.resolve().is_relative_to(output):
            raise ValueError(f"Unsafe license target: {relative}")
        if source.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        data = target.read_bytes()
        manifest["files"].append({"path": relative.as_posix(), "origin": origin,
                                  "sha256": hashlib.sha256(data).hexdigest()})

    distributions = sorted(metadata.distributions(), key=lambda d: (d.metadata["Name"] or "").lower())
    for distribution in distributions:
        name = distribution.metadata["Name"] or "unknown"
        version = distribution.version
        folder = re.sub(r"[^a-zA-Z0-9._-]", "_", f"{name}-{version}")
        count = 0
        for record in distribution.files or []:
            relative = Path(str(record))
            if not is_notice(relative):
                continue
            source = Path(distribution.locate_file(record))
            if source.is_file():
                copy(source, Path("packages") / folder / relative, f"installed distribution {name}=={version}")
                count += 1
        manifest["distributions"].append({
            "name": name, "version": version,
            "license_expression": distribution.metadata.get("License-Expression"),
            "license": distribution.metadata.get("License"),
            "license_files": count,
        })
        if not count:
            manifest["unresolved"].append(f"{name}=={version}: no installed license/notice text found")

    # Python's own license is outside package RECORD files.
    import sys
    for root in {Path(sys.base_prefix), Path(sys.prefix)}:
        for name in ("LICENSE.txt", "LICENSE", "LICENSE.md"):
            source = root / name
            if source.is_file():
                copy(source, Path("python") / name, "Python runtime")

    # Copy only cards/licenses/provenance; never model weights or tokenizer data.
    model_manifest = model_dir / "manifest.json"
    revisions = json.loads(model_manifest.read_text(encoding="utf-8-sig")) if model_manifest.exists() else {}
    if model_manifest.exists():
        copy(model_manifest, Path("models/weights-manifest.json"), "downloaded model revision/checksum manifest")
    for directory in sorted(model_dir.iterdir()) if model_dir.is_dir() else []:
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        has_license = False
        for source in directory.rglob("*"):
            if not source.is_file() or ".cache" in source.parts:
                continue
            if is_notice(source) or source.name in {"README.md", "license-provenance.json"}:
                copy(source, Path("models") / directory.name / source.relative_to(directory),
                     "downloaded model card or upstream supplemental license")
                has_license |= is_notice(source)
        info = revisions.get(directory.name, {})
        manifest["models"].append({"name": directory.name, "repository": info.get("repository"),
                                    "revision": info.get("revision"), "has_license_text": has_license})
        if not has_license:
            manifest["unresolved"].append(f"model {directory.name}: license text missing; README is not full license text")

    supplements = ROOT / "docs" / "third_party"
    if supplements.is_dir():
        for source in supplements.rglob("*"):
            if source.is_file():
                copy(source, Path("upstream") / source.relative_to(supplements), "upstream supplement; see provenance.json")
    for name in ("THIRD_PARTY_NOTICES.md", "BINARY_LICENSE.txt", "requirements-lock.txt"):
        source = ROOT / name
        if source.is_file():
            copy(source, Path(name), "Free Search distribution documentation")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "licenses")
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models")
    args = parser.parse_args()
    manifest = collect(args.output, args.model_dir)
    print(json.dumps({"output": str(args.output.resolve()), "files": len(manifest["files"]),
                      "distributions": len(manifest["distributions"]),
                      "unresolved": manifest["unresolved"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

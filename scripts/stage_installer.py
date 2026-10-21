"""Combine both edition entries with one runtime and one verified model copy."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def stage(program: Path, output: Path):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "dist"):
        raise ValueError("Installer staging must stay inside dist/.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use an empty staging directory to avoid shipping stale files.")
    manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8-sig"))
    for directory, info in manifest.items():
        for name, expected in info["files"].items():
            source = ROOT / "models" / directory / name
            with source.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Model checksum mismatch: {source.name}")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(program / "_internal", output / "_internal")
    for edition in ("offline", "api"):
        shutil.copy2(program / "FreeSearch-offline.exe", output / f"FreeSearch-{edition}.exe")
        (output / "_internal" / f"edition-FreeSearch-{edition}.json").write_text(
            json.dumps({"edition": edition}), encoding="utf-8")
    shutil.copytree(ROOT / "models", output / "models", ignore=shutil.ignore_patterns(".cache"))
    shutil.copytree(ROOT / "dist/licenses", output / "licenses")
    shutil.copytree(ROOT / "docs", output / "docs")
    for name in ("README.md", "LICENSE", "BINARY_LICENSE.txt", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copy2(ROOT / "packaging/installed.json", output / "installed.json")
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program-dir", type=Path, default=ROOT / "dist/release-build/FreeSearch-offline")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/installer-stage/FreeSearch")
    args = parser.parse_args()
    stage(args.program_dir, args.output_dir)

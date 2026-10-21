"""Prepare local portable editions and separate program/model ZIPs (no private indexes)."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist/releases"
OUT.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--programs-only", action="store_true", help="更新 EXE 包，复用已生成的模型包")
args = parser.parse_args()


def archive(name, entries):
    target = OUT / name
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as output:
        for source, relative in entries:
            output.write(source, relative)
    with target.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    target.with_suffix(".zip.sha256").write_text(checksum + "  " + target.name + "\n", encoding="ascii")
    print(json.dumps({"file": name, "bytes": target.stat().st_size, "sha256": checksum}), flush=True)


def files(directory, prefix):
    return [(p, (Path(prefix) / p.relative_to(directory)).as_posix())
            for p in sorted(directory.rglob("*"))
            if p.is_file() and not any(part in {".cache", "runtime-data", "__pycache__"}
                                       for part in p.relative_to(directory).parts)]


manifest = json.loads((ROOT / "models/manifest.json").read_text(encoding="utf-8"))
for name, model in manifest.items():
    for relative, expected in model["files"].items():
        with (ROOT / "models" / name / relative).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Model checksum mismatch: {name}/{relative}")

for edition in ("offline", "api"):
    program = ROOT / "dist" / f"FreeSearch-{edition}"
    if not (program / f"FreeSearch-{edition}.exe").is_file():
        raise FileNotFoundError(f"Build {edition} before packaging")
    actual = json.loads((program / "_internal/edition.json").read_text(encoding="utf-8-sig"))
    if actual["edition"] != edition:
        raise ValueError(f"Wrong edition flag: {edition}")
    shutil.copytree(ROOT / "dist/licenses", program / "licenses", dirs_exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, program / name)
    shutil.copy2(ROOT / "docs/QUICKSTART.zh-CN.md", program / "使用说明.md")
    entries = [(p, relative) for p, relative in files(program, program.name)
               if "models" not in p.relative_to(program).parts]
    archive(f"FreeSearch-{edition}-program.zip", entries)
    # Make this machine's portable directory immediately runnable with no arguments.
    if not args.programs_only or not (program / "models/manifest.json").exists():
        shutil.copytree(ROOT / "models", program / "models", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".cache"))

if not args.programs_only:
    for name in manifest:
        entries = files(ROOT / "models" / name, f"models/{name}")
        archive(f"FreeSearch-model-{name}.zip", entries)
    archive("FreeSearch-model-manifest.zip", [(ROOT / "models/manifest.json", "models/manifest.json")])

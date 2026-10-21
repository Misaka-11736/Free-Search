"""Create a source-only upload archive using an explicit allowlist."""
from pathlib import Path
import hashlib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ["README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "pyproject.toml",
         "requirements-lock.txt", ".gitignore", ".gitattributes", "CONTEXT.md", "BINARY_LICENSE.txt"]
FOLDERS = ["src", "tests", "scripts", "evaluation", "docs", "packaging", ".github"]
target = ROOT / "dist/releases/FreeSearch-source.zip"
target.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for item in FILES:
        archive.write(ROOT / item, "Free-Search/" + item)
    for folder in FOLDERS:
        for path in (ROOT / folder).rglob("*"):
            if not path.is_file() or any(x == "__pycache__" or x.endswith(".egg-info") for x in path.parts):
                continue
            archive.write(path, "Free-Search/" + path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(target) as archive:
    assert not any(n.split("/")[1] in {"private", "models", "runtime-data", ".venv", "build"}
                   for n in archive.namelist())
with target.open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
target.with_suffix(".zip.sha256").write_text(checksum + "  " + target.name + "\n", encoding="ascii")
print(target)

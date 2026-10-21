"""Verify and package the dependency sources pinned in the public inventory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
from zipfile import ZipFile, ZIP_STORED


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/third_party/source-provenance.json"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def package(cache_dir: Path, output: Path, download: bool = False) -> dict:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    sources = []
    for entry in inventory["source_archives"]:
        name = entry["filename"]
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError(f"Unsafe source archive name: {name}")
        source = cache_dir / name
        if not source.exists() and download:
            temporary = source.with_name(source.name + ".download")
            request = urllib.request.Request(entry["source_url"], headers={"User-Agent": "FreeSearch-source-packager"})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if temporary.stat().st_size != entry["bytes"] or digest(temporary) != entry["sha256"]:
                raise ValueError(f"Downloaded source checksum mismatch: {name}")
            temporary.replace(source)
        if not source.is_file():
            raise FileNotFoundError(f"Missing {name}; put it in {cache_dir} or use --download")
        if source.stat().st_size != entry["bytes"] or digest(source) != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {name}")
        sources.append(source)

    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_STORED, allowZip64=True) as archive:
        for source in sources:
            archive.write(source, "sources/" + source.name)
        archive.write(INVENTORY, "source-provenance.json")
        archive.write(INVENTORY.with_name("BINARY_SOURCES.md"), "BINARY_SOURCES.md")
        for name in ("THIRD_PARTY_NOTICES.md", "requirements-lock.txt"):
            archive.write(ROOT / name, name)
    result = {"path": str(output.resolve()), "archives": len(sources), "bytes": output.stat().st_size,
              "sha256": digest(output)}
    output.with_suffix(output.suffix + ".sha256").write_text(
        f"{result['sha256']}  {output.name}\n", encoding="ascii")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "private/binary-provenance/sources")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/installer-release/FreeSearch-dependency-sources.zip")
    parser.add_argument("--download", action="store_true", help="Download missing pinned sources from official upstreams")
    args = parser.parse_args()
    print(json.dumps(package(args.cache_dir, args.output, args.download), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

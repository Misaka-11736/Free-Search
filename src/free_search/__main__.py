import argparse
import json
import os
from pathlib import Path
import sys


def launch_settings(root: Path, bundle: Path, executable: Path):
    edition_file = bundle / f"edition-{executable.stem}.json"
    if not edition_file.exists():
        edition_file = bundle / "edition.json"
    edition = json.loads(edition_file.read_text(encoding="utf-8-sig"))["edition"] if edition_file.exists() else "offline"
    if edition not in {"offline", "api"}:
        raise ValueError("无效的发行版本标记。")
    runtime = root / "runtime-data"
    if (root / "installed.json").exists():
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        runtime = local / "FreeSearch" / "data"
    return edition, runtime


def main():
    frozen = getattr(sys, "frozen", False)
    root = Path(sys.executable).parent if frozen else Path(__file__).resolve().parents[2]
    # Release edition is bundled and cannot be switched by an environment variable.
    bundle = Path(getattr(sys, "_MEIPASS", root))
    edition, runtime = launch_settings(root, bundle, Path(sys.executable))
    if edition == "offline":
        from .offline import install_network_guard
        install_network_guard()
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=runtime)
    parser.add_argument("--model-dir", type=Path, default=root / "models")
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--index", nargs="+")
    parser.add_argument("--images-only", action="store_true", help="与 --index 合用：先索引图片，其他文件稍后补齐")
    parser.add_argument("--query")
    parser.add_argument("--transcribe", type=Path)
    parser.add_argument("--output", type=Path, help="将命令行结果保存为 JSON（窗口版 EXE 无终端输出）")
    parser.add_argument("--mode", choices=["bm25", "vector", "hybrid_no_rerank", "hybrid"], default="hybrid")
    args = parser.parse_args()
    if args.images_only and not args.index:
        parser.error("--images-only 需要同时指定 --index 目录")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(args.data_dir / "hf-cache")
    os.environ["TEMP"] = str(args.data_dir / "tmp")
    os.environ["TMP"] = os.environ["TEMP"]
    Path(os.environ["TEMP"]).mkdir(exist_ok=True)
    from .engine import SearchEngine
    if args.diagnose or args.index or args.query or args.transcribe:
        engine = SearchEngine(args.data_dir, args.model_dir)
        try:
            output = {}
            if args.index:
                output["index"] = engine.index(args.index, images_only=args.images_only)
            if args.query:
                output["results"] = engine.search(args.query, mode=args.mode)
            if args.transcribe:
                output["transcription"] = engine.models.transcribe(args.transcribe)
            if args.diagnose:
                output["diagnostics"] = {"edition": edition, **engine.stats()}
                result = json.dumps(output["diagnostics"], ensure_ascii=False, indent=2)
                (args.data_dir / "diagnostics.json").write_text(result, encoding="utf-8")
            result = json.dumps(output, ensure_ascii=False, indent=2)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(result, encoding="utf-8")
            if sys.stdout is not None:
                print(result)
        except Exception as exc:
            import traceback
            failure = json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
            (args.data_dir / "command-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(failure, encoding="utf-8")
            if sys.stderr is not None:
                print(failure, file=sys.stderr)
            return 1
        finally:
            engine.close()
        return 0
    from .ui import run
    return run(args.data_dir, args.model_dir, edition)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())

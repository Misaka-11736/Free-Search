from pathlib import Path
import json
import os
import sys
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from free_search.models import LocalModels

m = LocalModels(ROOT / "models")
inventory = json.loads((ROOT / "private/pilot-inventory.json").read_text(encoding="utf-8-sig"))
photo = next(f["path"] for r in inventory if r["kind"] == "images"
             for f in r["files"] if f["extension"] == ".png")
result = {"available": m.availability(), "checks": {}}
checks = {
    "text": lambda: list(m.embed_text(["设备散热设计", "旅行照片"]).shape),
    "query": lambda: list(m.embed_query("设备如何降温").shape),
    "image": lambda: list(m.embed_images([photo]).shape),
    "vision_text": lambda: list(m.embed_vision_text(["软件界面的截图"]).shape),
    "rerank": lambda: m.rerank("如何给设备降温", ["使用散热器降低设备温度", "旅行照片拍摄技巧"]),
    "ocr": lambda: {"characters": len(m.ocr(photo))},
}
for name, check in checks.items():
    start = time.perf_counter()
    try:
        result["checks"][name] = dict(result=check(), seconds=time.perf_counter()-start, status="passed")
    except Exception as exc:
        result["checks"][name] = dict(status="failed", error=f"{type(exc).__name__}: {exc}")
    result["checks"][name]["rss_mb"] = psutil.Process().memory_info().rss / 1024**2
    print(name, result["checks"][name], flush=True)
    (ROOT / "private/model-smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

"""100k actual files with a seeded lexical/vector index; tests delta work, not quality."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from free_search.engine import SearchEngine, digest


class CounterModels:
    def __init__(self):
        self.count = 0

    def availability(self):
        return {"text_embedding": True}

    def embed_text(self, texts):
        self.count += len(texts)
        return np.tile(np.arange(1, 33, dtype=np.float32), (len(texts), 1))

    embed_images = embed_text


def main():
    base = ROOT / "private" / "benchmark-100k"
    corpus = base / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    model = CounterModels()
    engine = SearchEngine(base / "index", base / "models", models=model)
    # Constant counting vectors deliberately do not benchmark ANN training/recall.
    engine.optimize_vectors = lambda: None
    count = 100_000
    started = time.perf_counter()
    if engine.stats()["files"] != count:
        vectors = []
        for batch in range(100):
            folder = corpus / str(batch)
            folder.mkdir(exist_ok=True)
            files, chunks = [], []
            for j in range(1000):
                i = batch * 1000 + j
                path = folder / f"{i}.txt"
                text = f"baseline document {i}"
                path.write_text(text, encoding="utf-8")
                stat = path.stat()
                key = digest(os.path.normcase(str(path.resolve())))
                sha = hashlib.sha256(text.encode()).hexdigest()
                gen = digest(sha + engine.model_state)
                chunk_id = digest(key + gen + "0")
                files.append((key, str(path), str(corpus), stat.st_size, stat.st_mtime_ns,
                              sha, gen, "ready", None, engine.model_state))
                chunks.append((chunk_id, key, text, text, "", "text", None))
                vectors.append(dict(id=chunk_id,file_id=key,generation=gen,path=str(path),
                                    ext=".txt",modified=stat.st_mtime,vector=[float(x) for x in range(1,33)]))
            with engine.db:
                engine.db.executemany("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?,?,?)", files)
                engine.db.executemany("INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?,?,?)", chunks)
            if batch % 10 == 0:
                print(f"seeded {(batch + 1) * 1000}", flush=True)
        engine.vectors.create_table("text", vectors, mode="overwrite")
    engine.db.execute("UPDATE files SET model_state=?", (engine.model_state,))
    engine.db.commit()
    print("Fixture ready; checking unchanged files", flush=True)
    baseline = engine.index([str(corpus)])
    assert baseline["processed"] == 0, baseline
    before = dict(engine.db.execute("SELECT id,generation FROM files").fetchall())
    for i in range(3):
        (corpus / "0" / f"{i}.txt").write_text(f"changed file {i} at {time.time_ns()}", encoding="utf-8")
    model.count = 0
    print("Measuring three-file update", flush=True)
    delta_started = time.perf_counter()
    delta = engine.index([str(corpus)])
    after = dict(engine.db.execute("SELECT id,generation FROM files").fetchall())
    changed = sum(before[k] != after[k] for k in before)
    assert delta["processed"] == 3 and delta["unchanged"] == count - 3, delta
    assert model.count == 3 and changed == 3
    result = dict(files=count, baseline=baseline, delta=delta,
                  changed_generations=changed, model_inputs=model.count,
                  delta_seconds=time.perf_counter()-delta_started,
                  total_seconds=time.perf_counter()-started,
                  fixture="Synthetic actual files, seeded indexes and counting embedding; ANN maintenance disabled. Not retrieval quality.")
    (base / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result), flush=True)
    engine.close()


if __name__ == "__main__":
    main()

"""Incremental file manifest, transactional lexical index and local vector retrieval."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout
import jieba
import numpy as np

from .extractors import SUPPORTED_EXTENSIONS, Chunk, extract
from .models import LocalModels

_LOCK = threading.RLock()
_MODELS = {}


def tokenize(text: str) -> str:
    return " ".join(t.lower() for t in jieba.cut(text) if t.strip())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SearchEngine:
    def __init__(self, data_dir: Path, model_dir: Path, models=None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        jieba.dt.tmp_dir = str(self.data_dir)
        model_key = str(Path(model_dir).resolve())
        manifest = Path(model_dir) / "manifest.json"
        info = json.loads(manifest.read_text(encoding="utf-8-sig")) if manifest.exists() else {}
        cache_key = model_key + digest(json.dumps(info, sort_keys=True))
        if models is None and cache_key not in _MODELS:
            _MODELS[cache_key] = LocalModels(Path(model_dir))
        self.models = models or _MODELS[cache_key]
        self.api = None
        self.db = sqlite3.connect(self.data_dir / "catalog.sqlite", timeout=60, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=NORMAL;
          CREATE TABLE IF NOT EXISTS files(
            id TEXT PRIMARY KEY,path TEXT UNIQUE,root TEXT,size INTEGER,mtime_ns INTEGER,
            sha256 TEXT,generation TEXT,status TEXT,error TEXT,model_state TEXT);
          CREATE TABLE IF NOT EXISTS chunks(
            id TEXT PRIMARY KEY,file_id TEXT,text TEXT,tokens TEXT,locator TEXT,
            modality TEXT,asset_path TEXT);
          CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file_id);
          CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(tokens,content='chunks',content_rowid='rowid');
          CREATE TRIGGER IF NOT EXISTS chunk_insert AFTER INSERT ON chunks BEGIN
            INSERT INTO fts(rowid,tokens) VALUES(new.rowid,new.tokens); END;
          CREATE TRIGGER IF NOT EXISTS chunk_delete AFTER DELETE ON chunks BEGIN
            INSERT INTO fts(fts,rowid,tokens) VALUES('delete',old.rowid,old.tokens); END;
          CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,started REAL,stats TEXT);
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        """)
        self._vectors = None
        self._available = self.models.availability()
        relevant = {k: info.get(k, model_key) for k in ("text-embedding", "vision", "speech")}
        capabilities = {k: v for k, v in self._available.items() if k != "text_reranker"}
        self.model_state = digest("extractor-v1" + json.dumps(relevant, sort_keys=True)
                                  + json.dumps(capabilities, sort_keys=True))

    @property
    def vectors(self):
        if self._vectors is None:
            import lancedb
            self._vectors = lancedb.connect(str(self.data_dir / "vectors"))
        return self._vectors

    def _table(self, name):
        try:
            return self.vectors.open_table(name)
        except (ValueError, FileNotFoundError):
            return None

    def _vector_add(self, name, rows):
        if not rows:
            return
        table = self._table(name)
        if table is None:
            self.vectors.create_table(name, rows)
        else:
            table.add(rows)

    def optimize_vectors(self):
        """Append new rows to existing indexes; first ANN build only above threshold."""
        if not (self._available.get("text_embedding") or self._available.get("vision")):
            return
        for name in ("text", "vision"):
            table = self._table(name)
            if table is None:
                continue
            indices = table.list_indices()
            if table.count_rows() >= 1024 and not any("vector" in x.columns for x in indices):
                table.create_index(metric="cosine", index_type="IVF_FLAT",
                                   num_partitions=min(256, max(8, int(table.count_rows() ** .5))))
            else:
                table.optimize()

    def _vector_delete(self, file_id, keep_generation=None):
        if not (self._available.get("text_embedding") or self._available.get("vision")):
            return
        for name in ("text", "vision"):
            table = self._table(name)
            if table is not None:
                condition = f"file_id = '{file_id}'"
                if keep_generation:
                    condition += f" AND generation != '{keep_generation}'"
                table.delete(condition)

    @contextmanager
    def _writer(self):
        lock = FileLock(self.data_dir / "index.lock", timeout=0)
        try:
            lock.acquire()
        except Timeout:
            raise RuntimeError("另一个 Free Search 实例正在更新此索引，请等待其完成后重试。") from None
        try:
            yield
        finally:
            lock.release()

    def index(self, roots: list[str], progress=None) -> dict:
        with self._writer():
            return self._index(roots, progress)

    def _index(self, roots, progress):
        stats = dict(discovered=0, processed=0, unchanged=0, deleted=0, failed=0,
                     unsupported=0, embedded_chunks=0, enumeration_errors=0)
        roots = list(dict.fromkeys(str(Path(r).resolve()) for r in roots))
        self.db.execute("INSERT OR REPLACE INTO settings VALUES('roots',?)", (json.dumps(roots),))
        self.db.commit()
        for root in roots:
            # Only a complete enumeration of an available root may imply deletions.
            if not Path(root).is_dir():
                stats["enumeration_errors"] += 1
                continue
            seen = set()
            walk_errors = []
            for folder, dirs, names in os.walk(root, onerror=walk_errors.append, followlinks=False):
                dirs[:] = [d for d in dirs if not Path(folder, d).is_symlink()
                           and not Path(folder, d).resolve().is_relative_to(self.data_dir.resolve())]
                for name in names:
                    path = Path(folder, name)
                    if path.is_symlink() or path.is_relative_to(self.data_dir):
                        continue
                    key = digest(os.path.normcase(str(path)))
                    seen.add(key)
                    stats["discovered"] += 1
                    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                        stats["unsupported"] += 1
                        try:
                            self._index_metadata(path, root, key)
                        except OSError:
                            stats["failed"] += 1
                        if progress and stats["discovered"] % 250 == 0:
                            progress(dict(stats))
                        continue
                    with _LOCK:
                        try:
                            changed, embedded = self._index_file(path, root, key)
                            stats["processed" if changed else "unchanged"] += 1
                            stats["embedded_chunks"] += embedded
                        except Exception as exc:
                            self.db.rollback()
                            stats["failed"] += 1
                            self.db.execute("""INSERT INTO files(id,path,root,status,error)
                              VALUES(?,?,?,'error',?) ON CONFLICT(id) DO UPDATE SET
                              status='error',error=excluded.error""",
                              (key, str(path), root, f"{type(exc).__name__}: {exc}"[:1000]))
                            self.db.commit()
                    if progress:
                        progress(dict(stats))
            stats["enumeration_errors"] += len(walk_errors)
            if not walk_errors:
                with _LOCK:
                    for old in self.db.execute("SELECT id FROM files WHERE root=?", (root,)).fetchall():
                        if old["id"] not in seen:
                            self.db.execute("DELETE FROM chunks WHERE file_id=?", (old["id"],))
                            self.db.execute("DELETE FROM files WHERE id=?", (old["id"],))
                            self.db.commit()
                            self._vector_delete(old["id"])
                            stats["deleted"] += 1
        self.db.execute("INSERT INTO runs(started,stats) VALUES(?,?)", (time.time(), json.dumps(stats)))
        self.db.commit()
        self.optimize_vectors()
        return stats

    def _index_metadata(self, path, root, key):
        stat = path.stat()
        old = self.db.execute("SELECT size,mtime_ns FROM files WHERE id=?", (key,)).fetchone()
        if old and (old["size"], old["mtime_ns"]) == (stat.st_size, stat.st_mtime_ns):
            return
        with self.db:
            self.db.execute("DELETE FROM chunks WHERE file_id=?", (key,))
            self.db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,'metadata',?,?)",
                            (key, str(path), root, stat.st_size, stat.st_mtime_ns, "", "",
                             "当前格式仅索引文件名与元数据", ""))
            self.db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)",
                            (digest(key+"metadata"), key, path.name, tokenize(path.name),
                             "仅文件名与元数据；未读取内部内容", "metadata", None))

    def index_files(self, paths: list[str], progress=None) -> dict:
        """Explicit private evaluation corpus; never expands to adjacent directories."""
        with self._writer():
            return self._index_files(paths, progress)

    def _index_files(self, paths, progress):
        stats = dict(discovered=0, processed=0, unchanged=0, failed=0, embedded_chunks=0)
        with _LOCK:
            for item in paths:
                path = Path(item).resolve()
                stats["discovered"] += 1
                try:
                    changed, embedded = self._index_file(
                        path, str(path.parent), digest(os.path.normcase(str(path))))
                    stats["processed" if changed else "unchanged"] += 1
                    stats["embedded_chunks"] += embedded
                except Exception:
                    self.db.rollback()
                    stats["failed"] += 1
                    raise
                if progress:
                    progress(dict(stats))
            self.optimize_vectors()
        return stats

    def _index_file(self, path, root, key):
        before = path.stat()
        old = self.db.execute("SELECT * FROM files WHERE id=?", (key,)).fetchone()
        if (old and old["status"] == "ready" and old["size"] == before.st_size
                and old["mtime_ns"] == before.st_mtime_ns and old["model_state"] == self.model_state):
            return False, 0
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if old and old["sha256"] == checksum and old["model_state"] == self.model_state and old["status"] == "ready":
            self.db.execute("UPDATE files SET size=?,mtime_ns=? WHERE id=?",
                            (before.st_size, before.st_mtime_ns, key))
            self.db.commit()
            return False, 0
        generation = digest(checksum + self.model_state)
        # Staging vectors are invisible until their chunk IDs have been committed to SQLite.
        chunks = [Chunk(path.name, "文件名", "metadata")] + extract(
            path, self.data_dir / "assets" / key, self.models)
        rows, text_rows, visual_rows = [], [], []
        for n, chunk in enumerate(chunks):
            chunk_id = digest(key + generation + str(n))
            rows.append((chunk_id, key, chunk.text, tokenize(chunk.text), chunk.locator,
                         chunk.modality, str(chunk.asset_path) if chunk.asset_path else None))
            meta = dict(id=chunk_id, file_id=key, generation=generation, path=str(path),
                        ext=path.suffix.lower(), modified=before.st_mtime)
            if chunk.text.strip() and chunk.modality != "metadata" and self._available.get("text_embedding"):
                text_rows.append({**meta, "input": chunk.text})
            if chunk.asset_path and self._available.get("vision"):
                visual_rows.append({**meta, "input": str(chunk.asset_path)})
        for batch_rows, model, table_name in (
                (text_rows, self.models.embed_text, "text"),
                (visual_rows, self.models.embed_images, "vision")):
            for start in range(0, len(batch_rows), 16):
                batch = batch_rows[start:start + 16]
                vectors = model([r["input"] for r in batch])
                records = [{k: v for k, v in r.items() if k != "input"} | {"vector": v.tolist()}
                           for r, v in zip(batch, vectors)]
                # Delete an interrupted attempt of this same generation before retrying.
                table = self._table(table_name)
                if table is not None:
                    ids = ",".join("'" + r["id"] + "'" for r in records)
                    table.delete(f"id IN ({ids})")
                self._vector_add(table_name, records)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("文件在解析期间变化，请重试")
        with self.db:
            self.db.execute("DELETE FROM chunks WHERE file_id=?", (key,))
            self.db.execute("""INSERT OR REPLACE INTO files
              VALUES(?,?,?,?,?,?,?,'ready',NULL,?)""",
              (key, str(path), root, before.st_size, before.st_mtime_ns, checksum, generation, self.model_state))
            self.db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?,?)", rows)
        self._vector_delete(key, generation)
        return True, len(text_rows) + len(visual_rows)

    def _filter(self, filters, prefix="f."):
        conditions, args = ["f.status IN ('ready','metadata')"], []
        if filters.get("ext"):
            extensions = [x.strip().lower() for x in filters["ext"].split(",") if x.strip()]
            if not extensions:
                raise ValueError("请提供至少一个文件扩展名，例如 .pdf,.docx")
            extensions = [x if x.startswith(".") else "." + x for x in extensions]
            conditions.append("(" + " OR ".join("lower(f.path) LIKE ?" for _ in extensions) + ")")
            args.extend("%" + x for x in extensions)
        if filters.get("path_prefix"):
            base = os.path.normcase(os.path.abspath(filters["path_prefix"])).rstrip("\\/")
            conditions.append("(lower(f.path)=? OR substr(lower(f.path),1,?)=?)")
            args.extend([base.lower(), len(base) + 1, base.lower() + os.sep])
        for field, op in (("modified_after", ">="), ("modified_before", "<=")):
            if filters.get(field) is not None:
                conditions.append(f"(f.mtime_ns / 1000000000.0) {op} ?")
                args.append(float(filters[field]))
        return " AND ".join(conditions), args

    def search(self, query: str, filters=None, limit=20, image_path=None, mode="hybrid", query_source=None):
        with _LOCK:
            return self._search(query, filters or {}, limit, image_path, mode, query_source)

    def _search(self, query, filters, limit, image_path, mode, query_source):
        if mode != "bm25" and self.db.execute(
                "SELECT 1 FROM files WHERE status='ready' AND model_state != ? LIMIT 1",
                (self.model_state,)).fetchone():
            raise ValueError("模型配置已变化，请先增量更新索引，避免混用不同模型的向量。")
        clause, args = self._filter(filters)
        rankings = []
        if query.strip() and mode != "vector":
            tokens = list(dict.fromkeys(tokenize(query).split()))[:64]
            match = " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)
            if match:
                rows = self.db.execute(f"""SELECT c.id FROM fts JOIN chunks c ON c.rowid=fts.rowid
                  JOIN files f ON f.id=c.file_id WHERE fts MATCH ? AND {clause}
                  ORDER BY bm25(fts) LIMIT 150""", [match, *args]).fetchall()
                rankings.append([r["id"] for r in rows])
        vector_queries = []
        if mode != "bm25":
            if query.strip() and self._available.get("text_embedding"):
                vector_queries.append(("text", self.models.embed_query(query)))
            if self._available.get("vision"):
                if image_path:
                    vector_queries.append(("vision", self.models.embed_images([image_path])[0]))
                elif query.strip():
                    vector_queries.append(("vision", self.models.embed_vision_text([query])[0]))
        for name, vector in vector_queries:
            table = self._table(name)
            if table is None:
                continue
            def literal(value):
                return "'" + str(value).replace("'", "''") + "'"
            restrictions = []
            if filters.get("ext"):
                exts = [x.strip().lower() for x in filters["ext"].split(",") if x.strip()]
                restrictions.append("ext IN (" + ",".join(literal(x if x.startswith(".") else "." + x)
                                                          for x in exts) + ")")
            if filters.get("path_prefix"):
                prefix = os.path.abspath(filters["path_prefix"]).rstrip("\\/").lower()
                restrictions.append(f"(lower(path) = {literal(prefix)} OR "
                                    f"starts_with(lower(path), {literal(prefix + os.sep)}))")
            for field, op in (("modified_after", ">="), ("modified_before", "<=")):
                if filters.get(field) is not None:
                    restrictions.append(f"modified {op} {float(filters[field])}")
            request = table.search(np.asarray(vector)).metric("cosine")
            if restrictions:
                request = request.where(" AND ".join(restrictions), prefilter=True)
            found = request.limit(150).to_list()
            rankings.append([r["id"] for r in found])
        scores = {}
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking):
                scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (60 + rank + 1)
        candidates = []
        for chunk_id in sorted(scores, key=scores.get, reverse=True)[:100]:
            row = self.db.execute(f"""SELECT c.*,f.path,f.mtime_ns FROM chunks c
              JOIN files f ON f.id=c.file_id WHERE c.id=? AND {clause}""", [chunk_id, *args]).fetchone()
            if row and Path(row["path"]).exists():
                candidates.append(dict(row) | {"score": scores[chunk_id], "ranking": "hybrid"})
        if query and mode == "hybrid" and self._available.get("text_reranker"):
            textual = [r for r in candidates[:40] if r["text"].strip()]
            values = self.models.rerank(query, [r["text"] for r in textual])
            for row, score in zip(textual, values):
                row["score"] = float(score)
                row["ranking"] = "text_reranker"
            # Rerank text within its existing slots so unrelated text cannot
            # displace visual matches that a text-only model cannot assess.
            textual_ids = {r["id"] for r in textual}
            ordered_text = iter(sorted(textual, key=lambda r: r["score"], reverse=True))
            candidates = [next(ordered_text) if r["id"] in textual_ids else r for r in candidates]
        if self.api is not None and query:
            candidates = self.api.rerank(query, candidates, query_source=query_source)
        results, paths = [], set()
        for row in candidates:
            if row["path"] not in paths:
                results.append(row)
                paths.add(row["path"])
                if len(results) >= limit:
                    break
        return results

    def stats(self):
        return {
            "files": self.db.execute("SELECT count(*) FROM files WHERE status='ready'").fetchone()[0],
            "failed": self.db.execute("SELECT count(*) FROM files WHERE status='error'").fetchone()[0],
            "metadata_only": self.db.execute("SELECT count(*) FROM files WHERE status='metadata'").fetchone()[0],
            "chunks": self.db.execute("SELECT count(*) FROM chunks").fetchone()[0],
            "models": self._available,
            "roots": json.loads((self.db.execute("SELECT value FROM settings WHERE key='roots'").fetchone() or ["[]"])[0]),
        }

    def close(self):
        self.db.close()

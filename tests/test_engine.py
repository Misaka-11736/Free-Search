from pathlib import Path
import os
import subprocess
import sys
import pytest

from free_search.engine import SearchEngine


class NoModels:
    def availability(self):
        return {}

    def embed_text(self, _):
        raise AssertionError("unexpected inference")

    embed_images = embed_text


def engine(tmp_path):
    return SearchEngine(tmp_path / "db", tmp_path / "models", models=NoModels())


def test_incremental_three_and_delete(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    for i in range(25):
        (root / f"{i}.txt").write_text(f"文档 {i} 电池散热设计", encoding="utf-8")
    search = engine(tmp_path)
    assert search.index([str(root)])["processed"] == 25
    assert search.index([str(root)])["unchanged"] == 25
    before = dict(search.db.execute("SELECT path,generation FROM files").fetchall())
    for i in range(3):
        (root / f"{i}.txt").write_text(f"修改的文档 {i} 流体力学", encoding="utf-8")
    stats = search.index([str(root)])
    assert stats["processed"] == 3
    assert stats["unchanged"] == 22
    after = dict(search.db.execute("SELECT path,generation FROM files").fetchall())
    assert sum(before[p] != after[p] for p in before) == 3
    (root / "0.txt").unlink()
    assert search.index([str(root)])["deleted"] == 1
    assert all(Path(row["path"]).exists() for row in search.search("流体力学"))
    search.close()


def test_filters_apply_at_retrieval(tmp_path):
    root = tmp_path / "docs"
    sub = root / "allowed"
    sub.mkdir(parents=True)
    (sub / "ok.txt").write_text("星空拍摄计划", encoding="utf-8")
    (root / "other.md").write_text("星空拍摄计划", encoding="utf-8")
    s = engine(tmp_path)
    s.index([str(root)])
    assert len(s.search("星空", {"path_prefix": str(sub)})) == 1
    assert len(s.search("星空", {"ext": ".md"})) == 1
    assert not s.search("星空", {"modified_after": 9999999999})
    s.close()


def test_failure_keeps_old_generation_but_hides_stale_result(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    root.mkdir()
    path = root / "a.txt"
    path.write_text("旧的内容", encoding="utf-8")
    s = engine(tmp_path)
    s.index([str(root)])
    path.write_text("新的内容 改动", encoding="utf-8")
    monkeypatch.setattr("free_search.engine.extract", lambda *_: (_ for _ in ()).throw(ValueError("broken")))
    assert s.index([str(root)])["failed"] == 1
    assert not s.search("旧的内容")
    s.close()


def test_changed_model_state_requires_reindex_for_vectors(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "a.txt").write_text("电池散热设计", encoding="utf-8")
    s = engine(tmp_path)
    s.index([str(root)])
    s.model_state = "different-model"
    with pytest.raises(ValueError, match="模型配置已变化"):
        s.search("电池")
    assert s.search("电池", mode="bm25")
    s.index([str(root)])
    assert s.search("电池")
    s.close()


def test_empty_extension_filter_has_clear_error(tmp_path):
    s = engine(tmp_path)
    with pytest.raises(ValueError, match="扩展名"):
        s.search("内容", {"ext": ", ,"})
    s.close()


def test_text_reranking_preserves_visual_match_among_many_documents(tmp_path):
    import numpy as np
    from PIL import Image

    class MixedModels:
        def availability(self):
            return {"text_embedding": True, "vision": True, "text_reranker": True}

        def embed_text(self, texts):
            return np.array([[0., 1., 0.] for _ in texts], dtype=np.float32)

        def embed_query(self, query):
            return np.array([1., 0., 0.], dtype=np.float32)

        def embed_images(self, images):
            return np.array([[1., 0., 0.] for _ in images], dtype=np.float32)

        def embed_vision_text(self, texts):
            return self.embed_images(texts)

        def rerank(self, query, texts):
            return [0.] * len(texts)

    root = tmp_path / "files"
    root.mkdir()
    for number in range(25):
        (root / f"document-{number}.txt").write_text("Unrelated astronomy document " + str(number))
    photo = root / "photo.png"
    Image.new("RGB", (10, 10), "orange").save(photo)
    search = SearchEngine(tmp_path / "db", tmp_path / "models", models=MixedModels())
    try:
        search.index_files([str(path) for path in root.iterdir()])
        baseline = search.search("橙色跑车照片", mode="hybrid_no_rerank", limit=20)
        reranked = search.search("橙色跑车照片", mode="hybrid", limit=20)
        before = [r["path"] for r in baseline].index(str(photo))
        assert before < 5
        assert [r["path"] for r in reranked].index(str(photo)) == before
    finally:
        search.close()


@pytest.mark.parametrize("method", ["index", "index_files"])
def test_other_process_cannot_update_shared_index(tmp_path, method):
    root = tmp_path / "docs"
    root.mkdir()
    path = root / "one.txt"
    path.write_text("共享索引内容", encoding="utf-8")
    search = engine(tmp_path)
    search.index([str(root)])
    code = ("from filelock import FileLock; import sys; "
            "lock=FileLock(sys.argv[1]); lock.acquire(); "
            "print('ready',flush=True); sys.stdin.readline(); lock.release()")
    child = subprocess.Popen([sys.executable, "-c", code, str(search.data_dir / "index.lock")],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="另一个 Free Search 实例"):
            getattr(search, method)([str(root if method == "index" else path)])
        assert search.search("共享索引", mode="bm25")
    finally:
        child.communicate("\n", timeout=10)
    assert getattr(search, method)([str(root if method == "index" else path)])["unchanged"] == 1
    search.close()


def test_image_stage_defers_other_files_and_preserves_their_index(tmp_path, monkeypatch):
    from free_search.extractors import Chunk

    root = tmp_path / "files"
    root.mkdir()
    photo = root / "photo.PNG"
    document = root / "notes.txt"
    recording = root / "meeting.wav"
    other = root / "archive.dat"
    for path in (photo, document, recording, other):
        path.write_text(path.name)
    parsed = []

    def extract_file(path, *_):
        parsed.append(path.name)
        return [Chunk("indexed " + path.name)]

    monkeypatch.setattr("free_search.engine.extract", extract_file)
    search = engine(tmp_path)
    try:
        images = search.index([str(root)], images_only=True)
        assert images["processed"] == 1
        assert images["deferred"] == 3
        assert parsed == [photo.name]
        assert search.db.execute("SELECT count(*) FROM files").fetchone()[0] == 1
        parsed.clear()
        complete = search.index([str(root)])
        assert complete["processed"] == 2
        assert complete["unchanged"] == 1
        assert set(parsed) == {document.name, recording.name}
        assert search.stats()["metadata_only"] == 1

        photo.unlink()
        document.unlink()
        recording.unlink()
        other.unlink()
        assert search.index([str(root)], images_only=True)["deleted"] == 1
        remaining = {row[0] for row in search.db.execute("SELECT path FROM files")}
        assert remaining == {str(document), str(recording), str(other)}
        assert search.index([str(root)])["deleted"] == 3
    finally:
        search.close()


class CountingModels(NoModels):
    def __init__(self):
        self.inputs = 0

    def availability(self):
        return {"text_embedding": True}

    def embed_text(self, texts):
        import numpy as np
        self.inputs += len(texts)
        return np.array([[1., 0., 0.] for _ in texts], dtype=np.float32)


def test_new_file_uses_batched_appends_without_repeated_deletes(tmp_path, monkeypatch):
    from lancedb.table import LanceTable
    from free_search.extractors import Chunk

    path = tmp_path / "large.txt"
    path.write_text("large document")
    monkeypatch.setattr("free_search.engine.extract",
                        lambda *_: [Chunk(f"passage {n}") for n in range(280)])
    deletes = []
    original_delete = LanceTable.delete

    def delete(table, condition):
        deletes.append(condition)
        return original_delete(table, condition)

    monkeypatch.setattr(LanceTable, "delete", delete)
    search = SearchEngine(tmp_path / "db", tmp_path / "models", models=CountingModels())
    writes = []
    original_add = search._vector_add

    def add(name, rows):
        writes.append(len(rows))
        original_add(name, rows)

    monkeypatch.setattr(search, "_vector_add", add)
    try:
        assert search.index_files([str(path)])["embedded_chunks"] == 280
        assert writes == [256, 24]
        assert deletes == []
        assert search._table("text").count_rows() == 280
    finally:
        search.close()


@pytest.mark.parametrize("existing", [False, True])
def test_partial_vector_write_retries_without_duplicates(tmp_path, monkeypatch, existing):
    from free_search.extractors import Chunk

    path = tmp_path / "document.txt"
    path.write_text("original document")
    search = SearchEngine(tmp_path / "db", tmp_path / "models", models=CountingModels())
    try:
        if existing:
            search.index_files([str(path)])
            previous = search.db.execute("SELECT generation FROM files").fetchone()[0]
            path.write_text("modified document")
        monkeypatch.setattr("free_search.engine.extract",
                            lambda *_: [Chunk(f"passage {n}") for n in range(280)])
        original_add = search._vector_add

        def failed_add(name, rows):
            original_add(name, rows)
            raise RuntimeError("interrupted after append")

        monkeypatch.setattr(search, "_vector_add", failed_add)
        with pytest.raises(RuntimeError, match="interrupted after append"):
            search.index_files([str(path)])
        if existing:
            row = search.db.execute("SELECT generation,status FROM files").fetchone()
            assert tuple(row) == (previous, "ready")
            assert search.search("original", mode="bm25")
        else:
            assert not search.db.execute("SELECT 1 FROM files").fetchone()
        search.close()
        # Reopening must also find and clean staging rows left by an earlier process.
        search = SearchEngine(tmp_path / "db", tmp_path / "models", models=CountingModels())
        assert search.index_files([str(path)])["processed"] == 1
        table = search._table("text")
        rows = table.search().select(["id", "generation"]).limit(None).to_list()
        assert len(rows) == len({row["id"] for row in rows}) == 280
        assert len({row["generation"] for row in rows}) == 1
    finally:
        search.close()


def test_pause_during_vectors_preserves_committed_files_and_skips_deletion(tmp_path, monkeypatch):
    from free_search.extractors import Chunk

    root = tmp_path / "docs"
    root.mkdir()
    path = root / "large.txt"
    removed = root / "removed.txt"
    path.write_text("old searchable content")
    removed.write_text("keep until complete enumeration")
    models = CountingModels()
    search = SearchEngine(tmp_path / "db", tmp_path / "models", models=models)
    try:
        search.index([str(root)])
        old_generation = search.db.execute("SELECT generation FROM files WHERE path=?", (str(path),)).fetchone()[0]
        removed.unlink()
        path.write_text("new document content")
        monkeypatch.setattr("free_search.engine.extract",
                            lambda *_: [Chunk(f"passage {n}") for n in range(560)])
        initial_inputs = models.inputs

        def progress(stats):
            if models.inputs - initial_inputs >= 256:
                raise InterruptedError("pause")

        with pytest.raises(InterruptedError, match="pause"):
            search.index([str(root)], progress=progress)
        assert models.inputs - initial_inputs == 256
        row = search.db.execute("SELECT generation,status FROM files WHERE path=?", (str(path),)).fetchone()
        assert tuple(row) == (old_generation, "ready")
        assert search.db.execute("SELECT 1 FROM files WHERE path=?", (str(removed),)).fetchone()
        assert search.search("old searchable", mode="bm25")
        result = search.index([str(root)])
        assert result["processed"] == 1
        assert result["deleted"] == 1
        assert search._table("text").count_rows() == 560
    finally:
        search.close()

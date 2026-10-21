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

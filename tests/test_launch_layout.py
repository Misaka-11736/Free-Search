import json
from pathlib import Path

import pytest

from free_search.__main__ import launch_settings


def test_installed_entries_share_data_but_keep_editions(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    bundle = root / "_internal"
    bundle.mkdir(parents=True)
    (root / "installed.json").write_text("{}")
    local = tmp_path / "local-app-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    for edition in ("offline", "api"):
        (bundle / f"edition-FreeSearch-{edition}.json").write_text(json.dumps({"edition": edition}))
        mode, data = launch_settings(root, bundle, Path(f"FreeSearch-{edition}.exe"))
        assert mode == edition
        assert data == local / "FreeSearch" / "data"


def test_portable_keeps_existing_data_and_edition(tmp_path):
    (tmp_path / "edition.json").write_text('{"edition":"api"}')
    mode, data = launch_settings(tmp_path, tmp_path, Path("renamed.exe"))
    assert mode == "api"
    assert data == tmp_path / "runtime-data"


def test_invalid_edition_fails_closed(tmp_path):
    (tmp_path / "edition.json").write_text('{"edition":"unknown"}')
    with pytest.raises(ValueError, match="发行版本"):
        launch_settings(tmp_path, tmp_path, Path("FreeSearch.exe"))

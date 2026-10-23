import json

import httpx
import pytest

from free_search.api import ApiClient, ApiConfig, ApiError, Consent


def client(tmp_path, handler, **kwargs):
    consent = kwargs.pop("consent", Consent(text=True, roots=(str(tmp_path),)))
    config = kwargs.pop("config", ApiConfig("https://provider.example/v1", "rerank"))
    return ApiClient(config, consent, edition="api",
                     transport=httpx.MockTransport(handler), **kwargs)


def candidates(tmp_path):
    return [
        {"path": str(tmp_path / "a.txt"), "text": "first", "modality": "text"},
        {"path": str(tmp_path / "b.txt"), "text": "second", "modality": "text"},
    ]


def test_offline_and_consent_block_before_network(tmp_path):
    with pytest.raises(ApiError, match="离线"):
        ApiClient(ApiConfig("https://example.com", "r"), Consent(text=True), edition="offline")
    api = client(tmp_path, lambda _: pytest.fail("unauthorized network"),
                 consent=Consent(roots=(str(tmp_path),)))
    with pytest.raises(ApiError, match="授权"):
        api.rerank("query", candidates(tmp_path))
    assert api.requests == 0


@pytest.mark.parametrize("endpoint", [
    "http://example.com", "file:///tmp/a", "https://key:secret@example.com",
    "https://example.com?key=secret", "https://example.com#key",
])
def test_reject_unsafe_endpoint(endpoint):
    with pytest.raises(ValueError):
        ApiConfig(endpoint, "reranker")


@pytest.mark.parametrize("endpoint", ["https://example.com/v1", "http://127.0.0.1:8000", "http://localhost:8000"])
def test_allowed_endpoints(endpoint):
    assert ApiConfig(endpoint, "r").endpoint == endpoint


def test_rerank_no_paths_and_media_requires_separate_consent(tmp_path):
    items = candidates(tmp_path)
    items.insert(1, {"path": str(tmp_path / "secret.png"), "text": "image private", "modality": "text"})
    items.append({"path": str(tmp_path.parent / "outside.txt"), "text": "outside", "modality": "text"})

    def handler(request):
        data = json.loads(request.content)
        assert data["documents"] == ["first", "second"]
        assert str(tmp_path) not in request.content.decode()
        return httpx.Response(200, json={"results": [
            {"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1},
        ]})

    api = client(tmp_path, handler)
    results = api.rerank("find second", items)
    assert [r["text"] for r in results] == ["second", "image private", "first", "outside"]
    assert api.requests == 1


def test_api_session_budget_and_redirect_do_not_leak(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://another.example/"})

    api = client(tmp_path, handler, config=ApiConfig("https://provider.example", "r", request_limit=1))
    with pytest.raises(ApiError, match="302"):
        api.rerank("query", candidates(tmp_path))
    with pytest.raises(ApiError, match="上限"):
        api.rerank("query", candidates(tmp_path))
    assert len(calls) == 1


def test_byte_limit_blocks_request(tmp_path):
    api = client(tmp_path, lambda _: pytest.fail("budget exceeded"),
                 config=ApiConfig("https://provider.example", "r", byte_limit=1))
    with pytest.raises(ApiError, match="上限"):
        api.rerank("query", candidates(tmp_path))
    assert api.requests == 0


@pytest.mark.parametrize("results", [
    [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 1}],
    [{"index": 0, "relevance_score": 1}],
    [{"index": 0, "relevance_score": float("nan")}, {"index": 1, "relevance_score": 1}],
])
def test_invalid_service_results_do_not_corrupt_ranking(tmp_path, results):
    api = client(tmp_path, lambda _: httpx.Response(200, json={"results": results}))
    with pytest.raises(ApiError):
        api.rerank("q", candidates(tmp_path))


def test_audio_video_consent_applies_to_transcribed_text(tmp_path):
    item = {"path": str(tmp_path / "meeting.wav"), "text": "meeting words", "modality": "text"}
    assert not Consent(text=True, roots=(str(tmp_path),)).permits(item)
    assert Consent(text=True, audio_video=True, roots=(str(tmp_path),)).permits(item)


@pytest.mark.parametrize("modality,suffix", [("audio", ".wav"), ("image", ".png")])
def test_derived_query_requires_source_consent_before_network(tmp_path, modality, suffix):
    api = client(tmp_path, lambda _: pytest.fail("derived query must not leave the computer"))
    source = {"path": str(tmp_path / ("question" + suffix)), "modality": modality}
    with pytest.raises(ApiError, match="来源类型或目录"):
        api.rerank("private derived query", candidates(tmp_path), query_source=source)
    assert api.requests == 0
    assert api.bytes_sent == 0


def test_authorized_speech_query_respects_directory_scope(tmp_path):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"results": [
            {"index": 0, "relevance_score": 1}, {"index": 1, "relevance_score": 0},
        ]})

    api = client(tmp_path, handler,
                 consent=Consent(text=True, audio_video=True, roots=(str(tmp_path),)))
    source = {"path": str(tmp_path.parent / "outside.wav"), "modality": "audio"}
    with pytest.raises(ApiError, match="来源类型或目录"):
        api.rerank("speech query", candidates(tmp_path), query_source=source)
    assert not sent
    source["path"] = str(tmp_path / "inside.wav")
    api.rerank("speech query", candidates(tmp_path), query_source=source)
    assert sent[0]["query"] == "speech query"
    assert "path" not in sent[0]


def test_ui_preserves_voice_provenance_until_query_is_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from free_search.ui import SearchWindow

    app = QApplication.instance() or QApplication([])
    jobs = []
    monkeypatch.setattr(SearchWindow, "start_job", lambda self, label, action, completed, **kwargs: jobs.append(action))
    window = SearchWindow(tmp_path, tmp_path / "models", "api")
    source_path = tmp_path / "voice.wav"
    window.transcribed([{"text": "voice question"}], str(source_path))
    source = {"path": str(source_path.resolve()), "modality": "audio"}
    assert window.query_source == source
    window.query.setText("edited voice question")
    assert window.query_source == source
    captured = {}

    class Engine:
        def search(self, query, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(window, "with_engine", lambda action: action(Engine()))
    window.search()
    jobs[-1](lambda *parts: None)
    assert captured["query_source"] == source
    window.query.clear()
    assert window.query_source is None
    window.query.setText("new typed query")
    assert window.query_source is None
    window.close()
    window.deleteLater()
    app.processEvents()


def test_ui_job_cleanup_and_cancel_only_for_index(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from free_search.ui import SearchWindow

    app = QApplication.instance() or QApplication([])
    # Avoid loading models for this lifecycle test.
    monkeypatch.setattr(SearchWindow, "inspect", lambda self, progress: {})
    monkeypatch.setattr(SearchWindow, "inspected", lambda self, result: None)
    window = SearchWindow(tmp_path, tmp_path / "models", "offline")

    def finish_job():
        loop = QEventLoop()
        if window.job is not None:
            window.job.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
        app.processEvents()
        assert window.job is None
        assert not window.cancel_button.isEnabled()

    assert not window.cancel_button.isEnabled()
    finish_job()
    window.start_job("index", lambda progress: {}, lambda value: None, cancellable=True)
    assert window.cancel_button.isEnabled()
    finish_job()
    window.start_job("search", lambda progress: [], lambda value: None)
    assert not window.cancel_button.isEnabled()
    finish_job()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_ui_image_stage_can_search_before_completing_all_content(tmp_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from free_search.ui import SearchWindow

    app = QApplication.instance() or QApplication([])
    jobs = []
    monkeypatch.setattr(SearchWindow, "start_job",
                        lambda self, label, action, completed, **kwargs: jobs.append((action, completed, kwargs)))
    window = SearchWindow(tmp_path, tmp_path / "models", "offline")
    window.roots.addItem(str(tmp_path / "photos"))
    modes = []

    class Engine:
        def index(self, roots, progress, images_only):
            modes.append(images_only)
            stats = dict(discovered=10, processed=2, unchanged=1, failed=0, deferred=7)
            progress({**stats, "current_file": "photo.png", "phase": "图片编码 0/1"})
            return stats

    monkeypatch.setattr(window, "with_engine", lambda action: action(Engine()))
    try:
        window.image_index_button.click()
        action, completed, options = jobs[-1]
        assert options["cancellable"]
        messages = []
        completed(action(messages.append))
        assert modes == [True]
        assert "photo.png" in messages[-1]
        assert "可以先搜索照片" in window.status.text()
        window.set_busy(True)
        assert not window.image_index_button.isEnabled()
        window.set_busy(False)
        assert window.search_button.isEnabled()
        window.index_button.click()
        action, completed, _ = jobs[-1]
        completed(action(messages.append))
        assert modes == [True, False]
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()

from __future__ import annotations

import rag_client


class _Resp:
    def __init__(self, data=None, status_code: int = 200):
        self._data = data or {}
        self.status_code = status_code

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


def test_query_missing_collection_does_not_create(monkeypatch):
    monkeypatch.setenv("DEER_RAG_URL", "http://fake-rag")
    calls: list[tuple[str, str, object]] = []

    def fake_get(url, *args, **kwargs):
        calls.append(("GET", url, None))
        if url.endswith("/collections"):
            return _Resp({"items": []})
        return _Resp({})

    def fake_post(url, *args, **kwargs):
        calls.append(("POST", url, kwargs.get("json")))
        return _Resp({})

    monkeypatch.setattr(rag_client.httpx, "get", fake_get)
    monkeypatch.setattr(rag_client.httpx, "post", fake_post)

    assert rag_client.query("missing", "hello") == ("", [])
    assert not any(url.endswith("/collections") for method, url, _ in calls if method == "POST")
    assert not any(url.endswith("/retrieve") for method, url, _ in calls if method == "POST")


def test_ingest_text_with_rebuild_false_skips_index_build(monkeypatch):
    monkeypatch.setenv("DEER_RAG_URL", "http://fake-rag")
    calls: list[tuple[str, str, object]] = []

    def fake_get(url, *args, **kwargs):
        calls.append(("GET", url, None))
        if url.endswith("/collections"):
            return _Resp({"items": [{"id": "c1", "name": "default"}]})
        return _Resp({})

    def fake_post(url, *args, **kwargs):
        calls.append(("POST", url, kwargs.get("json")))
        if url.endswith("/ingest/text"):
            return _Resp({"ok": True})
        return _Resp({})

    monkeypatch.setattr(rag_client.httpx, "get", fake_get)
    monkeypatch.setattr(rag_client.httpx, "post", fake_post)

    assert rag_client.ingest_text("default", "hello world", "doc.txt", rebuild=False) is True
    assert any(url.endswith("/ingest/text") for method, url, _ in calls if method == "POST")
    assert not any(url.endswith("/indexes/build") for method, url, _ in calls if method == "POST")


def test_build_indexes_only_builds_for_existing_collection(monkeypatch):
    monkeypatch.setenv("DEER_RAG_URL", "http://fake-rag")
    calls: list[tuple[str, str, object]] = []

    def fake_get(url, *args, **kwargs):
        calls.append(("GET", url, None))
        if url.endswith("/collections"):
            return _Resp({"items": [{"id": "c1", "name": "default"}]})
        return _Resp({})

    def fake_post(url, *args, **kwargs):
        calls.append(("POST", url, kwargs.get("json")))
        if url.endswith("/indexes/build"):
            return _Resp({"ok": True})
        return _Resp({})

    monkeypatch.setattr(rag_client.httpx, "get", fake_get)
    monkeypatch.setattr(rag_client.httpx, "post", fake_post)

    assert rag_client.build_indexes("default") is True

    build_calls = [
        payload
        for method, url, payload in calls
        if method == "POST" and url.endswith("/indexes/build")
    ]
    assert build_calls == [{"collection_id": "c1"}]

"""Tests for the local-first / web-fallback add-by-DOI logic. httpx is mocked
so nothing touches a real Zotero library."""

import httpx
import pytest

from popstack import zotero

DOI = "10.1234/abcd.5678"
CROSSREF = {"message": {"title": ["A Paper"], "author": [{"given": "A", "family": "B"}],
                        "container-title": ["J"], "issued": {"date-parts": [[2026]]},
                        "URL": "http://x"}}


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(zotero.config, "ZOTERO_LOCAL_URL", "http://localhost:23119/api/users/0")
    monkeypatch.setattr(zotero.config, "ZOTERO_API_KEY", "")
    monkeypatch.setattr(zotero.config, "ZOTERO_USER_ID", "")


def _patch_http(monkeypatch, post_handler):
    def fake_get(url, *a, **k):
        return httpx.Response(200, json=CROSSREF, request=httpx.Request("GET", url))
    def fake_post(url, *a, **k):
        return post_handler(url, *a, **k)
    monkeypatch.setattr(zotero.httpx, "get", fake_get)
    monkeypatch.setattr(zotero.httpx, "post", fake_post)


def test_invalid_doi():
    r = zotero.add_by_doi("not a doi")
    assert r["added"] is False and "not a valid DOI" in r["error"]


def test_local_write_succeeds(monkeypatch):
    def post(url, *a, **k):
        assert "localhost:23119" in url  # local tried first
        return httpx.Response(200, json={"successful": {"0": {"key": "LOCALKEY"}}},
                              request=httpx.Request("POST", url))
    _patch_http(monkeypatch, post)
    r = zotero.add_by_doi(DOI)
    assert r["added"] and r["via"] == "local" and r["key"] == "LOCALKEY"


def test_local_fails_web_not_configured(monkeypatch):
    def post(url, *a, **k):
        return httpx.Response(405, text="Method Not Allowed", request=httpx.Request("POST", url))
    _patch_http(monkeypatch, post)
    r = zotero.add_by_doi(DOI)
    assert r["added"] is False
    assert "HTTP 405" in r["attempts"]["local"]
    assert "not configured" in r["attempts"]["web"]
    assert "manually" in r["error"]  # agent gets an actionable message


def test_local_fails_web_succeeds(monkeypatch):
    monkeypatch.setattr(zotero.config, "ZOTERO_API_KEY", "KEY")
    monkeypatch.setattr(zotero.config, "ZOTERO_USER_ID", "123")

    def post(url, *a, **k):
        if "localhost" in url:
            return httpx.Response(403, text="Forbidden", request=httpx.Request("POST", url))
        assert "api.zotero.org/users/123" in url
        return httpx.Response(200, json={"successful": {"0": {"key": "WEBKEY"}}},
                              request=httpx.Request("POST", url))
    _patch_http(monkeypatch, post)
    r = zotero.add_by_doi(DOI)
    assert r["added"] and r["via"] == "web" and r["key"] == "WEBKEY"


def test_local_unreachable_reports_reason(monkeypatch):
    def post(url, *a, **k):
        raise httpx.ConnectError("connection refused")
    _patch_http(monkeypatch, post)
    r = zotero.add_by_doi(DOI)
    assert r["added"] is False
    assert "unreachable" in r["attempts"]["local"]


def test_crossref_failure_reported(monkeypatch):
    def fake_get(url, *a, **k):
        return httpx.Response(404, text="not found", request=httpx.Request("GET", url))
    monkeypatch.setattr(zotero.httpx, "get", fake_get)
    r = zotero.add_by_doi(DOI)
    assert r["added"] is False and "Crossref" in r["error"]


# ---- collection-aware filing (follow existing organization) ----

COLLECTIONS = [
    {"key": "AAAAAAAA", "data": {"name": "agent", "parentCollection": False}},
    {"key": "BBBBBBBB", "data": {"name": "agents", "parentCollection": "AAAAAAAA"}},
    {"key": "CCCCCCCC", "data": {"name": "frameworks", "parentCollection": "BBBBBBBB"}},
]


def _patch_collections(monkeypatch):
    def fake_get(url, *a, **k):
        if url.endswith("/collections"):
            return httpx.Response(200, json=COLLECTIONS, request=httpx.Request("GET", url))
        return httpx.Response(200, json=CROSSREF, request=httpx.Request("GET", url))
    monkeypatch.setattr(zotero.httpx, "get", fake_get)


def test_collections_builds_paths(monkeypatch):
    _patch_collections(monkeypatch)
    cols = zotero.collections()["collections"]
    paths = {c["path"]: c["key"] for c in cols}
    assert paths["agent/agents/frameworks"] == "CCCCCCCC"
    assert paths["agent"] == "AAAAAAAA"


def test_resolve_by_path_name_key(monkeypatch):
    _patch_collections(monkeypatch)
    cols = zotero.collections()["collections"]
    assert zotero._resolve_collection("agent/agents/frameworks", cols) == "CCCCCCCC"
    assert zotero._resolve_collection("frameworks", cols) == "CCCCCCCC"   # by name
    assert zotero._resolve_collection("CCCCCCCC", cols) == "CCCCCCCC"     # by key
    assert zotero._resolve_collection("nonexistent", cols) is None


def test_add_files_into_collection(monkeypatch):
    _patch_collections(monkeypatch)
    captured = {}

    def fake_post(url, *a, **k):
        captured["json"] = k.get("json")
        return httpx.Response(200, json={"successful": {"0": {"key": "NEW"}}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(zotero.httpx, "post", fake_post)

    r = zotero.add_by_doi(DOI, collection="agent/agents/frameworks")
    assert r["added"] and r["filed_in"] == "agent/agents/frameworks"
    assert captured["json"][0]["collections"] == ["CCCCCCCC"]


def test_unknown_collection_lists_available(monkeypatch):
    _patch_collections(monkeypatch)
    r = zotero.add_by_doi(DOI, collection="does/not/exist")
    assert r["added"] is False
    assert "not found" in r["error"]
    assert "agent/agents/frameworks" in r["available_collections"]


def test_failed_write_reports_intended_collection(monkeypatch):
    _patch_collections(monkeypatch)
    monkeypatch.setattr(zotero.httpx, "post",
                        lambda url, *a, **k: httpx.Response(400, text="Endpoint does not support method",
                                                           request=httpx.Request("POST", url)))
    r = zotero.add_by_doi(DOI, collection="frameworks")
    assert r["added"] is False
    assert r["intended_collection"] == "agent/agents/frameworks"
    assert "agent/agents/frameworks" in r["error"]  # tells user where to add manually

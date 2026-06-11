"""Tests for deck-aware Anki card creation (AnkiConnect mocked — no real Anki)."""

import httpx
import pytest

from popstack import anki


def _ankiconnect(monkeypatch, handler):
    """Mock httpx.post to dispatch on the AnkiConnect action."""
    def fake_post(url, *a, **k):
        body = k.get("json", {})
        result = handler(body.get("action"), body.get("params", {}))
        return httpx.Response(200, json={"result": result, "error": None},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(anki.httpx, "post", fake_post)


def test_decks_lists_hierarchy(monkeypatch):
    _ankiconnect(monkeypatch, lambda action, p: ["Default", "agent::agents", "ML::Papers"])
    assert anki.decks()["decks"] == ["Default", "ML::Papers", "agent::agents"]


def test_create_deck_hierarchical(monkeypatch):
    seen = {}
    _ankiconnect(monkeypatch, lambda action, p: seen.update(p) or 1)
    r = anki.create_deck("ML::Papers::pi0")
    assert r["created"] == "ML::Papers::pi0"
    assert seen["deck"] == "ML::Papers::pi0"


def test_create_deck_requires_name():
    assert "error" in anki.create_deck("  ")


def test_add_cards_files_into_given_deck_and_creates_if_missing(monkeypatch):
    calls = []

    def handler(action, params):
        calls.append(action)
        if action == "deckNames":
            return ["Default"]            # target deck does not exist yet
        if action == "createDeck":
            assert params["deck"] == "ML::Papers::pi0"
            return 1
        if action == "addNotes":
            assert params["notes"][0]["deckName"] == "ML::Papers::pi0"
            return [111]
        if action == "sync":
            return None
        return None

    _ankiconnect(monkeypatch, handler)
    r = anki.add_cards([{"front": "q", "back": "a"}], deck="ML::Papers::pi0")
    assert r["added"] == 1 and r["deck"] == "ML::Papers::pi0" and r["note_ids"] == [111]
    assert "createDeck" in calls  # created the hierarchical deck


def test_add_cards_source_backlink_in_back(monkeypatch):
    captured = {}

    def handler(action, params):
        if action == "deckNames":
            return ["ML::Papers::pi0"]
        if action == "addNotes":
            captured["back"] = params["notes"][0]["fields"]["Back"]
            return [222]
        return None

    _ankiconnect(monkeypatch, handler)
    anki.add_cards([{"front": "q", "back": "a", "source": "obsidian://x"}],
                   deck="ML::Papers::pi0", sync=False)
    assert "obsidian://x" in captured["back"]


def test_unavailable_is_graceful(monkeypatch):
    def boom(url, *a, **k):
        raise httpx.ConnectError("no anki")
    monkeypatch.setattr(anki.httpx, "post", boom)
    assert anki.decks()["available"] is False
    assert "error" in anki.add_cards([{"front": "q", "back": "a"}], deck="X")

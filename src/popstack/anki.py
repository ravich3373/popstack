"""AnkiConnect client (add-on 2055492159). Optional: every function returns a
helpful error instead of raising when Anki isn't installed/running. Reviews
belong in Anki's own apps — popstack only creates cards and reads due counts.
"""

from typing import Any

import httpx

from . import config

_TIMEOUT = 8.0


def _call(action: str, timeout: float = _TIMEOUT, **params: Any) -> Any:
    r = httpx.post(
        config.ANKI_URL,
        json={"action": action, "version": 6, "params": params},
        timeout=timeout,
    )
    r.raise_for_status()
    body = r.json()
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body.get("result")


_UNAVAILABLE = (
    "AnkiConnect unreachable. Install Anki + the AnkiConnect add-on "
    "(2055492159) and keep Anki running; cards sync to phone via AnkiWeb."
)


def status(timeout: float = _TIMEOUT, include_decks: bool = True) -> dict[str, Any]:
    """AnkiConnect status. On the scheduled Today.md path, pass a short
    timeout and include_decks=False so a down Anki fails fast (the render
    only needs due_cards)."""
    try:
        version = _call("version", timeout=timeout)
        due = _call("findCards", timeout=timeout, query="is:due")
        out = {"available": True, "ankiconnect_version": version, "due_cards": len(due)}
        if include_decks:
            out["decks"] = _call("deckNames", timeout=timeout)
        return out
    except (httpx.HTTPError, RuntimeError) as e:
        return {"available": False, "error": f"{_UNAVAILABLE} ({e})"}


def add_cards(cards: list[dict[str, str]], deck: str | None = None) -> dict[str, Any]:
    """cards: [{"front": ..., "back": ...}, ...] — Basic notes, duplicate-safe."""
    deck = deck or config.ANKI_DEFAULT_DECK
    try:
        if deck not in _call("deckNames"):
            _call("createDeck", deck=deck)
        notes = [
            {
                "deckName": deck,
                "modelName": "Basic",
                "fields": {"Front": c["front"], "Back": c["back"]},
                "tags": ["popstack"],
                "options": {"allowDuplicate": False},
            }
            for c in cards
        ]
        ids = _call("addNotes", notes=notes)
        added = [i for i in ids if i]
        return {"added": len(added), "skipped_duplicates": len(ids) - len(added), "deck": deck}
    except (httpx.HTTPError, RuntimeError) as e:
        return {"error": f"{_UNAVAILABLE} ({e})"}

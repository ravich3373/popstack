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


def decks() -> dict[str, Any]:
    """List existing deck names. Anki decks are hierarchical via '::'
    (e.g. 'agent::agents::frameworks'), so this is the deck *tree*. Read it
    before adding cards to file them into the right existing deck (ADR-016)."""
    try:
        return {"decks": sorted(_call("deckNames"))}
    except (httpx.HTTPError, RuntimeError) as e:
        return {"available": False, "error": f"{_UNAVAILABLE} ({e})"}


def create_deck(name: str) -> dict[str, Any]:
    """Create a deck. Use '::' for hierarchy — e.g. 'ML::Papers::pi0' nests pi0
    under Papers under ML (Anki creates the whole chain). Idempotent."""
    name = (name or "").strip()
    if not name:
        return {"error": "deck name required"}
    try:
        _call("createDeck", deck=name)
        return {"created": name}
    except (httpx.HTTPError, RuntimeError) as e:
        return {"error": f"{_UNAVAILABLE} ({e})"}


def add_cards(
    cards: list[dict[str, str]], deck: str | None = None, sync: bool = True
) -> dict[str, Any]:
    """cards: [{"front":.., "back":.., "source":..(optional)}, ...] — Basic notes,
    duplicate-safe. Pass an explicit `deck` chosen for the TOPIC (hierarchical
    via '::', e.g. 'ML::Papers::pi0') — call decks() first and reuse/extend the
    existing tree rather than dumping into one bucket (ADR-016). The deck is
    created (with its parents) if missing. `source` carries obsidian://+zotero://
    backlinks (ADR-015). sync=True pushes to AnkiWeb so cards reach your phone."""
    deck = deck or config.ANKI_DEFAULT_DECK
    try:
        if deck not in _call("deckNames"):
            _call("createDeck", deck=deck)
        notes = [
            {
                "deckName": deck,
                "modelName": "Basic",
                "fields": {
                    "Front": c["front"],
                    "Back": c["back"] + (
                        f"<hr><small>source: {c['source']}</small>" if c.get("source") else ""),
                },
                "tags": ["popstack"],
                "options": {"allowDuplicate": False},
            }
            for c in cards
        ]
        ids = _call("addNotes", notes=notes)
        added = [i for i in ids if i]
        synced = False
        if sync and added:
            try:
                _call("sync")
                synced = True
            except (httpx.HTTPError, RuntimeError):
                pass  # not logged into AnkiWeb yet; cards are still added locally
        return {"added": len(added), "note_ids": added,
                "skipped_duplicates": len(ids) - len(added), "deck": deck, "synced": synced}
    except (httpx.HTTPError, RuntimeError) as e:
        return {"error": f"{_UNAVAILABLE} ({e})"}

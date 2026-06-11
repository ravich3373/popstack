"""Zotero access. Reads via the local API (Zotero 7+ desktop, needs
Settings → Advanced → "Allow other applications…" enabled). Writes (add by
DOI) via the web API when ZOTERO_API_KEY/ZOTERO_USER_ID are configured.
"""

import re
import urllib.parse
import uuid
from typing import Any

import httpx

from . import config

_TIMEOUT = 10.0
_DOI_RE = re.compile(r"10\.\d{4,9}/\S+")


def _item_summary(item: dict[str, Any]) -> dict[str, Any]:
    d = item.get("data", {})
    creators = ", ".join(
        " ".join(filter(None, [c.get("firstName"), c.get("lastName")])) or c.get("name", "")
        for c in d.get("creators", [])[:4]
    )
    return {
        "key": item.get("key"),
        "type": d.get("itemType"),
        "title": d.get("title"),
        "creators": creators,
        "date": d.get("date"),
        "doi": d.get("DOI"),
        "url": d.get("url"),
        "tags": [t["tag"] for t in d.get("tags", [])][:8],
        "abstract": (d.get("abstractNote") or "")[:500],
    }


def search(query: str, limit: int = 8) -> dict[str, Any]:
    """Search the local Zotero library (title/creator/year + indexed fulltext)."""
    try:
        r = httpx.get(
            f"{config.ZOTERO_LOCAL_URL}/items",
            params={"q": query, "qmode": "everything", "limit": limit, "itemType": "-attachment"},
            timeout=_TIMEOUT,
        )
        if r.status_code == 403:
            return {
                "error": "Zotero local API refused (403). In Zotero: Settings → Advanced → "
                "enable 'Allow other applications on this computer to communicate with Zotero'."
            }
        r.raise_for_status()
        return {"query": query, "items": [_item_summary(i) for i in r.json()]}
    except httpx.HTTPError as e:
        return {"error": f"Zotero local API unreachable ({e}). Is the Zotero app running?"}


_KEY_RE = re.compile(r"[A-Z0-9]{8}")


def collections(limit: int = 300) -> dict[str, Any]:
    """List the user's Zotero collections (folders) with their full path, e.g.
    'agent/agents/frameworks'. Read-only; works via the local API. Use this to
    file a new paper into the RIGHT existing collection instead of the root."""
    try:
        r = httpx.get(f"{config.ZOTERO_LOCAL_URL}/collections",
                      params={"limit": limit}, timeout=_TIMEOUT)
        if r.status_code == 403:
            return {"error": "Zotero local API refused (403). Enable 'Allow other "
                    "applications…' in Zotero Settings → Advanced."}
        r.raise_for_status()
        by_key = {row["key"]: row.get("data", {}) for row in r.json()}
    except httpx.HTTPError as e:
        return {"error": f"Zotero local API unreachable ({e}). Is Zotero running?"}

    def path(key: str) -> str:
        names, seen = [], set()
        while key and key in by_key and key not in seen:
            seen.add(key)
            d = by_key[key]
            names.append(d.get("name", "?"))
            parent = d.get("parentCollection")
            key = parent if parent else None
        return "/".join(reversed(names))

    cols = [{"key": k, "name": d.get("name", "?"), "path": path(k)} for k, d in by_key.items()]
    cols.sort(key=lambda c: c["path"].lower())
    return {"collections": cols}


def _resolve_collection(spec: str, cols: list[dict[str, Any]]) -> str | None:
    """Resolve a collection spec to its key. Accepts a Zotero key, an exact
    full path (case-insensitive), or an exact collection name."""
    s = spec.strip()
    keys = {c["key"] for c in cols}
    if _KEY_RE.fullmatch(s) and s in keys:
        return s
    sl = s.lower()
    for c in cols:  # exact path first (unambiguous), then exact name
        if c["path"].lower() == sl:
            return c["key"]
    for c in cols:
        if c["name"].lower() == sl:
            return c["key"]
    return None


def _item_from_doi(doi: str) -> dict[str, Any]:
    """Build a Zotero journalArticle item from Crossref metadata for a DOI."""
    meta = httpx.get(
        f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}",
        timeout=_TIMEOUT,
    ).raise_for_status().json()["message"]
    return {
        "itemType": "journalArticle",
        "title": (meta.get("title") or [""])[0],
        "creators": [
            {"creatorType": "author", "firstName": a.get("given", ""), "lastName": a.get("family", "")}
            for a in meta.get("author", [])[:20]
        ],
        "publicationTitle": (meta.get("container-title") or [""])[0],
        "date": "-".join(str(p) for p in meta.get("issued", {}).get("date-parts", [[""]])[0]),
        "DOI": doi,
        "url": meta.get("URL", ""),
    }


def _post_items(url: str, item: dict[str, Any], headers: dict[str, str]) -> tuple[bool, str]:
    """POST one item to a Zotero API (local or web). Returns (ok, key_or_reason)."""
    h = {"Zotero-API-Version": "3", "Zotero-Write-Token": uuid.uuid4().hex, **headers}
    try:
        r = httpx.post(url, json=[item], headers=h, timeout=_TIMEOUT)
    except httpx.HTTPError as e:
        return False, f"unreachable ({e})"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
    try:
        body = r.json()
    except ValueError:
        return False, f"non-JSON response (HTTP {r.status_code})"
    if body.get("successful"):
        return True, next(iter(body["successful"].values()))["key"]
    failed = body.get("failed") or {}
    reason = next(iter(failed.values()), {}).get("message") if failed else "no item created"
    return False, str(reason)


def add_by_doi(doi: str, collection: str | None = None) -> dict[str, Any]:
    """Add a paper to Zotero by DOI, filed into `collection` (a collection key,
    full path like 'agent/agents/frameworks', or exact name). Call
    collections() first and pick the best-matching EXISTING collection — don't
    leave papers in the root. Tries the LOCAL API first, then the WEB API if a
    key + user id are configured. Returns a structured result so the agent knows
    what happened and why."""
    doi = doi.strip()
    if not _DOI_RE.fullmatch(doi):
        return {"added": False, "error": f"not a valid DOI: {doi!r}"}
    try:
        item = _item_from_doi(doi)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return {"added": False, "error": f"could not fetch DOI metadata from Crossref: {e}"}

    filed_path = None
    if collection:
        cols = collections()
        if "error" in cols:
            return {"added": False, "error": f"could not read collections to file the paper: {cols['error']}"}
        key = _resolve_collection(collection, cols["collections"])
        if not key:
            return {"added": False, "title": item["title"],
                    "error": f"collection {collection!r} not found — pick an existing one",
                    "available_collections": [c["path"] for c in cols["collections"]]}
        item["collections"] = [key]
        filed_path = next(c["path"] for c in cols["collections"] if c["key"] == key)

    attempts: dict[str, str] = {}

    # 1) local API (preferred): POST <local>/items, no auth needed
    ok, info = _post_items(f"{config.ZOTERO_LOCAL_URL}/items", item, {})
    if ok:
        return {"added": True, "via": "local", "key": info, "title": item["title"],
                "filed_in": filed_path,
                "note": "added to the running Zotero desktop library; syncs to your other devices"}
    attempts["local"] = info

    # 2) web API fallback (only if configured)
    if config.ZOTERO_API_KEY and config.ZOTERO_USER_ID:
        ok, info = _post_items(
            f"https://api.zotero.org/users/{config.ZOTERO_USER_ID}/items",
            item, {"Zotero-API-Key": config.ZOTERO_API_KEY},
        )
        if ok:
            return {"added": True, "via": "web", "key": info, "title": item["title"],
                    "filed_in": filed_path,
                    "note": "added via the Zotero web API; syncs to the desktop on next sync"}
        attempts["web"] = info
    else:
        attempts["web"] = "not configured (no ZOTERO_API_KEY/ZOTERO_USER_ID)"

    return {
        "added": False,
        "title": item["title"],
        "intended_collection": filed_path,
        "error": "could not add to Zotero. Local write failed and the web API "
                 "is unavailable/unconfigured — add the paper manually (into "
                 f"{filed_path or 'the right collection'}), or set ZOTERO_API_KEY "
                 "+ ZOTERO_USER_ID to enable the web fallback.",
        "attempts": attempts,
    }

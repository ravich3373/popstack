"""Zotero access. Reads via the local API (Zotero 7+ desktop, needs
Settings → Advanced → "Allow other applications…" enabled). Writes (add by
DOI) via the web API when ZOTERO_API_KEY/ZOTERO_USER_ID are configured.
"""

from typing import Any

import httpx

from . import config

_TIMEOUT = 10.0


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


def add_by_doi(doi: str) -> dict[str, Any]:
    """Create a Zotero item from a DOI via Crossref metadata + the web API."""
    if not (config.ZOTERO_API_KEY and config.ZOTERO_USER_ID):
        return {
            "error": "set ZOTERO_API_KEY and ZOTERO_USER_ID for writes "
            "(zotero.org → Settings → Security → API keys)"
        }
    try:
        meta = httpx.get(
            f"https://api.crossref.org/works/{doi}", timeout=_TIMEOUT
        ).raise_for_status().json()["message"]
        item = {
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
        r = httpx.post(
            f"https://api.zotero.org/users/{config.ZOTERO_USER_ID}/items",
            json=[item],
            headers={"Zotero-API-Key": config.ZOTERO_API_KEY, "Zotero-API-Version": "3"},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("successful"):
            key = next(iter(body["successful"].values()))["key"]
            return {"added": True, "key": key, "title": item["title"],
                    "note": "syncs to the desktop library on next Zotero sync"}
        return {"added": False, "response": body}
    except httpx.HTTPError as e:
        return {"error": f"add_by_doi failed: {e}"}

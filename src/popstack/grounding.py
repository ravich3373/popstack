"""Ground a task in what you already know: search the vault (ripgrep when
available, pure-python fallback) and Zotero, return structured hits. The
model on the other end composes the brief — this module just finds.
"""

import json
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import config, zotero

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with",
    "read", "write", "review", "check", "look", "into", "about", "task",
}
_WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def _terms(task: dict[str, Any]) -> list[str]:
    """Search terms from the task: wikilinks (best signal), tags, title words."""
    terms: list[str] = []
    for link in _WIKILINK.findall(task.get("body", "") or ""):
        terms.append(link.strip())
    terms += [str(t) for t in task.get("tags", [])]
    terms += [
        w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", task.get("title", ""))
        if w.lower() not in _STOPWORDS
    ]
    seen: set[str] = set()
    return [t for t in terms if not (t.lower() in seen or seen.add(t.lower()))][:8]


def _rg_search(term: str, vault: Path, limit: int) -> list[dict[str, Any]]:
    # --json gives unambiguous fields (a colon in the vault path or the matched
    # line would corrupt the plain "path:lineno:text" format).
    cmd = ["rg", "-i", "--json", "-m", "3", "-g", "*.md",
           "-g", f"!{config.STACK_DIRNAME}/**", "--fixed-strings", term, str(vault)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    hits: list[dict[str, Any]] = []
    for line in out.stdout.splitlines():
        if len(hits) >= limit:
            break
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") != "match":
            continue
        data = evt["data"]
        path_text = data.get("path", {}).get("text")
        if not path_text:
            continue
        try:
            rel = str(Path(path_text).relative_to(vault))
        except ValueError:
            rel = path_text
        hits.append({"file": rel,
                     "line": data.get("line_number", 0),
                     "snippet": (data.get("lines", {}).get("text") or "").strip()[:240]})
    return hits


def _py_search(term: str, vault: Path, limit: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    needle = term.lower()
    for path in vault.rglob("*.md"):
        if config.STACK_DIRNAME in path.parts:
            continue
        try:
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if needle in line.lower():
                    hits.append({"file": str(path.relative_to(vault)),
                                 "line": lineno, "snippet": line.strip()[:240]})
                    break  # one hit per file per term is enough signal
        except (UnicodeDecodeError, OSError):
            continue
        if len(hits) >= limit:
            break
    return hits


def _search_one(term: str, vault: Path, limit: int) -> list[dict[str, Any]]:
    if shutil.which("rg"):
        try:
            return _rg_search(term, vault, limit)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return _py_search(term, vault, limit)


def vault_search(term: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search every configured vault. Each hit is
    tagged with the `vault` it came from, up to `limit` hits per vault."""
    out: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for vault in config.VAULTS:
        rv = vault.resolve()
        if rv in seen or not vault.exists():
            continue
        seen.add(rv)
        for hit in _search_one(term, vault, limit):
            hit["vault"] = vault.name
            out.append(hit)
    return out


def ground(task: dict[str, Any]) -> dict[str, Any]:
    """Vault + Zotero context for a task, ranked by how many terms hit a note,
    across all configured vaults. Notes are keyed by (vault, file) so the same
    filename in two vaults doesn't collide — and so connections can span vaults."""
    terms = _terms(task)
    file_hits: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"terms": set(), "snippets": []}
    )
    term_vaults: dict[str, set[str]] = defaultdict(set)
    for term in terms:
        for hit in vault_search(term):
            v = hit.get("vault", "")
            entry = file_hits[(v, hit["file"])]
            entry["terms"].add(term)
            term_vaults[term].add(v)
            if len(entry["snippets"]) < 3:
                entry["snippets"].append(hit["snippet"])

    notes = sorted(
        (
            {"vault": vault, "file": f, "matched_terms": sorted(v["terms"]),
             "snippets": v["snippets"]}
            for (vault, f), v in file_hits.items()
        ),
        key=lambda e: -len(e["matched_terms"]),
    )[:10]

    # Concepts that appear in 2+ vaults are cross-vault connection candidates
    # (e.g. a paper's math in one vault + its implementation in another).
    # The substrate for agent-maintained linking (FR-7 / ADR-015).
    cross_vault = sorted(
        ({"term": t, "vaults": sorted(vs)} for t, vs in term_vaults.items() if len(vs) >= 2),
        key=lambda c: c["term"],
    )

    zot = zotero.search(" ".join(terms[:3]) or task.get("title", ""), limit=5)
    return {
        "task_id": task.get("id"),
        "search_terms": terms,
        "vault_notes": notes,
        "cross_vault_connections": cross_vault,
        "zotero": zot,
    }

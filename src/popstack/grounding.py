"""Ground a task in what you already know: search the vault (ripgrep when
available, pure-python fallback) and Zotero, return structured hits. The
model on the other end composes the brief — this module just finds.
"""

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
    cmd = ["rg", "-i", "--no-heading", "-n", "-m", "3", "-g", "*.md",
           "-g", f"!{config.STACK_DIRNAME}/**", "--fixed-strings", term, str(vault)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    hits = []
    for line in out.stdout.splitlines()[:limit]:
        path, _, rest = line.partition(":")
        lineno, _, snippet = rest.partition(":")
        hits.append({"file": str(Path(path).relative_to(vault)),
                     "line": int(lineno or 0), "snippet": snippet.strip()[:240]})
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


def vault_search(term: str, limit: int = 10) -> list[dict[str, Any]]:
    vault = config.VAULT_PATH
    if not vault.exists():
        return []
    if shutil.which("rg"):
        try:
            return _rg_search(term, vault, limit)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return _py_search(term, vault, limit)


def ground(task: dict[str, Any]) -> dict[str, Any]:
    """Vault + Zotero context for a task, ranked by how many terms hit a file."""
    terms = _terms(task)
    file_hits: dict[str, dict[str, Any]] = defaultdict(lambda: {"terms": set(), "snippets": []})
    for term in terms:
        for hit in vault_search(term):
            entry = file_hits[hit["file"]]
            entry["terms"].add(term)
            if len(entry["snippets"]) < 3:
                entry["snippets"].append(hit["snippet"])

    notes = sorted(
        (
            {"file": f, "matched_terms": sorted(v["terms"]), "snippets": v["snippets"]}
            for f, v in file_hits.items()
        ),
        key=lambda e: -len(e["matched_terms"]),
    )[:8]

    zot = zotero.search(" ".join(terms[:3]) or task.get("title", ""), limit=5)
    return {
        "task_id": task.get("id"),
        "search_terms": terms,
        "vault_notes": notes,
        "zotero": zot,
    }

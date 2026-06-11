"""Write notes into the KB in the user's conventions (FR-8, ADR-013) and
maintain cross-tool links (ADR-015). The *agent* decides the content and which
conventions apply (it reads example notes first via grounding); this module is
the safe, durable WRITE primitive + the link bookkeeping.

Safety (this touches the user's real ~4,358-note vault):
- New notes land in a quarantine folder (config.NOTES_DIR) by default — never
  silently mixed into existing folders.
- Writes never clobber: creating an existing note errors unless overwrite=True.
- Appends only add content under a clearly-marked heading; existing prose is
  never rewritten.
- Every write target is validated to live inside a known vault (no traversal).
"""

import datetime as dt
from pathlib import Path
from typing import Any

import frontmatter

from . import config
from .stack import _slugify


def _allowed_roots() -> list[Path]:
    roots = list(config.VAULTS) + [config.NOTES_VAULT]
    return [r.resolve() for r in roots]


def _inside_allowed(path: Path) -> bool:
    rp = path.resolve()
    return any(rp == root or root in rp.parents for root in _allowed_roots())


def _wikilink(name: str) -> str:
    # accept "Note", "[[Note]]", or "[[Note|alias]]" → normalized "[[Note]]"
    n = name.strip()
    if n.startswith("[[") and n.endswith("]]"):
        return n
    return f"[[{n}]]"


def write_note(
    title: str,
    body: str,
    tags: list[str] | None = None,
    related: list[str] | None = None,
    source: str | None = None,
    folder: str | None = None,
    vault: str | None = None,
    overwrite: bool = False,
    preview: bool = False,
) -> dict[str, Any]:
    """Create a markdown note with frontmatter (title/created/tags/source/
    related-wikilinks) in the user's style. Defaults to the quarantine folder.
    preview=True returns the exact file content without writing — show it to the
    user first (ADR-013). Returns the note path and its [[wikilink]]."""
    root = Path(vault).expanduser() if vault else config.NOTES_VAULT
    sub = folder if folder is not None else config.NOTES_DIR
    note_title = title.strip()
    path = (root / sub / f"{_slugify(note_title)}.md")

    if not _inside_allowed(path):
        return {"error": f"refusing to write outside a known vault: {path}"}

    meta: dict[str, Any] = {
        "title": note_title,
        "created": dt.date.today().isoformat(),
    }
    if tags:
        meta["tags"] = list(tags)
    if source:
        meta["source"] = source
    if related:
        meta["related"] = [_wikilink(r) for r in related]
    content = frontmatter.dumps(frontmatter.Post(body.strip() + "\n", **meta)) + "\n"

    wikilink = f"[[{note_title}]]"
    if preview:
        return {"preview": True, "path": str(path), "wikilink": wikilink, "content": content}
    if path.exists() and not overwrite:
        return {"error": f"note already exists: {path} (pass overwrite=True or append_snippet instead)",
                "path": str(path), "wikilink": wikilink}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"written": True, "path": str(path), "wikilink": wikilink}


def _resolve_note(note: str) -> Path | None:
    """Resolve a note by absolute path, or by path/title relative to the notes
    vault or any knowledge vault. Matches both the literal name and the
    slugified filename write_note() produces."""
    p = Path(note).expanduser()
    if p.is_absolute() and p.exists():
        return p
    stem = Path(note).stem
    names = {note, f"{note}.md", f"{_slugify(stem)}.md"}
    patterns = {f"{stem}.md", f"{_slugify(stem)}.md"}
    for root in [config.NOTES_VAULT, *config.VAULTS]:
        for sub in ("", config.NOTES_DIR):
            base = root / sub if sub else root
            for n in names:
                cand = base / n
                if cand.exists():
                    return cand
        for pat in patterns:
            hits = list(root.rglob(pat))
            if hits:
                return hits[0]
    return None


def append_snippet(
    note: str,
    snippet: str,
    lang: str = "",
    heading: str = "Snippets",
    source: str | None = None,
    preview: bool = False,
) -> dict[str, Any]:
    """Append a fenced code block to an existing note, under `heading` (created
    if missing). Never rewrites existing content. `source` adds a provenance
    line (e.g. a repo path / file:line)."""
    path = _resolve_note(note)
    if path is None:
        return {"error": f"note not found: {note!r} (create it with write_note first)"}
    if not _inside_allowed(path):
        return {"error": f"refusing to write outside a known vault: {path}"}

    text = path.read_text(encoding="utf-8")
    block = f"```{lang}\n{snippet.rstrip()}\n```"
    if source:
        block += f"\n<small>source: {source}</small>"

    head = f"## {heading}"
    addition = (block if head in text else f"\n{head}\n\n{block}")
    new_text = text.rstrip() + "\n\n" + addition + "\n"

    if preview:
        return {"preview": True, "path": str(path), "appended": addition}
    path.write_text(new_text, encoding="utf-8")
    return {"appended": True, "path": str(path)}


def add_to_moc(moc: str, link_to: str, note: str = "") -> dict[str, Any]:
    """Add a `- [[link_to]] — note` bullet to a Map-of-Content note (created in
    the notes folder if missing). Keeps the KB navigable as it grows."""
    path = _resolve_note(moc)
    if path is None:
        # create the MOC in the notes folder
        res = write_note(moc, f"# {moc}\n\nIndex.\n", tags=["moc"])
        if "error" in res:
            return res
        path = Path(res["path"])
    line = f"- {_wikilink(link_to)}" + (f" — {note}" if note else "")
    text = path.read_text(encoding="utf-8")
    if _wikilink(link_to) in text:
        return {"already_linked": True, "path": str(path)}
    path.write_text(text.rstrip() + "\n" + line + "\n", encoding="utf-8")
    return {"linked": True, "path": str(path), "line": line}

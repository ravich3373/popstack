"""The popstack MCP server.

Two transports from one process:
    popstack                      # stdio — register in Claude Code locally
    popstack --http               # streamable HTTP — expose via Tailscale
                                  #   Funnel for the claude.ai connector

The bearer token guards header-controllable clients; the claude.ai connector
needs OAuth (not yet implemented) — see README. `--http` refuses to start
without a token unless you pass --insecure (which forces loopback only).
"""

import argparse
import hmac
import sys

from mcp.server.fastmcp import FastMCP

from . import anki as anki_mod
from . import config, grounding
from . import zotero as zotero_mod
from . import codebase as codebase_mod
from . import notes as notes_mod
from . import templates
from .goals import Goals
from .stack import Stack

mcp = FastMCP("popstack")


def _stack() -> Stack:
    return Stack()


# ---------- goals (decompose a source into a plan) ----------

@mcp.tool()
def list_source_templates() -> dict:
    """Source-types that have a built-in decomposition template
    (paper, codebase, language, algorithm, system-design). For anything else,
    decompose it yourself and pass the outline to decompose_source."""
    return {"kinds": templates.kinds(),
            "note": "for an unlisted kind, pass an outline to decompose_source"}


@mcp.tool()
def decompose_source(
    title: str,
    kind: str,
    source: str = "",
    outline: list[dict] | None = None,
) -> dict:
    """Turn a source into an editable goal -> subgoal -> subtask plan (FR-1).
    kind: paper|codebase|language|algorithm|system-design (or your own).
    If kind has a built-in template, omit `outline`. Otherwise YOU decompose
    the source and pass outline=[{"subgoal": str, "subtasks": [str,...]}, ...]
    (the agent fallback). The first subgoal's subtasks start active; the rest
    wait in the reservoir until promote_subgoal. Returns the plan; the user can
    edit it with capture_task/move_task/complete_task."""
    try:
        return Goals().create(title, kind, source or None, outline)
    except ValueError as e:
        return {"error": str(e)}


@mcp.tool()
def show_plan(goal_id: str) -> dict:
    """The goal's plan grouped by subgoal, with progress."""
    try:
        return Goals().plan(goal_id)
    except FileNotFoundError as e:
        return {"error": str(e)}


@mcp.tool()
def list_goals() -> list[dict]:
    """All learning goals with progress."""
    return Goals().list_goals()


@mcp.tool()
def promote_subgoal(goal_id: str) -> dict:
    """Bring the next staged subgoal's subtasks into the active pool (call when
    the current subgoal is done)."""
    try:
        return Goals().promote_next(goal_id)
    except FileNotFoundError as e:
        return {"error": str(e)}


# ---------- the execution loop ----------

@mcp.tool()
def capture_task(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    due: str | None = None,
    priority: str = "medium",
    est_minutes: int | None = None,
    pool: str = "active",
    goal: str | None = None,
    subgoal: str | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Push a new subtask. priority: high|medium|low. Use [[wikilinks]] in body
    to connect it to vault notes. Optionally attach it to a goal/subgoal and
    list dep subtask-ids that must finish first. If the active pool is full it
    lands in the reservoir."""
    return _stack().capture(title, body, tags, due, priority, est_minutes, pool,
                            goal, subgoal, deps)


@mcp.tool()
def draw_next(current_goal: str | None = None) -> dict:
    """Hand over the next subtask to work on — a weighted sample over eligible
    active subtasks (priority + neglect; dependency-blocked and cooling-down
    excluded), biased to CONTINUE the current goal/thread rather than jump to an
    unrelated one (ADR-009). Pass current_goal to force a thread, else it's
    inferred from what you most recently worked. Follow with ground_task, work
    a focused block, then complete_task or park_task."""
    try:
        return _stack().draw(current_goal=current_goal)
    except LookupError as e:
        return {"error": str(e)}


@mcp.tool()
def park_task(task_id: str, next_action: str, cooldown_hours: float | None = None) -> dict:
    """Push a task back onto the stack. next_action is REQUIRED and must be a
    specific next step ("re-derive eq 3", not "continue") — specific plans
    are what stop parked tasks from intruding. Default cooldown 4h."""
    return _stack().park(task_id, next_action, cooldown_hours)


@mcp.tool()
def complete_task(task_id: str, note: str = "") -> dict:
    """Mark a task done (moves it to Stack/done with a timestamp)."""
    return _stack().complete(task_id, note)


@mcp.tool()
def move_task(task_id: str, to: str) -> dict:
    """Promote a task to 'active' or shelve it to 'reservoir'."""
    return _stack().move(task_id, to)


@mcp.tool()
def list_stack(pool: str = "active") -> list[dict]:
    """List tasks in a pool (active|reservoir|done). Active is sorted by
    current pop weight."""
    return _stack().list_pool(pool)


@mcp.tool()
def stack_health() -> dict:
    """Counts, overdue tasks, and stale tasks (3+ pushes or >30 days old) —
    the weekly-review view."""
    return _stack().health()


@mcp.tool()
def record_usage(input_tokens: int, output_tokens: int,
                 task_id: str | None = None, model: str | None = None) -> dict:
    """Record token usage against a subtask (default: the in-focus one). popstack
    cannot measure tokens itself — the LLM does — so the client supplies them.
    Usually called automatically by a Claude Code Stop hook (see usage.py); call
    it directly only if you have real token counts to attribute."""
    return _stack().record_usage(input_tokens, output_tokens, task_id, model)


@mcp.tool()
def usage_report() -> dict:
    """Token totals per task and per goal (and grand total), from what's been
    recorded via record_usage / the Stop hook."""
    return _stack().usage_report()


# ---------- codebases ----------

@mcp.tool()
def clone_repo(url: str) -> dict:
    """Shallow-clone a GitHub/git repo into the local workspace for a codebase
    learning goal. Returns the local path to read."""
    return codebase_mod.clone_repo(url)


@mcp.tool()
def map_repo(path: str) -> dict:
    """Map a local repo: languages by line count, build system, likely entry
    points, top-level layout, README. Use this to ground a codebase decompose_
    source (pass the result as the outline, or read the entry points first)."""
    return codebase_mod.map_repo(path)


# ---------- writing into the KB (FR-8 / ADR-013, ADR-015) ----------

@mcp.tool()
def write_note(title: str, body: str, tags: list[str] | None = None,
               related: list[str] | None = None, source: str | None = None,
               folder: str | None = None, vault: str | None = None,
               overwrite: bool = False, preview: bool = False) -> dict:
    """Create a KB note in the user's conventions (frontmatter + [[wikilinks]]).
    Defaults to a quarantine folder so it never silently mixes into the vault.
    ALWAYS call with preview=True first and show the user the content before
    writing for real (ADR-013). `related` are note titles to wikilink; `source`
    is a provenance link (zotero://, repo url, file path)."""
    return notes_mod.write_note(title, body, tags, related, source, folder, vault,
                                overwrite, preview)


@mcp.tool()
def append_snippet(note: str, snippet: str, lang: str = "", heading: str = "Snippets",
                   source: str | None = None, preview: bool = False) -> dict:
    """Append a fenced code snippet to an EXISTING note under `heading` (never
    rewrites existing content). `note` is a title or path; `source` is e.g.
    repo/file:line. Use preview=True first."""
    return notes_mod.append_snippet(note, snippet, lang, heading, source, preview)


@mcp.tool()
def add_to_moc(moc: str, link_to: str, note: str = "") -> dict:
    """Add a `- [[link_to]] — note` bullet to a Map-of-Content note (created if
    missing), to keep the KB navigable as it grows."""
    return notes_mod.add_to_moc(moc, link_to, note)


@mcp.tool()
def ground_task(task_id: str) -> dict:
    """Find what the vault and Zotero already know about a task (searches by
    its wikilinks, tags, and title terms). Compose the results into a short
    brief before starting the timebox."""
    stack = _stack()
    path = stack._path(task_id)
    post = stack._load(path)
    task = stack._summary(path, post, body=post.content)
    return grounding.ground(task)


@mcp.tool()
def vault_search(query: str, limit: int = 10) -> list[dict]:
    """Full-text search over the Obsidian vault (excludes the Stack folder)."""
    return grounding.vault_search(query, limit)


@mcp.tool()
def zotero_search(query: str, limit: int = 8) -> dict:
    """Search the Zotero library (local API; metadata + indexed fulltext)."""
    return zotero_mod.search(query, limit)


@mcp.tool()
def zotero_add_doi(doi: str) -> dict:
    """Add a paper to Zotero by DOI (web API; requires ZOTERO_API_KEY)."""
    return zotero_mod.add_by_doi(doi)


@mcp.tool()
def anki_add_cards(cards: list[dict], deck: str | None = None) -> dict:
    """Create Anki cards from recall misses. cards: [{"front":..,"back":..}].
    Reviews happen in Anki's own apps; this only writes."""
    return anki_mod.add_cards(cards, deck)


@mcp.tool()
def anki_status() -> dict:
    """AnkiConnect availability, due-card count, deck names."""
    return anki_mod.status()


class _BearerAuth:
    """Minimal ASGI middleware: require Authorization: Bearer <AUTH_TOKEN>.

    Note: a shared bearer token works for header-controllable MCP clients
    (Claude Code's `--header`, curl, the Agent SDK), NOT for the claude.ai
    web/mobile custom connector, which requires OAuth 2.1 (see README).
    """

    def __init__(self, app, token: str):
        self.app, self.token = app, token
        self._expected = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Let CORS preflight through (it can't carry the auth header).
            if scope.get("method") == "OPTIONS":
                await send({"type": "http.response.start", "status": 204,
                            "headers": [(b"content-length", b"0")]})
                await send({"type": "http.response.body", "body": b""})
                return
            headers = dict(scope.get("headers") or [])
            got = headers.get(b"authorization", b"").decode()
            if not hmac.compare_digest(got, self._expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await self.app(scope, receive, send)


def main() -> None:
    parser = argparse.ArgumentParser(description="popstack MCP server")
    parser.add_argument("--http", action="store_true",
                        help="serve streamable HTTP (default: stdio)")
    parser.add_argument("--insecure", action="store_true",
                        help="allow --http with no auth token (binds 127.0.0.1 only)")
    args = parser.parse_args()

    if not args.http:
        mcp.run()  # stdio
        return

    try:
        import uvicorn
    except ModuleNotFoundError:
        sys.exit("--http needs the 'http' extra: pip install 'popstack[http]'")

    app = mcp.streamable_http_app()
    host = config.HOST
    if config.AUTH_TOKEN:
        app = _BearerAuth(app, config.AUTH_TOKEN)
    elif args.insecure:
        # fail-safe: an unauthenticated endpoint may never leave loopback.
        host = "127.0.0.1"
        print("WARNING: --insecure: serving UNAUTHENTICATED on 127.0.0.1 only.")
    else:
        sys.exit(
            "refusing to serve --http without POPSTACK_AUTH_TOKEN.\n"
            "Set a token (openssl rand -hex 32) or pass --insecure for "
            "loopback-only unauthenticated use."
        )
    uvicorn.run(app, host=host, port=config.PORT)


if __name__ == "__main__":
    main()

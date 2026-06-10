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
from .stack import Stack

mcp = FastMCP("popstack")


def _stack() -> Stack:
    return Stack()


@mcp.tool()
def capture_task(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    due: str | None = None,
    priority: str = "medium",
    est_minutes: int | None = None,
    pool: str = "active",
) -> dict:
    """Push a new task. priority: high|medium|low. due: YYYY-MM-DD. Use
    [[wikilinks]] in body to connect the task to vault notes (improves
    grounding). If the active pool is full it lands in the reservoir."""
    return _stack().capture(title, body, tags, due, priority, est_minutes, pool)


@mcp.tool()
def pop_task() -> dict:
    """Weighted-random pop from the active pool (deadline + priority +
    capped age; cooling-down tasks excluded). Returns the task with its
    weight breakdown. Follow with ground_task, then work a timebox, then
    complete_task or park_task."""
    try:
        return _stack().pop()
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

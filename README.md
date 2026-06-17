# popstack

A **personal learning agent** as an MCP server. You hand it a technical source
— an ML/CS paper, a codebase, a topic — and it decomposes it into an editable
plan, drives you through it, grounds each step in what your Obsidian vaults +
Zotero already know, and makes it *stick* with Anki spaced repetition and
cross-vault connections.

```
source → decompose → draw next step → ground → understand → retain (Anki) → connect → ingest
```

The execution engine (drawing the next step, parking with an if-then next
action, completion, the daily view) is built; decomposition, multi-vault
grounding, retention, connections, and doc-ingestion are the P2–P5 roadmap.

> Was: a generic random "task stack" (v1). Pivoted to a learning agent once the
> real purpose became clear — see [PRD](docs/PRD.md) and ADR-008. The engine
> survives as one component.

**Status:** the engine + P2 (decompose / goal trees / goal-aware draw) are
**code-complete and tested.** Usable on the laptop once you register it with
Claude Code (see [Use from Claude Code](#use-from-claude-code-laptop-stdio));
**phone access is designed, not built.** (Per-machine deployment state is
operator-local — see `local/`, gitignored — not tracked in this repo.)

**Docs:** [Setup & Usage](docs/SETUP.md) (start here — install, configure, use) ·
[PRD](docs/PRD.md) (what & why) · [Architecture](docs/ARCHITECTURE.md)
(how it runs / what's live) · [Design](docs/DESIGN.md) (how each part works) ·
[Portability](docs/PORTABILITY.md) (learn anywhere) ·
[Decision log](docs/DECISIONS.md) (why these choices — argue with this one)

## Layout in the vault

```
<vault>/Stack/
  active/      eligible for pops (capped, default 20)
  reservoir/   someday / not-now (capture overflow lands here)
  done/        completed history
  Today.md     generated glanceable view (popstack-today)
```

Each task = one `.md` file with frontmatter (`title`, `priority`, `due`,
`pushes`, `cooldown_until`, `next_action`, `tags`, `est_minutes`). Use
`[[wikilinks]]` in task bodies — grounding searches by them first.

## Setup

```bash
cd popstack
uv sync
cp .env.example .env   # edit: vault path, auth token, zotero key (optional)
uv run pytest          # should be green
```

- **Zotero**: enable *Settings → Advanced → "Allow other applications on this
  computer to communicate with Zotero"* (fixes the local-API 403). Reads need
  no key. `zotero_add_doi` tries the local library first, then the web API if
  `ZOTERO_API_KEY` + `ZOTERO_USER_ID` are set (local writes are often
  read-only); otherwise it reports the failure so you can add the paper manually.
- **Anki** (optional): install Anki + AnkiConnect add-on `2055492159`; keep
  Anki running. Cards sync to your phone via AnkiWeb; reviews happen in
  AnkiMobile/AnkiDroid.

## Use from Claude Code (laptop, stdio)

```bash
claude mcp add popstack --scope user -- uv --directory ~/Documents/repos/popstack run popstack
```

Then in any session: *"decompose this paper"*, *"draw the next subtask and
ground it"*, *"park it — next action: re-derive the update rule"*.

## Token usage per task

popstack can't *measure* tokens (the model consumes them; the client sees the
counts), but it **records and attributes** them per subtask. Add a Claude Code
**Stop hook** so each turn's real usage (from the transcript) lands on whatever
subtask you most recently drew. In `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      { "matcher": "", "hooks": [
        { "type": "command",
          "command": "uv --directory ~/Documents/repos/popstack run popstack-usage --hook" }
      ]}
    ]
  }
}
```

Then ask *"usage_report"* (or call the tool) for per-task and per-goal totals.
Tokens are also shown on each task (`tokens_in`/`tokens_out`). You can record
manually too: `record_usage(input_tokens, output_tokens, task_id?)`.

## Use from your phone

> ⚠️ **The claude.ai connector route is not ready yet.** claude.ai web/mobile
> custom connectors authenticate via **OAuth 2.1** (PKCE / dynamic client
> registration), not a static bearer token — there is no field to paste a
> token into. popstack does not implement an OAuth provider yet (it's the
> P1 milestone). So the phone-via-Claude-app path is **blocked on OAuth**.
>
> What *does* work on the phone today:
> - **Obsidian mobile** renders the Stack and `Today.md` (below) over your
>   vault's own sync — glanceable, and you can capture by editing markdown.
> - Any **header-controllable MCP client** (Claude Code with `--header`,
>   curl, the Agent SDK) can use the HTTP endpoint with the bearer token.

The HTTP transport, for those header-controllable clients (and as the base
the future OAuth layer will wrap):

```bash
uv sync --extra http              # installs uvicorn (only the --http path needs it)
set -a; source .env; set +a       # POPSTACK_AUTH_TOKEN must be set
uv run popstack --http            # serves 127.0.0.1:8444; refuses to start unauthenticated
# first time only: enable Funnel for your tailnet, then:
tailscale funnel --bg 8444        # 8444 = LOCAL port; public URL lands on :443 — copy what it prints
```

> Funnel makes the endpoint **public internet**. The bearer token is the
> floor; real login (MCP OAuth) is the P1 upgrade — do it before any task
> body holds anything sensitive.

## Tier 2: the glanceable Today.md

```bash
uv run popstack-today   # writes <vault>/Stack/Today.md
```

Schedule it (launchd/cron) every morning on the always-on node; Obsidian sync
puts it on your phone. Top-3 by weight, overdue, stale (3+ pushes), Anki due.

## Smoke checklist

After `uv sync`, a quick end-to-end sanity check:

- `uv run pytest -q` — 30 tests green.
- 13 tools registered: `uv run python -c "import asyncio; from popstack.server import mcp; print(len(asyncio.run(mcp.list_tools())))"`
- HTTP fails closed: `POPSTACK_AUTH_TOKEN= uv run popstack --http` refuses to start.
- Full loop (against a throwaway vault):
  `POPSTACK_VAULT=$(mktemp -d) uv run python -c "from popstack.stack import Stack; s=Stack(); t=s.capture('demo'); p=s.pop(); print(s.park(p['id'],'next step')); print(s.complete(p['id']))"`

## Design notes (the why)

- **Weighted sampling, not LIFO/uniform**: Taskwarrior's urgency model ported
  to sampling weights; aging escalates with a ceiling (their maintainers'
  answer to staleness), cooldowns stop pop-park ping-pong.
- **Small active pool + reservoir**: choice-overload effects are conditional
  on large similar option sets — keep the draw pool small (Llama Life's
  "Not Now" precedent).
- **park() requires next_action**: specific plans, not bare capture, are what
  stop open tasks from intruding (Masicampo & Baumeister 2011).
- **Vault as database**: capture/sync/phone-GUI come free with Obsidian;
  tasks live in the same graph as knowledge, so grounding is wikilink-native.

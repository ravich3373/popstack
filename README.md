# popstack

Personal task stack as an MCP server. Tasks live as markdown in your Obsidian
vault (so every device already renders and syncs them); pops are
**weighted-random** (deadline + priority + capped aging — stale tasks surface
*more*, bounded); parking a task **requires a one-line next action**;
grounding searches your vault + Zotero; recall misses become Anki cards.

```
push → pop (weighted random) → ground → timebox → complete | park(next_action)
```

**Docs:** [PRD](docs/PRD.md) (what & why) · [Design](docs/DESIGN.md) (how) ·
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
  computer to communicate with Zotero"* (fixes the local-API 403). For
  `zotero_add_doi`, create an API key at zotero.org → Settings → Security.
- **Anki** (optional): install Anki + AnkiConnect add-on `2055492159`; keep
  Anki running. Cards sync to your phone via AnkiWeb; reviews happen in
  AnkiMobile/AnkiDroid.

## Use from Claude Code (laptop, stdio)

```bash
claude mcp add popstack --scope user -- uv --directory ~/Documents/repos/popstack run popstack
```

Then in any session: *"pop a task and ground it"*, *"park it — next action:
re-derive the update rule"*, *"capture: read the FSRS paper, due Friday"*.

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

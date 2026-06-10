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

## Use from your phone (claude.ai connector over Tailscale)

1. On the always-on node:
   ```bash
   set -a; source .env; set +a       # POPSTACK_AUTH_TOKEN must be set!
   uv run popstack --http            # serves 127.0.0.1:8444
   tailscale funnel --bg 8444        # public HTTPS url on your tailnet node
   ```
2. claude.ai → Settings → Connectors → **Add custom connector** → the Funnel
   URL + `/mcp` path. Configure the bearer token if the connector UI offers
   auth headers; the server rejects requests without it either way.
3. The Claude iOS/Android app now pops/parks/grounds from anywhere.

> Funnel makes the endpoint public. The bearer check in `server.py` is the
> minimum viable guard; the proper upgrade is MCP OAuth — do that before
> putting anything sensitive in task bodies.

## Tier 2: the glanceable Today.md

```bash
uv run popstack-today   # writes <vault>/Stack/Today.md
```

Schedule it (launchd/cron) every morning on the always-on node; Obsidian sync
puts it on your phone. Top-3 by weight, overdue, stale (3+ pushes), Anki due.

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

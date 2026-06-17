# Setup & Usage

> The one place that walks you from a fresh clone to actually using popstack on
> your laptop, including token-usage tracking. Runtime concepts are in
> [ARCHITECTURE.md](ARCHITECTURE.md); phone access is in
> [PORTABILITY.md](PORTABILITY.md) (not built yet).

The laptop path below is the only working way to use it today; phone access is designed but not built (see [PORTABILITY.md](PORTABILITY.md)).

---

## 0. Prerequisites

- **uv** (Python package runner) — `which uv` should resolve. The repo targets
  Python ≥3.12.
- **Claude Code** (the CLI) installed and logged in — this is the client that
  runs the agent and launches popstack.
- **ripgrep** (`rg`) recommended for fast vault search (a pure-python fallback
  exists if it's missing).
- The repo at `~/Documents/repos/popstack`.

---

## 1. One-time setup (laptop)

### 1a. Install dependencies
```bash
cd ~/Documents/repos/popstack
uv sync                 # core; add `--extra http` only if you'll serve over HTTP later
uv run pytest -q        # sanity: should be all green
```

### 1b. Configure `.env`
Create a `.env` from `.env.example`, pointing at your own vaults, with a generated auth token. Check it:
```bash
cat .env
```
Key settings:
- `POPSTACK_VAULT` — where the task **Stack** lives (a vault folder you choose).
- `POPSTACK_VAULTS` — the knowledge vaults **grounding** searches
  (comma-separated paths to your vaults). The Stack vault is always included.
- `POPSTACK_AUTH_TOKEN` — only used for the HTTP transport (phone, later).

### 1c. Register popstack with Claude Code (the one command)
```bash
claude mcp add popstack --scope user -- uv --directory ~/Documents/repos/popstack run popstack
```
- `--scope user` = available in **all** Claude Code sessions on this laptop.
- This is per-machine, **not** per-device — see [ARCHITECTURE §3b](ARCHITECTURE.md#3b-do-i-configure-this-on-every-device-no).
- Verify: `claude mcp list` should show `popstack`. Undo anytime with
  `claude mcp remove popstack`.

### 1d. Enable token-usage tracking (the Stop hook)
popstack can't measure tokens itself; this hook feeds it each turn's real usage
(from the transcript) and attributes it to the subtask you're working. Add to
`~/.claude/settings.json`:
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
That's it — tokens now accrue per task automatically. (Skip this if you don't
care about usage; everything else works without it.)

### 1e. Optional integrations
- **Zotero** (for paper grounding): in Zotero, enable *Settings → Advanced →
  "Allow other applications on this computer to communicate with Zotero."*
  Reading/grounding needs **no API key** (it uses the local API at `users/0`).
  `zotero_add_doi` tries the local library first, but most Zotero builds make
  the local API **read-only**, so add-by-DOI usually falls back to the web API
  — set `ZOTERO_API_KEY` + `ZOTERO_USER_ID` (zotero.org → Settings → Security)
  to enable that, or just add papers manually (the agent will tell you clearly
  if a DOI add couldn't go through).
- **Anki** (retention — the P3 layer): install Anki + the AnkiConnect add-on
  `2055492159`, keep Anki running. Cards sync to your phone via AnkiWeb; you
  review in AnkiDroid/AnkiMobile. (Not required for the core loop.)

---

## 2. Daily use

You don't call tools by hand — you talk to Claude Code in plain language and it
calls popstack's tools. A typical learning session:

| You say… | What happens (tools) |
|---|---|
| "Decompose the π₀ paper — it's in Zotero. Use the paper template." | `decompose_source(kind="paper", …)` → an editable goal tree |
| "Show me the plan." | `show_plan(goal_id)` |
| "Tweak it — I already know diffusion policies, drop that subgoal; add 'compare to baselines'." | `complete_task`/`move_task`/`capture_task` |
| "What should I work on now?" | `draw_next` — the next subtask, biased to continue this goal |
| "Ground it." | `ground_task` — relevant notes across your vaults + Zotero, with cross-vault connections |
| "Learn the llama.cpp codebase — here's the GitHub URL." | `clone_repo` → `map_repo` → `decompose_source(kind="codebase", …)` |
| "Add this function to my Sampler note." | `append_snippet(note, code, lang, source="repo/file:line")` (preview first) |
| "Make a note for flow matching, link it to DDPM and the paper." | `write_note(title, body, related, source)` (preview first) |
| "I get it — park this. Next: implement the sampler and check Figure 3." | `park_task(task_id, next_action=…)` |
| "Done with this one." | `complete_task` |
| "Finished the math subgoal — bring in the next." | `promote_subgoal(goal_id)` |
| "How are my goals going?" | `list_goals` / `stack_health` |
| "How many tokens has this paper cost me?" | `usage_report` |

The loop, in short: **decompose → draw → ground → understand → (cards) →
park/complete → promote.**

---

## 3. Tool reference (25 tools)

**Planning** — `list_source_templates`, `decompose_source`, `show_plan`,
`list_goals`, `promote_subgoal`

**The loop** — `capture_task`, `draw_next`, `park_task`, `complete_task`,
`move_task`, `list_stack`, `stack_health`

**Knowledge / grounding** — `ground_task`, `vault_search`, `zotero_search`,
`zotero_add_doi`

**Codebases** — `clone_repo`, `map_repo`

**Writing into the KB** — `vault_layout` (discover folders + MOCs first),
`write_note`, `append_snippet`, `add_to_moc` (file into the right existing
folder/MOC; always `preview=True` first)

**Retention (Anki)** — `anki_decks`, `anki_create_deck`, `anki_add_cards`,
`anki_status` (decks are hierarchical via `::`; file cards into a topic deck,
not one bucket)

**Token usage** — `record_usage`, `usage_report`

Source-type templates with built-in decompositions: **paper, codebase,
language, algorithm, system-design**. For anything else, the agent decomposes it
and passes its own outline (the fallback).

---

## 4. Verify it works

```bash
# 30-second offline check (throwaway vault), exercises the full loop:
POPSTACK_VAULT=$(mktemp -d) uv run python - <<'PY'
from popstack.goals import Goals
from popstack.stack import Stack
g = Goals(Stack())
plan = g.create("Understand pi0", "paper", source="zotero:DEMO")
print("subgoals:", [s["subgoal"] for s in plan["subgoals"]])
d = g.stack.draw()
print("drew:", d["title"][:40], "| goal:", d["goal"])
g.stack.record_usage(2000, 400)
print("usage:", g.stack.usage_report()["total"])
PY
```

In Claude Code: start a **new** session after step 1c, then ask
*"list_source_templates"* — if popstack is wired up, you'll get the five kinds.

---

## 5. Troubleshooting

- **Claude doesn't see the tools** → you registered in an existing session;
  start a new one. Check `claude mcp list`.
- **Zotero search returns a 403** → enable the "Allow other applications…"
  setting (1e).
- **`anki_*` say "unreachable"** → Anki isn't running / AnkiConnect not
  installed; the rest of popstack is unaffected.
- **`usage_report` is empty** → the Stop hook isn't firing or you haven't drawn
  a task yet; usage attributes to the most recently `draw_next`ed subtask.
- **Grounding finds nothing** → check `POPSTACK_VAULTS` points at real folders.

---

## 6. Later (not yet built)

- **Retention on the phone** — install Anki, set up AnkiWeb sync (P3).
- **The agent on your phone** — a home server running `popstack --http` over
  Tailscale + a claude.ai connector. See [PORTABILITY.md](PORTABILITY.md).

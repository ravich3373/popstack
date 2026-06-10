# Design Doc — popstack

> **What a design doc is for:** given the [PRD](PRD.md)'s *what/why*, this
> records *how* — architecture, data model, algorithms, contracts, and the
> alternatives that were rejected (so they don't get re-litigated by
> accident). When you change the *how*, update this doc and add an entry to
> [DECISIONS.md](DECISIONS.md).

- **Status:** implemented (P0) · **Last updated:** 2026-06-10

## 1. Architecture

The central idea: **separate where the agent runs from where you touch it.**
One small server on an always-on node; the GUIs are apps you already use.

```
┌─ always-on node ───────────────────────────────────────────────┐
│                                                                │
│  popstack MCP server (Python, FastMCP)                         │
│  ├── stack.py      task engine     ──►  <vault>/Stack/*.md     │
│  ├── grounding.py  vault search    ──►  <vault>/**/*.md  (rg)  │
│  ├── zotero.py     papers          ──►  localhost:23119 (read) │
│  │                                      api.zotero.org  (write)│
│  ├── anki.py       cards           ──►  localhost:8765         │
│  └── today.py      Today.md        ──►  <vault>/Stack/Today.md │
│                                                                │
│  transports:  stdio (local)  ·  streamable HTTP :8444 (remote) │
└───────┬──────────────────────────────┬─────────────────────────┘
        │ stdio                        │ Tailscale Funnel (HTTPS, bearer)
        ▼                              ▼
  Claude Code (laptop)        claude.ai connector → Claude iOS/Android/web
                                       +
                       Obsidian mobile (renders Stack/ + Today.md via sync)
                       AnkiMobile/AnkiDroid (reviews, via AnkiWeb sync)
```

Key property: popstack has **no database and no UI**. The vault is the
database (and Obsidian its viewer); Claude apps are the interactive UI;
Anki's apps own reviews. popstack is ~600 lines of glue with good semantics.

## 2. Data model

A task is one markdown file; the pool is encoded by directory:

```
<vault>/Stack/
  active/      pop-eligible, capped (ACTIVE_LIMIT=20)
  reservoir/   someday / not-now / overflow
  done/        completed (history)
  Today.md     generated; not a task (lives outside pool dirs)
```

### Task file

```markdown
---
title: Read FSRS scheduler paper
created: 2026-06-10T09:00:00        # set on capture; drives the age term
priority: high                       # high | medium | low
due: 2026-06-12                      # optional
pushes: 1                            # park count; 3+ ⇒ flagged stale
next_action: summarize section 2     # required by park(); the warm-start
cooldown_until: 2026-06-10T13:00:00  # pop-ineligible until then
last_popped: 2026-06-10T09:14:02
tags: [learning]
est_minutes: 30
---
Free-form notes. [[spaced repetition]] wikilinks here are the *primary*
grounding signal — tasks live in the same graph as knowledge.

- parked 2026-06-10T09:44 → next: summarize section 2
```

### Lifecycle

```
            capture (overflow)               promote
  capture ──────────────────────► reservoir ────────► active
     │                                ▲                  │ pop (stamp last_popped)
     ▼                        shelve  │                  ▼
   active ────────────────────────────┘        complete │ park(next_action!)
     │                                            │     └─► same file: pushes+1,
     └────────────── complete ────────────────────┴──► done/   cooldown set
```

Parks *modify in place* and append a history line — a task accumulates its
own narrative, which is exactly what you want rendered in Obsidian.

## 3. Pop algorithm

Weighted random sample over eligible active tasks (cooldowns excluded):

```
weight = 1.0  base        — everything stays drawable (it's a sample, not a sort)
       + 12.0 · clamp((14 − days_until_due)/14, 0, 1)   — due ramp, capped when overdue
       + {high: 6, medium: 3, low: 0}                   — priority
       +  2.0 · min(age_days/365, 1)                    — aging: UP, with a ceiling
```

Worked example (from the smoke test, 2 days to due, high):
`1 + 10.36 + 6 + 0 ≈ 17.4` vs a fresh undated medium task `1 + 0 + 3 + 0 = 4`
→ ~81/19 draw odds. Urgency dominates; nothing starves.

Rationale (see ADR-002/003): constants are a port of Taskwarrior's
battle-tested urgency coefficients (due 12, priority H 6, age 2 capped) from
deterministic *ranking* into *sampling weights*. Deterministic ranking would
re-serve the same task after every park (loop-lock); uniform random starves
deadlines. Aging goes **up** with a ceiling — Taskwarrior's maintainers'
explicit position is stale tasks must surface more, bounded so one ancient
task can't dominate the draw.

Cooldown (default 4 h) prevents pop→park→pop ping-pong of one heavy task.

## 4. Component map

| File | Responsibility | Notes |
|------|----------------|-------|
| `config.py` | env-driven settings | no config files; .env sourced by launcher |
| `stack.py` | engine: capture/pop/park/complete/move/list/health | pure stdlib + `frontmatter`; fully unit-tested |
| `grounding.py` | term extraction (wikilinks > tags > title words) → vault search (ripgrep, python fallback) → merge with Zotero hits | returns structured hits; the *model* writes the brief |
| `zotero.py` | local API reads (`q=&qmode=everything`), Crossref→web-API writes | 403 → actionable message about the Zotero setting |
| `anki.py` | AnkiConnect: status/add cards (Basic, dup-safe) | absent Anki → `{available: false, error: how-to}` |
| `server.py` | FastMCP wiring of 13 tools; stdio + HTTP; bearer middleware | tools carry docstrings = the model's usage manual |
| `today.py` | render Today.md (top-3 by weight, overdue, stale, Anki due) | run by launchd/cron |

A deliberate seam: **stack.py knows nothing about MCP** and server.py holds
no logic. The engine is importable by a future PWA backend (P3), a CLI, or
tests without touching the protocol layer.

## 5. Transports & security

- **stdio** — local Claude Code; OS-user trust boundary; no auth.
- **streamable HTTP** (`--http`, 127.0.0.1:8444) — for remote use via
  `tailscale funnel 8444`. Funnel is **public internet**; defense layers:
  1. Bearer middleware (401 without `Authorization: Bearer <token>`); token
     required in config before exposing.
  2. Funnel off by default; enable when needed.
  3. Planned (P1 exit): MCP OAuth — the proper answer, required before task
     bodies contain anything sensitive (PRD R-1).
- Blast radius if breached: read/write of vault markdown + Anki card
  creation + Zotero metadata writes. No shell, no arbitrary file paths
  (all paths derive from config, ids are slugs resolved within Stack/).

## 6. Alternatives considered

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Task store | vault markdown | Todoist API backend; SQLite | sync+phone GUI free via Obsidian; tasks join the knowledge graph (grounding); no lock-in (NFR-1). Todoist won the *pre-Obsidian* analysis — integrating the vault flipped it (ADR-001) |
| Pop semantics | weighted random | LIFO stack; uniform random; deterministic rank | LIFO buries old (why xtask-cli died); uniform starves urgent; deterministic loop-locks after parks (ADR-002) |
| Pool structure | small active + reservoir | one big stack | choice-overload effects are conditional on large similar sets; cap doubles as WIP limit (ADR-004) |
| Park rule | next_action mandatory | free-form park | specific plans stop open-task intrusion (Masicampo & Baumeister 2011); cheap to enforce at the API (ADR-005) |
| Server | custom FastMCP (~600 loc) | community Obsidian/Zotero/Anki MCP servers composed | the *loop semantics* (weights, cooldowns, park contract) are the product; generic servers can't enforce them. Zotero/Anki client code is trivial (ADR-006) |
| Remote GUI | claude.ai connector | build PWA now | zero UI code for full interactivity; PWA deferred until usage proves which 4 screens matter (PRD P3) |
| Reviews | Anki's own apps | in-popstack SRS | FSRS + offline + mobile polish are years of work shipped free; popstack only writes cards (ADR-006) |

## 7. Failure modes

| Failure | Behavior |
|---|---|
| Zotero app closed / API disabled | grounding returns vault hits + explanatory `zotero.error`; loop unaffected (NFR-4) |
| Anki not installed | `anki_*` return install instructions; never raises |
| Vault path wrong | Stack dirs are created where pointed; `vault_search` returns `[]` — fix .env |
| Concurrent edits (sync conflict) | server is the only *writer* of Stack files in practice; Obsidian merge handles body text; frontmatter conflict = last-writer-wins (accepted, R-3) |
| Empty/all-cooling pool | `pop_task` returns a structured error telling you to promote/wait |

## 8. Testing

- `tests/test_stack.py` — 11 unit tests on the engine: capture/overflow,
  weighting (statistical: 300 seeded draws), cooldown exclusion, park
  contract, completion moves, pool caps, health flags. Pure tmpdir, no I/O
  beyond files.
- Integrations (Zotero/Anki) are thin HTTP clients verified by smoke test;
  unit-mocking them would test the mocks. Revisit if logic grows.
- Smoke (manual, documented in README): 13 tools registered; HTTP 401/200
  auth behavior; full capture→pop→park→Today.md flow.

## 9. Future work

P1: launchd schedule, Funnel runbook, weight tuning. P2: recall drills
(prompt/skill layer — likely a `drill.py` choosing a random vault note /
Zotero item + an MCP prompt template), metric instrumentation (pop/park/done
counts are already derivable from frontmatter — add a `stats` tool). P3: PWA
(SDK backend reusing `stack.py` unchanged — the seam in §4 exists for this).

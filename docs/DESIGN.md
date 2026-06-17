# Design Doc — popstack

> **What a design doc is for:** the [PRD](PRD.md) says *what* the product
> must do and *why*; this document says *how* — architecture, data model,
> algorithms, integration contracts, and the alternatives that were
> rejected (recorded so they don't get re-litigated by accident). When the
> *how* changes, update this file and log the reasoning in
> [DECISIONS.md](DECISIONS.md).
>
> **Audience:** a developer with no prior context (you, in six months).
> Every tool and acronym is glossed on first use. If a section assumes
> something unstated, treat that as a bug in the doc.

- **Status:** P1 (execution engine) implemented; P2–P6 designed below.
- **Vocabulary** (goal, subgoal, subtask, draw, ground, park, recall card…) is
  defined in [PRD §2](PRD.md#2-words-this-document-uses) and used here without
  re-definition.

## 0. v2 architecture — the learning agent

> The product pivoted ([DECISIONS](DECISIONS.md) ADR-008): popstack is a
> *learning agent*, not a generic task stack. §1–§8 below document the
> **execution engine** that is built and still valid (it now operates on the
> *leaves* of a goal tree). This section frames the larger v2 system the engine
> sits inside; the new components are designed, not yet built.

The loop is **decompose → drive → ground → retain → connect → ingest**, built as
components around the existing engine:

```
 source (paper / codebase / topic / Zotero item)
        │
        ▼  Decomposer (LLM, template per source-type) ───────────► editable PLAN
        │                                                          Goal
        │                                                          ├─ Subgoal
        │                                                          │   ├─ Subtask  ◄─┐
        ▼                                                          │   └─ Subtask    │ markdown
   Engine (BUILT): draw the next leaf (resume-biased, dep-aware),  └─ Subgoal        │ in vault
   park (if-then), complete, Today.md     ADR-009/010/011          (tree, in vault) ─┘
        │
        ▼  Grounder: search ALL your vaults + Zotero ──► brief + connections
        │   (grounding.py searches all POPSTACK_VAULTS; flags cross-vault concepts)
        ▼  Retainer: understood → recall cards (Anki, byproduct) + generative drills  ADR-012
        ▼  Connector: surface cross-vault links for the current material           (P4)
        ▼  Ingestor: authored doc → atomic notes + MOC + cards, in your conventions ADR-013 (P5)
```

Component status: **Engine, Decomposer, dep-aware draw, multi-vault Grounder,
Anki card creation, Zotero, codebase clone/map, note-writing** ✅
(code-complete + tested) · generative recall **drills** 🔜 P3 · **Connector** (cross-vault link
*candidates* land today in grounding; *writing* the links 🔜) P4 · **Ingestor**
🔜 P5. Each keeps the ADR-006 discipline: own the *loop/learning semantics*,
delegate deep tools (FSRS to Anki, library to Zotero, rendering to Obsidian).

Data-model change (ADR-010): tasks are now **leaves of a Goal→Subgoal→Subtask
tree** (frontmatter carries parent/child + dependency wikilinks). The
`active`/`reservoir` pools (§2) hold *in-play subtasks* drawn across goals; the
engine's draw/park/complete operate unchanged on those leaves. The full tree
data model is specified when P2 is built.

## 1. Architecture (execution engine, built)

The central idea: **separate where the agent runs from where you touch
it.** One small server on an always-on machine; the user-facing "GUIs" are
apps already in daily use (Claude's apps, Obsidian, Anki's apps).

popstack itself is an **MCP server**. MCP (Model Context Protocol) is the
standard interface through which Claude applications discover and call
external tools — one server, written once, is usable from Claude Code on
any local machine *and* the Claude phone app, with no popstack UI code at all.

```
┌─ always-on machine ────────────────────────────────────────────┐
│                                                                │
│  popstack MCP server (Python, ~700 lines of code)                      │
│  ├── stack.py      task engine     ──►  <vault>/Stack/*.md     │
│  ├── grounding.py  vault search    ──►  <vault>/**/*.md        │
│  ├── zotero.py     papers          ──►  localhost:23119 (read) │
│  │                                      api.zotero.org  (write)│
│  ├── anki.py       flashcards      ──►  localhost:8765         │
│  └── today.py      Today.md        ──►  <vault>/Stack/Today.md │
│                                                                │
│  transports:   stdio  ·  HTTP :8444 (+ bearer auth)            │
└───────┬──────────────────────────────┬─────────────────────────┘
        │ stdio                        │ Tailscale Funnel (public HTTPS)
        ▼                              ▼
  Claude Code (local)          claude.ai connector
                               → Claude iOS / Android / web
        plus, via the vault's own sync:
  Obsidian (any device)  — renders Stack/ files and Today.md
  AnkiMobile / AnkiDroid — owns flashcard reviews (via AnkiWeb sync)
```

Transports, glossed:
- **stdio** — the Claude client launches the server as a subprocess and
  talks over stdin/stdout. Zero network exposure; local only.
- **HTTP** (`--http`) — a normal web endpoint on port 8444, for remote use.
  **Tailscale Funnel** is Tailscale's feature that publishes a local port
  at a public HTTPS URL — needed because the claude.ai connector is called
  by Anthropic's cloud, which can't reach a private network.

Key property: popstack has **no database and no UI**. The vault is the
database and Obsidian its viewer; Claude apps are the interactive UI;
Anki's apps own reviews. popstack is glue with opinionated semantics.

## 2. Data model

A task is one markdown file with a YAML header ("frontmatter"); which pool
it's in is encoded by which directory it sits in:

```
<vault>/Stack/
  active/      eligible to be handed out (capped, ACTIVE_LIMIT=20)
  reservoir/   someday / not-now / overflow
  done/        completed (kept as history)
  Today.md     generated view — lives outside the pool dirs, never a task
```

### Task file, annotated

```markdown
---
title: Read FSRS scheduler paper
created: 2026-06-10T09:00:00        # set at capture; drives the age weight
priority: high                       # high | medium | low
due: 2026-06-12                      # optional
pushes: 1                            # how many times parked; 3+ ⇒ "stale"
next_action: summarize section 2     # required by park(); the warm restart
cooldown_until: 2026-06-10T13:00:00  # not handed out again until then
last_popped: 2026-06-10T09:14:02
tags: [learning]
est_minutes: 30
---
Free-form notes. [[spaced repetition]] — wikilinks here are the *primary*
grounding signal, because tasks live in the same linked graph as knowledge.

- parked 2026-06-10T09:44 → next: summarize section 2
```

Parking *modifies the same file* — bumps `pushes`, sets the cooldown,
appends a timestamped history line — so a task accumulates its own
narrative, which is exactly what Obsidian then renders.

### Lifecycle

```
 capture ──► active ──(pool full at capture? → reservoir)
                │
                │ draw           (task is "in hand"; file unchanged
                ▼                 except a last_popped stamp)
            in hand ──────────► complete ──► moved to done/
                │
                └── park(next step required)
                        └─► same file, back in active/:
                            pushes+1 · next_action recorded
                            cooldown_until = now + 4h

 reservoir ◄── shelve / promote ──► active     (explicit moves, cap enforced)
```

## 3. Draw algorithm

**In words first.** Every eligible task holds raffle tickets. Existing at
all buys 1 ticket — everything stays drawable. A deadline within two weeks
buys up to 12 more, the closer the more, maxed out once overdue. Priority
buys 6 (high) or 3 (medium). Dust buys up to 2 more, accumulating over a
year and then capped — neglected tasks get steadily louder, but never
deafening. A draw takes one ticket (the engine method is named `pop()`). Tasks still in a park-cooldown hold no
tickets at all this round.

The formula:

```
weight = 1.0                                            base
       + 12.0 · clamp((14 − days_until_due) / 14, 0, 1) deadline ramp
       + {high: 6.0, medium: 3.0, low: 0.0}             priority
       +  2.0 · min(age_days / 365, 1)                  aging, capped
```

Worked example: a high-priority task due in 2 days scores
`1 + 12·(12/14) + 6 + 0 = 1 + 10.29 + 6 ≈ 17.29`; a fresh, undated, medium
task scores `1 + 0 + 3 + 0 = 4`. Drawing odds ≈ 81% / 19% — urgency
dominates without monopolizing.

**Where the constants come from.** They are a port of the "urgency"
coefficients of **Taskwarrior** — a ~15-year-old open-source CLI task
manager whose defaults (due 12, priority-high 6, age 2 capped at a year)
are the most field-tested numbers available for exactly this weighting
problem. Two deliberate departures, recorded in ADR-002/003:

- Taskwarrior *ranks* deterministically; popstack *samples*. A
  deterministic "highest urgency first" would re-serve the same heavy task
  immediately after every park (loop-lock) and would quietly reintroduce
  the "scan the list and rationalize" step the PRD bans (G2).
- Aging goes **up** with a ceiling, never down — stale tasks must resurface
  (PRD G2's "nothing buried forever"), but one ancient task must not drown
  the pool.

The park-cooldown (default 4 h) is what prevents draw→park→draw ping-pong of
a single dominant task.

## 4. Component map

Read this next to the source; the largest file (stack.py) is ~310 lines.

| File | Responsibility | Notes |
|------|----------------|-------|
| `config.py` | all settings, from environment variables | a `.env` file sourced by the launcher; no config framework |
| `stack.py` | the engine: capture / draw / park / complete / move / list / health | pure file manipulation + the weight function; fully unit-tested; **knows nothing about MCP** |
| `grounding.py` | task → search terms (wikilinks first, then tags, then title words) → hits across **all configured vaults** (`POPSTACK_VAULTS`), each tagged with its vault, merged with Zotero; flags concepts hitting 2+ vaults as **cross-vault connection candidates** (FR-7 substrate) | `ripgrep --json` when installed, pure-python fallback; returns structured hits — the *model* writes the prose brief |
| `zotero.py` | paper library client | reads via Zotero's local HTTP API; writes (add-by-DOI) via the zotero.org web API using Crossref metadata |
| `anki.py` | flashcard client (AnkiConnect, the standard Anki automation add-on) | absent Anki ⇒ `{available: false, error: how-to-fix}`, never an exception |
| `server.py` | exposes 29 tools over MCP; both transports; bearer-auth middleware | tool docstrings are the model's usage manual — write them as instructions |
| `today.py` | renders `Today.md` (top-3 by weight, overdue, stale, cards due) | run on a schedule (launchd/cron) |

The deliberate seam: `stack.py` is importable without MCP. A future P3 app
backend, a CLI, or tests reuse the engine unchanged; `server.py` holds no
logic of its own.

## 5. Transports & security

- **stdio (local):** trust boundary is the OS user; no auth.
- **HTTP + Funnel:** Funnel makes the endpoint **public internet**.
  Defense, in order:
  1. **Bearer token** — a single shared secret sent as an HTTP header
     (`Authorization: Bearer …`), compared in constant time; the middleware
     in `server.py` rejects anything else with 401, and `--http` refuses to
     start without a token (or `--insecure`, which forces loopback). A
     floor, not an answer — and note it only works for *header-controllable*
     clients (Claude Code `--header`, curl, the Agent SDK).
  2. **The claude.ai connector is not covered by this** — claude.ai custom
     connectors require OAuth 2.1, not a static header, so the phone-app
     route is *blocked* until OAuth lands (P1). See README.
  3. **Funnel stays off** until remote access is actually wanted.
  4. **OAuth (planned, P1 exit):** real login, required by NFR-3 before
     task contents become sensitive. ADR-007 is to be superseded by it.
- **Blast radius if the token leaks:** read access spans the **whole vault
  except `Stack/`** (via `vault_search`/`ground_task`); write access is
  confined to `Stack/` markdown, plus creating Anki cards and adding Zotero
  metadata. No shell, no arbitrary paths — task ids are charset-validated
  and resolve only within the Stack directories.

## 6. Alternatives considered

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Task store | vault markdown | Todoist-API backend; SQLite | sync + phone rendering come free with Obsidian; tasks join the knowledge graph (grounding); zero lock-in (NFR-1). Todoist had won the *pre-Obsidian* analysis; integrating the vault flipped it (ADR-001) |
| Hand-out semantics | weighted random sample | strict LIFO; uniform random; deterministic ranking | LIFO buries old tasks (the failure of xtask-cli, an abandoned 2017 stack-CLI we studied); uniform starves deadlines; deterministic loop-locks after parks (ADR-002) |
| Pool structure | small active pool + reservoir | one big stack | choice-overload evidence applies to *large, similar* option sets; the cap doubles as a work-in-progress limit (ADR-004) |
| Park rule | next step mandatory | free-form park | a specific written plan is what stops an open task from nagging (Masicampo & Baumeister 2011), and future-you restarts warm (ADR-005) |
| Server | one custom MCP server | composing community Obsidian/Zotero/Anki MCP servers | the product *is* the loop semantics (weights, cooldowns, the park contract) — generic servers can't enforce them; the integration clients are trivially small (ADR-006) |
| Phone UI | claude.ai connector | building an app now | full interactivity for zero UI code; an app is deferred until real usage shows which four screens matter (PRD P3) |
| Flashcard reviews | Anki's own apps | building review UI | FSRS (the Free Spaced Repetition Scheduler that Anki uses) + offline + mobile polish are years of shipped work; popstack only *creates* cards (ADR-006) |

## 7. Failure modes

| Failure | Behavior |
|---|---|
| Zotero closed / its local API disabled | grounding still returns vault hits, plus an explanatory `zotero.error`; loop unaffected (NFR-4) |
| Anki not installed | `anki_*` tools return setup instructions; never raise |
| Vault path misconfigured | Stack dirs get created at the wrong path and searches return nothing — symptom is obvious; fix `.env` |
| Sync conflict on a task file | only the server writes task files in practice; Obsidian merges bodies; frontmatter is last-writer-wins (accepted, PRD R-3) |
| Active pool empty / everything cooling down | a draw returns a structured error saying to promote from the reservoir or wait out cooldowns |

## 8. Testing

- `tests/test_stack.py` — 24 unit tests on the engine: capture/overflow,
  statistical weighting (300 seeded draws), cooldown exclusion, the park
  contract, completion moves, pool caps, health flags. Runs on a temp dir;
  no network.
- The integration clients (Zotero/Anki) are thin HTTP wrappers verified by
  the documented smoke test; unit-mocking them would mostly test the mocks.
  Revisit if logic accumulates there.
- Smoke checklist (README): 29 tools registered; HTTP auth 401/200; full
  capture → draw → park → Today.md flow.

## 9. Future work

**P1:** scheduling (launchd), Funnel runbook, weight tuning from real draws.
**P2:** recall drills — likely a `drill.py` that picks a random vault note
or Zotero item plus an MCP prompt template; a `stats` tool (draw/park/done
counts are already derivable from frontmatter). **P3:** the app — an Agent
SDK backend reusing `stack.py` unchanged (the §4 seam exists for this).

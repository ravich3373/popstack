# PRD — popstack

> **What a PRD is for:** it pins down the *problem, users, requirements, and
> success criteria* before/while building, so every later design argument can
> be settled by asking "which option serves the PRD?" It deliberately avoids
> saying *how* — that's [DESIGN.md](DESIGN.md). Decisions and their rationale
> are logged in [DECISIONS.md](DECISIONS.md).

- **Status:** v1.0 (P0 shipped) · **Owner:** @ravich3373 · **Last updated:** 2026-06-10

## 1. Problem

Tasks arrive on every device and get parked in heads, chat threads, and ad-hoc
notes. Choosing *which* task to do next is itself a task — and under a large,
similar-looking backlog it produces stalling, not prioritizing. Existing tools
solve fragments (capture, timers, random pickers, reference management) but
nothing closes the loop of: capture anywhere → *be handed* one task → start
with the relevant personal knowledge in front of you → timebox → finish or
park it *with a plan*.

## 2. Goals

| # | Goal | Measured by |
|---|------|-------------|
| G1 | Capture a task from any device in <10 s | time from thought → saved task |
| G2 | Remove the "choose next" step: one weighted-random pop | pops/week actually worked |
| G3 | Every popped task arrives grounded in own notes + papers | % pops where grounding gets used |
| G4 | Parked tasks carry a specific next action (always) | enforced by the system (100%) |
| G5 | Knowledge compounds: recall misses become spaced-repetition cards | cards created/week |
| G6 | Own the data: plain markdown in the user's vault, no lock-in | zero proprietary storage |

**Non-goals (v1):** multi-user/teams; replacing Anki's review UI; a custom
mobile app (Tier 3 — only if the loop proves itself); calendar/scheduling;
automatic task generation.

## 3. Users & context

One user (a software/ML engineer), three device classes:

- **Laptop** — deep work; Claude Code is already open all day.
- **Phone** — capture + light interaction via the Claude app and Obsidian mobile.
- **Always-on node** — hosts the server, vault replica, Zotero, Anki.

Existing tools that must be embraced, not replaced: **Obsidian** (knowledge,
sync, mobile GUI), **Zotero** (papers), **Anki** (spaced repetition).

## 4. User stories

1. *Capture:* "On my phone I tell Claude 'park: read the FSRS paper, due
   Friday' and it's in the stack before I lock the screen."
2. *Pop:* "I say 'pop' and get exactly one task — chosen for me, weighted by
   urgency — with a one-screen brief of what my vault and library already
   know about it."
3. *Timebox & park:* "After 30 minutes I either complete it or park it; the
   system refuses to park without a one-line next action, so future-me starts
   warm."
4. *Recall:* "In downtime I ask for a drill; it quizzes me from a random note
   or paper, grades me, and writes my misses into Anki."
5. *Glance:* "Each morning, Today.md in Obsidian shows the top of the stack,
   what's overdue, what's gone stale, and how many cards are due — on every
   device, with zero interaction."

## 5. Requirements

### Functional

| ID | Requirement | Status |
|----|-------------|--------|
| FR-1 | Capture task with title/body/tags/due/priority/estimate | ✅ `capture_task` |
| FR-2 | Two pools: small active pool (cap 20) + reservoir; overflow + promote/shelve | ✅ |
| FR-3 | Weighted-random pop (deadline + priority + capped aging); cooldown exclusion | ✅ `pop_task` |
| FR-4 | Park requires non-empty specific next action; sets cooldown; logs history | ✅ `park_task` |
| FR-5 | Complete with optional note; history retained | ✅ `complete_task` |
| FR-6 | Grounding: search vault (wikilinks > tags > title terms) + Zotero | ✅ `ground_task` |
| FR-7 | Zotero: search library; add item by DOI | ✅ |
| FR-8 | Anki: create cards; report due counts; degrade gracefully when absent | ✅ |
| FR-9 | Health view: overdue, stale (3+ pushes or >30 d), pool counts | ✅ `stack_health` |
| FR-10 | Generated `Today.md` glanceable view in the vault | ✅ `popstack-today` |
| FR-11 | Recall drill workflow (quiz from random note/paper → grade → cards) | 🔜 P2 (skill/prompt layer) |
| FR-12 | Scheduled automation (morning Today.md, weekly review) | 🔜 P1 |

### Non-functional

- **NFR-1 Data ownership:** all task state is human-readable markdown inside
  the user's vault; deleting popstack loses nothing.
- **NFR-2 Access:** every FR usable from laptop (stdio) and phone (remote
  MCP); no popstack-specific GUI required in P0–P2.
- **NFR-3 Security:** remote endpoint requires a bearer token at minimum;
  OAuth before any sensitive content (see R-1).
- **NFR-4 Robustness:** integrations (Zotero/Anki) failing must never block
  the core loop; errors are explanatory, not exceptions.
- **NFR-5 Zero-ops:** no database server, no migrations; survives machine
  restarts with no state outside the vault + .env.

## 6. Success metrics (review monthly)

- ≥10 pops/week actually worked (G2) · park:complete ratio < 3:1 (G4 working)
- stale count trending ↓ (FR-9) · ≥5 recall cards/week once P2 lands (G5)
- Qualitative: "do I still trust the stack?" — the system dies the day
  capture stops being reflexive.

## 7. Risks

| ID | Risk | Mitigation |
|----|------|-----------|
| R-1 | Public Funnel endpoint → vault write access if token leaks | bearer token now; MCP OAuth before sensitive use; keep Funnel off until needed |
| R-2 | Meta-work trap: tuning the system replaces using it | P3 gated on a month of P1/P2 usage data |
| R-3 | Sync conflicts (two devices edit one task file) | tasks are single-writer in practice (server-only writes); Obsidian sync handles the vault; revisit if conflicts observed |
| R-4 | Random pop serves a stale/irrelevant task → trust erosion | weights + cooldowns + repick-always-allowed; tune constants from health data |
| R-5 | Abandonment (the fate of most personal productivity systems) | success metrics reviewed monthly; kill/simplify features that go unused |

## 8. Phases

- **P0 — engine + MCP server** ✅ *(this repo, 2026-06-10)*
- **P1 — daily use:** Claude Code registration, scheduled Today.md,
  Funnel + claude.ai connector, weight tuning from real usage.
- **P2 — recall loop:** drill prompts/skills over vault + Zotero, misses →
  Anki; success metric instrumentation.
- **P3 — purpose-built PWA** *(only if P1/P2 usage demands it):* one-button
  pop, visible countdown, swipe-to-park; Claude Agent SDK backend reusing the
  same MCP tools.

## 9. Open questions

1. Weight constants are Taskwarrior-inspired defaults — re-tune after ~50 real pops?
2. Should `est_minutes` influence pop weight (short tasks when little time)? Context/energy tags?
3. Recall drill format: free recall vs cloze vs "explain to a beginner"?
4. OAuth implementation: roll our own vs an MCP auth library — decide at P1 exit.

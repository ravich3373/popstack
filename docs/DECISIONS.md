# Decision Log (ADRs) — popstack

> **What this is:** Architecture Decision Records — one short entry per
> consequential choice: the context, the decision, what it costs. To change
> course later, don't edit history — add a new ADR that *supersedes* the old
> one and link them. This file is the one to argue with.

Format: `Status: accepted | superseded by ADR-NNN` · keep entries short.

---

## ADR-001 — The Obsidian vault is the database
**Status:** accepted · 2026-06-10

**Context.** The task store needs multi-device sync, a phone GUI, and to sit
next to personal knowledge for grounding. Candidates: Todoist API backend
(proven by the "Random Task" app), SQLite + custom sync, vault markdown.

**Decision.** Tasks are markdown files with YAML frontmatter under
`<vault>/Stack/{active,reservoir,done}/`. Pool membership = directory.

**Consequences.** Sync, mobile rendering, backup, and human-editability are
free (Obsidian); tasks participate in the wikilink graph (grounding becomes
native); zero lock-in. Costs: no transactions (acceptable: single writer in
practice — see PRD R-3), no queries beyond file walks (fine at personal
scale), and the earlier Todoist-based plan is obsolete.

---

## ADR-002 — Pops are *random samples*, not rankings
**Status:** accepted · 2026-06-10

**Context.** Deterministic "highest urgency first" re-serves the same task
right after you park it (loop-lock) and reintroduces the choose-or-rationalize
step the PRD set out to remove. Pure LIFO buries old tasks (the failure mode
of the abandoned xtask-cli); uniform random starves deadlines.

**Decision.** Pop draws randomly with probability proportional to a weight.

**Consequences.** The "be handed a task" experience the PRD wants; urgent
work dominates odds without monopoly. Cost: occasional low-urgency picks —
mitigated by repick-always-allowed (the model never forces a pop on you).

---

## ADR-003 — Weights port Taskwarrior's urgency model; aging goes UP, capped
**Status:** accepted · 2026-06-10

**Context.** Weight constants could be invented, learned, or borrowed.
Taskwarrior's urgency polynomial (due 12, priority H 6, age 2 capped at
365 d) has had ~15 years of field tuning; its maintainers explicitly hold
that stale tasks must surface *more*, bounded.

**Decision.** `1 + due_ramp(≤12, 14-day window) + priority{6,3,0} +
age(≤2, /365d)`; park sets a 4 h default cooldown that excludes the task.

**Consequences.** Defensible defaults instead of vibes; one familiar knob set
to retune (PRD open question 1). Cooldown kills pop→park ping-pong. Cost:
constants tuned for engineers' work backlogs — revisit after ~50 real pops.

---

## ADR-004 — Two pools: small active (cap 20) + reservoir
**Status:** accepted · 2026-06-10

**Context.** The choice-overload literature (Scheibehenne 2010 vs Chernev
2015) supports harm only under *large, similar, uncertain* option sets; a
giant single stack also makes random pops feel arbitrary and untrustworthy.

**Decision.** Pops draw only from a capped active pool; capture overflow and
"not now" live in a reservoir with explicit promote/shelve moves.

**Consequences.** The draw pool stays meaningful (every member was admitted
on purpose); the cap is a de-facto WIP limit; promotion is a weekly-review
act. Cost: one more concept than "a stack" — accepted, the names are obvious.

---

## ADR-005 — `park()` requires a specific next action
**Status:** accepted · 2026-06-10

**Context.** Masicampo & Baumeister (2011): unfulfilled goals intrude on
unrelated work; writing a *specific* plan — not merely capturing the task —
eliminates the intrusion. Also, future-you restarts warm instead of cold.

**Decision.** The API rejects parks with an empty/blank `next_action`; parks
append a timestamped history line to the task body.

**Consequences.** Every parked task carries its restart instruction; the
stack accumulates narratives. Cost: ~5 s of friction per park — that
friction *is the feature*.

---

## ADR-006 — Thin custom server; integrate, don't rebuild
**Status:** accepted · 2026-06-10

**Context.** Community MCP servers exist for Obsidian, Zotero, and Anki; an
alternative design composes them. But the product here is the *loop
semantics* — weights, cooldowns, pool caps, the park contract — which generic
servers cannot enforce. Conversely, SRS scheduling (FSRS), review UIs, and
reference management are deep products that would be folly to rebuild.

**Decision.** One small custom FastMCP server owns the loop; Zotero and Anki
are reached through their existing local APIs as thin clients; Anki's own
apps own reviews; Obsidian owns rendering/sync.

**Consequences.** ~600 lines total; each integration degrades gracefully
(NFR-4). Cost: we maintain small API clients ourselves — acceptable, they're
a few dozen lines each.

---

## ADR-007 — Remote access via claude.ai connector + Tailscale Funnel; bearer now, OAuth before sensitive use
**Status:** accepted · 2026-06-10 · *revisit at P1 exit (PRD §9 Q4)*

**Context.** claude.ai custom connectors give every device an interactive
agent GUI with zero UI code, but require a publicly reachable HTTPS endpoint
— Anthropic's cloud connects to it, so tailnet-private serving is not enough.

**Decision.** Serve streamable HTTP behind Tailscale Funnel with mandatory
bearer-token middleware; keep Funnel disabled until phone access is actually
wanted; commit to MCP OAuth before task content becomes sensitive.

**Consequences.** Phone access for one middleware class worth of code. Cost:
a public endpoint exists when Funnel is on (PRD R-1) — the bearer token is a
floor, not an answer; ADR to be superseded by the OAuth implementation.

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
**Status:** amended by ADR-009 (random demoted to a tie-breaker) · 2026-06-10

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
**Status:** amended by ADR-011 (split forgotten vs avoided; add pushes penalty) · 2026-06-10

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

## ADR-005 — `park()` requires a specific next action (an if-then plan)
**Status:** accepted · 2026-06-10 · re-anchored 2026-06-10

**Context.** Future-you should restart warm, not cold. The original citation
(Masicampo & Baumeister 2011) is replication-shaky; the PRD critique
(verified) re-anchored this to **Gollwitzer's implementation intentions**
(d≈0.65 across ~90 tests) and the Ovsiankina resumption tendency — both of
which specifically favor *if-then* ("when X, I will Y") plans over bare notes.

**Decision.** The API rejects parks with an empty/blank `next_action`, and the
prompt asks for an **if-then** form ("when I next sit down → implement the
sampler"). Parks append a timestamped history line to the task body.

**Consequences.** Every parked subtask carries a concrete trigger→action restart
cue. Cost: ~5 s of friction per park — that friction *is the feature*.

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

> **2026-06-10 review note:** the claude.ai connector specifically needs
> OAuth 2.1 (not a static bearer), so the *phone-app* route is blocked until
> OAuth lands. The bearer transport still serves header-controllable clients.

---

## ADR-008 — popstack is a personal *learning agent*, not a generic task manager
**Status:** accepted · 2026-06-10 · supersedes the v1 product framing

**Context.** v1 framed the product as a random task stack for generic
productivity. The user's actual need (clarified 2026-06-10, and corroborated
by ~4,358 vault notes + ~844 Zotero items with *zero* spaced repetition): take
a hard technical source — an ML/CS paper, a codebase, a language, an algorithm
family, a system-design topic — and deeply understand *and retain* it. The
prior PRD critique had flagged "two products glued by a slogan (100x
engineer)"; the clarification resolves it — execution is in service of
*learning*, which is the product.

**Decision.** Reframe around the learning loop: decompose → drive → ground →
retain → connect → ingest. Drop "100x engineer/scientist" for the falsifiable
mission in PRD §5. The v1 task engine becomes the *execution* component.

**Consequences.** Knowledge features (grounding, Anki, connections) move from
"feature creep" to core; the data model grows from a flat pool to a goal tree
(ADR-010); the random-draw mechanic is demoted (ADR-009). Cost: bigger scope —
managed by phase-gating (PRD §9), each phase earning the next on real usage.

---

## ADR-009 — The draw is resume-biased and dependency-aware, not random across goals
**Status:** accepted · 2026-06-10 · amends ADR-002

**Context.** ADR-002 chose weighted-*random* draw to kill the "choose next"
step. The PRD critique (verified) showed this conflates two problems:
**loop-lock on re-draw** (real — the cooldown already solves it) and **forcing
the next item to be a different, unrelated thing** (harmful: it institutions
attention-residue task-switching — Leroy 2009 — across unrelated domains, the
opposite of deep work). For learning, sequence and dependencies matter.

**Decision.** Default the next draw to *continue the current goal/thread* or an
unblocked dependency; draw fresh across goals only on explicit complete/abandon
or when the user asks to switch. Randomness is demoted to a tie-breaker among
near-equal candidates (top-k sample), not the headline. The cooldown — not
randomized selection — is the loop-lock fix.

**Consequences.** Protects flow on deep work; honors the learning plan's
structure. Cost: "be handed a surprising task" is mostly gone — acceptable, it
was never the point for focused study (the user can still ask to shuffle).

---

## ADR-010 — Tasks live in a Goal → Subgoal → Subtask tree, not a flat pool
**Status:** accepted · 2026-06-10 · extends ADR-001

**Context.** A learning objective ("understand & replicate paper X") is not one
task; it's a tree the agent proposes and the user edits, with dependencies
(understand the math *before* replicating). The flat active/reservoir pool
can't express this.

**Decision.** Model Goal → Subgoal → Subtask as markdown files in the vault
(frontmatter carries parent/child + dependency links; bodies use wikilinks).
The "active pool" becomes the set of in-play *subtasks* drawn across goals. The
existing engine operates on the leaves.

**Consequences.** Plans are first-class, editable, and live in the graph
alongside knowledge. Reuses ADR-001's vault-as-database. Cost: more structure
than a flat list — justified by the product (PRD §4).

---

## ADR-011 — Aging splits "forgotten" vs "avoided"; declined tasks de-escalate
**Status:** accepted · 2026-06-10 · amends ADR-003

**Context.** ADR-003 escalated *all* neglected tasks. The critique (verified
against Steel 2007, the strongest procrastination result) showed this pushes
hardest on *aversive* tasks — re-presenting them on a timer trains more
avoidance and guilt, not action. Aging conflates "genuinely forgotten"
(resurface) with "actively avoided" (decompose/drop), whose right responses are
opposite.

**Decision.** Age-boost only *un-offered* subtasks. A subtask offered and
declined K times **de-escalates and routes to triage** (decompose / drop /
defer-with-plan), not re-roll. Add a `pushes` penalty to the draw weight
(parked-often ⇒ lower odds, the inverse of today). Add an `expire` state so
aging can't build a doom pile.

**Consequences.** Avoidance gets *decomposition* (raising expectancy, the TMT
lever) instead of nagging. Cost: more lifecycle states — see DESIGN §2.

---

## ADR-012 — Retention is the point: cards as a byproduct, generative recall, reviews in Anki
**Status:** accepted · 2026-06-10 · extends ADR-006

**Context.** The biggest gap in the user's setup is **zero spaced repetition**
across 4,358 notes. Retention is where "understand deeply" becomes "still know
it in 6 months." Showing notes (restudy) is the weak form; making the user
*retrieve* (the testing effect, Bjork's desirable difficulties) is the strong
form.

**Decision.** When a subtask is understood, the agent proposes recall cards as
a *byproduct* (not a separate chore) into Anki. Drills are **generative** — ask
first, reveal after — and misses become cards. Anki's apps own scheduling
(FSRS) and review; popstack only creates and queries.

**Consequences.** Closes the retention gap that motivates the whole product.
Cost: depends on the user installing Anki (P3 includes that path).

---

## ADR-013 — Agent-authored notes must conform to the existing KB conventions
**Status:** accepted · partially implemented 2026-06-10 (`notes.py`: safe write
primitive — quarantine folder, preview-first, no-clobber, frontmatter +
wikilinks. The agent supplies content + per-area conventions; automatic
convention *detection* is still manual/agent-driven.)

**Context.** The vaults have strong, consistent conventions (YAML frontmatter,
wikilinks-as-navigation, MOCs, callouts for math, numbered/Johnny-Decimal
folders, a `_Rules.md` paper convention). An agent that writes in its own style
would fork the graph and erode its value.

**Decision.** Grounding-derived notes and ingested docs adopt the detected
conventions of their target area, link into existing MOCs/notes, and are shown
to the user for approval before write. The agent extends one graph; it never
starts a parallel one (NFR-1).

**Consequences.** The KB stays coherent and searchable. Cost: the agent must
*learn* the conventions per vault/area (a grounding step), not assume one style.

---

## ADR-014 — Portability: offline-first recall, tailnet-private agent
**Status:** accepted · 2026-06-10 · narrows ADR-007 for personal access · see [PORTABILITY.md](PORTABILITY.md)

**Context.** "Learn anywhere — bed, toilet, car" is two needs: high-frequency
**recall** (must work offline) and lower-frequency **agent interaction** (needs
the LLM + node, online). Conflating them makes the design impossible; splitting
them makes it easy.

**Decision.** Three tiers: (1) **Recall = Anki apps + AnkiWeb sync** — offline,
anywhere, the daily driver; popstack only *creates* cards on the node and
triggers a sync. (2) **Glance/capture = Obsidian mobile** over vault sync,
offline-deferred. (3) **Agent = a thin PWA served by the node, reached over the
**tailnet** (Tailscale, WireGuard) — private, works from anywhere with internet,
**no public endpoint**. Funnel + OAuth (ADR-007) is demoted to the *optional*
claude.ai-cloud route, not the path for personal access.

**Consequences.** The most-portable activity (recall) never depends on the node
or connectivity. Personal access needs no public exposure — this also erases
risk R-1 for the normal case. Cost: a (thin) PWA is real UI work; its
deterministic half needs no LLM and is buildable first, the generative half
follows.

---

## ADR-015 — The agent maintains the cross-tool link graph (Obsidian ↔ Zotero ↔ Anki); the user never hand-wires links
**Status:** accepted · 2026-06-10

**Context.** Creating links by hand is the friction that kills knowledge graphs
— the user explicitly does not want to do it. Value comes from the *triangle*:
a concept's Obsidian note, its source paper in Zotero, and its Anki cards, all
mutually navigable. Today none of that is automatic.

**Decision.** Linking is the agent's/code's job, using each tool's stable
identifiers, written into durable fields:
- **Obsidian → Obsidian:** `[[wikilinks]]` in note bodies + a `related:`
  frontmatter list — the agent proposes and writes them (the Connector, FR-7).
- **Obsidian → Zotero:** store the Zotero item key in note frontmatter
  (`zotero_key`) and link via `zotero://select/library/items/<KEY>` (and the
  DOI when present).
- **Obsidian → Anki:** after creating cards, write their note IDs back into the
  source note's frontmatter (`anki_notes: [...]`).
- **Anki → Obsidian/Zotero:** every generated card carries a **Source** field
  with an `obsidian://open?vault=…&file=…` URI and the `zotero://`/DOI link, plus
  a tag naming the source note — so a card under review links home.
The agent maintains this triangle whenever it grounds a subtask, writes a note,
or makes a card; links are proposed for approval before write (ADR-013).

**Consequences.** Every vertex (card, note, paper) reaches the others; the graph
grows as a byproduct of learning, not a chore. The note IDs / item keys are the
durable join keys, robust to renames. Cost: a small "link store" the agent keeps
consistent; broken links if an item is deleted in one tool (acceptable, detect
on the weekly review). Requires the Better-BibTeX citekey or item key from
Zotero (item key from the local API suffices; citekeys optional).

---

## ADR-016 — File into the user's EXISTING organization, everywhere; never dump in the root
**Status:** accepted · 2026-06-10 · generalizes ADR-013

**Context.** A top reason to use an agent is that it *respects your filing
system* — papers belong in the right Zotero collection, notes in the right
Obsidian folder/MOC, cards in the right Anki deck. Dumping everything in the
base location (unfiled items, a flat notes folder, one mega-deck) destroys the
organization the user spent years building (186 Zotero collections; MOC-indexed
vaults).

**Decision.** Every write tool is organization-aware: it **discovers the
existing structure first**, then files into the best-matching existing
container.
- **Zotero:** `collections()` lists the folder tree (by path); `add_by_doi`
  takes a `collection` and files there. Unknown collection → return the
  available list so the agent re-picks; failed write → report the *intended*
  collection so the user can file manually.
- **Obsidian:** `write_note(folder=…)` + `add_to_moc` place notes in the right
  area and index; the quarantine folder is the *safe default*, not the goal —
  the agent should ground first and target the real folder/MOC.
- **Anki:** `add_cards(deck=…)` files into a topic deck, not one bucket.
The agent picks the container after *reading* the structure; it never invents a
parallel one (cf. ADR-013).

**Consequences.** New material lands where the user would have put it. Cost: an
extra discovery read before each write (cheap, and it's also what grounds good
placement). Where a write can't go through (e.g. read-only local Zotero), the
tool still reports the *intended* location so the manual fallback stays tidy.

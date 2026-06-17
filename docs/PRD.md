# PRD — popstack (a personal learning agent)

> **What a PRD is for:** it pins down the *problem, the user, what the product
> must do, and how we'll know it works*, in language anyone can follow without
> having been in the room. Mechanisms live in [DESIGN.md](DESIGN.md);
> contested choices in [DECISIONS.md](DECISIONS.md).
>
> Rules this doc follows: **(1) write for zero context** — define every
> invented word before using it; **(2) state outcomes, not mechanisms**;
> **(3) every goal is falsifiable** — if it can't be measured, it's a slogan.

- **Status:** v2.0 — **scope pivot**. v1 was a generic random task stack; this
  rewrites the product around its real purpose: helping the user deeply
  understand and *retain* technical material. The v1 task engine survives as
  one component (execution).

## 1. The problem

The user is a software/ML engineer who learns by going deep: understanding the
math, experiments, and results of ML and CS papers (compilers, distributed
systems, databases); understanding real codebases; learning languages;
practicing algorithms and system design. The evidence of this is already on
disk — a large body of notes across several Obsidian vaults and a Zotero library.

Three failures sit on top of that effort:

1. **No decomposition.** Faced with "understand and replicate this paper," the
   hard part is turning it into a concrete plan — what to understand first,
   what depends on what, what "done" means. Today that planning is ad hoc and
   often skipped, so big sources stall.
2. **No retention.** This is the costly one. Across all those notes there is **zero
   spaced repetition** — Anki isn't even installed. Knowledge is *captured and
   re-read* but not *drilled*, so it
   decays. Re-reading feels like learning and mostly isn't.
3. **No connection.** The vaults are complementary — one for implementation,
   one for theory, one for systems/practice — and densely wikilinked
   internally, but cross-vault links (a paper's math ↔ the
   theorem that grounds it ↔ the implementation) are made by hand, if
   at all. The connective tissue that turns notes into understanding is missing.

popstack closes the loop: **decompose a source into an editable plan → drive
the user through it → ground each step in what they already know → make it
stick (Anki + connections) → fold newly-authored docs back into the KB.**

## 2. Words this document uses

| Word | Meaning here |
|---|---|
| **source** | the thing to learn: a paper, a codebase, a language, an algorithm family, a system-design topic |
| **goal** | a learning objective over one source, e.g. *"understand & replicate the π₀ paper"* or *"understand the llama.cpp inference path"* |
| **subgoal** | a major part of a goal, e.g. *"understand the math,"* *"reproduce the main experiment,"* *"map the architecture"* |
| **subtask** | one concrete, sittable unit of work under a subgoal, e.g. *"re-derive the flow-matching loss"* — the leaves the user actually does |
| **plan** | the goal → subgoal → subtask tree the agent proposes and the user **edits** (dependencies allowed) |
| **the pool** | the small set of subtasks currently in play (active), drawn from across the user's goals |
| **draw** (was "pop") | "what should I work on now" — the agent proposes one subtask, biased to *continue the current thread*, never a blind random jump (see [DECISIONS](DECISIONS.md) ADR-009) |
| **ground** | gather what the user already knows about a subtask — relevant notes across your vaults and papers in Zotero — and present it as a brief |
| **connection** | a non-obvious link the agent surfaces between the current material and an existing note (often cross-vault) |
| **recall card** | an Anki flashcard generated from something just understood; reviewed in Anki's own apps |
| **ingest** | turn a large doc the user authored (e.g. a long architecture write-up) into atomic KB notes + a MOC + recall cards, in their existing conventions |
| **park** | set a subtask aside *with a written next action* (an if-then plan), so resuming starts warm |

## 3. Who it's for, on what

One user; the ecosystem is already in place:

- **Obsidian vaults** — several, organized by theme (e.g. systems/ML, coding & interview prep,
  math/ML theory). Conventions: YAML frontmatter, **wikilinks as
  primary navigation**, MOC/index notes, atomic-note + callout style. The agent
  must **fit these conventions, not impose new ones** (NFR-1).
- **Zotero** — an ML/systems/theory-heavy library; the source of papers.
- **Anki** — *not installed yet*; the retention layer to stand up (P3).
- **Devices** — a local machine (deep work, Claude Code); phone (capture, light review,
  Anki); an always-on node hosting the agent.
- **Languages in play** — Python, C++, Go, Rust, Bazel, TypeScript.

## 4. The product, in one learning project

You drop the π₀ robotics paper (already in Zotero) on the agent: *"I want to
understand and replicate this."*

It **decomposes** into a plan — *understand the math (flow matching, the
action head) · understand the architecture · reproduce the main experiment ·
replicate a minimal version* — each with subtasks. You **edit** it: you
already know diffusion policies, so you delete that subgoal and add *"compare
to diffusion-policy baselines."*

You say **"what now."** It **draws** the first math subtask and **grounds** it:
it surfaces your notes on ODEs/optimal transport, the
diffusion-policy paper in Zotero, and flags a **connection** — *"this loss is
the continuous-time limit of the DDPM objective in your
quantization notes."* You work a focused block.

You understood the flow-matching derivation, so the agent proposes two **recall
cards** ("Why is flow matching simulation-free at training time?") into Anki.
You **park** the next subtask with an if-then next action: *"when I next sit
down → implement the sampler and check it against Figure 3."*

Weeks later you've written a full architecture doc on the replication. You say
**"ingest this"** — it splits the doc into atomic notes that match your vault
style, builds a MOC, wikilinks them into your existing graph, and generates
recall cards from the key facts.

The loop: **decompose → edit → draw-and-ground → understand → retain → connect
→ (ingest) — without ever facing a blank page or relearning what you forgot.**

## 5. Goals

| # | Outcome we want | How we'd know it's working |
|---|-----------------|----------------------------|
| G1 | Turn a source into an editable plan in minutes, not an afternoon | sources get *started* instead of stalling; plans are kept and edited, not discarded |
| G2 | Be driven through a goal constructively — handed the next sensible step (biased to continue the current thread), with a written next action when set aside — instead of choosing from scratch or forced-randomly switching | started subgoals reach "understood"; low abandonment of in-progress goals |
| G3 | Start each step from what you already know: relevant notes + papers surfaced as a brief, and **new notes written in your existing conventions** | the brief is used; the KB grows without a second, divergent style |
| G4 | What you understand becomes durable: it turns into spaced-repetition cards you actually review | retention measured by Anki (cards created *and* matured), where today it is **zero** |
| G5 | Surface non-obvious connections across your vaults, so knowledge compounds into a graph rather than piling up | cross-vault links created per goal; you discover links you wouldn't have made |
| G6 | Fold the large docs you author back into the KB as atomic notes + cards | authored docs stop being write-only artifacts |
| G7 | You own everything and can extend it: notes/cards live in tools you already trust; new sources and tools can be added | uninstalling loses nothing; adding a new source type or tool doesn't require a rewrite |

**The bet (falsifiable):** *Decomposition + grounding + forced retention makes
the user understand hard sources more completely and remember them far longer
than capture-and-reread does — without adding so much friction that capture or
study stops.*

**Falsifier / kill-criterion (set the baseline now):** after 8 weeks of real
use, if (a) Anki retention isn't materially above "nothing" for material
learned through popstack, **and** (b) goals started in popstack don't reach
"understood" more than the user's pre-popstack baseline, **or** (c) the user
re-rolls/overrides the proposed next step >40% of the time (it's not proposing
useful work) — narrow hard or retire it.

## 6. What the system must do

The *how* for each is in [DESIGN.md](DESIGN.md).

### Functional

| ID | The system must… | Status · design |
|----|------------------|-----------------|
| FR-1 | Decompose a source (paper/codebase/topic) into a goal → subgoal → subtask **plan**, and let the user edit it (add/remove/reorder/mark dependencies) | 🔜 P2 |
| FR-2 | Track goals and their trees; show progress (subtasks done / understood per subgoal) | 🔜 P2 |
| FR-3 | Hand over the next sensible subtask on request — biased to continue the current goal/thread or an unblocked dependency, **not** a blind random jump across unrelated goals; the user may decline | ⚙️ engine built (draw); bias logic 🔜 P2 |
| FR-4 | Refuse to park a subtask without a specific **if-then** next action; record it on the subtask | ✅ (park; tighten to if-then) |
| FR-5 | Ground a subtask: search **all** your vaults and Zotero, returning a brief | ⚙️ single-vault search built; multi-vault 🔜 P2 |
| FR-6 | Generate Anki cards from understood material; report due counts; **never** host reviews (Anki's apps do) | ✅ card creation; drill flow 🔜 P3 |
| FR-7 | **Maintain the cross-tool link graph itself** (Obsidian↔Zotero↔Anki) — create the wikilinks, the note↔paper links, and the card↔note↔paper triangle. The user never hand-wires a link (ADR-015) | 🔜 P4 |
| FR-8 | Create new KB notes that match existing conventions (frontmatter, wikilinks, MOC placement, callouts) | 🔜 P3 |
| FR-9 | Ingest an authored doc into atomic KB notes + a MOC + recall cards | 🔜 P5 |
| FR-10 | A generative recall drill: ask first, reveal after (retrieval, not restudy); misses → cards | 🔜 P3 |
| FR-11 | Daily glanceable view (active subtasks, what's due in Anki, stale goals) | ✅ (Today.md) |
| FR-12 | Be extensible: add a new source type or external tool without reworking the core | design constraint |

### Non-functional

- **NFR-1 · Respect the existing KB.** New notes/cards adopt the user's
  conventions (YAML frontmatter, wikilinks-as-navigation, MOCs, callouts,
  numbered/Johnny-Decimal folders). The agent extends the graph; it never
  starts a parallel, divergent one.
- **NFR-2 · Ownership.** All state — goals, subtasks, notes, cards — lives in
  tools the user already trusts (markdown in the vault; cards in Anki).
  Uninstalling popstack loses nothing.
- **NFR-3 · Reach (learn anywhere).** Recall works **offline** anywhere (Anki);
  the agent is reachable **privately** from anywhere with internet (tailnet), no
  public endpoint. See [PORTABILITY.md](PORTABILITY.md) / ADR-014.
- **NFR-4 · Graceful degradation.** Zotero/Anki absent must never block the
  core loop; errors explain the fix.
- **NFR-5 · Safety when remote.** The endpoint rejects unauthenticated
  requests; real login (OAuth) before exposing anything sensitive.
- **NFR-6 · Extensibility.** Sources, grounding backends, and card/connection
  generators are pluggable.

## 7. Success metrics (review monthly — outcomes, not activity)

Deliberately *not* "draws/week" or streaks (those reward time-in-tool, the
abandonment trap). Measure value:

- **Retention** — Anki cards created through popstack that reach "mature," and
  review accuracy on them. Baseline today is zero, so any durable retention is
  signal.
- **Goal progress** — fraction of started goals whose subgoals reach
  "understood"; replications actually achieved.
- **Connection density** — cross-vault links created per goal (and how often
  the user keeps an agent-proposed connection).
- **Friction signals (diagnostics, not targets)** — accept-on-first-draw rate
  (≥70% = the agent proposes useful work); capture latency; deadline-hit on any
  dated goals. High re-roll is the **falsifier**, not a vanity metric.

## 8. Risks

| ID | Risk | Mitigation |
|----|------|-----------|
| R-1 | Public endpoint → vault read/write if the token leaks | bearer floor now; OAuth before remote sensitive use; Funnel off until needed |
| R-2 | The agent's decomposition is generic/wrong, so plans get ignored | plans are *editable proposals*, not commitments; measure how much gets kept (FR-1) |
| R-3 | Agent-authored notes drift from the user's style and pollute the graph | NFR-1 is load-bearing; ingest/notes go through a convention check; user approves before write |
| R-4 | Retention layer never adopted because Anki setup friction | P3 includes the Anki install path; cards are a *byproduct* of work, not a separate chore |
| R-5 | Meta-work trap — building/curating the system replaces learning | P4/P5 gated on P2/P3 still being used at the monthly review |
| R-6 | Scope sprawl (it tries to be everything) | phase gating; each phase must earn the next on real usage |

## 9. Phases

- **P1 — execution engine** ✅ *(built: pools, draw, park, complete, Today.md,
  hardened in the 2026-06-10 review).*
- **P2 — decomposition + driving:** source → editable plan (FR-1/2);
  resume-biased, dependency-aware draw (FR-3); multi-vault grounding (FR-5).
- **P3 — retention:** stand up Anki; generative drills (FR-10); cards as a
  byproduct of understood subtasks (FR-6); convention-respecting note writing
  (FR-8).
- **P4 — connections:** cross-vault link discovery (FR-7).
- **P5 — ingestion:** authored doc → KB notes + MOC + cards (FR-9).
- **P6 — extensibility & (only if earned) a purpose-built UI.**

## 10. Non-goals (v2)

Teams/multi-user; replacing Anki's review UI or Zotero's library UI; a custom
mobile app before P6; **auto-*creating* tasks without the user** (the agent
*proposes*, the user disposes — auto-*suggest* is core, auto-*commit* is not);
being a general productivity/to-do app (it is a *learning* agent).

## 11. Open questions

1. **Name.** "popstack" described the old random-stack mechanic; the product is
   now a learning agent. Rename? (First good ADR exercise.) "draw" already
   replaces "pop" in the vocabulary.
2. How much **autonomy** in "driving"? Pure proposer, or may it schedule
   reviews / nudge on stale goals unprompted?
3. Decomposition: one fixed template per source-type (paper/codebase/language/
   algorithm/system-design), or fully generated each time? Probably templates +
   editing.
4. Recall format per domain — cloze for definitions, problem-cards for
   algorithms (the `coding` proofs suggest derivation-cards), explain-to-a-
   beginner for systems. Decide empirically (FR-10).
5. Do dated **deadlines** even apply here (learning is mostly self-paced), or is
   the weight just priority + dependency + neglect? Likely drop hard deadlines
   for most goals.

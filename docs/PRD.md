# PRD — popstack

> **What a PRD is for:** it pins down the *problem, the users, what the
> product must do, and how we'll know it works* — in language anyone can
> follow without having been in the room. It deliberately avoids *how*:
> mechanisms and architecture live in [DESIGN.md](DESIGN.md); the reasoning
> behind contested choices lives in [DECISIONS.md](DECISIONS.md).
>
> Two rules this document follows (the v1.0 draft broke both):
> **(1) write for a reader with zero context** — every invented word is
> defined before it is used; **(2) state outcomes, not mechanisms** — "the
> system hands you one task" is a requirement; "weighted-random sampling"
> is a design choice and stays out of this file.

- **Status:** v1.1 · **Owner:** @ravich3373 · **Last updated:** 2026-06-10

## 1. The problem

Tasks arrive everywhere — at the work laptop, on the phone, mid-conversation
— and get parked in heads, chat threads, and scattered notes. Two specific
failures follow:

1. **Captured badly.** A task that isn't written down somewhere trusted
   keeps nagging at you (it occupies working memory). A task written
   somewhere you never look again is simply lost.
2. **Chosen badly.** When you sit down to work, you face a long list of
   similar-looking items and must *decide* what to do first. That decision
   is itself work, and under a big backlog it reliably turns into stalling:
   re-reading the list, picking something easy, or escaping to something
   else entirely.

Plenty of tools solve pieces of this — to-do apps, timers, random pickers,
reference managers. None of them connect the pieces: save a task from
anywhere, get handed one thing to do, see what you already know that's
relevant to it, work it for a bounded slice of time, and put it back with
enough notes that future-you resumes warm instead of cold. popstack is that
connection, built around tools already in daily use (Obsidian, Zotero, Anki,
Claude).

## 2. Words this document uses

popstack borrows programming words and bends some of them. Defined once,
here; used freely afterwards.

| Word | Meaning here |
|---|---|
| **task** | one thing to do, stored as one plain-text (markdown) file |
| **the stack** | all your tasks together. Despite the name, *not* a strict last-in-first-out stack — see **pop** |
| **active pool** | the small set of tasks (at most ~20) currently eligible to be handed to you |
| **reservoir** | every other task — someday-items and overflow. Moving tasks between reservoir and active pool is a deliberate act |
| **pop** | "hand me one task." The system picks exactly one task from the active pool and presents it. Popping does **not** delete the task; a task leaves the stack only when completed. (Yes, this stretches the programming word — see open question Q5) |
| **park** | put the task you were handed back, after working on it, with a written one-line next step |
| **grounding** | gathering what you already know about a task — your own notes and saved papers — and presenting it alongside the task |
| **timebox** | a fixed-length work interval (e.g. 30 minutes), after which you stop and either complete or park |
| **recall drill** | the system quizzes you on something from your notes or papers; what you get wrong becomes a flashcard |

## 3. Who it's for, on what devices

One user (a software/ML engineer) across three device classes:

- **Laptop** — deep work; Claude Code is already open all day.
- **Phone** — capturing tasks and light interaction (via the Claude app and
  Obsidian mobile).
- **An always-on machine** — runs the popstack server and holds the Obsidian
  vault, Zotero library, and Anki collection.

Hard constraint: Obsidian (notes), Zotero (papers), and Anki (flashcards)
are already in use and must be **embraced, not replaced**.

## 4. How it works — one day with popstack

Morning, phone: Obsidian shows a generated **Today** note — the three tasks
most likely to be handed out next, anything overdue, anything gone stale.

At the desk you tell Claude **"pop."** It hands you exactly one task — say
*Read the FSRS scheduler paper* — together with a short brief: the two vault
notes that mention spaced repetition, and the related papers already in
Zotero. You read no list and made no decision.

You work it for a 30-minute timebox. Not finished — so you **park** it. The
system refuses until you give a one-line next step (*"summarize §2 into the
vault note"*). The task goes back carrying that note, and won't be offered
again for a few hours.

On the train you say **"capture: review Bazel remote-cache settings, due
Friday."** It's saved before the screen locks, as a markdown file in your
own vault.

Evening, ten free minutes: **"drill me."** It pulls a random note from your
vault, asks three questions, and the one you miss becomes an Anki flashcard
your phone will resurface next week.

The loop, in one line:

> **save from anywhere → be handed one task → see what you know → work a
> timebox → done, or back-with-a-plan**

## 5. Goals

| # | The outcome we want | How we'd know it's working |
|---|---------------------|----------------------------|
| G1 | Saving a task takes seconds and one step, from any device — fast enough that nothing stays "in your head because writing it down is effort" | capture feels reflexive; tasks stop living in chat threads and heads |
| G2 | Starting work requires **no choosing**: ask, and exactly one task is handed to you. Tasks nearer their deadline, higher in priority, or neglected for a long time must come up more often — but nothing in the active pool may be buried forever | handed tasks are usually accepted rather than re-rolled; deadlines stop being missed; old tasks resurface on their own |
| G3 | Every handed task arrives with what you already know about it (your notes, your saved papers), so work starts from your knowledge instead of a blank page | the brief is read and used on most pops |
| G4 | A task can only be put back with a concrete next step attached, so parked work stops nagging and resuming starts warm | no "where was I?" archaeology when a task comes back |
| G5 | What you learn compounds: anything you fail to recall becomes a flashcard that your phone resurfaces on a spaced schedule | misses become cards; cards actually get reviewed |
| G6 | The data stays yours: every task is a plain markdown file in your own vault | deleting popstack loses nothing; no proprietary storage anywhere |

**Non-goals (v1):** teams or any second user; replacing Anki's review
experience; building a custom mobile app (reconsidered only in P3, after
real usage); calendar scheduling; generating tasks automatically.

## 6. What the system must do

Requirements say *what*, in user-visible terms. The *how* for each is in
[DESIGN.md](DESIGN.md) (linked per row).

### Functional requirements

| ID | The system must… | Status · design |
|----|------------------|-----------------|
| FR-1 | Save a task with a title and optional notes, tags, due date, priority, and time estimate | ✅ · [§2](DESIGN.md#2-data-model) |
| FR-2 | Keep the active pool small (default cap 20). Tasks beyond the cap land in the reservoir; moving between pool and reservoir is an explicit action | ✅ · [§2](DESIGN.md#2-data-model) |
| FR-3 | On request, hand over exactly **one** active task. A closer deadline, higher priority, and longer neglect must each raise a task's chance of being handed out. A just-parked task must not reappear for a few hours (default 4). The user may always decline and ask again | ✅ · [§3](DESIGN.md#3-pop-algorithm) |
| FR-4 | Refuse to park a task unless a specific next step is written; record that step, and the park history, on the task itself | ✅ · [§2](DESIGN.md#2-data-model) |
| FR-5 | Mark a task complete (optional note) and keep completed tasks as browsable history | ✅ |
| FR-6 | For any task, collect what the vault and the paper library already contain about it, for use as a brief | ✅ · [§4](DESIGN.md#4-component-map) |
| FR-7 | Search the paper library; save a new paper given just its DOI | ✅ |
| FR-8 | Create flashcards; report how many are due. If Anki is absent, explain how to set it up instead of failing | ✅ |
| FR-9 | Report stack health: pool counts, overdue tasks, and stale tasks (parked 3+ times, or older than 30 days) | ✅ |
| FR-10 | Generate a daily **Today** note in the vault: likely next tasks, overdue, stale, flashcards due | ✅ |
| FR-11 | Run recall drills over notes and papers, and turn misses into flashcards | 🔜 P2 |
| FR-12 | Do the routine things on a schedule, unprompted (morning Today note; weekly health review) | 🔜 P1 |

### Non-functional requirements

- **NFR-1 · Ownership.** All task state is human-readable markdown inside
  the user's vault. Uninstalling popstack loses nothing.
- **NFR-2 · Reach.** Everything above must be usable from the laptop *and*
  the phone. No popstack-specific app may be required through P2.
- **NFR-3 · Safety when reachable from the internet.** The server must
  reject any request that doesn't present the configured secret. Before
  task contents become sensitive, real login (OAuth) is required, not just
  a shared secret.
- **NFR-4 · Graceful degradation.** Zotero or Anki being closed or missing
  must never block the core loop, and every error must say what to fix.
- **NFR-5 · Zero operations.** No database server, no migrations, nothing
  to administer. All state is files; a reboot loses nothing.

## 7. How we'll judge it (review monthly)

- ≥10 tasks handed out *and worked* per week (G2 alive)
- parks-to-completes below 3:1 (G4 alive — tasks finish, not just cycle)
- the stale list trends down, not up (FR-9 doing its job)
- ≥5 flashcards created per week once drills land (G5 alive)
- The qualitative one that decides everything: **is capture still
  reflexive?** The system dies the day a task feels easier to keep in your
  head.

## 8. Risks

| ID | Risk | Mitigation |
|----|------|-----------|
| R-1 | When exposed to the internet, anyone holding the secret token can read and write the Stack folder of the vault | secret required at minimum; keep the public endpoint off until phone use starts; OAuth before anything sensitive (NFR-3) |
| R-2 | Tinkering with the system replaces using it (the classic productivity-tool trap) | P3 is gated on a month of real P1/P2 usage data |
| R-3 | Two devices edit the same task file at the same moment (sync conflict) | in practice only the server writes task files; Obsidian's sync merges note bodies; accepted as last-writer-wins for metadata until observed in the wild |
| R-4 | A handed task feels stale or irrelevant → trust in "just pop" erodes | urgency raises odds, cooldowns stop repeats, declining is always allowed; tune from health data |
| R-5 | Abandonment — the fate of most personal productivity systems | the §7 metrics are reviewed monthly; unused features get deleted, not maintained |

## 9. Phases

- **P0 — engine + server** ✅ *(this repo, 2026-06-10)*
- **P1 — daily use:** register with Claude Code; schedule the Today note;
  expose to the phone (with the secret); tune handing-out behavior from
  real usage.
- **P2 — the learning loop:** recall drills; misses → flashcards; metric
  instrumentation.
- **P3 — a purpose-built app** *(only if P1/P2 usage demands it):*
  one-button pop, a visible countdown, swipe-to-park.

## 10. Open questions

1. The urgency behavior (FR-3) ships with borrowed defaults — re-tune after
   ~50 real pops?
2. Should a task's time estimate influence what gets handed out ("I have 15
   minutes — give me something short")? Energy/context tags?
3. Recall drill format: free recall, cloze deletion, or
   explain-it-to-a-beginner?
4. OAuth: implement ourselves or adopt a library — decide at P1 exit.
5. **Naming:** "pop" stretches the programming word (nothing is removed,
   and selection isn't last-in-first-out). Rename to **draw**? Touches tool
   names and docs — decide before muscle memory sets in. *(Good first ADR
   exercise: if yes, write ADR-008 superseding the vocabulary.)*

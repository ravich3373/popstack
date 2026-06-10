# Portability — learning from anywhere

> The goal: learn in bed, on the toilet, in the back of a car — anywhere. This
> doc designs *how you reach the agent and your recall infra* across places and
> connectivity. It is referenced by [DESIGN.md](DESIGN.md) and decided in
> [DECISIONS.md](DECISIONS.md) ADR-014.

## The core realization

"Learn from anywhere" is really **two needs with very different infrastructure**,
and separating them makes the whole thing tractable:

1. **Recall** (review flashcards) — high frequency, short sessions, must work
   **offline**. This is what you actually do in bed/toilet/car. **Already solved
   by Anki's own apps** — world-class, offline, free. popstack's only job is to
   *create* the cards on the node; they sync to your phone automatically.
2. **Agent interaction** (decompose a source, draw the next step, get a brief,
   generative drilling) — lower frequency, needs the LLM and the node, so it's
   **online-only**. The trick is reaching the node *privately from anywhere*.

So: **recall is offline-first; the agent is online-private.** You are never
blocked from the thing you do most.

## Three tiers of access

### Tier 1 — Recall (offline, anywhere, daily driver)
**Anki app on the phone** (AnkiDroid free / AnkiMobile paid), synced via
**AnkiWeb** (Anki's free sync; or self-host a sync server later).

```
node: Anki + AnkiConnect ──(popstack adds cards, then triggers sync)──► AnkiWeb
                                                                          │ sync
phone: AnkiDroid / AnkiMobile ◄───────────────────────────────────────────┘
        └─ reviews run 100% locally/offline; sync only when online
```

Review 200 cards on a plane with no signal; it syncs when you land. This is the
bed/toilet/car path and it needs **zero popstack UI**.

### Tier 2 — Glance & capture (offline-deferred)
**Obsidian mobile** renders your vault — the goal plans, the briefs, `Today.md`,
your notes — over the vault's own sync. Read offline; **capture** a thought by
appending to an inbox note that the node triages when it next sees it online.

### Tier 3 — Agent (online, **private via Tailscale — no public endpoint**)
A thin **PWA** (installable web page) served by the node, reached over your
**tailnet**. Because Tailscale meshes your phone directly to the node
(WireGuard, NAT-traversal), this works from anywhere you have internet —
including cellular in the back of a car — **without exposing anything to the
public internet**. Decompose, draw the next subtask, read its brief, mark
progress; and (when you want depth) generative drills.

```
phone (Tailscale on) ──tailnet, WireGuard──► node: popstack HTTP + PWA
   anywhere with internet · private · no Funnel, no OAuth needed
```

> This supersedes the earlier "public Funnel + bearer/OAuth" plan **for your own
> access**: a tailnet-private PWA needs no public endpoint at all, which also
> erases risk R-1. Public Funnel + OAuth is now only for the *optional* claude.ai
> cloud-connector route (Anthropic's cloud reaching your node) — a nicety, not the
> path.

## Connectivity matrix (what works where)

| Place / connectivity | Tier 1 Recall | Tier 2 Glance/capture | Tier 3 Agent |
|---|---|---|---|
| Bed / toilet (home wifi → tailnet) | ✅ offline | ✅ | ✅ |
| Car, cellular signal | ✅ offline | ✅ | ✅ (tailnet over cellular) |
| Subway / plane / dead zone (no internet) | ✅ **offline** | ✅ read; capture queues | ❌ (queues for later) |
| Node down (but phone online) | ✅ (AnkiWeb has the cards) | ✅ (vault sync) | ❌ |

The design guarantees the **most-frequent, most-portable activity (recall)
never depends on connectivity or the node**.

## What this means we build

| Tier | Build | Phase |
|---|---|---|
| 1 Recall | Install Anki + AnkiConnect on the node; `anki.py` triggers an AnkiWeb **sync** after adding cards; set up AnkiDroid/AnkiMobile + AnkiWeb on the phone | P3 (manual setup + a one-line code add) |
| 2 Glance/capture | Free via Obsidian; add an `inbox` note + a triage tool on the node | P2/P3 (small) |
| 3 Agent | Thin PWA over the existing HTTP transport; serve it from the node; reach via tailnet. Deterministic actions (draw/plan/brief/progress) need no LLM; generative drills call the agent runtime | P-portability (slots beside P3) |

**Split inside Tier 3** (honest): the *deterministic* actions (draw the next
subtask, show the plan, show a brief, mark done/park, review a fixed card) are a
thin client over popstack's existing tools and need no LLM — buildable now. The
*generative* actions (decompose a new source, free-text-graded drills) need an
agent runtime on the node (Claude Agent SDK) or the claude.ai connector; that's
the heavier half and can follow.

## The phone learning session, concretely

- **Toilet, 3 min:** open AnkiDroid → review due cards (offline). Done. (Tier 1)
- **Bed, 15 min:** open the PWA → "draw" → it gives the next subtask of your
  active goal + a brief from your vault → you read/think → mark understood →
  it queues two cards. (Tier 3, tailnet)
- **Back of a car, signal:** PWA → "drill me on the flow-matching derivation" →
  generative Q&A, misses become cards for tomorrow. (Tier 3, tailnet)
- **Plane, no signal:** AnkiDroid offline review; jot ideas into the Obsidian
  inbox note; both sync on landing. (Tiers 1–2)

## Open questions

- Self-hosted Anki sync server vs AnkiWeb? (AnkiWeb is fine to start; self-host
  if you want everything on your own infra.)
- PWA vs a chat-bot bridge (Telegram/Signal) for the lowest-friction "from the
  lock screen" agent access? The bot is friction-light but async; the PWA is
  interactive. Decide when building Tier 3.
- Does the node need a true on-device agent runtime (Agent SDK) for generative
  drills offline-of-claude.ai, or is the claude.ai connector enough once OAuth
  lands?

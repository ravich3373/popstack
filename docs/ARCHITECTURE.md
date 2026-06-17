# System Architecture — popstack

> [PRD](PRD.md) = what/why · [DESIGN](DESIGN.md) = how each component works ·
> this doc = **how the pieces physically run and talk to each other**: which
> processes exist, where they run, what protocol connects them, and — bluntly —
> **what actually runs today vs. what is still just code or just a design.**

- **Status:** implementation status is in [DESIGN](DESIGN.md) / [PRD phases](PRD.md#9-phases). Per-machine runtime/deployment state is operator-local, not committed.

## 1. The one idea to hold onto: brain ≠ tools ≠ state

"The agent" is not a single program. It is three things that must be wired
together:

| Role | What it is | Where it runs | Who provides it |
|------|-----------|---------------|-----------------|
| **Brain** | the Claude model that reasons, decomposes, drills | **Anthropic's cloud**, always remote | Anthropic |
| **Tools + state** | popstack: the goal trees, draw, grounding, Anki/Zotero clients, your task markdown | a machine *you* run (locally now; an always-on node later) | this repo |
| **Surface** | the thing you actually touch — a chat client or app | terminal / phone apps | Claude Code, claude.ai app, Obsidian, Anki |

**"Access the agent on my phone"** therefore means: run a *Claude client*
(brain-connected) on or reachable from your phone, wired to popstack's tools
over the network. You never connect "to popstack" directly — you connect to a
Claude surface that *calls* popstack. This is why phone access is a real build,
not a config toggle.

```
   YOU ──talk to──►  a Claude SURFACE  ──calls the model──►  BRAIN (Anthropic cloud)
                          │                                      │ "use the decompose_source tool"
                          └────────────── calls tools ───────────┘
                                          ▼
                              popstack TOOLS + STATE
                              (engine, goals, grounding,
                               Anki/Zotero clients, vault)
```

## 2. Components (what's in the repo)

All Python, one package:

| Module | Responsibility |
|--------|----------------|
| `stack.py` | the engine: subtasks as markdown, the draw (dependency-aware, resume-biased), park/complete/move, health |
| `goals.py` + `templates.py` | decompose a source into a Goal→Subgoal→Subtask tree |
| `grounding.py` | search the vault(s) for relevant notes (multi-vault is P2-remaining) |
| `zotero.py` / `anki.py` | thin clients for the Zotero local API and AnkiConnect |
| `today.py` | render the glanceable `Today.md` |
| `server.py` | exposes all of the above as **MCP tools**, over two transports (stdio, HTTP) |

popstack is **stateless infrastructure over the vault**: its only durable state
is markdown files in `<vault>/Stack/`. No database, no daemon required.

## 3. Where things run (the deployment planes)

```
┌─ ANTHROPIC CLOUD ───────────────────────────────────────────────┐
│  Claude model (the brain)                                        │
└───────▲───────────────────────────────────────▲─────────────────┘
        │ HTTPS (model API)                      │ HTTPS
        │                                        │
┌─ YOUR MACHINE ─────────────┐     ┌─ ALWAYS-ON NODE (future) ─────────────┐
│ Claude Code (surface+brain │     │ popstack HTTP server                  │
│   connection)              │     │ Anki + AnkiConnect                    │
│   │ MCP over stdio         │     │ Zotero (local API)                    │
│   ▼                        │     │ vault replica                         │
│ popstack (stdio subprocess)│     │ (future) PWA + Agent SDK runtime      │
│   │ files / localhost      │     └───▲───────────────▲──────────────┬────┘
│   ▼                        │         │ tailnet (WireGuard)          │ Anki
│ vault · Zotero · Anki      │         │ HTTPS private                │ sync
└────────────────────────────┘         │                              ▼
                                ┌─ YOUR PHONE (future) ──────────────────────┐
                                │ Claude app / PWA (surface)  ◄─ agent        │
                                │ Obsidian mobile (glance)    ◄─ vault sync   │
                                │ AnkiDroid / AnkiMobile      ◄─ AnkiWeb sync │
                                └─────────────────────────────────────────────┘
```

Two ways popstack is reached, by transport:

- **stdio** — the Claude client launches popstack as a child process and talks
  over stdin/stdout. Local only, no network, no auth. *This is the local path.*
- **HTTP** — popstack runs as a web server (`--http`); a remote Claude surface
  calls it over the network. For *your* devices this rides the **tailnet**
  (private, no public exposure, ADR-014); a public Funnel + OAuth is only needed
  for the claude.ai cloud connector.

## 3b. Do I configure this on every device? (No.)

A common confusion: `claude mcp add` is **not** a per-device step. There are two
distinct connection mechanisms, and you use each once:

| Mechanism | Configures | Scope | You do it… |
|-----------|-----------|-------|-----------|
| `claude mcp add` | the **Claude Code CLI** on one machine | per-machine that runs Claude Code | on your **machine, once** |
| **claude.ai custom connector** | your **claude.ai account** | every device you're signed into | on your **account, once** (when the node is live) |

So: one `claude mcp add` on your machine today; later, one connector setup pointing
at your node (over Tailscale) that your phone, web, and desktop all inherit. The
phone never runs `claude mcp add` — there is no Claude Code on it. Configuration
is per-machine-running-Claude-Code or per-account, **never per-device-you-use.**

## 4. Wire protocols (who speaks what)

| From → To | Protocol | Notes |
|-----------|----------|-------|
| Claude surface → Brain | HTTPS (model API) | always remote |
| Claude Code → popstack | **MCP / stdio** | local subprocess |
| claude.ai / PWA → popstack | **MCP / HTTP** over Tailscale | private; Funnel+OAuth only for claude.ai cloud |
| popstack → vault | filesystem | markdown read/write |
| popstack → Zotero | HTTP `localhost:23119` | local API |
| popstack → Anki | HTTP `localhost:8765` | AnkiConnect |
| node Anki ↔ phone Anki | Anki sync ↔ **AnkiWeb** | offline-capable on the phone |
| vault ↔ all devices | Obsidian/iCloud/git sync | independent of popstack |

## 5. Two request flows

**A. Decompose a paper (local, works once registered):**
```
you (Claude Code): "decompose the pi0 paper, it's in Zotero"
  → brain decides to call decompose_source(kind="paper", source=...)
  → MCP/stdio → popstack.goals.create() writes the goal tree to <vault>/Stack/goals/
  → returns the plan → brain shows it → you edit it in chat or in Obsidian
```

**B. Review cards on the phone (target; needs P3 setup):**
```
node: popstack.anki.add_cards() → AnkiConnect → node's Anki → sync → AnkiWeb
phone: AnkiDroid ← sync ← AnkiWeb → you review, offline, in bed
  (no popstack, no brain, no network needed during review)
```

## 6. Implementation status (codebase, not your machine)

| Capability | Today | To make it real |
|-----------|-------|-----------------|
| P2 engine (decompose, draw, goals) | ✅ **code + tests on GitHub** | — |
| Use it **locally** | ⚠️ **not until you run one command** | `claude mcp add popstack --scope user -- uv --directory <repo> run popstack`, then talk to it in a Claude Code session |
| Grounding across your configured vaults + cross-vault connections | ✅ **code + tests** | set `POPSTACK_VAULTS` to your vaults |
| Codebase support (clone, map, decompose) | ✅ **code + tests** | `clone_repo`/`map_repo`; the agent reads the code with its own tools |
| Writing notes into the KB (snippets, MOCs, links) | ✅ **code + tests** (quarantine folder, preview-first, no-clobber) | `write_note`/`append_snippet`/`add_to_moc`; set `POPSTACK_NOTES_*` |
| Retention / Anki on phone | ❌ Anki not installed | install Anki + AnkiConnect on a node; set up AnkiDroid + AnkiWeb (P3) |
| **Agent on the phone** | ❌ **does not exist** | stand up the always-on node + tailnet HTTP serving + a phone Claude surface (PWA+Agent SDK, or claude.ai connector once OAuth) — this is the biggest remaining build |
| Anything running as a service | ❌ **nothing is deployed** | popstack only runs when a client launches it (stdio) or you run `--http` |

**Plainly:** right now this is a tested codebase on GitHub. The first time you
can use it at all is on your machine after the `claude mcp add` command. Phone
access is several build steps (a node, tailnet serving, a phone surface) away —
all designed in [PORTABILITY.md](PORTABILITY.md), none built.

## 7. The path to "I can learn on my phone"

In dependency order:

1. **Local use** — `claude mcp add …` (you, 1 min). Validates the loop.
2. **A node** — pick an always-on machine (old laptop / Mac mini); put the vault,
   Zotero, and Anki on it; run `popstack --http`; join it to your tailnet.
3. **Recall on phone** — install Anki + AnkiConnect on the node, AnkiDroid +
   AnkiWeb on the phone. *This alone gives you offline learning anywhere* and is
   the highest-leverage step (closes the zero-spaced-repetition gap).
4. **Agent on phone** — build the Tier-3 surface: a PWA over the tailnet for the
   deterministic actions (draw/plan/brief), then an Agent SDK loop (or the
   claude.ai connector) for generative decomposition/drills.

Steps 1 and 3 deliver most of the value and need little code; step 4 is the real
app-building.

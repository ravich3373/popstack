# Anki knowledge deck

`popstack-and-coram-knowledge.txt` — **164 spaced-repetition cards** covering the
knowledge behind building popstack and the Coram agentic-adaptation report. Each
card was generated from the actual source docs and **adversarially fact-checked
against its source** before inclusion (no memory, no invention).

## Decks (created automatically on import, hierarchical via `::`)

| Cards | Deck | Covers |
|------:|------|--------|
| 17 | `popstack::Concepts` | MCP, brain/tools/surface, transports, connectors |
| 18 | `popstack::Architecture` | deployment planes, portability tiers |
| 21 | `popstack::Design Decisions` | the ADRs and their *why* |
| 17 | `popstack::Integrations` | Zotero/Anki/Obsidian specifics + the org principle |
| 14 | `popstack::Behavioral Science` | the verified findings, with correct attributions |
| 17 | `Coram Agents::Repo Inventory` | how each repo is adapted |
| 20 | `Coram Agents::Agent Interfaces` | CLAUDE.md, skills, hooks, MCP, … |
| 20 | `Coram Agents::Improvements` | the recommendations |
| 20 | `Coram Agents::Claude Code Reference` | the capability reference |

## How to import (once Anki is installed)

1. Open Anki → **File → Import** → choose `popstack-and-coram-knowledge.txt`.
2. The file's header lines tell Anki everything: tab-separated, Basic notetype,
   **column 1 = deck** (so the `::` decks are created for you), column 4 = tags.
3. In the import dialog, confirm the field mapping is **Front → Front,
   Back → Back** (it should be automatic), then **Import**.
4. The nine decks appear under `popstack` and `Coram Agents`.

> The cards use `<br>` for line breaks and `#html:true`, so they render cleanly.

## After Anki + AnkiConnect are installed

Once Anki is running with the **AnkiConnect** add-on (`2055492159`), the agent
can add *new* cards straight into these decks via the `anki_add_cards` tool
(filed by topic, hierarchically) — no more import files needed. Reviews always
happen in Anki's own apps (AnkiDroid/AnkiMobile), which is exactly the
offline-anywhere recall the design counts on.

## Notes

- A couple of facts (e.g. the brain/tools/surface model) appear in two decks
  by design — they're load-bearing enough to drill from two angles. If you'd
  rather not, suspend one during review.
- Regenerate/extend anytime: the cards came from `docs/*.md` + the coram report;
  re-run the knowledge-to-anki workflow after the docs change.

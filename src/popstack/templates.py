"""Decomposition templates: per source-type skeletons for turning a source
into a goal -> subgoal -> subtask plan (PRD FR-1, ADR-008).

Each template is an ordered list of subgoals; each subgoal has ordered
subtasks. The agent/user edits the result. When a source-type has no template,
the caller falls back to an agent-supplied outline (create_from_outline) — see
goals.py. Templates are data on purpose: easy to read, edit, and extend.

The shapes here match how the user actually learns (ML/CS papers, real
codebases, languages, algorithms with proofs, system design with capacity math).
"""

from typing import Any

# kind -> [ {subgoal, subtasks:[...]}, ... ]
TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "paper": [
        {"subgoal": "Skim & context", "subtasks": [
            "Read abstract, intro, and conclusions; state the core claim in one sentence",
            "Place it among related work — what does it improve on, and how",
            "Note the 2-3 questions you most need answered to trust the result",
        ]},
        {"subgoal": "Understand the math", "subtasks": [
            "Identify the key formalism / objective",
            "Re-derive the main result on paper",
            "Work the smallest concrete example end to end",
        ]},
        {"subgoal": "Understand the experiments", "subtasks": [
            "List datasets, baselines, and metrics",
            "Understand the training/eval setup and the key hyperparameters",
            "Read the ablations — which components actually matter",
        ]},
        {"subgoal": "Understand the results", "subtasks": [
            "What do the headline numbers actually show",
            "State the limitations and the conditions under which it would break",
        ]},
        {"subgoal": "Replicate", "subtasks": [
            "Find or skeleton the code; get it building/running",
            "Reproduce one minimal result",
            "Compare to the reported number and explain any gap",
        ]},
        {"subgoal": "Retain & connect", "subtasks": [
            "Make recall cards for the core ideas and the key derivation",
            "Link to the related notes and papers this builds on",
        ]},
    ],
    "codebase": [
        {"subgoal": "Map the architecture", "subtasks": [
            "Build and run it; get a working local instance",
            "Find the entry points and the top-level component map",
            "Draw the component diagram (who talks to whom)",
        ]},
        {"subgoal": "Trace the core path", "subtasks": [
            "Pick one end-to-end flow and read it top to bottom",
            "Note the key data structures and the contracts between components",
        ]},
        {"subgoal": "Understand a subsystem deeply", "subtasks": [
            "Pick the most load-bearing module and read it closely",
            "Write down its invariants and the non-obvious decisions",
        ]},
        {"subgoal": "Replicate / modify", "subtasks": [
            "Make a small, real change",
            "Run the tests and verify the behavior changed as expected",
        ]},
        {"subgoal": "Retain & connect", "subtasks": [
            "Make cards for the key design decisions and contracts",
            "Link to related systems notes in the KB",
        ]},
    ],
    "language": [
        {"subgoal": "Core model", "subtasks": [
            "Syntax and the type system",
            "The memory / ownership / execution model",
            "The build, run, and test toolchain",
        ]},
        {"subgoal": "Idioms", "subtasks": [
            "Error handling the idiomatic way",
            "Concurrency model and primitives",
            "The standard-library pieces you'll use most",
        ]},
        {"subgoal": "Practice", "subtasks": [
            "Solve 5 small problems in it",
            "Read a chunk of idiomatic real-world code",
            "Write one small program from scratch",
        ]},
        {"subgoal": "Retain", "subtasks": [
            "Cards for syntax gotchas and idioms",
        ]},
    ],
    "algorithm": [
        {"subgoal": "Understand", "subtasks": [
            "The problem it solves and where it's the right tool",
            "The invariant / recurrence at its heart",
            "The proof of correctness",
        ]},
        {"subgoal": "Implement", "subtasks": [
            "Code it from scratch without looking",
            "Test the edge cases",
            "Analyze time and space complexity",
        ]},
        {"subgoal": "Practice", "subtasks": [
            "Solve 3 variants",
            "Drill recognizing when to reach for it",
        ]},
        {"subgoal": "Retain", "subtasks": [
            "A derivation card and a pattern-recognition card",
        ]},
    ],
    "system-design": [
        {"subgoal": "Fundamentals", "subtasks": [
            "The core trade-off this design navigates",
            "The canonical components and why each earns its place",
            "The back-of-envelope capacity math",
        ]},
        {"subgoal": "Case study", "subtasks": [
            "Walk a real design and justify each choice",
            "Find the failure modes and how they're handled",
        ]},
        {"subgoal": "Practice", "subtasks": [
            "Do one timed design",
            "Critique it against the trade-offs",
        ]},
        {"subgoal": "Retain", "subtasks": [
            "Cards for the numbers and the key trade-offs",
        ]},
    ],
}

# Aliases so the agent can pass natural names.
ALIASES = {
    "research-paper": "paper", "arxiv": "paper", "ml-paper": "paper", "cs-paper": "paper",
    "repo": "codebase", "code": "codebase", "project": "codebase",
    "programming-language": "language", "lang": "language",
    "data-structure": "algorithm", "algo": "algorithm", "ds": "algorithm",
    "systems-design": "system-design", "sysdesign": "system-design",
}


def kinds() -> list[str]:
    """Source-types that have a built-in template."""
    return sorted(TEMPLATES)


def resolve_kind(kind: str) -> str | None:
    """Normalize a source-type to a template key, or None if there is no
    template (the caller should then fall back to an agent-supplied outline)."""
    if not kind:
        return None
    k = kind.strip().lower()
    k = ALIASES.get(k, k)
    return k if k in TEMPLATES else None


def get_template(kind: str) -> list[dict[str, Any]] | None:
    """The subgoal/subtask outline for a source-type, or None if unknown."""
    resolved = resolve_kind(kind)
    return [dict(sg, subtasks=list(sg["subtasks"])) for sg in TEMPLATES[resolved]] if resolved else None

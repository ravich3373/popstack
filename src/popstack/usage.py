"""Record per-task token usage fed from the Claude Code client.

The MCP server can't see tokens (the model consumes them, the client sees the
counts). This console script bridges that: it takes token numbers — directly,
or read from a Claude Code session transcript — and records them against the
in-focus subtask via the engine.

Wired as a Claude Code **Stop hook** so it runs automatically each turn:

    "hooks": {
      "Stop": [
        { "matcher": "", "hooks": [
          { "type": "command",
            "command": "uv --directory ~/Documents/repos/popstack run popstack-usage --hook" }
        ]}
      ]
    }

The Stop hook sends its JSON (including `transcript_path`) on stdin; `--hook`
reads it, sums the latest turn's real input/output tokens from the transcript,
and attributes them to whatever subtask you most recently drew.
"""

import argparse
import json
import sys
from pathlib import Path

from .stack import Stack


def _transcript_from_stdin() -> str | None:
    """Read a Claude Code hook payload (JSON on stdin) and return its
    transcript_path, if present."""
    if sys.stdin.isatty():
        return None
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return None
    return payload.get("transcript_path")


def turn_usage_from_transcript(path: str) -> tuple[int, int, str | None]:
    """Sum input/output tokens of the assistant messages in the latest turn
    (everything after the last user message) of a Claude Code transcript JSONL.

    Each API call in a multi-step turn is billed separately, so summing per-call
    input+output across the turn is the right 'tokens used' figure. Cache-read
    tokens count as input. Returns (input_tokens, output_tokens, model)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # find the start of the latest turn (after the last user message)
    last_user = -1
    for i, r in enumerate(rows):
        if r.get("type") == "user":
            last_user = i

    tin = tout = 0
    model = None
    for r in rows[last_user + 1:]:
        if r.get("type") != "assistant":
            continue
        msg = r.get("message", {})
        u = msg.get("usage") or {}
        tin += int(u.get("input_tokens", 0)) + int(u.get("cache_read_input_tokens", 0)) \
            + int(u.get("cache_creation_input_tokens", 0))
        tout += int(u.get("output_tokens", 0))
        model = msg.get("model", model)
    return tin, tout, model


def main() -> None:
    p = argparse.ArgumentParser(description="record per-task token usage")
    p.add_argument("--hook", action="store_true",
                   help="read the Claude Code Stop-hook JSON from stdin (gets transcript_path)")
    p.add_argument("--from-transcript", help="Claude Code transcript JSONL; reads the latest turn's usage")
    p.add_argument("--in", dest="tin", type=int, default=0, help="input tokens")
    p.add_argument("--out", dest="tout", type=int, default=0, help="output tokens")
    p.add_argument("--task", help="subtask id (default: the in-focus task)")
    p.add_argument("--model", help="model id")
    args = p.parse_args()

    transcript = args.from_transcript or (_transcript_from_stdin() if args.hook else None)
    tin, tout, model = args.tin, args.tout, args.model
    if transcript:
        try:
            tin, tout, model = turn_usage_from_transcript(transcript)
        except OSError:
            return  # a hook must never break the turn; stay silent

    if tin == 0 and tout == 0:
        return  # nothing to record (e.g. a no-op turn) — stay quiet for hooks

    result = Stack().record_usage(tin, tout, task_id=args.task, model=model)
    # A hook should never break the turn; print and exit 0 regardless.
    print(json.dumps(result))


if __name__ == "__main__":
    main()

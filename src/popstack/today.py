"""Tier 2: write <vault>/Stack/Today.md — the glanceable, phone-visible view.
Run on a schedule (launchd/cron) on the always-on node; Obsidian sync carries
it to every device. It lives at the Stack root (not inside a pool directory),
so it is never treated as a task.
"""

import datetime as dt

from . import anki as anki_mod
from . import config
from .stack import Stack


def render() -> str:
    now = dt.datetime.now()
    stack = Stack()
    active = stack.list_pool("active", now)
    health = stack.health(now)
    anki = anki_mod.status()

    lines = [
        f"# Today — {now:%a %Y-%m-%d}",
        "",
        "## Top of the stack (by weight — pop one!)",
    ]
    for t in active[:3]:
        due = f" · due {t['due']}" if t["due"] else ""
        cooling = " · cooling down" if t.get("cooling_down") else ""
        next_a = f" · next: {t['next_action']}" if t.get("next_action") else ""
        lines.append(f"- **{t['title']}** (w={t['weight']}{due}{cooling}){next_a} — `{t['id']}`")
    if not active:
        lines.append("- _active pool is empty — promote something from the reservoir_")

    lines += ["", "## Health",
              f"- active {health['active']}/{health['active_limit']}, "
              f"reservoir {health['reservoir']}, done {health['done']}"]
    for t in health["overdue"]:
        lines.append(f"- ⚠️ overdue: **{t['title']}** (due {t['due']}) — `{t['id']}`")
    for t in health["stale"]:
        lines.append(f"- 🦴 stale: **{t['title']}** ({t['pushes']} pushes) — `{t['id']}`")

    if anki.get("available"):
        lines += ["", f"## Recall — {anki['due_cards']} Anki cards due"]
    return "\n".join(lines) + "\n"


def main() -> None:
    out = config.stack_root() / "Today.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

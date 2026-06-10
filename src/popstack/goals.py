"""Goals: turn a source into a Goal -> Subgoal -> Subtask tree (ADR-010, FR-1/2).

A goal is a learning objective over one source (a paper, codebase, topic). Its
plan comes from a per-source-type template (templates.py) or, when no template
fits, an agent-supplied outline (the fallback the user asked for). Subtasks are
ordinary engine tasks (stack.py) tagged with goal+subgoal; they are *staged by
subgoal* — the first subgoal's subtasks go into the active pool, later subgoals
wait in the reservoir until promoted, so you work the plan in order without
hard-wiring dependencies.

Goal definition files live at <vault>/Stack/goals/<goal-id>.md (outside the
task pools, so they are never drawn as tasks).
"""

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any

import frontmatter

from . import templates
from .stack import Stack, _slugify


class Goals:
    def __init__(self, stack: Stack | None = None):
        self.stack = stack or Stack()
        self.dir = self.stack.root / "goals"
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------- creation ----------

    def _new_id(self, title: str) -> str:
        now = dt.datetime.now().isoformat()
        digest = hashlib.sha1(f"{title}{now}".encode()).hexdigest()[:6]
        return f"{_slugify(title)}-{digest}"

    def create(
        self,
        title: str,
        kind: str,
        source: str | None = None,
        outline: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a goal and materialize its plan.

        outline (optional) overrides the template — it is the agent fallback:
        [{"subgoal": str, "subtasks": [str, ...]}, ...]. If omitted, the
        template for `kind` is used; if there is no such template and no
        outline, raises (the caller should supply an outline).
        """
        plan = outline or templates.get_template(kind)
        if not plan:
            raise ValueError(
                f"no template for source-type '{kind}'; pass an outline "
                "(the agent should decompose it and supply subgoals/subtasks)"
            )

        goal_id = self._new_id(title)
        now = dt.datetime.now()
        meta = {
            "title": title,
            "kind": templates.resolve_kind(kind) or kind,
            "created": now.isoformat(timespec="seconds"),
            "status": "active",
            "subgoals": [sg["subgoal"] for sg in plan],
        }
        if source:
            meta["source"] = source
        body = f"# {title}\n\nLearning goal over: {source or kind}\n"
        self._save_goal(goal_id, frontmatter.Post(body, **meta))

        # Stage: first subgoal -> active, the rest -> reservoir.
        created = []
        for i, sg in enumerate(plan):
            pool = "active" if i == 0 else "reservoir"
            for st in sg["subtasks"]:
                created.append(
                    self.stack.capture(st, pool=pool, goal=goal_id, subgoal=sg["subgoal"])
                )
        return self.plan(goal_id)

    # ---------- views ----------

    def _goal_path(self, goal_id: str) -> Path:
        p = self.dir / f"{goal_id}.md"
        if not p.exists():
            raise FileNotFoundError(f"no goal with id '{goal_id}'")
        return p

    def _save_goal(self, goal_id: str, post: frontmatter.Post) -> None:
        (self.dir / f"{goal_id}.md").write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")

    def _subtasks(self, goal_id: str) -> list[dict[str, Any]]:
        out = []
        for pool in ("active", "reservoir", "done"):
            out += [t for t in self.stack.list_pool(pool) if t.get("goal") == goal_id]
        return out

    def list_goals(self) -> list[dict[str, Any]]:
        goals = []
        for p in sorted(self.dir.glob("*.md")):
            post = frontmatter.load(p)
            subs = self._subtasks(p.stem)
            done = sum(1 for s in subs if s["pool"] == "done")
            goals.append({
                "id": p.stem,
                "title": post.metadata.get("title", p.stem),
                "kind": post.metadata.get("kind"),
                "status": post.metadata.get("status", "active"),
                "progress": f"{done}/{len(subs)}",
            })
        return goals

    def plan(self, goal_id: str) -> dict[str, Any]:
        """The goal's tree grouped by subgoal, with per-subgoal progress."""
        post = frontmatter.load(self._goal_path(goal_id))
        subs = self._subtasks(goal_id)
        order = post.metadata.get("subgoals", [])

        by_sg: dict[str, list[dict[str, Any]]] = {sg: [] for sg in order}
        for s in subs:
            by_sg.setdefault(s.get("subgoal") or "(unsorted)", []).append(s)

        subgoals = []
        for sg in list(by_sg):
            items = by_sg[sg]
            done = sum(1 for s in items if s["pool"] == "done")
            subgoals.append({
                "subgoal": sg,
                "progress": f"{done}/{len(items)}",
                "complete": bool(items) and done == len(items),
                "subtasks": [
                    {"id": s["id"], "title": s["title"], "pool": s["pool"]}
                    for s in items
                ],
            })
        total = len(subs)
        done = sum(1 for s in subs if s["pool"] == "done")
        return {
            "id": goal_id,
            "title": post.metadata.get("title", goal_id),
            "kind": post.metadata.get("kind"),
            "source": post.metadata.get("source"),
            "status": post.metadata.get("status", "active"),
            "progress": f"{done}/{total}",
            "subgoals": subgoals,
        }

    # ---------- progression ----------

    def promote_next(self, goal_id: str) -> dict[str, Any]:
        """Bring the next staged subgoal's subtasks (still in the reservoir)
        into the active pool. Call when a subgoal is done and you're ready for
        the next one."""
        plan = self.plan(goal_id)
        moved = []
        for sg in plan["subgoals"]:
            reservoir_ids = [s["id"] for s in sg["subtasks"] if s["pool"] == "reservoir"]
            if reservoir_ids:
                for tid in reservoir_ids:
                    try:
                        moved.append(self.stack.move(tid, "active"))
                    except ValueError:
                        break  # active pool full; stop promoting
                break  # only promote the earliest staged subgoal
        return {"promoted": [m["id"] for m in moved], "plan": self.plan(goal_id)}

    def complete_goal(self, goal_id: str) -> dict[str, Any]:
        post = frontmatter.load(self._goal_path(goal_id))
        post.metadata["status"] = "done"
        post.metadata["completed_at"] = dt.datetime.now().isoformat(timespec="seconds")
        self._save_goal(goal_id, post)
        return self.plan(goal_id)

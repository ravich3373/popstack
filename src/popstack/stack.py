"""The task stack: markdown files in the vault, weighted-random pops.

Layout under <vault>/Stack/:
    active/      tasks eligible for pops (capped at ACTIVE_LIMIT)
    reservoir/   someday / not-now (capture overflow lands here)
    done/        completed, kept for history

Each task is one markdown file with YAML frontmatter. Wikilinks in the body
connect tasks to vault knowledge, which is what makes grounding native.

Pop semantics (ported from Taskwarrior's urgency model into sampling
weights — deterministic ranking would always serve the same task; uniform
random starves urgent ones):
    weight = 1.0                                  (base: everything drawable)
           + up to 12.0 as a deadline approaches/passes
           + {high: 6.0, medium: 3.0, low: 0.0}   (priority)
           + up to 2.0 scaling with age, capped   (stale tasks surface MORE,
                                                   never decay — bounded so
                                                   one ancient task can't
                                                   dominate)
Tasks under a park-cooldown are excluded entirely.
"""

import datetime as dt
import hashlib
import random
import re
from pathlib import Path
from typing import Any

import frontmatter

from . import config

PRIORITY_WEIGHT = {"high": 6.0, "medium": 3.0, "low": 0.0}
DUE_MAX = 12.0
DUE_RAMP_DAYS = 14.0  # weight starts ramping two weeks out
AGE_MAX = 2.0
AGE_CAP_DAYS = 365.0

POOLS = ("active", "reservoir", "done")


def _now() -> dt.datetime:
    return dt.datetime.now()


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return slug or "task"


# Task ids are `<slug>-<6 hex>` (see capture); a bare slug charset. Anything
# else is rejected so a caller-supplied id can never escape the Stack dir.
_ID_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


def _parse_dt(value: Any) -> dt.datetime | None:
    """Parse a date/datetime from frontmatter. Returns None for anything
    unparseable (e.g. a hand-typed 'next friday') so one malformed file can't
    crash pop()/list/health for the whole pool."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    try:
        return dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None


class Stack:
    def __init__(self, root: Path | None = None, active_limit: int | None = None):
        self.root = root or config.stack_root()
        self.active_limit = active_limit or config.ACTIVE_LIMIT
        for pool in POOLS:
            (self.root / pool).mkdir(parents=True, exist_ok=True)

    # ---------- file plumbing ----------

    def _path(self, task_id: str) -> Path:
        # Validate at this single chokepoint so every caller (park/complete/
        # move/ground) is covered against path traversal via a crafted id.
        if not _ID_RE.fullmatch(task_id or ""):
            raise FileNotFoundError(f"no task with id '{task_id}'")
        for pool in POOLS:
            p = self.root / pool / f"{task_id}.md"
            if p.exists():
                # belt-and-suspenders: never return a path outside the pool dir
                if p.resolve().parent != (self.root / pool).resolve():
                    raise FileNotFoundError(f"no task with id '{task_id}'")
                return p
        raise FileNotFoundError(f"no task with id '{task_id}'")

    def _pool_of(self, path: Path) -> str:
        return path.parent.name

    def _load(self, path: Path) -> frontmatter.Post:
        return frontmatter.load(path)

    def _save(self, path: Path, post: frontmatter.Post) -> None:
        path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")

    def _tasks_in(self, pool: str) -> list[tuple[Path, frontmatter.Post]]:
        return [
            (p, self._load(p))
            for p in sorted((self.root / pool).glob("*.md"))
            if not p.name.startswith("_")
        ]

    @staticmethod
    def _summary(path: Path, post: frontmatter.Post, **extra: Any) -> dict[str, Any]:
        meta = post.metadata
        out = {
            "id": path.stem,
            "pool": path.parent.name,
            "title": meta.get("title", path.stem),
            "priority": meta.get("priority", "medium"),
            "due": str(meta["due"]) if meta.get("due") else None,
            "pushes": meta.get("pushes", 0),
            "next_action": meta.get("next_action"),
            "tags": meta.get("tags", []),
            "est_minutes": meta.get("est_minutes"),
            "created": str(meta.get("created", "")),
            "goal": meta.get("goal"),
            "subgoal": meta.get("subgoal"),
            "deps": meta.get("deps", []),
        }
        out.update(extra)
        return out

    # ---------- capture ----------

    def capture(
        self,
        title: str,
        body: str = "",
        tags: list[str] | None = None,
        due: str | None = None,
        priority: str = "medium",
        est_minutes: int | None = None,
        pool: str = "active",
        goal: str | None = None,
        subgoal: str | None = None,
        deps: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a subtask. If the active pool is full, it lands in the
        reservoir. A subtask may belong to a goal/subgoal and depend on other
        subtasks (by id) that must complete before it becomes eligible."""
        if priority not in PRIORITY_WEIGHT:
            raise ValueError(f"priority must be one of {sorted(PRIORITY_WEIGHT)}")
        if pool not in ("active", "reservoir"):
            raise ValueError("pool must be 'active' or 'reservoir'")

        overflowed = False
        if pool == "active" and len(self._tasks_in("active")) >= self.active_limit:
            pool, overflowed = "reservoir", True

        now = _now()
        digest = hashlib.sha1(f"{title}{now.isoformat()}".encode()).hexdigest()[:6]
        task_id = f"{_slugify(title)}-{digest}"

        meta: dict[str, Any] = {
            "title": title,
            "created": now.isoformat(timespec="seconds"),
            "priority": priority,
            "pushes": 0,
        }
        if due:
            meta["due"] = due
        if tags:
            meta["tags"] = tags
        if est_minutes:
            meta["est_minutes"] = est_minutes
        if goal:
            meta["goal"] = goal
        if subgoal:
            meta["subgoal"] = subgoal
        if deps:
            meta["deps"] = list(deps)

        post = frontmatter.Post(body, **meta)
        path = self.root / pool / f"{task_id}.md"
        self._save(path, post)
        return self._summary(path, post, overflowed_to_reservoir=overflowed)

    # ---------- weighting & pop ----------

    def _done_ids(self) -> set[str]:
        return {p.stem for p, _ in self._tasks_in("done")}

    def _weight(self, post: frontmatter.Post, now: dt.datetime) -> dict[str, float]:
        meta = post.metadata
        # Deadlines are optional for learning goals (ADR-008 §5); the term stays
        # for the rare dated task but contributes 0 when no due is set.
        due_term = 0.0
        due = _parse_dt(meta.get("due"))
        if due:
            days_left = (due - now).total_seconds() / 86400
            due_term = DUE_MAX * min(max((DUE_RAMP_DAYS - days_left) / DUE_RAMP_DAYS, 0.0), 1.0)

        priority_term = PRIORITY_WEIGHT.get(str(meta.get("priority", "medium")), 3.0)

        # Aging (ADR-011): boost only *un-offered* tasks (never drawn, never
        # parked) — a "forgotten" task should resurface; an "avoided" one (it's
        # been offered and pushed back) should NOT be nagged louder.
        pushes = int(meta.get("pushes", 0))
        offered = pushes > 0 or bool(meta.get("last_popped"))
        age_term = 0.0
        if not offered:
            created = _parse_dt(meta.get("created"))
            if created:
                age_days = max((now - created).total_seconds() / 86400, 0.0)
                age_term = AGE_MAX * min(age_days / AGE_CAP_DAYS, 1.0)

        base = 1.0 + due_term + priority_term + age_term
        # Pushes penalty (ADR-011): a task parked many times draws *less*, so an
        # avoided task fades from the rotation toward triage instead of dominating.
        penalty = 1.0 + 0.4 * pushes
        total = base / penalty
        return {
            "total": total, "due": due_term, "priority": priority_term,
            "age": age_term, "pushes_penalty": penalty,
        }

    def _eligible(self, now: dt.datetime) -> list[tuple[Path, frontmatter.Post]]:
        done = self._done_ids()
        out = []
        for path, post in self._tasks_in("active"):
            cooldown = _parse_dt(post.metadata.get("cooldown_until"))
            if cooldown and cooldown > now:
                continue
            # dependency gate: every listed dep must be complete (in done/)
            deps = post.metadata.get("deps") or []
            if any(d not in done for d in deps):
                continue
            out.append((path, post))
        return out

    # Resume bias (ADR-009): the next draw should usually *continue the current
    # thread*, not jump to an unrelated goal — random switching across domains is
    # the costly kind of task-switch. Same-goal eligible tasks get this multiplier.
    RESUME_BIAS = 4.0

    def _current_goal(self) -> str | None:
        """Infer the thread to continue: the goal of the most recently popped
        active task (the one you were just working)."""
        best_goal, best_when = None, ""
        for _, post in self._tasks_in("active"):
            lp = str(post.metadata.get("last_popped") or "")
            if lp > best_when and post.metadata.get("goal"):
                best_when, best_goal = lp, post.metadata["goal"]
        return best_goal

    def draw(
        self,
        now: dt.datetime | None = None,
        rng: random.Random | None = None,
        current_goal: str | None = None,
        resume: bool = True,
    ) -> dict[str, Any]:
        """Hand over the next subtask. Weighted sample over eligible (uncooled,
        dependency-satisfied) active subtasks, biased to continue the current
        goal/thread (resume=True). Stamps last_popped; finish with complete()
        or park(). Does not remove the task."""
        now = now or _now()
        rng = rng or random.Random()
        eligible = self._eligible(now)
        if not eligible:
            raise LookupError(
                "nothing eligible to draw (active pool empty, all cooling down, "
                "or all blocked by incomplete dependencies)"
            )

        thread = current_goal if current_goal is not None else (self._current_goal() if resume else None)
        weights = [self._weight(post, now) for _, post in eligible]
        sample = []
        for (_, post), w in zip(eligible, weights):
            biased = w["total"] * (self.RESUME_BIAS if thread and post.metadata.get("goal") == thread else 1.0)
            sample.append(biased)
        idx = rng.choices(range(len(eligible)), weights=sample, k=1)[0]
        path, post = eligible[idx]

        # last_popped is user-facing history (rendered in Obsidian) and feeds the
        # resume-thread inference above. Single-writer model, no locking (ADR-001).
        post.metadata["last_popped"] = now.isoformat(timespec="seconds")
        self._save(path, post)
        return self._summary(
            path,
            post,
            body=post.content.strip(),
            weight=round(sample[idx], 2),
            weight_breakdown={k: round(v, 2) for k, v in weights[idx].items() if k != "total"},
            resumed_thread=thread,
            pool_size=len(eligible),
        )

    # backwards-compatible alias (the tool/UI now says "draw")
    def pop(self, now: dt.datetime | None = None, rng: random.Random | None = None) -> dict[str, Any]:
        return self.draw(now=now, rng=rng, resume=False)

    # ---------- park / complete / move ----------

    def park(
        self,
        task_id: str,
        next_action: str,
        cooldown_hours: float | None = None,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        """Push a task back. A specific next action is mandatory — bare dumps
        don't offload the goal (Masicampo & Baumeister 2011)."""
        if not next_action or not next_action.strip():
            raise ValueError("park requires a specific one-line next_action")
        now = now or _now()
        hours = config.DEFAULT_COOLDOWN_HOURS if cooldown_hours is None else cooldown_hours

        path = self._path(task_id)
        post = self._load(path)
        post.metadata["pushes"] = int(post.metadata.get("pushes", 0)) + 1
        post.metadata["next_action"] = next_action.strip()
        post.metadata["cooldown_until"] = (now + dt.timedelta(hours=hours)).isoformat(
            timespec="seconds"
        )
        stamp = now.isoformat(timespec="seconds")
        post.content = (post.content.rstrip() + f"\n\n- parked {stamp} → next: {next_action.strip()}").lstrip()
        self._save(path, post)
        return self._summary(path, post, cooldown_until=post.metadata["cooldown_until"])

    def complete(self, task_id: str, note: str = "", now: dt.datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        path = self._path(task_id)
        if self._pool_of(path) == "done":
            # already completed — re-completing must not write-then-delete the
            # same file (that would destroy the record). Return the existing one.
            post = self._load(path)
            return self._summary(path, post, completed_at=post.metadata.get("completed_at"))
        post = self._load(path)
        post.metadata["completed_at"] = now.isoformat(timespec="seconds")
        if note:
            post.content = (post.content.rstrip() + f"\n\n- done: {note}").lstrip()
        dest = self.root / "done" / path.name
        # write metadata to the source, then move atomically (no save+unlink
        # window that could leave the task in both pools after a crash).
        self._save(path, post)
        path.replace(dest)
        return self._summary(dest, post, completed_at=post.metadata["completed_at"])

    def move(self, task_id: str, to: str) -> dict[str, Any]:
        """Promote (→active) or shelve (→reservoir)."""
        if to not in ("active", "reservoir"):
            raise ValueError("to must be 'active' or 'reservoir'")
        path = self._path(task_id)
        if self._pool_of(path) == to:
            return self._summary(path, self._load(path))
        if to == "active" and len(self._tasks_in("active")) >= self.active_limit:
            raise ValueError(
                f"active pool is at its limit ({self.active_limit}); "
                "complete or shelve something first"
            )
        dest = self.root / to / path.name
        path.rename(dest)
        return self._summary(dest, self._load(dest))

    # ---------- views ----------

    def list_pool(self, pool: str = "active", now: dt.datetime | None = None) -> list[dict[str, Any]]:
        if pool not in POOLS:
            raise ValueError(f"pool must be one of {POOLS}")
        now = now or _now()
        out = []
        for path, post in self._tasks_in(pool):
            w = self._weight(post, now) if pool == "active" else None
            cooldown = _parse_dt(post.metadata.get("cooldown_until"))
            out.append(
                self._summary(
                    path,
                    post,
                    weight=round(w["total"], 2) if w else None,
                    cooling_down=bool(cooldown and cooldown > now),
                )
            )
        if pool == "active":
            out.sort(key=lambda t: -(t["weight"] or 0))
        return out

    def health(self, now: dt.datetime | None = None) -> dict[str, Any]:
        now = now or _now()
        active = self.list_pool("active", now)
        stale = [
            t for t in active
            if t["pushes"] >= 3
            or (t["created"] and (now - _parse_dt(t["created"])).days > 30)
        ]
        overdue = [
            t for t in active
            if t["due"] and _parse_dt(t["due"]) and _parse_dt(t["due"]) < now
        ]
        return {
            "active": len(active),
            "active_limit": self.active_limit,
            "reservoir": len(self._tasks_in("reservoir")),
            "done": len(self._tasks_in("done")),
            "overdue": overdue,
            "stale": stale,
        }

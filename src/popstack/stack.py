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


def _parse_dt(value: Any) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time())
    return dt.datetime.fromisoformat(str(value))


class Stack:
    def __init__(self, root: Path | None = None, active_limit: int | None = None):
        self.root = root or config.stack_root()
        self.active_limit = active_limit or config.ACTIVE_LIMIT
        for pool in POOLS:
            (self.root / pool).mkdir(parents=True, exist_ok=True)

    # ---------- file plumbing ----------

    def _path(self, task_id: str) -> Path:
        for pool in POOLS:
            p = self.root / pool / f"{task_id}.md"
            if p.exists():
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
    ) -> dict[str, Any]:
        """Create a task. If the active pool is full, it lands in the reservoir."""
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

        post = frontmatter.Post(body, **meta)
        path = self.root / pool / f"{task_id}.md"
        self._save(path, post)
        return self._summary(path, post, overflowed_to_reservoir=overflowed)

    # ---------- weighting & pop ----------

    def _weight(self, post: frontmatter.Post, now: dt.datetime) -> dict[str, float]:
        meta = post.metadata
        due_term = 0.0
        due = _parse_dt(meta.get("due"))
        if due:
            days_left = (due - now).total_seconds() / 86400
            due_term = DUE_MAX * min(max((DUE_RAMP_DAYS - days_left) / DUE_RAMP_DAYS, 0.0), 1.0)

        priority_term = PRIORITY_WEIGHT.get(str(meta.get("priority", "medium")), 3.0)

        age_term = 0.0
        created = _parse_dt(meta.get("created"))
        if created:
            age_days = max((now - created).total_seconds() / 86400, 0.0)
            age_term = AGE_MAX * min(age_days / AGE_CAP_DAYS, 1.0)

        total = 1.0 + due_term + priority_term + age_term
        return {"total": total, "due": due_term, "priority": priority_term, "age": age_term}

    def _eligible(self, now: dt.datetime) -> list[tuple[Path, frontmatter.Post]]:
        out = []
        for path, post in self._tasks_in("active"):
            cooldown = _parse_dt(post.metadata.get("cooldown_until"))
            if cooldown and cooldown > now:
                continue
            out.append((path, post))
        return out

    def pop(self, now: dt.datetime | None = None, rng: random.Random | None = None) -> dict[str, Any]:
        """Weighted-random pop from the active pool. Does not remove the task —
        it stamps last_popped; you finish with complete() or park()."""
        now = now or _now()
        rng = rng or random.Random()
        eligible = self._eligible(now)
        if not eligible:
            raise LookupError(
                "nothing eligible to pop (active pool empty or everything cooling down)"
            )

        weights = [self._weight(post, now) for _, post in eligible]
        idx = rng.choices(range(len(eligible)), weights=[w["total"] for w in weights], k=1)[0]
        path, post = eligible[idx]

        post.metadata["last_popped"] = now.isoformat(timespec="seconds")
        self._save(path, post)
        return self._summary(
            path,
            post,
            body=post.content.strip(),
            weight=round(weights[idx]["total"], 2),
            weight_breakdown={k: round(v, 2) for k, v in weights[idx].items() if k != "total"},
            pool_size=len(eligible),
        )

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
        post = self._load(path)
        post.metadata["completed_at"] = now.isoformat(timespec="seconds")
        if note:
            post.content = (post.content.rstrip() + f"\n\n- done: {note}").lstrip()
        dest = self.root / "done" / path.name
        self._save(dest, post)
        path.unlink()
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

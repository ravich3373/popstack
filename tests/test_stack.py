import datetime as dt
import random

import pytest

from popstack.stack import Stack

NOW = dt.datetime(2026, 6, 10, 9, 0, 0)


@pytest.fixture
def stack(tmp_path):
    return Stack(root=tmp_path / "Stack", active_limit=3)


def test_capture_creates_active_task(stack):
    t = stack.capture("Read Rohrer interleaving paper", tags=["math"], priority="high")
    assert t["pool"] == "active"
    assert t["priority"] == "high"
    assert not t["overflowed_to_reservoir"]
    assert (stack.root / "active" / f"{t['id']}.md").exists()


def test_capture_overflows_to_reservoir_at_limit(stack):
    for i in range(3):
        stack.capture(f"task {i}")
    t = stack.capture("one too many")
    assert t["pool"] == "reservoir"
    assert t["overflowed_to_reservoir"]


def test_pop_returns_task_with_weight_breakdown(stack):
    stack.capture("solo task")
    popped = stack.pop(now=NOW, rng=random.Random(7))
    assert popped["title"] == "solo task"
    assert popped["weight"] >= 1.0
    assert set(popped["weight_breakdown"]) == {"due", "priority", "age"}


def test_pop_empty_raises(stack):
    with pytest.raises(LookupError):
        stack.pop(now=NOW)


def test_park_requires_next_action(stack):
    t = stack.capture("needs a plan")
    with pytest.raises(ValueError):
        stack.park(t["id"], next_action="   ")


def test_park_sets_cooldown_and_excludes_from_pop(stack):
    t = stack.capture("parked task")
    parked = stack.park(t["id"], next_action="re-derive eq 3", cooldown_hours=4, now=NOW)
    assert parked["pushes"] == 1
    assert parked["next_action"] == "re-derive eq 3"
    with pytest.raises(LookupError):  # only task is cooling down
        stack.pop(now=NOW + dt.timedelta(hours=1))
    assert stack.pop(now=NOW + dt.timedelta(hours=5))["id"] == t["id"]


def test_weighting_prefers_overdue_high_priority(stack):
    fresh = stack.capture("fresh low", priority="low")
    urgent = stack.capture("overdue high", priority="high", due="2026-06-01")
    counts = {fresh["id"]: 0, urgent["id"]: 0}
    rng = random.Random(42)
    for _ in range(300):
        counts[stack.pop(now=NOW, rng=rng)["id"]] += 1
    # urgent: 1 + 12 (overdue, capped) + 6 = 19 vs fresh: 1 → ~95/5 split
    assert counts[urgent["id"]] > counts[fresh["id"]] * 5


def test_age_term_grows_but_caps(stack):
    t = stack.capture("aging task")
    post = stack._load(stack._path(t["id"]))
    young = stack._weight(post, NOW + dt.timedelta(days=30))
    old = stack._weight(post, NOW + dt.timedelta(days=400))
    assert 0 < young["age"] < old["age"] <= 2.0


def test_complete_moves_to_done(stack):
    t = stack.capture("finish me")
    done = stack.complete(t["id"], note="shipped", now=NOW)
    assert done["pool"] == "done"
    assert not (stack.root / "active" / f"{t['id']}.md").exists()
    assert (stack.root / "done" / f"{t['id']}.md").exists()


def test_move_respects_active_limit(stack):
    parked = stack.capture("in reservoir", pool="reservoir")
    for i in range(3):
        stack.capture(f"filler {i}")
    with pytest.raises(ValueError):
        stack.move(parked["id"], "active")
    stack.complete(stack.list_pool("active")[0]["id"])
    assert stack.move(parked["id"], "active")["pool"] == "active"


def test_health_flags_overdue_and_stale(stack):
    stack.capture("overdue", due="2026-06-01")
    t = stack.capture("pushed around")
    for i in range(3):
        stack.park(t["id"], next_action=f"step {i}", cooldown_hours=0, now=NOW)
    h = stack.health(now=NOW)
    assert [x["title"] for x in h["overdue"]] == ["overdue"]
    assert [x["title"] for x in h["stale"]] == ["pushed around"]
    assert h["active"] == 2


# ---- regression tests for the 2026-06-10 review fixes ----

@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "../escape", "a/b", "Foo Bar", "", ".."])
def test_path_traversal_rejected(stack, bad_id):
    # crafted ids must never resolve outside the pool dirs (critical finding #1)
    with pytest.raises(FileNotFoundError):
        stack._path(bad_id)


def test_traversal_cannot_delete_outside_file(stack, tmp_path):
    victim = tmp_path / "victim.md"
    victim.write_text("important", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        stack.complete("../../victim")
    assert victim.exists()  # untouched


def test_double_complete_preserves_record(stack):
    t = stack.capture("finish once")
    stack.complete(t["id"], now=NOW)
    again = stack.complete(t["id"], now=NOW)  # must not self-destruct (#2)
    assert again["pool"] == "done"
    assert (stack.root / "done" / f"{t['id']}.md").exists()


def test_malformed_date_does_not_poison_pool(stack):
    good = stack.capture("good task")
    bad = stack.capture("bad date task")
    # simulate a hand-edited bad due date on the phone
    p = stack._path(bad["id"])
    p.write_text(p.read_text().replace("---\n", "---\ndue: next friday\n", 1), encoding="utf-8")
    # pop/list/health must still work for the rest of the pool (#3)
    assert stack.pop(now=NOW, rng=random.Random(1))["id"] in {good["id"], bad["id"]}
    assert len(stack.list_pool("active", NOW)) == 2
    assert stack.health(NOW)["active"] == 2

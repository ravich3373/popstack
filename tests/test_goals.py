import pytest

from popstack import templates
from popstack.goals import Goals
from popstack.stack import Stack


@pytest.fixture
def goals(tmp_path):
    return Goals(Stack(root=tmp_path / "Stack", active_limit=50))


# ---- templates ----

def test_known_kinds_have_templates():
    assert set(templates.kinds()) == {
        "paper", "codebase", "language", "algorithm", "system-design"
    }
    assert templates.get_template("paper")[0]["subgoal"] == "Skim & context"


def test_aliases_resolve():
    assert templates.resolve_kind("arxiv") == "paper"
    assert templates.resolve_kind("repo") == "codebase"
    assert templates.resolve_kind("nonsense") is None
    assert templates.get_template("nonsense") is None


# ---- goal creation ----

def test_create_from_paper_template_stages_by_subgoal(goals):
    plan = goals.create("Understand pi0", "paper", source="zotero:ABCD1234")
    assert plan["kind"] == "paper"
    assert plan["source"] == "zotero:ABCD1234"
    assert [sg["subgoal"] for sg in plan["subgoals"]][0] == "Skim & context"
    # first subgoal active, the rest staged in the reservoir
    assert all(s["pool"] == "active" for s in plan["subgoals"][0]["subtasks"])
    assert all(s["pool"] == "reservoir" for s in plan["subgoals"][1]["subtasks"])


def test_unknown_kind_without_outline_raises(goals):
    with pytest.raises(ValueError):
        goals.create("weird thing", "quantum-basket-weaving")


def test_agent_outline_fallback(goals):
    outline = [
        {"subgoal": "Part one", "subtasks": ["a", "b"]},
        {"subgoal": "Part two", "subtasks": ["c"]},
    ]
    plan = goals.create("Custom topic", "whatever", outline=outline)
    assert [sg["subgoal"] for sg in plan["subgoals"]] == ["Part one", "Part two"]
    assert len(plan["subgoals"][0]["subtasks"]) == 2
    assert plan["progress"] == "0/3"


def test_promote_next_brings_next_subgoal_active(goals):
    plan = goals.create("topic", "x", outline=[
        {"subgoal": "S1", "subtasks": ["a"]},
        {"subgoal": "S2", "subtasks": ["b", "c"]},
    ])
    gid = plan["id"]
    assert all(s["pool"] == "reservoir" for s in goals.plan(gid)["subgoals"][1]["subtasks"])
    res = goals.promote_next(gid)
    assert len(res["promoted"]) == 2
    assert all(s["pool"] == "active" for s in goals.plan(gid)["subgoals"][1]["subtasks"])


def test_progress_and_subgoal_completion(goals):
    plan = goals.create("topic", "x", outline=[{"subgoal": "S1", "subtasks": ["a", "b"]}])
    gid = plan["id"]
    first = goals.plan(gid)["subgoals"][0]["subtasks"][0]["id"]
    goals.stack.complete(first)
    p = goals.plan(gid)
    assert p["progress"] == "1/2"
    assert p["subgoals"][0]["progress"] == "1/2"
    assert not p["subgoals"][0]["complete"]


def test_list_goals(goals):
    goals.create("Goal A", "paper")
    goals.create("Goal B", "algorithm")
    listed = {g["title"]: g for g in goals.list_goals()}
    assert set(listed) == {"Goal A", "Goal B"}
    assert listed["Goal A"]["kind"] == "paper"

import json

import pytest

from popstack import usage
from popstack.stack import Stack


@pytest.fixture
def stack(tmp_path):
    return Stack(root=tmp_path / "Stack", active_limit=20)


def test_record_attributes_to_in_focus_task(stack):
    a = stack.capture("step a", goal="g1")
    stack.capture("step b", goal="g1")
    drawn = stack.draw()  # a or b becomes in-focus (last_popped)
    r = stack.record_usage(1000, 250)
    assert r["id"] == drawn["id"]
    assert r["tokens_in"] == 1000 and r["tokens_out"] == 250
    # accumulates
    stack.record_usage(500, 100, task_id=drawn["id"])
    rep = stack.usage_report()
    me = next(t for t in rep["per_task"] if t["id"] == drawn["id"])
    assert me["tokens_in"] == 1500 and me["tokens_out"] == 350 and me["turns"] == 2


def test_record_without_focus_errors(stack):
    stack.capture("never drawn")
    assert "error" in stack.record_usage(100, 100)  # nothing drawn yet


def test_usage_report_rolls_up_per_goal(stack):
    a = stack.capture("a", goal="paperX")
    b = stack.capture("b", goal="paperX")
    stack.record_usage(100, 10, task_id=a["id"])
    stack.record_usage(200, 20, task_id=b["id"])
    rep = stack.usage_report()
    assert rep["total"] == {"tokens_in": 300, "tokens_out": 30, "tokens": 330}
    pg = {g["goal"]: g for g in rep["per_goal"]}
    assert pg["paperX"]["tokens_in"] == 300 and pg["paperX"]["tokens_out"] == 30


def test_transcript_sums_latest_turn(tmp_path):
    # a transcript: user, assistant(2 calls this turn), then earlier turn ignored
    rows = [
        {"type": "user", "message": {"content": "old"}},
        {"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": 999, "output_tokens": 999}}},
        {"type": "user", "message": {"content": "new turn"}},
        {"type": "assistant", "message": {"model": "claude-x",
            "usage": {"input_tokens": 1000, "cache_read_input_tokens": 200, "output_tokens": 50}}},
        {"type": "assistant", "message": {"model": "claude-x",
            "usage": {"input_tokens": 1200, "output_tokens": 80}}},
    ]
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    tin, tout, model = usage.turn_usage_from_transcript(str(p))
    # only the last turn: (1000+200) + 1200 = 2400 in ; 50 + 80 = 130 out
    assert tin == 2400 and tout == 130 and model == "claude-x"

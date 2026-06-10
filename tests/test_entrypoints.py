"""The [project.scripts] entry points must import and be callable (#22)."""

import importlib

import pytest


@pytest.mark.parametrize(
    "module,attr",
    [("popstack.server", "main"), ("popstack.today", "main")],
)
def test_entry_point_resolves(module, attr):
    mod = importlib.import_module(module)
    assert callable(getattr(mod, attr))

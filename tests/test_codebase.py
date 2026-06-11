import subprocess

import pytest

from popstack import codebase


def _make_repo(root):
    (root / "cmd").mkdir(parents=True)
    (root / "internal").mkdir()
    (root / "go.mod").write_text("module example.com/x\n")
    (root / "cmd" / "main.go").write_text("package main\nfunc main() {}\n")
    (root / "internal" / "lib.go").write_text("package internal\n\nvar X = 1\n")
    (root / "README.md").write_text("# Example\n")
    (root / "util.py").write_text("def f():\n    return 1\n")


def test_map_repo_detects_languages_build_entrypoints(tmp_path):
    _make_repo(tmp_path)
    m = codebase.map_repo(str(tmp_path))
    assert m["primary_language"] == "Go"
    langs = {l["language"] for l in m["languages"]}
    assert {"Go", "Python"} <= langs
    assert m["build_system"] == {"go.mod": "Go modules"}
    assert "cmd/main.go" in m["entry_points"]
    assert m["readme"] == "README.md"
    assert "go.mod" in m["top_level"]


def test_map_repo_missing_path(tmp_path):
    assert "error" in codebase.map_repo(str(tmp_path / "nope"))


def test_map_repo_skips_vendor_and_git(tmp_path):
    _make_repo(tmp_path)
    (tmp_path / "node_modules" / "junk").mkdir(parents=True)
    (tmp_path / "node_modules" / "junk" / "a.js").write_text("var x=1\n")
    m = codebase.map_repo(str(tmp_path))
    assert "JavaScript" not in {l["language"] for l in m["languages"]}


def test_clone_rejects_bad_url():
    assert "error" in codebase.clone_repo("not a url")


def test_clone_local_repo(tmp_path, monkeypatch):
    # git clone works on a local path; make a real source repo and clone it
    src = tmp_path / "src"
    _make_repo(src)
    subprocess.run(["git", "init", "-q"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "add", "-A"], cwd=src, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "x"], cwd=src, check=True)
    monkeypatch.setattr(codebase.config, "WORKSPACE", tmp_path / "ws")
    monkeypatch.setattr(codebase, "_REPO_RE", __import__("re").compile(r".+"))
    res = codebase.clone_repo(str(src))
    assert res.get("cloned")
    assert (tmp_path / "ws" / "src" / "go.mod").exists()

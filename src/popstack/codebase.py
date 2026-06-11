"""Codebase support: acquire a repo and map its structure so a "understand this
codebase" goal (templates.py kind=codebase) is grounded in the real repo, not a
generic skeleton. The agent then reads the code (its own tools) and writes notes
(notes.py).

Acquisition is optional — in Claude Code the agent can `git clone` itself; this
provides a consistent workspace + a structural map either way.
"""

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from . import config

# extension -> language
LANGS = {
    ".py": "Python", ".pyi": "Python", ".go": "Go", ".rs": "Rust",
    ".c": "C", ".h": "C/C++ header", ".hpp": "C++ header", ".cc": "C++",
    ".cpp": "C++", ".cxx": "C++", ".java": "Java", ".kt": "Kotlin",
    ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".scala": "Scala", ".sh": "Shell", ".lua": "Lua", ".ml": "OCaml",
    ".hs": "Haskell", ".clj": "Clojure", ".ex": "Elixir", ".zig": "Zig",
    ".cu": "CUDA", ".proto": "Protobuf", ".fbs": "FlatBuffers",
}
BUILD_FILES = {
    "pyproject.toml": "Python (PEP 621)", "setup.py": "Python (setuptools)",
    "requirements.txt": "Python (pip)", "package.json": "Node/JS",
    "Cargo.toml": "Rust (cargo)", "go.mod": "Go modules",
    "CMakeLists.txt": "CMake", "Makefile": "Make", "BUILD": "Bazel",
    "BUILD.bazel": "Bazel", "WORKSPACE": "Bazel", "MODULE.bazel": "Bazel",
    "build.gradle": "Gradle", "pom.xml": "Maven", "Dockerfile": "Docker",
}
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
              "build", "target", ".mypy_cache", ".pytest_cache", "vendor"}
_REPO_RE = re.compile(r"^(https?://|git@)[\w./:@~-]+$")


def clone_repo(url: str, dest: str | None = None, depth: int = 1) -> dict[str, Any]:
    """Shallow-clone a repo into the workspace (config.WORKSPACE). Returns the
    local path. If it already exists, returns that (does not re-clone)."""
    url = url.strip()
    if not _REPO_RE.match(url):
        return {"error": f"not a valid git url: {url!r}"}
    name = re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1]) or "repo"
    target = Path(dest).expanduser() if dest else (config.WORKSPACE / name)
    if target.exists():
        return {"path": str(target), "already_present": True}
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "clone", "--depth", str(depth), url, str(target)],
            capture_output=True, text=True, timeout=300, check=True,
        )
    except subprocess.CalledProcessError as e:
        return {"error": f"git clone failed: {e.stderr.strip()[:300]}"}
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return {"error": f"git clone failed: {e}"}
    return {"path": str(target), "cloned": True}


def _iter_files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            yield p


def map_repo(path: str, max_entrypoints: int = 12) -> dict[str, Any]:
    """Summarize a local repo: languages by line count, build system, likely
    entry points, top-level layout, and the README — enough to ground a
    codebase decomposition."""
    root = Path(path).expanduser()
    if not root.exists():
        return {"error": f"path does not exist: {root}"}

    lang_lines: Counter = Counter()
    file_count = 0
    build = {}
    entrypoints = []
    readme = None

    for f in _iter_files(root):
        file_count += 1
        rel = f.relative_to(root)
        if f.name in BUILD_FILES:
            build[str(rel)] = BUILD_FILES[f.name]
        if readme is None and f.name.lower().startswith("readme"):
            readme = str(rel)
        lang = LANGS.get(f.suffix)
        if lang:
            try:
                lang_lines[lang] += sum(1 for _ in f.open("rb"))
            except OSError:
                pass
        # heuristic entry points
        stem = f.stem.lower()
        if (stem in {"main", "index", "app", "cli", "__main__", "server"}
                or rel.parts[:1] in (("cmd",), ("bin",))) and lang:
            if len(entrypoints) < max_entrypoints:
                entrypoints.append(str(rel))

    top = sorted(
        p.name + ("/" if p.is_dir() else "")
        for p in root.iterdir() if p.name not in _SKIP_DIRS
    )
    languages = [{"language": l, "lines": n} for l, n in lang_lines.most_common()]
    return {
        "path": str(root),
        "files": file_count,
        "languages": languages,
        "primary_language": languages[0]["language"] if languages else None,
        "build_system": build or None,
        "entry_points": entrypoints,
        "readme": readme,
        "top_level": top,
    }

import pytest

from popstack import notes


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = tmp_path / "kb"
    v.mkdir()
    monkeypatch.setattr(notes.config, "NOTES_VAULT", v)
    monkeypatch.setattr(notes.config, "NOTES_DIR", "popstack")
    monkeypatch.setattr(notes.config, "VAULTS", [v])
    return v


def test_write_note_creates_with_frontmatter(vault):
    res = notes.write_note(
        "Flow Matching", "The continuous-time limit of diffusion.",
        tags=["ml", "generative"], related=["DDPM", "[[Optimal Transport]]"],
        source="zotero://select/library/items/PI0KEY",
    )
    assert res["written"]
    p = vault / "popstack" / "flow-matching.md"
    assert p.exists()
    text = p.read_text()
    assert "title: Flow Matching" in text
    assert "created:" in text
    assert "[[DDPM]]" in text and "[[Optimal Transport]]" in text
    assert "zotero://select" in text


def test_preview_does_not_write(vault):
    res = notes.write_note("Temp", "body", preview=True)
    assert res["preview"] and "content" in res
    assert not (vault / "popstack" / "temp.md").exists()


def test_no_clobber(vault):
    notes.write_note("Dup", "first")
    res = notes.write_note("Dup", "second")
    assert "error" in res
    assert (vault / "popstack" / "dup.md").read_text().count("first") == 1


def test_refuses_outside_vault(vault, tmp_path):
    res = notes.write_note("Escape", "x", folder="../../../../tmp/evil")
    assert "error" in res and "outside" in res["error"]


def test_append_snippet_under_heading(vault):
    notes.write_note("Sampler", "How the sampler works.")
    r = notes.append_snippet("Sampler", "def step(x):\n    return x", lang="python",
                             source="repo/sampler.py:12")
    assert r["appended"]
    text = (vault / "popstack" / "sampler.md").read_text()
    assert "## Snippets" in text and "```python" in text and "def step" in text
    assert "How the sampler works." in text  # original preserved
    # a second snippet reuses the same heading
    notes.append_snippet("Sampler", "x = 1", lang="python")
    assert (vault / "popstack" / "sampler.md").read_text().count("## Snippets") == 1


def test_append_missing_note_errors(vault):
    assert "error" in notes.append_snippet("nope", "code")


def test_vault_layout_discovers_folders_and_mocs(tmp_path, monkeypatch):
    v = tmp_path / "kb"
    (v / "leetcode" / "Algorithms").mkdir(parents=True)
    (v / "systems" / "cuda").mkdir(parents=True)
    (v / ".obsidian").mkdir()
    (v / "leetcode" / "Algorithms" / "two-sum.md").write_text("x", encoding="utf-8")
    (v / "leetcode" / "00-MOC-Data-Structures.md").write_text("moc", encoding="utf-8")
    (v / "systems" / "cuda" / "streams.md").write_text("x", encoding="utf-8")
    (v / "systems" / "GPU Programming MOC.md").write_text("moc", encoding="utf-8")
    (v / ".obsidian" / "config.md").write_text("ignore", encoding="utf-8")
    monkeypatch.setattr(notes.config, "VAULTS", [v])

    layout = notes.vault_layout("kb")["vaults"][0]
    folder_paths = {f["path"] for f in layout["folders"]}
    assert "leetcode/Algorithms" in folder_paths and "systems/cuda" in folder_paths
    assert not any(f["path"].startswith(".obsidian") for f in layout["folders"])  # hidden skipped
    assert "leetcode/00-MOC-Data-Structures.md" in layout["mocs"]
    assert "systems/GPU Programming MOC.md" in layout["mocs"]


def test_vault_layout_unknown_vault_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(notes.config, "VAULTS", [tmp_path / "kb"])
    assert notes.vault_layout("nope")["vaults"] == []


def test_write_note_into_existing_folder(vault):
    (vault / "systems" / "cuda").mkdir(parents=True)
    res = notes.write_note("CUDA Streams", "Async execution.", folder="systems/cuda")
    assert res["written"]
    assert (vault / "systems" / "cuda" / "cuda-streams.md").exists()


def test_add_to_moc_creates_and_dedupes(vault):
    r1 = notes.add_to_moc("ML MOC", "Flow Matching", note="generative models")
    assert r1["linked"]
    r2 = notes.add_to_moc("ML MOC", "Flow Matching")
    assert r2.get("already_linked")
    moc = (vault / "popstack" / "ml-moc.md").read_text()
    assert moc.count("[[Flow Matching]]") == 1

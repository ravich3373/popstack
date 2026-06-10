"""Tests for the pure parts of grounding (term extraction) and vault search,
including a vault path that contains a colon (review findings #15/#21)."""

import pytest

from popstack import grounding


def test_terms_prioritizes_wikilinks_then_tags_then_title():
    task = {
        "title": "Read the FSRS scheduler paper",
        "body": "see [[spaced repetition]] and [[memory models]]",
        "tags": ["learning"],
    }
    terms = grounding._terms(task)
    assert terms[0] == "spaced repetition"
    assert "memory models" in terms
    assert "learning" in terms
    assert "scheduler" in terms  # title word, length>3, not a stopword
    assert "read" not in [t.lower() for t in terms]  # stopword dropped


def test_terms_dedup_case_insensitive():
    task = {"title": "Spaced repetition", "body": "[[spaced repetition]]", "tags": []}
    terms = [t.lower() for t in grounding._terms(task)]
    assert terms.count("spaced repetition") == 1


def test_vault_search_handles_colon_in_path(tmp_path, monkeypatch):
    # a vault dir name with a colon would corrupt naive "path:lineno:" parsing
    vault = tmp_path / "My: Vault"
    (vault / "notes").mkdir(parents=True)
    (vault / "notes" / "a.md").write_text("the quick brown fox\n", encoding="utf-8")
    monkeypatch.setattr(grounding.config, "VAULTS", [vault])

    hits = grounding.vault_search("brown", limit=5)
    assert any("a.md" in h["file"] and h["line"] == 1 and h["vault"] == "My: Vault" for h in hits)


def test_vault_search_empty_when_vault_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding.config, "VAULTS", [tmp_path / "nope"])
    assert grounding.vault_search("anything") == []


def test_grounding_spans_vaults_and_flags_cross_vault(tmp_path, monkeypatch):
    # a concept living in two vaults is a cross-vault connection candidate
    theory = tmp_path / "formalisms"
    code = tmp_path / "coding"
    theory.mkdir(); code.mkdir()
    (theory / "flow.md").write_text("flow matching is the continuous limit\n", encoding="utf-8")
    (code / "sampler.md").write_text("flow matching sampler implementation\n", encoding="utf-8")
    monkeypatch.setattr(grounding.config, "VAULTS", [theory, code])
    monkeypatch.setattr(grounding.zotero, "search", lambda *a, **k: {"items": []})

    res = grounding.ground({"id": "t1", "title": "understand flow matching", "body": "", "tags": []})
    vaults_hit = {n["vault"] for n in res["vault_notes"]}
    assert {"formalisms", "coding"} <= vaults_hit
    assert any(c["term"] == "matching" and set(c["vaults"]) == {"coding", "formalisms"}
               for c in res["cross_vault_connections"])

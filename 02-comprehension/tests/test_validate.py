"""Unit tests for validate.py. Offline, no API calls.

The tests copy the shipped placeholder set into a temp dir, confirm it passes,
then mutate copies to confirm each rule fails loudly.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import validate  # noqa: E402

PLACEHOLDER = "tarpon-webhook-tiers"


@pytest.fixture
def set_copy(tmp_path: Path) -> Path:
    """A writable copy of the placeholder set, returned as its directory."""
    src = validate.DOCS_DIR / PLACEHOLDER
    dst = tmp_path / PLACEHOLDER
    shutil.copytree(src, dst)
    return dst


def write_yaml(path: Path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_placeholder_set_is_valid(set_copy: Path):
    rep = validate.validate_set(set_copy)
    assert rep.ok, f"expected valid, got errors: {rep.errors}"


def test_missing_license_fails(set_copy: Path):
    set_path = set_copy / "set.yaml"
    data = yaml.safe_load(set_path.read_text())
    data["members"][0].pop("license")
    write_yaml(set_path, data)
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("license" in e.lower() for e in rep.errors)


def test_unknown_target_member_fails(set_copy: Path):
    q_path = set_copy / "questions.yaml"
    qs = yaml.safe_load(q_path.read_text())
    qs[0]["target_member"] = "does-not-exist"
    write_yaml(q_path, qs)
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("does-not-exist" in e for e in rep.errors)


def test_question_depends_on_missing_fact_fails(set_copy: Path):
    q_path = set_copy / "questions.yaml"
    qs = yaml.safe_load(q_path.read_text())
    qs[0]["depends_on_facts"] = ["f99"]
    write_yaml(q_path, qs)
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("f99" in e for e in rep.errors)


def test_difference_referencing_unknown_fact_fails(set_copy: Path):
    d_path = set_copy / "members" / "tarpon-team" / "differences.yaml"
    diffs = yaml.safe_load(d_path.read_text())
    diffs[0]["fact_id"] = "f99"
    write_yaml(d_path, diffs)
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("f99" in e for e in rep.errors)


def test_generated_paraphrase_without_prompt_fails(set_copy: Path):
    p_path = set_copy / "paraphrases.yaml"
    ps = yaml.safe_load(p_path.read_text())
    # q01-p003 is the generated one; drop its generation_prompt
    ps[0]["paraphrases"][2].pop("generation_prompt")
    write_yaml(p_path, ps)
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("generation_prompt" in e for e in rep.errors)


def test_missing_version_file_fails(set_copy: Path):
    (set_copy / "members" / "tarpon-starter" / "versions" / "differentiated.md").unlink()
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("differentiated" in e for e in rep.errors)


def test_empty_version_file_fails(set_copy: Path):
    vpath = set_copy / "members" / "tarpon-starter" / "versions" / "original.md"
    vpath.write_text("   \n", encoding="utf-8")
    rep = validate.validate_set(set_copy)
    assert not rep.ok
    assert any("empty" in e.lower() for e in rep.errors)

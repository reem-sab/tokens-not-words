"""Tests for common.py, estimate.py, and run.py. Offline: the API client is mocked."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import common as c  # noqa: E402
import run as run_mod  # noqa: E402

SET = "tarpon-webhook-tiers"


# --- fakes ---

class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self, i, o, cr, cw):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = cr
        self.cache_creation_input_tokens = cw


class _Resp:
    def __init__(self, text, usage):
        self.content = [_Block(text)]
        self.usage = usage


class FakeMessages:
    def __init__(self, text):
        self._text = text
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _Resp(self._text, _Usage(1000, 20, 0, 0))

    def count_tokens(self, **kwargs):
        # deterministic small count based on text length
        text = kwargs.get("system", "")
        for m in kwargs.get("messages", []):
            text += str(m.get("content", ""))
        return types.SimpleNamespace(input_tokens=max(1, len(text) // 4))


class FakeClient:
    def __init__(self, text='{"answer": "5.", "confidence": 5}'):
        self.messages = FakeMessages(text)


# --- common ---

def test_cost_usd_matches_rates():
    cfg = c.get_model_cfg("claude-haiku-4-5")
    assert cfg["input_per_mtok"] == 1.00
    assert c.cost_usd(cfg, 1_000_000, 0, 0, 0) == pytest.approx(1.00)
    assert c.cost_usd(cfg, 0, 1_000_000, 0, 0) == pytest.approx(5.00)
    assert c.cost_usd(cfg, 0, 0, 1_000_000, 0) == pytest.approx(0.10)
    assert c.cost_usd(cfg, 0, 0, 0, 1_000_000) == pytest.approx(1.25)


def test_system_prompt_has_all_members():
    sysprompt = c.build_system_prompt(SET, "original")
    assert "Tarpon Starter" in sysprompt
    assert "Tarpon Team" in sysprompt
    assert "Tarpon Enterprise" in sysprompt
    assert "10 seconds" in sysprompt  # starter timeout
    assert "30 seconds" in sysprompt  # enterprise timeout


def test_bad_version_rejected():
    with pytest.raises(ValueError):
        c.build_system_prompt(SET, "does-not-exist")


def test_query_units_canonical_and_approved():
    units = c.iter_query_units(SET, include_pending=False)
    canonical = [u for u in units if u.is_canonical]
    # one canonical per question in questions.yaml
    assert len(canonical) == 12
    # approved paraphrases included, pending excluded
    assert any(u.paraphrase_id == "q01-p001" for u in units)
    assert not any(u.paraphrase_id == "q01-p003" for u in units)  # pending


def test_query_units_draft_includes_pending():
    units = c.iter_query_units(SET, include_pending=True)
    assert any(u.paraphrase_id == "q01-p003" for u in units)  # pending now included


def test_sample_keeps_canonicals():
    units = c.iter_query_units(SET, include_pending=True)
    sampled = c.sample_units(units, 0.0)
    assert all(u.is_canonical for u in sampled)
    assert len(sampled) == 12


# --- run.parse_answer ---

@pytest.mark.parametrize("text,ans,conf,err_none", [
    ('{"answer": "5.", "confidence": 5}', "5.", 5, True),
    ('```json\n{"answer": "yes", "confidence": 3}\n```', "yes", 3, True),
    ('Sure: {"answer": "10 MB", "confidence": 4} done', "10 MB", 4, True),
])
def test_parse_answer_ok(text, ans, conf, err_none):
    a, cf, err = run_mod.parse_answer(text)
    assert a == ans and cf == conf
    assert (err is None) == err_none


def test_parse_answer_bad_json():
    a, cf, err = run_mod.parse_answer("not json at all")
    assert a is None and err is not None


def test_parse_answer_confidence_out_of_range():
    a, cf, err = run_mod.parse_answer('{"answer": "x", "confidence": 9}')
    assert a == "x" and cf == 9 and "out of range" in err


# --- run() with a mock client ---

def test_run_writes_and_recomputes(tmp_path):
    client = FakeClient()
    raw = run_mod.run(
        set_slug=SET, version="original", models=["claude-haiku-4-5"],
        run_id="t1", reps=1, temperature=0.0, max_tokens=256,
        include_pending=False, sample_fraction=0.0,  # canonicals only = 12
        client=client, results_dir=tmp_path,
    )
    rows = c.read_jsonl(raw)
    assert len(rows) == 12
    assert client.messages.calls == 12
    # cost recompute matches per row
    cfg = c.get_model_cfg("claude-haiku-4-5")
    for r in rows:
        assert r["cost_usd"] == pytest.approx(
            c.cost_usd(cfg, r["input_tokens"], r["output_tokens"],
                       r["cache_read_tokens"], r["cache_write_tokens"])
        )
        assert r["answer"] == "5." and r["confidence"] == 5


def test_run_is_resumable(tmp_path):
    client1 = FakeClient()
    run_mod.run(
        set_slug=SET, version="original", models=["claude-haiku-4-5"],
        run_id="t2", reps=1, temperature=0.0, max_tokens=256,
        include_pending=False, sample_fraction=0.0,
        client=client1, results_dir=tmp_path,
    )
    # second run: everything already done, nothing new called
    client2 = FakeClient()
    run_mod.run(
        set_slug=SET, version="original", models=["claude-haiku-4-5"],
        run_id="t2", reps=1, temperature=0.0, max_tokens=256,
        include_pending=False, sample_fraction=0.0,
        client=client2, results_dir=tmp_path,
    )
    assert client2.messages.calls == 0


def test_run_logs_parse_error_without_dropping(tmp_path):
    client = FakeClient(text="the model rambled and returned no json")
    raw = run_mod.run(
        set_slug=SET, version="original", models=["claude-haiku-4-5"],
        run_id="t3", reps=1, temperature=0.0, max_tokens=256,
        include_pending=False, sample_fraction=0.0,
        client=client, results_dir=tmp_path,
    )
    rows = c.read_jsonl(raw)
    assert len(rows) == 12  # nothing dropped
    assert all(r["parse_error"] for r in rows)
    assert all(r["answer"] is None for r in rows)

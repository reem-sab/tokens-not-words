#!/usr/bin/env python3
"""Run comprehension queries against a model and log every call to raw.jsonl.

Each call loads the whole set (every member's chosen version) into a cached
system prompt and asks one question. The model returns JSON with an answer and a
confidence. Every call is logged, including parse failures. Nothing is dropped.

Safety:
  - Prints a cost estimate and requires confirmation before spending money
    (pass --yes to confirm non-interactively).
  - Resumes: a call already present in raw.jsonl is not repeated.
  - After the run, recomputes cost from logged tokens as a sanity check.

Usage:
  python run.py --set tarpon-webhook-tiers --yes
  python run.py --set tarpon-webhook-tiers --version differentiated --run-id demo --yes
  python run.py --set tarpon-webhook-tiers --draft --sample 0.1 --yes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import common as c

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_answer(text: str):
    """Return (answer, confidence, parse_error). Never raises."""
    if text is None:
        return None, None, "empty response"
    cleaned = _FENCE.sub("", text).strip()
    # Grab the first {...} block if there is surrounding prose.
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        obj = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as e:
        return None, None, f"json parse failed: {e}"
    if not isinstance(obj, dict) or "answer" not in obj:
        return None, None, "missing 'answer' key"
    answer = obj.get("answer")
    conf = obj.get("confidence")
    conf_err = None
    try:
        conf = int(conf)
        if not 1 <= conf <= 5:
            conf_err = f"confidence {conf} out of range 1-5"
    except (TypeError, ValueError):
        conf_err = f"confidence not an integer: {conf!r}"
        conf = None
    return answer, conf, conf_err


def extract_text(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def answer_one(client, model_id, model_cfg, system, user_text, max_tokens, temperature):
    """One API call. Returns a dict of results including token usage and cost."""
    t0 = time.time()
    response = client.messages.create(
        model=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_text}],
    )
    latency = time.time() - t0
    text = extract_text(response)
    answer, confidence, parse_error = parse_answer(text)

    u = response.usage
    input_tokens = getattr(u, "input_tokens", 0) or 0
    output_tokens = getattr(u, "output_tokens", 0) or 0
    cache_read = getattr(u, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(u, "cache_creation_input_tokens", 0) or 0
    cost = c.cost_usd(model_cfg, input_tokens, output_tokens, cache_read, cache_write)

    return {
        "answer": answer,
        "confidence": confidence,
        "parse_error": parse_error,
        "raw_text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "latency_s": round(latency, 3),
        "cost_usd": cost,
    }


def build_row(run_id, set_slug, version, model_id, unit, rep, temperature, result):
    return {
        "run_id": run_id,
        "set": set_slug,
        "version": version,
        "model": model_id,
        "question_id": unit.question_id,
        "paraphrase_id": unit.paraphrase_id,
        "is_canonical": unit.is_canonical,
        "source": unit.source,
        "target_member": unit.target_member,
        "repetition": rep,
        "temperature": temperature,
        "ts": datetime.now(timezone.utc).isoformat(),
        **result,
    }


def run(
    set_slug,
    version,
    models,
    run_id,
    reps,
    temperature,
    max_tokens,
    include_pending,
    sample_fraction,
    client=None,
    results_dir=None,
):
    """Execute the run. Returns the path to raw.jsonl. client is injectable for tests."""
    units = c.iter_query_units(set_slug, include_pending=include_pending)
    units = c.sample_units(units, sample_fraction)

    out_dir = (results_dir or c.RESULTS_DIR) / run_id
    raw_path = out_dir / "raw.jsonl"
    done = {c.call_key(r) for r in c.read_jsonl(raw_path)}

    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    written = 0
    skipped = 0
    parse_errors = 0
    for model_id in models:
        model_cfg = c.get_model_cfg(model_id)
        system = c.build_system_prompt(set_slug, version)
        for unit in units:
            for rep in range(reps):
                key = (set_slug, version, model_id, unit.question_id, unit.paraphrase_id, rep)
                if key in done:
                    skipped += 1
                    continue
                result = answer_one(
                    client, model_id, model_cfg, system, unit.text, max_tokens, temperature
                )
                row = build_row(run_id, set_slug, version, model_id, unit, rep, temperature, result)
                c.append_jsonl(raw_path, row)
                written += 1
                if result["parse_error"]:
                    parse_errors += 1

    print(f"wrote {written} calls, skipped {skipped} already-done, {parse_errors} parse errors")
    _sanity_check(raw_path)
    return raw_path


def _sanity_check(raw_path: Path) -> None:
    """Recompute cost from logged tokens and confirm it matches the logged cost."""
    rows = c.read_jsonl(raw_path)
    if not rows:
        print("sanity: no rows to check")
        return
    models_cfg = c.load_models_config()
    mismatches = 0
    total = 0.0
    for r in rows:
        cfg = c.get_model_cfg(r["model"], models_cfg)
        recomputed = c.cost_usd(
            cfg,
            r["input_tokens"],
            r["output_tokens"],
            r["cache_read_tokens"],
            r["cache_write_tokens"],
        )
        total += r["cost_usd"]
        if abs(recomputed - r["cost_usd"]) > 1e-9:
            mismatches += 1
    status = "OK" if mismatches == 0 else f"{mismatches} MISMATCH"
    print(f"sanity: cost recomputed from tokens [{status}]; logged total ${total:.6f}")


def _confirm(set_slug, version, models, args) -> bool:
    """Show the estimate and ask before spending money."""
    import estimate
    print("=== cost estimate (dry run) ===")
    estimate.main(
        [
            "--set", set_slug,
            "--version", version,
            "--models", *models,
            "--sample", str(args.sample),
            *(["--draft"] if args.draft else []),
        ]
    )
    print("=== end estimate ===")
    try:
        reply = input("Proceed and spend money on this run? type 'yes' to continue: ")
    except EOFError:
        return False
    return reply.strip().lower() == "yes"


def main(argv=None) -> int:
    run_cfg = c.load_run_config()
    ap = argparse.ArgumentParser(description="Run comprehension queries and log results.")
    ap.add_argument("--set", dest="set_slug", required=True)
    ap.add_argument("--version", default=run_cfg["default_version"])
    ap.add_argument("--models", nargs="*", default=run_cfg["default_models"])
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--draft", action="store_true", help="include pending paraphrases")
    ap.add_argument("--sample", type=float, default=run_cfg.get("sample_fraction", 1.0))
    ap.add_argument("--yes", action="store_true", help="skip the spend confirmation")
    args = ap.parse_args(argv)

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reps = int(run_cfg["repetitions"])
    temperature = float(run_cfg["temperature"])
    max_tokens = int(run_cfg["max_tokens"])

    if not args.yes and not _confirm(args.set_slug, args.version, args.models, args):
        print("aborted: not confirmed")
        return 1

    run(
        set_slug=args.set_slug,
        version=args.version,
        models=args.models,
        run_id=run_id,
        reps=reps,
        temperature=temperature,
        max_tokens=max_tokens,
        include_pending=args.draft,
        sample_fraction=args.sample,
    )
    print(f"run id: {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

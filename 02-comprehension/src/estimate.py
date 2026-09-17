#!/usr/bin/env python3
"""Dry run: estimate tokens and cost for a comprehension run. Generates no answers.

Breaks the estimate down by set, version, model, and paraphrase count, and
compares the total to the budget ceiling in config/run.yaml. It calls the
Anthropic count_tokens endpoint (which is not billed) when a key is available,
and falls back to an approximate offline count otherwise (clearly labeled).

Usage:
  python estimate.py --set tarpon-webhook-tiers
  python estimate.py --set tarpon-webhook-tiers --version differentiated --draft
  python estimate.py --set tarpon-webhook-tiers --models claude-haiku-4-5 --sample 0.1
"""
from __future__ import annotations

import argparse
import sys

import common as c


def estimate_model(set_slug, version, model_id, units, reps, assumed_output, client):
    """Return a dict with the token and cost breakdown for one model."""
    model_cfg = c.get_model_cfg(model_id)
    system = c.build_system_prompt(set_slug, version)

    system_tokens, method = c.count_input_tokens(model_id, system, " ", client=client)
    user_tokens = 0
    for u in units:
        ut, m2 = c.count_input_tokens(model_id, "", u.text, client=client)
        user_tokens += ut
        method = "offline" if "offline" in (method, m2) else method

    total_calls = len(units) * reps
    # Caching assumption: the system prefix is written to cache once and read on
    # every later call. This is optimistic (it ignores the 5-minute cache TTL, so a
    # long run may re-warm the cache more than once). Stated in the output.
    cache_write_tokens = system_tokens
    cache_read_tokens = system_tokens * max(0, total_calls - 1)
    input_tokens = user_tokens * reps
    output_tokens = assumed_output * total_calls

    cost = c.cost_usd(
        model_cfg,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    return {
        "model": model_id,
        "method": method,
        "system_tokens": system_tokens,
        "calls": total_calls,
        "input_tokens": input_tokens,
        "cache_write_tokens": cache_write_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }


def main(argv=None) -> int:
    run_cfg = c.load_run_config()
    ap = argparse.ArgumentParser(description="Estimate cost for a comprehension run.")
    ap.add_argument("--set", dest="set_slug", required=True)
    ap.add_argument("--version", default=run_cfg["default_version"])
    ap.add_argument("--models", nargs="*", default=run_cfg["default_models"])
    ap.add_argument("--draft", action="store_true", help="include pending paraphrases")
    ap.add_argument("--sample", type=float, default=run_cfg.get("sample_fraction", 1.0))
    args = ap.parse_args(argv)

    reps = int(run_cfg["repetitions"])
    assumed_output = int(run_cfg["assumed_output_tokens"])
    ceiling = run_cfg.get("budget_ceiling_usd")

    units = c.iter_query_units(args.set_slug, include_pending=args.draft)
    units = c.sample_units(units, args.sample)
    n_canonical = sum(1 for u in units if u.is_canonical)
    n_paraphrase = len(units) - n_canonical

    # Reuse one client across all count_tokens calls if a key is available.
    client = None
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception:
        client = None

    print(f"set:      {args.set_slug}")
    print(f"version:  {args.version}")
    print(f"draft:    {args.draft} (pending paraphrases {'included' if args.draft else 'excluded'})")
    print(f"queries:  {len(units)}  ({n_canonical} canonical + {n_paraphrase} paraphrase)")
    print(f"reps:     {reps}   sample: {args.sample}")
    print()

    total = 0.0
    any_offline = False
    for model_id in args.models:
        r = estimate_model(
            args.set_slug, args.version, model_id, units, reps, assumed_output, client
        )
        total += r["cost_usd"]
        any_offline = any_offline or r["method"] != "api"
        print(f"model: {r['model']}  [{r['method']} token count]")
        print(f"  system prompt: {r['system_tokens']:,} tokens (cached)")
        print(f"  calls:         {r['calls']:,}")
        print(f"  input:         {r['input_tokens']:,} tokens")
        print(f"  cache write:   {r['cache_write_tokens']:,} tokens")
        print(f"  cache read:    {r['cache_read_tokens']:,} tokens")
        print(f"  output (est):  {r['output_tokens']:,} tokens")
        print(f"  cost:          ${r['cost_usd']:.4f}")
        print()

    print(f"TOTAL estimated cost: ${total:.4f}")
    if any_offline:
        print(
            "NOTE: at least one count used the OFFLINE approximation (no API key "
            "found). Token counts and cost are rough. Run with a key for exact counts."
        )
    print(
        "NOTE: caching estimate is optimistic (assumes one cache warm; a long run "
        "may re-warm past the 5-minute TTL). Pricing date: "
        f"{c.load_models_config()['pricing_date']} (verify before a paid run)."
    )

    if ceiling is not None:
        if total > ceiling:
            print(f"\nOVER BUDGET: ${total:.4f} exceeds the ceiling ${ceiling:.4f}.")
            return 3
        print(f"\nWithin budget ceiling (${ceiling:.4f}).")
    else:
        print("\nNo budget ceiling set (config/run.yaml budget_ceiling_usd: null).")

    return 0


if __name__ == "__main__":
    sys.exit(main())

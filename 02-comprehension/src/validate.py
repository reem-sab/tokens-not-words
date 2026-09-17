#!/usr/bin/env python3
"""Validate comprehension doc sets against the schemas and cross-file rules.

This runs offline. It never calls a paid API, so it is safe to run in CI.

Checks:
  - Every YAML file matches its JSON schema (schemas/).
  - set.yaml lists 3 to 5 members and defines an "original" version.
  - Every member has facts.yaml, differences.yaml, and a version file per
    version named in set.yaml.
  - Every difference references a real fact id for that member.
  - Every question's target_member exists and every depends_on_facts id exists in
    that member's facts.
  - Every paraphrase's question_id exists; ids are unique; generated paraphrases
    carry a generation prompt and model.
  - Every member has a license (refuse a set with a missing license).
  - Fact inventory (structural): every version file exists and is non-empty. Full
    fact-equality across versions needs human review, or the optional --llm check
    added with the runner in a later milestone.

Usage:
  python validate.py            # validate every set under docs/
  python validate.py --set tarpon-webhook-tiers
  python validate.py --llm      # (deferred) list facts missing/added per version
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
COMP_ROOT = HERE.parent
SCHEMA_DIR = COMP_ROOT / "schemas"
DOCS_DIR = COMP_ROOT / "docs"


class SetReport:
    """Errors fail the run; warnings and notes are for humans."""

    def __init__(self, slug: str):
        self.slug = slug
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_schema(name: str) -> Draft202012Validator:
    with (SCHEMA_DIR / name).open(encoding="utf-8") as f:
        return Draft202012Validator(json.load(f))


def schema_errors(validator: Draft202012Validator, instance, label: str) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path)
        where = f"{label} at '{loc}'" if loc else label
        out.append(f"{where}: {err.message}")
    return out


def validate_set(set_dir: Path) -> SetReport:
    rep = SetReport(set_dir.name)

    set_schema = load_schema("set.schema.json")
    facts_schema = load_schema("facts.schema.json")
    diffs_schema = load_schema("differences.schema.json")
    questions_schema = load_schema("questions.schema.json")
    paraphrases_schema = load_schema("paraphrases.schema.json")

    # --- set.yaml ---
    set_path = set_dir / "set.yaml"
    if not set_path.exists():
        rep.error("set.yaml is missing")
        return rep
    try:
        set_data = load_yaml(set_path)
    except yaml.YAMLError as e:
        rep.error(f"set.yaml is not valid YAML: {e}")
        return rep

    errs = schema_errors(set_schema, set_data, "set.yaml")
    if errs:
        rep.errors.extend(errs)
        return rep  # structure is unreliable past this point

    member_ids = [m["id"] for m in set_data["members"]]
    version_names = [v["name"] for v in set_data["versions"]]

    if "original" not in version_names:
        rep.error("set.yaml versions must include 'original'")

    for m in set_data["members"]:
        if not str(m.get("license", "")).strip():
            rep.error(f"member '{m['id']}' has no license")

    # --- per member ---
    member_facts: dict[str, set[str]] = {}
    for m in set_data["members"]:
        mid = m["id"]
        mdir = set_dir / "members" / mid
        if not mdir.is_dir():
            rep.error(f"member '{mid}' directory is missing at members/{mid}/")
            continue

        # facts.yaml
        facts_path = mdir / "facts.yaml"
        fact_ids: set[str] = set()
        if not facts_path.exists():
            rep.error(f"member '{mid}' is missing facts.yaml")
        else:
            facts = load_yaml(facts_path)
            errs = schema_errors(facts_schema, facts, f"{mid}/facts.yaml")
            if errs:
                rep.errors.extend(errs)
            else:
                for fact in facts:
                    if fact["id"] in fact_ids:
                        rep.error(f"{mid}/facts.yaml has duplicate fact id '{fact['id']}'")
                    fact_ids.add(fact["id"])
        member_facts[mid] = fact_ids

        # differences.yaml
        diffs_path = mdir / "differences.yaml"
        if not diffs_path.exists():
            rep.error(f"member '{mid}' is missing differences.yaml")
        else:
            diffs = load_yaml(diffs_path)
            errs = schema_errors(diffs_schema, diffs, f"{mid}/differences.yaml")
            if errs:
                rep.errors.extend(errs)
            else:
                for d in diffs:
                    if d["fact_id"] not in fact_ids:
                        rep.error(
                            f"{mid}/differences.yaml references unknown fact "
                            f"'{d['fact_id']}'"
                        )

        # version files + structural fact-inventory check
        for vname in version_names:
            vpath = mdir / "versions" / f"{vname}.md"
            if not vpath.exists():
                rep.error(f"member '{mid}' is missing version file versions/{vname}.md")
            elif not vpath.read_text(encoding="utf-8").strip():
                rep.error(f"member '{mid}' version '{vname}' is empty")

    # --- questions.yaml ---
    q_path = set_dir / "questions.yaml"
    question_ids: set[str] = set()
    if not q_path.exists():
        rep.error("questions.yaml is missing")
    else:
        questions = load_yaml(q_path)
        errs = schema_errors(questions_schema, questions, "questions.yaml")
        if errs:
            rep.errors.extend(errs)
        else:
            for q in questions:
                if q["id"] in question_ids:
                    rep.error(f"questions.yaml has duplicate question id '{q['id']}'")
                question_ids.add(q["id"])
                tm = q["target_member"]
                if tm not in member_ids:
                    rep.error(
                        f"question '{q['id']}' targets unknown member '{tm}'"
                    )
                else:
                    for fid in q["depends_on_facts"]:
                        if fid not in member_facts.get(tm, set()):
                            rep.error(
                                f"question '{q['id']}' depends on fact '{fid}' "
                                f"not found in member '{tm}'"
                            )

    # --- paraphrases.yaml ---
    p_path = set_dir / "paraphrases.yaml"
    if not p_path.exists():
        rep.warn("paraphrases.yaml is missing (allowed while a set is being built)")
    else:
        paraphrases = load_yaml(p_path)
        errs = schema_errors(paraphrases_schema, paraphrases, "paraphrases.yaml")
        if errs:
            rep.errors.extend(errs)
        else:
            seen_pids: set[str] = set()
            approved = 0
            pending = 0
            for group in paraphrases:
                qid = group["question_id"]
                if question_ids and qid not in question_ids:
                    rep.error(
                        f"paraphrases reference unknown question '{qid}'"
                    )
                for p in group["paraphrases"]:
                    if p["id"] in seen_pids:
                        rep.error(f"duplicate paraphrase id '{p['id']}'")
                    seen_pids.add(p["id"])
                    if not p["id"].startswith(qid + "-"):
                        rep.warn(
                            f"paraphrase '{p['id']}' id does not match its "
                            f"question '{qid}'"
                        )
                    if p["review_status"] == "approved":
                        approved += 1
                    elif p["review_status"] == "pending":
                        pending += 1
            rep.note(
                f"paraphrases: {approved} approved, {pending} pending "
                f"(pending run only in draft mode)"
            )

    # --- fact-inventory reminder ---
    total_facts = sum(len(v) for v in member_facts.values())
    rep.note(
        f"fact inventory needs human confirmation: {len(member_ids)} members x "
        f"{len(version_names)} versions, {total_facts} facts total. Confirm every "
        f"version states the same facts as its original (writing changes only)."
    )

    return rep


def run_llm_check(set_dir: Path) -> None:
    print(
        "  [--llm] The optional LLM fact-diff check is not implemented yet. It is\n"
        "  added with the runner in a later milestone: it will list any fact\n"
        "  missing or added per version. It needs the API, stays off by default,\n"
        "  and never runs in CI."
    )


def discover_sets() -> list[Path]:
    if not DOCS_DIR.is_dir():
        return []
    return sorted(p for p in DOCS_DIR.iterdir() if p.is_dir() and (p / "set.yaml").exists())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate comprehension doc sets.")
    ap.add_argument("--set", dest="set_slug", help="validate only this set slug")
    ap.add_argument(
        "--llm",
        action="store_true",
        help="also run the (deferred) LLM fact-diff check",
    )
    args = ap.parse_args(argv)

    if args.set_slug:
        set_dirs = [DOCS_DIR / args.set_slug]
        if not set_dirs[0].is_dir():
            print(f"error: set '{args.set_slug}' not found under {DOCS_DIR}")
            return 2
    else:
        set_dirs = discover_sets()
        if not set_dirs:
            print(f"no doc sets found under {DOCS_DIR}")
            return 0

    any_errors = False
    for set_dir in set_dirs:
        rep = validate_set(set_dir)
        status = "OK" if rep.ok else "FAIL"
        print(f"[{status}] {rep.slug}")
        for msg in rep.errors:
            print(f"  ERROR: {msg}")
        for msg in rep.warnings:
            print(f"  warn:  {msg}")
        for msg in rep.notes:
            print(f"  note:  {msg}")
        if args.llm:
            run_llm_check(set_dir)
        any_errors = any_errors or not rep.ok

    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared helpers for the comprehension pipeline: loading, prompt building,
query enumeration, token counting, and cost math.

No module-level API calls. Token counting uses the Anthropic API when a key is
available and falls back to a clearly-labeled offline estimate otherwise, so the
dry-run estimate works without a key (with a warning) and is exact with one.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
COMP_ROOT = HERE.parent
DOCS_DIR = COMP_ROOT / "docs"
CONFIG_DIR = COMP_ROOT / "config"
RESULTS_DIR = COMP_ROOT / "results"

# Fixed instruction prepended to the documentation in the system prompt.
SYSTEM_INSTRUCTION = (
    "You are answering questions about product documentation.\n"
    "Rules:\n"
    "- Answer using ONLY the documentation provided below. Do not use outside "
    "knowledge.\n"
    "- The documentation covers several similar products or tiers. Read carefully "
    "and use the one the question asks about.\n"
    "- Reply with a single JSON object and nothing else: "
    '{"answer": "<concise answer>", "confidence": <integer 1 to 5>}.\n'
    "- confidence is how sure you are: 1 means a guess, 5 means certain."
)


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_run_config() -> dict:
    return load_yaml(CONFIG_DIR / "run.yaml")


def load_models_config() -> dict:
    return load_yaml(CONFIG_DIR / "models.yaml")


def get_model_cfg(model_id: str, models_config: dict | None = None) -> dict:
    models_config = models_config or load_models_config()
    for m in models_config["models"]:
        if m["id"] == model_id:
            return m
    raise KeyError(f"model '{model_id}' not found in models.yaml")


def set_dir(set_slug: str) -> Path:
    d = DOCS_DIR / set_slug
    if not (d / "set.yaml").exists():
        raise FileNotFoundError(f"set '{set_slug}' not found under {DOCS_DIR}")
    return d


def load_set(set_slug: str) -> dict:
    return load_yaml(set_dir(set_slug) / "set.yaml")


def build_system_prompt(set_slug: str, version: str) -> str:
    """Concatenate every member's chosen version into one system prompt.

    All members are loaded together on purpose: the test is whether the model can
    keep similar members apart.
    """
    s = load_set(set_slug)
    version_names = [v["name"] for v in s["versions"]]
    if version not in version_names:
        raise ValueError(
            f"version '{version}' is not defined for set '{set_slug}' "
            f"(have: {', '.join(version_names)})"
        )
    parts = [SYSTEM_INSTRUCTION, "", "Documentation:", ""]
    for m in s["members"]:
        vpath = set_dir(set_slug) / "members" / m["id"] / "versions" / f"{version}.md"
        parts.append(f"===== {m['title']} =====")
        parts.append(vpath.read_text(encoding="utf-8").strip())
        parts.append("")
    return "\n".join(parts).strip() + "\n"


@dataclass(frozen=True)
class QueryUnit:
    question_id: str
    paraphrase_id: str  # the canonical question uses the question id itself
    is_canonical: bool
    source: str  # canonical | human | generated
    review_status: str  # canonical questions are treated as approved
    text: str
    target_member: str


def iter_query_units(set_slug: str, include_pending: bool = False) -> list[QueryUnit]:
    """Every query to run: the canonical question plus its paraphrases.

    Approved paraphrases always run. Pending paraphrases run only when
    include_pending is True (draft mode). Rejected paraphrases never run.
    """
    d = set_dir(set_slug)
    questions = load_yaml(d / "questions.yaml")
    p_path = d / "paraphrases.yaml"
    paraphrases = load_yaml(p_path) if p_path.exists() else []
    para_by_q: dict[str, list[dict]] = {g["question_id"]: g["paraphrases"] for g in paraphrases}

    units: list[QueryUnit] = []
    for q in questions:
        qid = q["id"]
        units.append(
            QueryUnit(
                question_id=qid,
                paraphrase_id=qid,
                is_canonical=True,
                source="canonical",
                review_status="approved",
                text=q["question"],
                target_member=q["target_member"],
            )
        )
        for p in para_by_q.get(qid, []):
            status = p["review_status"]
            if status == "rejected":
                continue
            if status == "pending" and not include_pending:
                continue
            units.append(
                QueryUnit(
                    question_id=qid,
                    paraphrase_id=p["id"],
                    is_canonical=False,
                    source=p["source"],
                    review_status=status,
                    text=p["text"],
                    target_member=q["target_member"],
                )
            )
    return units


def sample_units(units: list[QueryUnit], fraction: float) -> list[QueryUnit]:
    """Deterministic sample: keep every question's canonical query, then take a
    fraction of the paraphrases. Never drops a canonical query."""
    if fraction >= 1.0:
        return units
    kept = [u for u in units if u.is_canonical]
    paraphrases = [u for u in units if not u.is_canonical]
    n = math.ceil(len(paraphrases) * fraction)
    kept.extend(paraphrases[:n])
    return kept


# --- cost math ---

def cost_usd(
    model_cfg: dict,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Cost of one call from token counts. input_tokens is uncached input only
    (matches Anthropic's usage fields, where cached tokens are reported separately)."""
    per_m = 1_000_000
    return (
        input_tokens / per_m * model_cfg["input_per_mtok"]
        + output_tokens / per_m * model_cfg["output_per_mtok"]
        + cache_read_tokens / per_m * model_cfg["cache_read_per_mtok"]
        + cache_write_tokens / per_m * model_cfg["cache_write_per_mtok"]
    )


# --- token counting (API when available, offline fallback otherwise) ---

def count_tokens_offline(text: str) -> int:
    """Rough offline token estimate. Approximate. Labeled as such wherever used."""
    # ~4 characters per token is a common rough rule for English prose.
    return max(1, math.ceil(len(text) / 4))


def count_input_tokens(model_id: str, system: str, user_text: str, client=None) -> tuple[int, str]:
    """Return (input_tokens, method). method is 'api' (exact) or 'offline' (approx).

    Uses the Anthropic count_tokens endpoint when a client (or key) is available.
    count_tokens is not billed for token usage.
    """
    provider = None
    try:
        provider = get_model_cfg(model_id)["provider"]
    except KeyError:
        provider = "anthropic"

    if provider == "anthropic":
        try:
            if client is None:
                import anthropic  # noqa: local import so the module loads without the dep
                client = anthropic.Anthropic()
            kwargs = {
                "model": model_id,
                "messages": [{"role": "user", "content": user_text or " "}],
            }
            if system:
                kwargs["system"] = system
            resp = client.messages.count_tokens(**kwargs)
            return resp.input_tokens, "api"
        except Exception:
            return count_tokens_offline((system or "") + "\n" + user_text), "offline"
    elif provider == "openai":
        try:
            import tiktoken
            enc = tiktoken.get_encoding("o200k_base")
            return len(enc.encode(system + "\n" + user_text)), "tiktoken"
        except Exception:
            return count_tokens_offline(system + "\n" + user_text), "offline"
    return count_tokens_offline(system + "\n" + user_text), "offline"


# --- jsonl helpers (append-only raw log, resume-safe) ---

def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def call_key(row: dict) -> tuple:
    """Identity of one call, for resume. A row already present is not re-run."""
    return (
        row["set"],
        row["version"],
        row["model"],
        row["question_id"],
        row["paraphrase_id"],
        row["repetition"],
    )


def unit_asdict(u: QueryUnit) -> dict:
    return asdict(u)

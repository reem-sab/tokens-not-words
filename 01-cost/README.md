# Tokens, not words: what your writing costs an AI to read

Most of what we write is increasingly read by machines, not people. In my last role, docs analytics showed **~60% of traffic was automated** — LLM crawlers and agents, not humans. Those readers don't count words. They count **tokens**, and tokens cost money and time.

This notebook measures that, live — with the correct tokenizer per model, a real cost-vs-quality comparison across Claude tiers, a prompt-caching demo, and a reusable calculator.

## Key findings (all computed in-notebook)

- **Tokenizers disagree:** the same paragraph was 46 tokens for GPT vs 77 for Claude — so you can never price one model with another's counts.
- **Formatting isn't free:** JSON and code cost ~3× and ~1.7× more per word than prose.
- **A whole novel:** it costs Claude about **$0.51** to read the entire text of *Pride and Prejudice* (~253k tokens).
- **Prompt caching:** a repeated read dropped from **$0.63 → $0.05 (~12× cheaper)** in three lines.

## What's inside

`tokens-not-words.ipynb` — a self-contained Deepnote notebook:

1. Tokens vs words on a small corpus (prose / table / JSON / code)
2. SQL aggregation over the results
3. Exact Claude token counts + per-model cost
4. A live cost / latency / quality comparison across Claude Haiku 4.5, Sonnet 5, and Opus 5
5. The "cost to read a novel" hook (public-domain text)
6. A prompt-caching demo and a reusable cost calculator

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or set it as a Deepnote secret
```

Then run the notebook top to bottom.

## Accuracy notes

- Claude token counts use **Anthropic's `count_tokens` API**; `tiktoken` is used only for the GPT-family tokenizer and the concept — the two tokenizers do not match.
- Pricing is Anthropic list price **as of 2026-06-24** — verify current before reuse.
- Novel text: *Pride and Prejudice*, Project Gutenberg #1342 (public domain).

Built in [Deepnote](https://deepnote.com).

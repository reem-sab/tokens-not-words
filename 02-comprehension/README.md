# Part 2: Comprehension

**The question:** if the facts stay the same and only the writing changes, do a
model's answers get more accurate?

This part tests documentation the way an AI reads it. It loads a set of similar
but distinct docs (for example, three tiers of one product) into a model at once,
asks questions whose answers depend on telling them apart, and measures how often
the model gets them right. Then it rewrites the docs for clarity, keeping the
facts identical, and measures again.

A token is the unit a model reads in, roughly a short chunk of a word. A "set" is
a group of 3 to 5 related docs. A "member" is one doc in a set.

## Status

In progress. Right now the repo has the data format, a validator, and a fictional
placeholder set (`docs/tarpon-webhook-tiers/`) used to build and test the pipeline
before a real doc set is chosen. The runner, judge, and report come next.

## Validate the data (no API key needed)

```bash
pip install -r requirements.txt
python src/validate.py
```

This checks the doc sets against the schemas and the cross-file rules. It runs
offline and makes no paid API calls.

## How it will work

1. Pick a set of similar docs and write a fact inventory for each member.
2. Write questions whose answers depend on the distinguishing facts.
3. Add paraphrases of each question to test whether the model is consistent.
4. Run the questions against several models, on the original docs and on a
   clearer rewrite.
5. Score the answers, including a `wrong_sibling` label for when the model gives a
   different member's answer.
6. Report accuracy, consistency, and how often the model was confidently wrong.

## Contributing

Contribution docs and templates arrive with the full pipeline. Paraphrase review
will be a good first task for people who do not code. If you want to help shape
this, watch the repo.

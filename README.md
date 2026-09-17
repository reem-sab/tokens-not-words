# Tokens, not words

Most of what we write is now read by machines as often as people. This repo is a
series of small, reproducible experiments about what that means for anyone who
writes for a living. Each part measures one thing, with code you can run yourself
and data you can check.

A token is the unit a language model reads in, roughly a short chunk of a word.
Everything here starts from that idea and builds out.

## The series

**Part 1: Cost.** What does your writing cost a machine to read? A notebook that
counts tokens across formats, compares the price of the same text across models,
and shows how prompt caching (reusing an already-read document) can cut a
repeated read by about 12 times. It computes, live, that it costs roughly 51
cents for a model to read all of *Pride and Prejudice*.
See [`01-cost/`](01-cost/).

**Part 2: Comprehension.** If the facts stay the same and only the writing
changes, do a model's answers get more accurate? An open test that rewrites the
same document for clarity and measures whether the model understands it better.
In progress, under [`02-comprehension/`](02-comprehension/).

**Later parts.** Findability (can a retrieval system even surface your writing?)
and actionability (can an agent follow it?). Planned, not started.

## Who this is for

Technical writers, content designers, and anyone curious about how AI reads what
we publish. Part 2 is built to be contributed to, including by writers who rarely
touch code. If you want to help measure this at scale, start with the part 2
README.

## License

MIT. See [`LICENSE`](LICENSE).

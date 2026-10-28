# Architecture

This is the design of the code in `worker/`, and why it is built this way. For a tour of the files, read
[CODE-GUIDE.md](CODE-GUIDE.md) first.

## The shape

```
worker/
  1_indexing/     read documents, clean, chunk, embed, store
  2_retrieval/    prepare the question, search, merge, rerank
  3_generation/   build the prompt, ask the model, check the reply
  4_evaluation/   load questions, score retrieval, judge answers, report
  common/         settings and the code that talks to the AI services and the database
```

Each phase folder has one file per step and a `main.py` that calls the steps in order, as plain function calls.
A step is a function that takes data in and returns data out. Data moves between steps as plain lists and dictionaries.

## Why it is built this way

**Plain functions in numbered files.** You can read a `main.py` top to bottom like a recipe and open any step to see exactly
what it does. There are no interfaces to look up and no framework to learn.

**One step, one job.** Changing how documents are split means editing only `3_chunk.py`. Changing how questions are rephrased
means editing only `1_query.py`. No other file needs to change, which keeps experiments cheap and results comparable.

**The AI services sit behind four functions** (`embed_texts`, `embed_query`, `ask_llm`, `ask_judge` in `common/models.py`).
The steps never know whether Gemini or Groq answered. Switching provider is a line in `.env`.

**Free-tier protection is separate from the steps.** Waiting for rate limits (`throttle.py`), retrying (`retry.py`),
remembering answers on disk (`cache.py`) and capping daily calls are wrappers around the AI clients, so the steps stay short.

**Collections.** Documents are stored under a collection name (`COLLECTION` in `common/config.py`). A new chunking method
gets a new collection name, so two indexes of the same documents can sit side by side. `--source` searches one dataset at a time.

## What was tried and replaced

The first version of this project used interfaces, a strategy registry and experiment config files, a design that makes it
possible to combine many methods without editing any existing code. It was replaced because it was hard to read for the
person who has to understand and explain it. The cost of the simpler version: trying a new method means editing a step
file (or adding a setting in `common/config.py`) rather than writing a config file, and combining many methods at once takes
a little more manual work. If the number of methods grows large, that design can come back; the steps already have the
same boundaries.

## Known limits

- **Query decomposition** (splitting a question into dependent sub-questions) needs more than the straight pipeline in
  `2_retrieval/main.py`. It would be a different version of `retrieve()`.
- **Changing the embedding model** changes the vector size, which is fixed at 768 in the database table. It needs a new
  table or migration, and re-embedding everything.
- **The judge is an AI model**, so scores are noisy. Compare methods over the whole question set, not single questions, and
  run the held-out test questions once at the end.
- **Keyword search is not built yet.** `2_retrieval/2_search.py` does vector search only. Hybrid search will need a
  Postgres full-text query added there.

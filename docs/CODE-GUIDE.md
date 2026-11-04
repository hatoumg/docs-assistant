# Code guide: how the system is laid out

Run every command from the `worker` folder with the virtual environment active.

## The four phases

| Folder | Job | Run it |
|---|---|---|
| `1_indexing/` | Read documents and store them so they can be searched | `python -m 1_indexing.main ../data/raw/cuad-dev` |
| `2_retrieval/` | Find the chunks that can answer a question | `python -m 2_retrieval.main "your question" --source cuad-dev` |
| `3_generation/` | Write an answer from those chunks, with citations | `python -m 3_generation.main "your question" --source cuad-dev` |
| `4_evaluation/` | Score the system on a file of questions | `python -m 4_evaluation.main ../evals/contracts-dev.json --source cuad-dev --retrieval-only` |

Each folder has one file per step (`1_load.py`, `2_clean.py`, and so on) and a `main.py` that calls the steps in order.
Open a `main.py` first. It reads like a recipe.

## The steps

**Phase 1, indexing:** `1_load` reads files, `2_clean` removes noise, `3_chunk` cuts text into chunks,
`4_embed` turns chunks into vectors, `5_store` saves them in the database.

**Phase 2, retrieval:** `1_query` prepares the question, `2_search` finds the nearest chunks,
`3_merge` combines result lists, `4_rerank` puts them in a better order.

**Phase 3, generation:** `1_prompt` builds the prompt, `2_generate` asks the model,
`3_check` reads the reply and finds the citations.

**Phase 4, evaluation:** `1_questions` loads the questions, `2_retrieval_scores` checks whether the right file
was found, `3_judge` has a model grade the answer, `4_report` prints and saves the results.

## Why the file names start with numbers

The numbers show the order. Python does not allow `from 1_chunk import ...` because names cannot start with a digit, so each
`main.py` imports its steps with a small helper: `split_documents = load("1_indexing.3_chunk", "split_documents")`.
That is the only odd-looking line. `python -m 1_indexing.main` works as normal.

## The common folder

- `common/config.py` holds the numbers you change when experimenting (chunk size, overlap, how many chunks to use).
- `common/models.py` is the one place that talks to the AI services, with four functions: `embed_texts`, `embed_query`,
  `ask_llm` and `ask_judge`. The files next to it do the plumbing: `throttle.py` waits when a free-tier limit is near,
  `retry.py` retries failed calls, `cache.py` remembers answers on disk and caps daily calls, `gemini.py` and
  `openai_compatible.py` talk to the answering services, `providers.py` and `fallback.py` choose between them.
  `ollama.py` makes the embeddings on your own computer (install Ollama, then `ollama pull nomic-embed-text`).
  You do not need to read those to follow the steps.
- `common/database.py` opens the database connection.
- `common/settings.py` reads `.env`.

## How to try a different method

Change one step file, run the evaluation, compare with the earlier results in `evals/results-simple.csv`.

| To try | Edit |
|---|---|
| Different chunk size or overlap | the numbers in `common/config.py`, then use a new `COLLECTION` name and index again |
| A different way of splitting | `1_indexing/3_chunk.py` (and a new `COLLECTION` name) |
| Ask the AI to rephrase the question | `2_retrieval/1_query.py`: return several questions. Step 3 already merges their results |
| A better way to combine results | `2_retrieval/3_merge.py` |
| Rerank the chunks | `2_retrieval/4_rerank.py` |
| A different prompt | `3_generation/1_prompt.py` |

Rules for fair comparison: change one thing at a time, use the dev questions while tuning, and run the test questions
once at the end.

## Where the data goes

- Documents go in the database under the collection name in `common/config.py` (`simple`).
  A different collection name is a separate index, so several chunking methods can sit side by side.
- `--source` names a dataset (the folder you indexed, such as `cuad-dev`) so one test does not search another dataset.
- Results go to `evals/results-simple.csv`.

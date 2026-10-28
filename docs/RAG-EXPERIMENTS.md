# RAG experiments: techniques, comparison method and scoring

This file says which techniques will be tried at each stage of the pipeline, how they are compared, and how answers are scored. Nothing here is required for the MVP (M1). It is the plan for the "quality" work in M2.

## The pipeline

```
question -> 1 Query translation -> 2 Routing -> 3 Query construction
         -> 4 Indexing (done before questions) -> 5 Retrieval -> 6 Generation -> answer + citations
```

Before stage 4, files are turned into clean text by a parsing step (stage 0, below). Stage 0 only matters for PDFs, slides and web pages. Markdown and text files need little more than cleaning.

## How the comparison works

1. **Baseline first.** Build the simplest version of every stage (listed as "Baseline" below). Run the full eval and record the score.
2. **Change one stage at a time.** Hold every other stage at its current best. Try each of the five techniques for that stage and record all scores.
3. **Keep the winner.** The best technique becomes the new baseline for the next stage. If nothing beats the baseline, keep the baseline and write that down. A "no gain" result is still a result.
4. **Order of testing:** Parsing (PDF sets only), Indexing, Retrieval, Query translation, Query construction, Routing, Generation. Retrieval problems cap everything after them, so fix them first.
5. **Use dev questions to choose, test questions to report.** Pick winners on the dev set. Run the test set once per milestone (see `evals/README.md`).
6. **Keep cost down.** Stages 1 to 5 can be scored with retrieval metrics only (no AI judge). Cache every model call. Use a small model while experimenting.

Record every run as a row in `evals/results.csv`: date, stage, technique, dev score, retrieval metrics, cost, latency.

## Techniques to compare (baseline plus five)

### 0. Parsing (turn files into clean text, before indexing)

Test this on the PDF sets (annual report, research papers), where tables and columns break plain extraction. Markdown and text sets do not need it. Prefer tools that run on your own machine for private files, because hosted services receive your documents.

| Technique | Idea |
| --- | --- |
| Baseline: plain text extraction | A basic PDF text extractor (for example pdftotext or pypdf), then the same cleaning step. |
| MarkItDown | Microsoft's open-source converter from many file types to Markdown. |
| Docling | Open-source layout parser from IBM. Keeps headings and tables, and can feed structure-aware chunking. |
| Unstructured | Open-source library (and hosted service) for many formats, with chunking by section title. |
| LlamaParse | Hosted parsing service from LlamaIndex, aimed at tables and images. Needs an account and a key, and usage is limited. |
| Firecrawl | Turns a web page into Markdown. Use it only for web sources, such as scraping documentation sites. |

Score parsing on table and layout questions: Hit@5 and answer correctness on the PDF set, plus parse time, cost and whether files leave your machine. Check each tool's current features and pricing before testing it.

### 1. Query translation (rewrite the question before searching)

| Technique | Idea |
| --- | --- |
| Baseline: none | Search with the question exactly as typed. |
| Multi-query | Ask the model for 3 to 5 rewordings, search with each, merge the results. |
| RAG-Fusion | Multi-query, then combine the ranked lists with reciprocal rank fusion. |
| Decomposition | Split a hard question into smaller sub-questions, answer each, then combine. |
| Step-back | Also ask a broader version of the question to fetch background passages. |
| HyDE | Have the model write a fake answer, then search using that text. |

### 2. Routing (decide where to look and how)

Needs more than one source, which you will have (FastAPI docs, contracts, your own files).

| Technique | Idea |
| --- | --- |
| Baseline: none | Search every document set. |
| Rule-based | Keywords and patterns choose the set (for example "clause" or "agreement" means contracts). |
| Semantic routing | Embed the question and compare it with a short description of each set. |
| Logical routing (LLM) | The model picks the source and returns it as structured output. |
| Trained classifier | A small scikit-learn model trained on your dev questions picks the source. |
| Agent tool choice | The model picks a tool: search a set, open a document, ask a follow-up, or answer without searching. |

### 3. Query construction (turn the question into a structured search)

| Technique | Idea |
| --- | --- |
| Baseline: none | Plain text query only. |
| Self-query metadata filters | Extract filters from the question (document name, contract type, date) and apply them in SQL. |
| Text-to-SQL | For structured data, such as the CUAD clause table loaded into Postgres, the model writes the SQL. Validate and run it read-only. |
| Keyword extraction | Pull key terms out for a keyword or hybrid search. |
| Conversation condensing | Rewrite a follow-up ("what about its term?") into a stand-alone question using chat history. |
| Structured query object | The model fills a fixed schema, for example `{document, clause_type, question}`, using the 41 CUAD clause categories. |

### 4. Indexing (how documents are stored for search)

| Technique | Idea |
| --- | --- |
| Baseline: fixed-size chunks | About 500 tokens with a small overlap. Also try 256 and 1024. |
| Recursive, structure-aware | Split by headings, then paragraphs, then sentences. |
| Semantic chunking | Start a new chunk where the topic changes. |
| Parent-child | Search small chunks, but give the model the larger parent section. |
| Multi-representation | Embed a short summary of each chunk or document, but return the full text. |
| Hierarchical summaries (RAPTOR-style) | Summaries of groups of chunks, searched along with the chunks. |

Also compare two embedding models, and record the storage size and indexing time.

### 5. Retrieval (finding the passages)

| Technique | Idea |
| --- | --- |
| Baseline: dense vectors | pgvector similarity search, top 5. Also try top 3 and top 10. |
| Keyword (BM25 or Postgres full-text) | Exact-word matching. Strong for names and clause titles. |
| Hybrid with rank fusion | Combine vector and keyword results with reciprocal rank fusion. |
| Cross-encoder re-ranking | Retrieve 20, re-score each with a re-ranking model, keep the best 5. |
| MMR (diversity) | Pick passages that are relevant but different from each other. |
| Contextual compression | Trim each passage to the sentences that matter before generation. |

### 6. Generation (writing the answer)

| Technique | Idea |
| --- | --- |
| Baseline: plain prompt | "Answer using this context." |
| Strict grounded prompt | Answer only from the context, cite passage IDs, say "not found" otherwise. |
| Quote first | Extract the supporting quotes, then answer from the quotes. |
| Retrieval grading (CRAG-style) | The model grades each passage as relevant or not. If none are, re-search or say "not found". |
| Self-check | A second pass checks every claim against the passages and removes unsupported ones. |
| Abstention threshold | If the best retrieval score is below a set value, answer "not found" without calling the model. |

Also compare two Gemini models (small and large) on cost, speed and score.

## Scoring criteria

### Retrieval (computed automatically from the labelled source passage)

| Metric | Meaning |
| --- | --- |
| Hit@5 | Was a correct source passage in the top 5? (yes/no, averaged) |
| MRR | How high was the first correct passage? (1 for first, 0.5 for second, and so on) |
| Recall@k | What share of all the correct passages were found in the top k? |

### Answer quality (scored per question, 0 to 2)

| Criterion | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Correctness | Wrong or missing | Partly right or incomplete | Matches the reference answer |
| Faithfulness | Contains claims not in the retrieved text | One minor unsupported detail | Every claim is supported by the retrieved text |
| Citation accuracy | No citation or wrong passage | Right document, wrong passage | The cited passage supports the answer |
| Honesty on unanswerable questions | Invents an answer | Hedges but still guesses | Clearly says "not found" |

- **Pass:** Correctness 2, Faithfulness 2 and Citation accuracy at least 1. For "not-found" questions, pass means Honesty 2.
- **Headline score:** passed questions divided by total questions.
- **Also report:** average tokens per question, calls per question, and median and 95th percentile response time.

### Who scores

1. An AI judge scores each answer with a fixed rubric prompt kept in `evals/judge_prompt.md`. Use a different model from the one that wrote the answer when possible.
2. You hand-score a random 20% of answers. If you and the judge agree on fewer than 80%, fix the rubric prompt before trusting any scores.
3. Keep the judge prompt, the model name and the temperature fixed across all runs, so scores are comparable.

## Reporting

At each milestone, put one table in the README: stage, technique tried, dev score, test score (at milestone ends only), cost and speed, and a one-line reason for the choice. Include the techniques that lost.

## Later: feedback loop (not part of M1 or M2)

Add this when time allows, after the comparison work.

- Add thumbs up and down and a "wrong answer" button, with the result stored in Postgres next to the question, passages and answer.
- Add every flagged failure to the dev set as a new question with the corrected answer.
- Log a low retrieval score, then retry automatically with a different technique, such as multi-query or a larger top-k.
- Review the failures each Friday and re-run the eval, so every fix shows up as a score change.
- Keep this separate from the test set. Failures found by users go into the dev set only.

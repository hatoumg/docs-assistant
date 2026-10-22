# Evals

One JSON file per document set, for example `technical.json`. Each entry:

```json
{
  "question": "What does X do?",
  "answer": "One sentence with the correct answer.",
  "source": "file name and passage where the answer appears",
  "kind": "direct | multi-passage | not-found"
}
```

Write 10 to 20 per set. Include some questions the documents cannot answer, where the correct response is "not found".

## Dev set and test set

There is no training set, because no model is trained here. There are two kinds of evaluation data:

| Set | Used for | Rule |
| --- | --- | --- |
| Dev | Tuning while building (chunk size, prompts, technique choice) | Look at failures and change things freely. |
| Test | The score reported in the README | Different documents and different questions. Do not look at it while tuning. Run it only at milestone ends. |

Rules:

1. Split by document, not only by question. A document must never be in both sets.
2. Decide the split before tuning and record it below.
3. If you change something because of a test failure, move that question to dev and write a new test question.
4. Report both scores, for example "dev 85%, test 72%".

### Current split

| Set | Documents | Questions |
| --- | --- | --- |
| Dev | FastAPI tutorial sample (5 files), about 5 CUAD contracts (to choose) | `technical.json`, `contracts-dev.json` (to write) |
| Test | 5 to 10 different CUAD contracts (to choose) | `contracts-test.json` (to write) |

The scoring criteria, judge and comparison method are in [docs/RAG-EXPERIMENTS.md](../docs/RAG-EXPERIMENTS.md).

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

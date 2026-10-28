# Project plan: docs-assistant

## Problem

People have documents they cannot search well. They want answers they can trust, with the source shown.

## Users

Anyone with a folder of PDFs or Markdown files who wants to ask questions in plain language. The first user is the author, using their own notes and projects.

## MVP

A user uploads a document, asks a question, and gets an answer with a citation to the passage it came from. It runs locally with `docker compose up` and scores at least 70% on a written test set of 10 questions.

## Out of scope for the MVP

Agent loop, Redis, MCP server, Kubernetes, Terraform and AWS, monitoring dashboards, GraphQL, a React front end.

## Success measures

- Eval accuracy of 70% or more on document set 1.
- Tests pass in CI.
- A stranger can run the project in 5 minutes by following the README.

## Milestones

| Milestone | Due | Main result |
| --- | --- | --- |
| M1 MVP | 2026-11-04 | Cited answers locally, eval at 70% or more |
| M2 Agent and quality | 2026-11-11 | Agent, cache, MCP, evals in CI |
| M3 Production deploy | 2026-11-18 | Running on k3s and AWS, then torn down |
| M4 Monitoring and polish | 2026-11-18 | Dashboards, README, demo |

If M1 takes longer than two weeks, move the later milestones. Skipping a milestone is better than shipping it half finished.

## Risks

- Free AI API limits: cap requests per day and cache answers.
- Messy PDFs: start with Markdown and text files.
- Scope creep: anything not in the MVP waits for a later milestone.
- AWS cost: set a $1 budget alert before the first deploy and tear down after the demo.

## Decisions log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-21 | Use pgvector inside PostgreSQL | One database to run instead of a separate vector store |
| 2026-10-22 | Split evaluation data into dev and test sets | Avoid tuning to the questions used for the reported score |
| 2026-10-22 | Compare RAG techniques one stage at a time against a baseline | Shows which change caused which score change |
| 2026-10-23 | Keep a simple text chunker for the MVP and compare document parsers (Docling, Unstructured, LlamaParse, MarkItDown) on the PDF sets in M2 | Markdown and text need no parser, while PDFs and tables do |

## Evaluation and experiments

- Evaluation data is split into a dev set (for tuning) and a test set (for reporting). See `evals/README.md`.
- Techniques for query translation, routing, query construction, indexing, retrieval and generation are compared one stage at a time against a baseline, using the scoring criteria in `docs/RAG-EXPERIMENTS.md`.
- Document parsing options are compared on the PDF sets only (stage 0 in `docs/RAG-EXPERIMENTS.md`).
- This comparison work belongs to milestone M2. M1 uses the baseline of every stage.

## Datasets

- FastAPI tutorial docs (MIT): https://github.com/fastapi/fastapi
- CUAD business contracts (CC BY 4.0): https://www.kaggle.com/datasets/theatticusproject/atticus-open-contract-dataset-aok-beta
- Full list and licenses: `data/README.md`

## Future work (when time allows)

- Feedback loop: thumbs up and down, flagged failures added to the dev set, and automatic retry with a different technique when retrieval confidence is low. Details at the end of `docs/RAG-EXPERIMENTS.md`.

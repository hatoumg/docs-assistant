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

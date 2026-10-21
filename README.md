# docs-assistant

An AI assistant that answers questions about your documents and shows the passage each answer came from.

**Status:** planning. See [docs/PLAN.md](docs/PLAN.md) for scope, milestones and the backlog.

## Planned stack

TypeScript API, Python answer worker, PostgreSQL with pgvector, Gemini, Docker Compose, GitHub Actions. Later: Redis, an agent loop, an MCP server, Kubernetes, Terraform on AWS, Prometheus and Grafana.

## Quick start

Coming in milestone M1. The goal is `docker compose up` on a fresh clone in under 5 minutes.

## Project process

- Work is tracked as GitHub Issues, grouped by milestone, on the project board.
- Nothing is committed to `main` directly. Every change is a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

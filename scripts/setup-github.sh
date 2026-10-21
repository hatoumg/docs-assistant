#!/usr/bin/env bash
# Creates labels, milestones and the 12 starter issues.
# Requires the GitHub CLI (gh) and `gh auth login` done by you first.
# Run from the repo folder:  bash scripts/setup-github.sh
set -euo pipefail

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "Setting up $REPO"

label() { gh label create "$1" --color "$2" --description "$3" --force >/dev/null; }
label feature "0e8a16" "New functionality"
label bug "d73a4a" "Something is broken"
label infra "5319e7" "Docker, CI, cloud, Kubernetes"
label docs "0075ca" "Documentation"
label testing "fbca04" "Tests and evals"
label data "c5def5" "Document sets and datasets"
label "priority: high" "b60205" "Do first"
label "priority: low" "cfd3d7" "Do later"

milestone() {
  gh api "repos/$REPO/milestones" -f title="$1" -f due_on="$2" -f description="$3" >/dev/null 2>&1 || echo "Milestone '$1' may already exist"
}
milestone "M1 MVP" "2026-11-04T23:59:59Z" "Working RAG locally with cited answers"
milestone "M2 Agent and quality" "2026-11-11T23:59:59Z" "Agent loop, cache, MCP, evals in CI"
milestone "M3 Production deploy" "2026-11-18T23:59:59Z" "k3s and AWS deploy, then teardown"
milestone "M4 Monitoring and polish" "2026-11-18T23:59:59Z" "Dashboards, README, demo"

issue() { # title, labels, milestone, body
  gh issue create --title "$1" --label "$2" --milestone "$3" --body "$4" >/dev/null
  echo "Created: $1"
}
STORY="As a user with a folder of documents, I want"
M="M1 MVP"

issue "Docker Compose with Postgres and pgvector" "infra,priority: high" "$M" "$STORY a one-command local setup, so that I can run the project quickly.

- [ ] \`docker compose up\` starts PostgreSQL with pgvector
- [ ] A test query works
- [ ] Setup steps added to the README"
issue "Database schema for documents and chunks" "feature,priority: high" "$M" "$STORY my documents stored in chunks, so that they can be searched.

- [ ] Migration creates documents and chunks tables
- [ ] Chunks have a vector column
- [ ] Migration runs from a clean database"
issue "Collect document set 1 (technical docs)" "data,priority: high" "$M" "$STORY sample documents to test with, so that I can measure quality.

- [ ] 5 to 10 files in data/samples/technical/
- [ ] License file included
- [ ] data/README.md updated"
issue "Write 10 test questions for set 1" "data,testing,priority: high" "$M" "$STORY a written test set, so that I know if answers are correct.

- [ ] evals/technical.json has 10 questions
- [ ] Each has an answer and source passage
- [ ] Includes at least 2 'not found' questions"
issue "Upload and chunk a document" "feature,priority: high" "$M" "$STORY to upload a file, so that it can be searched.

- [ ] Upload endpoint accepts Markdown and text files
- [ ] Text is split into chunks of about 500 tokens
- [ ] A test checks the chunk count for a sample file"
issue "Create and store embeddings" "feature,priority: high" "$M" "$STORY chunks turned into vectors, so that search works by meaning.

- [ ] Every chunk has a stored embedding
- [ ] Embedding calls are rate limited
- [ ] A test covers the stored vectors"
issue "Search chunks by similarity" "feature,priority: high" "$M" "$STORY the closest passages to my question, so that answers use the right text.

- [ ] A query returns the 5 closest chunks
- [ ] A test checks a known question against a known chunk"
issue "Answer with Gemini and cite sources" "feature,priority: high" "$M" "$STORY an answer with the passage it came from, so that I can trust it.

- [ ] Response contains the answer and source passages
- [ ] Says 'not found' when the documents do not contain the answer
- [ ] A request cap protects the API key"
issue "API with login" "feature" "$M" "$STORY to sign in, so that only I can see my documents.

- [ ] Endpoints reject requests without a valid token
- [ ] Passwords are hashed
- [ ] Tests cover login and a rejected request"
issue "Unit tests for API and worker" "testing" "$M" "$STORY reliable code, so that changes do not break it.

- [ ] Jest suite runs for the API
- [ ] pytest suite runs for the worker
- [ ] Both run with one documented command"
issue "CI on every pull request" "infra,testing,priority: high" "$M" "$STORY automatic checks, so that broken code cannot reach main.

- [ ] GitHub Actions runs tests and the eval
- [ ] Result shows as pass or fail on the pull request
- [ ] Branch protection requires the check"
issue "README setup guide" "docs" "$M" "$STORY clear setup steps, so that I can run the project in 5 minutes.

- [ ] A fresh clone runs by following the README
- [ ] Architecture diagram included
- [ ] Eval results shown"
echo "Done. Now create the Project board on GitHub (see docs/PLAN.md, Stage 3)."

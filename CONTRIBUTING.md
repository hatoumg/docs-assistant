# Contributing

## Workflow (GitHub Flow)

1. Pick one issue from the board and move it to **In progress**.
2. Create a branch: `<type>/<issue-number>-<short-name>`, for example `feature/5-chunk-documents`.
   Types: `feature`, `fix`, `docs`, `test`, `chore`.
3. Commit in small steps using Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
4. Push and open a pull request. Write `Closes #<issue>` in the description.
5. Wait for CI to pass and read your own diff.
6. Use **Squash and merge**, then delete the branch.

## Definition of ready

- Has a user story and an acceptance checklist.
- Small enough to finish in one to two days.
- Has a label and a milestone.

## Definition of done

- Every acceptance box is ticked.
- New code has tests, and all tests and the eval pass in CI.
- README or `docs/` updated if behavior changed.
- No secrets, API keys or large data files in the commit.

## Secrets

Never commit secrets. Copy `.env.example` to `.env` (git-ignored) and fill it in locally.

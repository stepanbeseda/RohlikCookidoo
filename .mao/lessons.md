# Lessons from MAO runs

Memory shared across PRs and worktrees of this project. Agent `memory:` is
stored per worktree, which is why this is a file in the repo. The
orchestrator adds findings whose shape repeats at the end of a run. All
agents read it before working; general lessons are in the skill's
`references/lessons-general.md`.

## Error shapes that repeated

(batch 2026-10-15, six PRs: the spec check found blocking issues in 4 of 6
specs; all were fixed in the spec before implementation, none reached review)
- A guard grep matches the spec's own new code (PR 02: a grep for old names
  hit the new test names; PR 03: G3 `CookidooClient(` hit the prescribed
  real-client test T7). Run every "must be empty" grep against the tree the
  spec builds, tests included, not only against `main`.
- Spec written against a base that moved (PR 05: a prototype `shopping.py`
  from before PR 02 and test counts from before PR 02 merged). Dependent
  PRs are cut from the merged base; re-measure counts and prototype files
  on the base the implementer will use.
- A new import shadows a loop variable (PR 04: `import text` vs the loop
  variable `text` in `write_current_files` -> ruff F402). Alias the import
  (`from rohlik_cookidoo import text as text_module`) or name the loop
  variable differently.

## Spec error shapes (designer)

- Negative greps (G1..) that the spec's own tests or new files satisfy; stale
  prototype files and test counts after a dependency merged; imports in
  prescribed tests that clash with names in the same module (see above).

## Operational lessons

- The main checkout's `.git/index` is owned by root; `git fetch` and
  `git status` fail there, `git worktree add` works. Work in a worktree
  under `.claude/worktrees/`, which has its own index.
- There is no Python environment on the host; `scripts/check.sh` runs the
  checks in Docker.
- The host has no global git identity; agents commit and rebase with
  `git -c user.name=... -c user.email=...` (a rebase stopped once for this).
- In worktrees `git rev-parse <a> <b>` with two revisions failed; use one
  revision per call.

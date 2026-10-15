# Lessons from MAO runs

Memory shared across PRs and worktrees of this project. Agent `memory:` is
stored per worktree, which is why this is a file in the repo. The
orchestrator adds findings whose shape repeats at the end of a run. All
agents read it before working; general lessons are in the skill's
`references/lessons-general.md`.

## Error shapes that repeated

## Spec error shapes (designer)

## Operational lessons

- The main checkout's `.git/index` is owned by root; `git fetch` and
  `git status` fail there, `git worktree add` works. Work in a worktree
  under `.claude/worktrees/`, which has its own index.
- There is no Python environment on the host; `scripts/check.sh` runs the
  checks in Docker.

# MAO — project configuration RohlikCookidoo

Project layer of the `/mao` skill (sbskills `mao`). Whatever stands here
takes precedence over the skill's general procedure. The repo's own rules
live in `README.md` and the module docstrings; they are linked, not copied.

## Files

- Checklist: `.mao/checklist.md`
- Lessons: `.mao/lessons.md`
- Host gate: none

## Plan

- File: `docs/plan.md`
- Decisions and boundaries: `## 1.`
- Common PR conditions: `## 2.`
- PR table: `## 3.`; row `| NN | <name> | <depends on> | <status> |`,
  read the number with the regex `^\| (\d{2}) \|`
- Chapters: `### PR NN — <name>`; a new one goes after the last `### PR`
  and before `## 5.`
- Open items: `## 5.`

## Commands

- Check (must be green before the PR): `scripts/check.sh`. It runs the CI
  test job (ruff, pytest, plugin manifest JSON) in a throwaway
  `python:3.12-slim` container, because this machine has no Python dev
  environment (no pip, venv or uv). It copies the working tree as git sees it
  (tracked + untracked, ignored files such as `.env` excluded) and ends with
  `CHECK OK tree=<commit>[-dirty] python=3.12 pytest=<n>_passed…` or
  `CHECK FAILED …` with exit code 1. `--python 3.13` / `3.14` runs another
  version from the CI matrix.
- Targeted tests: none separately; the full suite takes a few seconds, the
  container start and `pip install` most of the minute.
- Forbidden: creating a local venv or installing Python packages on the host;
  hand-editing `uv.lock` dependency entries; running `server.py` against the
  real Cookidoo account.

## Git

- Base branch: `main`; remote: `origin` (github.com/stepanbeseda/RohlikCookidoo)
- **Always work in a worktree** (`git worktree add .claude/worktrees/mao-prNN
  -b mao/prNN-<slug> origin/main`; `.claude/` is gitignored). The main
  checkout's `.git/index` is owned by root, so git commands that touch the
  index fail there until it is fixed with
  `sudo chown ubuntu:ubuntu .git/index`.
- Run branch: `mao/pr<NN>-<slug>`
- Commits: English Conventional Commits (`feat:`, `fix:`, `refactor:`,
  `docs:`, `chore:`), a short subject, and a body of `- ` bullet lines
  describing each change. Trailers as the session requires
  (`Co-Authored-By: …`).
- PR title: `<name from the table> (PR NN)`, sentence case, like the
  history ("Self-host behind Tailscale Funnel by default").
- Merge: `gh pr merge --merge --delete-branch` (the history uses merge
  commits).
- CI checks: `test (3.12)`, `test (3.13)`, `test (3.14)`, `docker`.

## Test host

None. The live server (Docker + Tailscale Funnel, see `README.md`) is the
user's production; nothing in a run touches it.

## Preview

None (no UI).

## Parallel runs

- Limit: 2 concurrent `scripts/check.sh` runs.
- Private names: none needed; `scripts/check.sh` uses `--rm` containers
  without names or ports. The `rohlik-cookidoo-pip-cache` Docker volume is a
  shared pip cache and safe to share.
- Schema migrations: none (no database). Changes to the format of
  `pantry.txt`, `products.json` or `preferences.json` are migrations — see
  the designer rules.
- Rebase after the base branch was merged under you:
  `git rebase origin/main`; a tree-identical rebase (`git diff <checked>
  HEAD` empty) keeps the check valid.

## Stop-and-ask

- Anything that deploys, restarts or reconfigures the live server
  (`docker compose`, Tailscale, the VPS).
- Reading, printing or editing `.env`, or the real `pantry.txt`,
  `products.json`, `preferences.json` in a data directory.
- Any real Cookidoo login or Rohlik call, including "spikes".
- Version bumps, tags, releases, publishing the plugin or marketplace.
- `--force` pushes, deleting branches other than the run's own.

## Role rules

### Designer (in addition to the skill's spec)

- The MCP tools' names, input fields, output fields, docstrings and
  `rohlik_cookidoo/guide.py` (`INSTRUCTIONS`) are the interface the model
  sees. List every change to them under "Contracts" as old → new, and say
  how a caller using the old shape is treated.
- Persisted files (`pantry.txt`, `products.json`, `preferences.json`) exist
  on a live deployment. A spec that changes how they are read or written
  states how the current files load, with a test fixture in today's format.
- Tests go through the deepened module's interface ("replace, don't layer"):
  name which old tests are deleted and where each case now lives.
- Every bug the plan chapter names gets a regression test that fails on
  `main`; the spec says how the implementer shows it failed.

### Worker (additional spec checks)

- Every tool field name the spec cites is checked against
  `rohlik_cookidoo/server.py` and `rohlik_cookidoo/guide.py`.
- Every "fails on main" claim is run on `origin/main` (in a scratch
  worktree), not read.

### Implementer

- Run `scripts/check.sh`; quote its last line.
- Do not bump the version (`pyproject.toml`, `.claude-plugin/plugin.json`,
  `uv.lock`); a release commit after the train does that.
- No new runtime dependencies unless the spec names one.
- Match the surrounding code: English identifiers and docstrings, the
  existing comment density, ruff line length 100.

### Reviewer (repo rules)

- Tool docstrings, `guide.py` and `README.md` agree with the behaviour.
- No test reads the repository's `.env` or the real data directory.
- No test talks to the network (Cookidoo is faked).

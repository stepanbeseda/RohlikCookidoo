# Checklist

The implementer goes through it in self-review, the reviewer in round 1;
each item gets `ok` / `finding` / `n/a` — an empty line is a blocking
finding. Add items from repeated findings.

## Acceptance criteria and tests

- [ ] Every acceptance criterion verifiable offline has a test that
  **fails** when the feature is disabled (mutation: comment out a line, the
  test must go red).
- [ ] Every bug named in the plan chapter has a regression test that fails
  on `main`.
- [ ] Tests call the deepened module's interface; no test imports a helper
  the spec made private.
- [ ] The test measures behaviour or parsed structure, not file text —
  `"x" in source` is satisfied by a comment too.
- [ ] Tests do not depend on the environment (`.env`, HOME, time zone, file
  order, network, the real data directory).
- [ ] Nothing was silently weakened: every deleted test has a "new home"
  line in the PR body.
- [ ] Every negative grep in the spec ("must be empty") was run against the
  tree the spec builds (its new tests and files included), not just against
  `main`; its positive hit on `main` is shown.
- [ ] Counts and file lists in the spec (test counts, prototype files) were
  measured on the base the implementer starts from, after every dependency
  merged.
- [ ] A new import in a module or test does not shadow a local or loop
  variable (ruff F402); the check ran with the new import in place.
- [ ] Time: fixed dates and relative dates in one test file are a calendar
  bomb — freeze the whole file or compute everything from `date.today()`.

## Failure

- [ ] A tool error reaches the model as a `ToolError` with a message that
  says what to fix, not a bare `KeyError` or traceback.
- [ ] Zero, an empty string and a missing value are handled deliberately
  (`packages: 0` is not "unset").
- [ ] Clean-up (temp files, sessions) is in `finally`, not on a single
  failure branch.

## MCP interface

- [ ] Tool names, input and output fields changed only as the spec's
  "Contracts" says; old shapes handled as the spec says.
- [ ] Tool docstrings and `rohlik_cookidoo/guide.py` `INSTRUCTIONS` match the
  new behaviour; grep for the old wording is empty.

## Configuration and secrets

- [ ] A new config value has its default in one place and is documented in
  `.env.example` and `README.md`.
- [ ] No secrets, personal paths or deployment identity in code or any
  commit (`git log -p`).

## Data

- [ ] `pantry.txt`, `products.json` and `preferences.json` written by the
  current release still load (fixture test); an invalid file is handled
  with a warning, not a crash.
- [ ] Writes are atomic (temp file + replace).

## Documentation

- [ ] Docstrings, `README.md` and `skills/*/SKILL.md` describe the new
  behaviour; links lead to existing files.

#!/usr/bin/env bash
# Run the CI test job (ruff, pytest, plugin manifests) in a throwaway container,
# so no local Python environment is needed. The working tree is copied in as
# git sees it (tracked and untracked files, minus ignored ones such as .env).
#
# Usage: scripts/check.sh [--python 3.13]
# Ends with one line: CHECK OK tree=<commit>[-dirty] python=<v> pytest=<summary>
set -euo pipefail

python=3.12
if [[ "${1:-}" == "--python" ]]; then
  python=${2:?--python needs a version}
fi

cd "$(git rev-parse --show-toplevel)"
tree=$(git rev-parse --short HEAD)
[[ -z "$(git status --porcelain)" ]] || tree="$tree-dirty"

log=$(mktemp)
trap 'rm -f "$log"' EXIT

set +e
git ls-files -z --cached --others --exclude-standard --deduplicate \
  | tar --null --ignore-failed-read -T - -cf - 2>/dev/null \
  | docker run --rm -i \
      -e PIP_ROOT_USER_ACTION=ignore -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
      -v rohlik-cookidoo-pip-cache:/root/.cache/pip \
      "python:${python}-slim" bash -euo pipefail -c '
        mkdir /work && cd /work && tar -xf -
        pip install -q ".[dev]"
        ruff check .
        python -m pytest -q -p no:cacheprovider
        python -m json.tool .claude-plugin/plugin.json > /dev/null
        python -m json.tool .claude-plugin/marketplace.json > /dev/null
        echo "__CHECK_PASSED__"
      ' 2>&1 | tee "$log"
set -e

summary=$(grep -E '^[0-9]+ (passed|failed)' "$log" | tail -1 | sed 's/ in [0-9.]*s.*//; s/, /,/g; s/ /_/g')
if grep -q '^__CHECK_PASSED__$' "$log"; then
  echo "CHECK OK tree=$tree python=$python pytest=${summary:-none}"
else
  echo "CHECK FAILED tree=$tree python=$python pytest=${summary:-none}"
  exit 1
fi

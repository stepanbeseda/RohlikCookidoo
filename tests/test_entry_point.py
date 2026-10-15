"""The `.env` file is read by the entry point `server.py`, never by importing the package."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
# Replaces load_dotenv with a recorder, so no real .env file is ever read
PROBE = (
    "import importlib, json, sys, dotenv\n"
    "calls = []\n"
    "dotenv.load_dotenv = lambda *args, **kwargs: calls.append(str(args[0])) or True\n"
    "importlib.import_module(sys.argv[1])\n"
    "print(json.dumps(calls))\n"
)


def load_dotenv_calls(module: str, cwd: Path) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-c", PROBE, module],
        cwd=cwd, env={**os.environ, "PYTHONPATH": str(REPOSITORY)},
        capture_output=True, text=True, timeout=120, check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_importing_the_server_loads_no_env_file(tmp_path):
    assert load_dotenv_calls("rohlik_cookidoo.server", tmp_path) == []


def test_entry_point_loads_the_env_file_next_to_it(tmp_path):
    assert load_dotenv_calls("server", tmp_path) == [str(REPOSITORY / ".env")]

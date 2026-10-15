"""Entry point of the RohlikCookidoo MCP server: `python server.py`.

Reads a `.env` file next to this file as a fallback for environment variables.
"""

from pathlib import Path

from dotenv import load_dotenv

from rohlik_cookidoo.server import main, mcp  # noqa: F401 - `mcp` is found by `fastmcp run`

load_dotenv(Path(__file__).parent / ".env")

if __name__ == "__main__":
    main()

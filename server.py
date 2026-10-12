"""Entry point of the RohlikCookidoo MCP server: `python server.py`."""

from rohlik_cookidoo.server import main, mcp  # noqa: F401 - `mcp` is found by `fastmcp run`

if __name__ == "__main__":
    main()

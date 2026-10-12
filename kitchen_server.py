"""Entry point of the kitchen MCP server: `python kitchen_server.py`."""

from rohlik_cookidoo.kitchen_server import mcp

if __name__ == "__main__":
    mcp.run()

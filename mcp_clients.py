"""MCP connections to the Cookidoo and Rohlik servers.

Uses async context managers to keep both connections open for the whole
run of the application.
"""

import json
import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from config import AppConfig


class MCPConnectionManager:
    """Manages connections to the MCP servers.

    Keeps stdio connections to the Cookidoo and Rohlik servers open and uses
    an AsyncExitStack to close them cleanly on exit.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        # AsyncExitStack keeps every entered context (connection) open
        # and closes them all on aclose()
        self._exit_stack = AsyncExitStack()
        self.cookidoo_session: ClientSession | None = None
        self.rohlik_session: ClientSession | None = None

    async def connect_cookidoo(self) -> None:
        """Connect to the Cookidoo MCP server (local, over stdio).

        The server is cookidoo_server.py from this repository, started as a
        local process with `fastmcp run` and reached over stdin/stdout.
        """
        server_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "cookidoo_server.py"
        )

        # Each server gets only its own credentials, not the whole environment
        env = {
            **get_default_environment(),
            "COOKIDOO_EMAIL": self.config.cookidoo_email,
            "COOKIDOO_PASSWORD": self.config.cookidoo_password,
        }
        for optional in ("COOKIDOO_COUNTRY", "COOKIDOO_LANGUAGE", "PANTRY_PATH"):
            if os.getenv(optional):
                env[optional] = os.environ[optional]

        server_params = StdioServerParameters(
            command="fastmcp",
            args=["run", server_path],
            env=env,
        )

        # stdio_client is an async context manager and has to stay open
        transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = transport

        # Create and initialize the MCP session
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        self.cookidoo_session = session
        print("Připojeno ke Cookidoo MCP serveru.")

    async def connect_rohlik(self) -> None:
        """Connect to the Rohlik MCP server (local, over stdio).

        Uses @tomaspavlin/rohlik-mcp pinned to a fixed version. The official
        mcp.rohlik.cz signs in through OAuth in a browser, which this CLI
        cannot do, and its tool names may differ.
        """
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@tomaspavlin/rohlik-mcp@3.3.0"],
            env={
                **get_default_environment(),
                "ROHLIK_USERNAME": self.config.rohlik_email,
                "ROHLIK_PASSWORD": self.config.rohlik_password,
                "ROHLIK_BASE_URL": "https://www.rohlik.cz",
            },
        )

        transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = transport

        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        self.rohlik_session = session
        print("Připojeno k Rohlik MCP serveru.")

    async def call_cookidoo_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Call a tool on the Cookidoo MCP server.

        Args:
            name: Tool name (e.g. "get_planned_recipes_this_week", "get_recipe_details")
            arguments: Tool arguments

        Returns:
            Structured result of the tool

        Raises:
            RuntimeError: If the tool reports an error.
        """
        if not self.cookidoo_session:
            raise ConnectionError("Nejsi připojen ke Cookidoo. Zavolej connect_cookidoo().")

        result = await self.cookidoo_session.call_tool(name, arguments or {})
        text = "\n".join(part.text for part in result.content if hasattr(part, "text"))
        if result.isError:
            raise RuntimeError(text)
        if result.structuredContent is not None:
            return result.structuredContent
        return json.loads(text)

    async def call_rohlik_tool(self, name: str, arguments: dict | None = None) -> str:
        """Call a tool on the Rohlik MCP server."""
        if not self.rohlik_session:
            raise ConnectionError("Nejsi připojen k Rohlíku. Zavolej connect_rohlik().")

        result = await self.rohlik_session.call_tool(name, arguments or {})
        texts = [part.text for part in result.content if hasattr(part, "text")]
        return "\n".join(texts)

    async def list_tools(self, server: str = "both") -> dict:
        """List the tools available on the MCP servers.

        Args:
            server: "cookidoo", "rohlik", or "both"
        """
        tools = {}

        if server in ("cookidoo", "both") and self.cookidoo_session:
            result = await self.cookidoo_session.list_tools()
            tools["cookidoo"] = [
                {"name": t.name, "description": t.description, "schema": t.inputSchema}
                for t in result.tools
            ]

        if server in ("rohlik", "both") and self.rohlik_session:
            result = await self.rohlik_session.list_tools()
            tools["rohlik"] = [
                {"name": t.name, "description": t.description, "schema": t.inputSchema}
                for t in result.tools
            ]

        return tools

    async def close(self) -> None:
        """Close all connections."""
        await self._exit_stack.aclose()
        self.cookidoo_session = None
        self.rohlik_session = None
        print("Všechna spojení uzavřena.")

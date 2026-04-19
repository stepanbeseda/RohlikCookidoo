"""Správa MCP připojení ke Cookidoo a Rohlik serverům.

Tento modul používá async kontext manažery pro udržení otevřených spojení
po celou dobu běhu aplikace.

Co je async/await?
- Normální funkce běží postupně: zavolej → čekej na výsledek → pokračuj
- Async funkce umožňují "čekat" na pomalé operace (síť, disk)
  bez blokování celého programu
- await = "počkej na výsledek této operace"
- async def = "tato funkce může používat await"
"""

import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import AppConfig


class MCPConnectionManager:
    """Správce připojení k MCP serverům.

    Udržuje otevřená spojení ke Cookidoo (lokální) a Rohlik (remote) serverům.
    Používá AsyncExitStack pro správné uzavření spojení při ukončení.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        # AsyncExitStack drží otevřené všechny kontexty (spojení)
        # a při uzavření je všechny korektně zavře
        self._exit_stack = AsyncExitStack()
        self.cookidoo_session: ClientSession | None = None
        self.rohlik_session: ClientSession | None = None

    async def connect_cookidoo(self) -> None:
        """Připojení ke Cookidoo MCP serveru (lokální, přes stdio).

        Cookidoo server běží jako lokální proces — spustíme ho příkazem
        `fastmcp run server.py` a komunikujeme přes stdin/stdout.
        """
        server_path = os.path.abspath(
            os.path.join(self.config.cookidoo_server_path, "server.py")
        )

        if not os.path.exists(server_path):
            raise FileNotFoundError(
                f"Cookidoo server nenalezen: {server_path}\n"
                f"Klonuj repo: git clone https://github.com/alexandrepa/mcp-cookidoo.git mcp-cookidoo"
            )

        # Parametry pro spuštění MCP serveru jako subprocess
        server_params = StdioServerParameters(
            command="fastmcp",
            args=["run", server_path],
            env={
                **os.environ,
                "COOKIDOO_EMAIL": self.config.cookidoo_email,
                "COOKIDOO_PASSWORD": self.config.cookidoo_password,
            },
        )

        # stdio_client je async kontext manažer — musíme ho držet otevřený
        transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read_stream, write_stream = transport

        # Vytvoříme MCP session a inicializujeme ji
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        self.cookidoo_session = session
        print("Připojeno ke Cookidoo MCP serveru.")

    async def connect_rohlik(self) -> None:
        """Připojení k Rohlik MCP serveru (self-hosted, lokální stdio).

        Používáme @tomaspavlin/rohlik-mcp, protože hostovaný mcp.rohlik.cz
        má rozbitou interní autentizaci (v5/login/access_token vrací 401
        pro validní credentials).
        """
        server_params = StdioServerParameters(
            command="npx",
            args=["-y", "@tomaspavlin/rohlik-mcp@3.3.0"],
            env={
                **os.environ,
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

    async def call_cookidoo_tool(self, name: str, arguments: dict | None = None) -> str:
        """Zavolá nástroj na Cookidoo MCP serveru.

        Args:
            name: Název nástroje (např. "connect_to_cookidoo", "get_recipe_details")
            arguments: Argumenty pro nástroj

        Returns:
            Textový výsledek z nástroje
        """
        if not self.cookidoo_session:
            raise ConnectionError("Nejsi připojen ke Cookidoo. Zavolej connect_cookidoo().")

        result = await self.cookidoo_session.call_tool(name, arguments or {})

        # MCP výsledek může obsahovat více částí — spojíme textové
        texts = [part.text for part in result.content if hasattr(part, "text")]
        return "\n".join(texts)

    async def call_rohlik_tool(self, name: str, arguments: dict | None = None) -> str:
        """Zavolá nástroj na Rohlik MCP serveru."""
        if not self.rohlik_session:
            raise ConnectionError("Nejsi připojen k Rohlíku. Zavolej connect_rohlik().")

        result = await self.rohlik_session.call_tool(name, arguments or {})
        texts = [part.text for part in result.content if hasattr(part, "text")]
        return "\n".join(texts)

    async def list_tools(self, server: str = "both") -> dict:
        """Vypíše dostupné nástroje z MCP serverů.

        Užitečné pro zjištění, jaké nástroje Rohlik server nabízí.

        Args:
            server: "cookidoo", "rohlik", nebo "both"
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
        """Uzavře všechna spojení."""
        await self._exit_stack.aclose()
        self.cookidoo_session = None
        self.rohlik_session = None
        print("Všechna spojení uzavřena.")

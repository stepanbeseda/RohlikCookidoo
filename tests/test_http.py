"""Tests for the HTTP mode: the secret URL token and host checks."""

import asyncio

import pytest
from starlette.testclient import TestClient

from rohlik_cookidoo.server import http_settings, mcp

TOKEN = "t0ken-" + "a" * 40
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
ENV = {"MCP_AUTH_TOKEN": TOKEN, "DOMAIN": "k.example.com"}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def client(env: dict, host: str) -> TestClient:
    settings = http_settings(env)
    app = mcp.http_app(
        **{k: v for k, v in settings.items() if k not in ("host", "port")}
    )
    return TestClient(app, base_url=f"https://{host}")


def asgi_get_status(env: dict, host_header: str) -> int:
    """GET /health the way a real server sees it: bound to 0.0.0.0, Host from the client.

    TestClient cannot express this, because it reports the requested host as
    the address the server is bound to.
    """
    settings = http_settings(env)
    app = mcp.http_app(**{k: v for k, v in settings.items() if k not in ("host", "port")})
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": "/health", "raw_path": b"/health", "query_string": b"",
        "headers": [(b"host", host_header.encode())],
        "server": ("0.0.0.0", 8000), "client": ("203.0.113.5", 40000),
    }
    statuses = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    asyncio.run(app(scope, receive, send))
    return statuses[0]


class TestSettings:
    def test_token_becomes_the_path(self):
        settings = http_settings({"MCP_AUTH_TOKEN": TOKEN})
        assert settings["path"] == f"/{TOKEN}/mcp"
        assert (settings["host"], settings["port"]) == ("127.0.0.1", 8000)
        assert "allowed_hosts" not in settings

    def test_host_port_and_domain(self):
        settings = http_settings({
            "MCP_AUTH_TOKEN": TOKEN, "HOST": "0.0.0.0", "PORT": "9000", "DOMAIN": "k.example.com",
        })
        assert (settings["host"], settings["port"]) == ("0.0.0.0", 9000)
        assert settings["allowed_hosts"] == ["k.example.com"]

    @pytest.mark.parametrize(
        "token", ["", "short", "a" * 31, "has space " + "a" * 40, "slash/" + "a" * 40]
    )
    def test_missing_short_or_odd_token_is_refused(self, token):
        with pytest.raises(ValueError, match="MCP_AUTH_TOKEN"):
            http_settings({"MCP_AUTH_TOKEN": token})


class TestRequests:

    def test_right_token_reaches_the_server(self):
        with client(ENV, "k.example.com") as http:
            response = http.post(f"/{TOKEN}/mcp", json=INITIALIZE, headers=HEADERS)
        assert response.status_code == 200
        assert "rohlik-cookidoo" in response.text

    @pytest.mark.parametrize("path", ["/mcp", "/", "/wrong-" + "b" * 40 + "/mcp", f"/{TOKEN}"])
    def test_any_other_path_is_not_found(self, path):
        with client(ENV, "k.example.com") as http:
            response = http.post(path, json=INITIALIZE, headers=HEADERS)
        assert response.status_code == 404
        assert TOKEN not in response.text

    @pytest.mark.parametrize(
        ("host", "status"),
        [("k.example.com", 200), ("localhost:8000", 200), ("evil.example.org", 421)],
    )
    def test_other_host_names_are_refused_when_domain_is_set(self, host, status):
        assert asgi_get_status(ENV, host) == status

    def test_any_host_name_is_served_without_a_domain(self):
        assert asgi_get_status({"MCP_AUTH_TOKEN": TOKEN}, "evil.example.org") == 200

    def test_health_needs_no_token_and_says_nothing(self):
        with client(ENV, "localhost") as http:
            response = http.get("/health")
        assert (response.status_code, response.text) == (200, "ok")


def test_secret_is_redacted_from_existing_log_handlers(capsys):
    import logging

    from rohlik_cookidoo.server import redact_from_logs

    logger = logging.getLogger("rohlik_cookidoo.test_redaction")
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        redact_from_logs(TOKEN)
        logger.info("Starting on http://0.0.0.0:8000/%s/mcp", TOKEN)
    finally:
        logger.removeHandler(handler)
    written = capsys.readouterr().err
    assert TOKEN not in written
    assert "/<token>/mcp" in written

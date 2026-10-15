"""The RohlikCookidoo MCP server.

One server for everything that is not Rohlik itself: the Cookidoo meal plan
and recipes, the shopping list, the home pantry, package and cart maths, and
the user's usual products and preferences.

Run it with `python server.py` from the repository root. Configuration comes
from environment variables; `server.py` also reads a `.env` file next to it
as a fallback (importing this module reads none):

    COOKIDOO_EMAIL, COOKIDOO_PASSWORD   Cookidoo credentials
    COOKIDOO_COUNTRY, COOKIDOO_LANGUAGE defaults "cz" / "cs"
    DATA_DIR                            where pantry.txt, products.json and
                                        preferences.json live (default: the
                                        repository root); PANTRY_PATH overrides
                                        the pantry file location

By default the server talks over stdio, for a client on the same machine. Set
MCP_TRANSPORT=http to serve remote clients:

    MCP_AUTH_TOKEN   required; a long random secret that becomes part of the
                     URL: https://<domain>/<token>/mcp
    HOST, PORT       where to listen, defaults 127.0.0.1 and 8000
    DOMAIN           public host name; when set, requests for any other host
                     are refused
"""

import logging
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import NotRequired, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from rohlik_cookidoo.cart import DEFAULT_MINIMUM_ORDER, PurchasePlanError
from rohlik_cookidoo.cart import plan_purchase as plan_purchase_core
from rohlik_cookidoo.cookidoo import CookidooClient, CookidooError
from rohlik_cookidoo.guide import INSTRUCTIONS, QUESTIONNAIRE_CATEGORIES, QUESTIONNAIRE_STEPS
from rohlik_cookidoo.household import Household
from rohlik_cookidoo.shopping import Recipe, ShoppingError, prepare

mcp = FastMCP("rohlik-cookidoo", instructions=INSTRUCTIONS)
cookidoo = CookidooClient()
household: Household | None = None


def current_household() -> Household:
    """The user's files, resolved from the environment on first use."""
    global household
    if household is None:
        household = Household.from_env(os.environ)
    return household


# Errors whose message tells the model what to fix; anything else is a bug
_TOOL_ERRORS = (CookidooError, PurchasePlanError, ShoppingError)


@contextmanager
def _tool_errors() -> Iterator[None]:
    """Hand an error the model can act on to it as a ToolError with the same message."""
    try:
        yield
    except _TOOL_ERRORS as e:
        raise ToolError(str(e)) from e


class PurchaseItem(TypedDict):
    name: str
    package_amount: str
    product_id: NotRequired[int]
    productId: NotRequired[int]
    price: NotRequired[float]
    quantity: NotRequired[float | None]
    unit: NotRequired[str | None]
    packages: NotRequired[int]


class CartLine(TypedDict):
    product_id: NotRequired[int]
    productId: NotRequired[int]
    quantity: NotRequired[float]


class BoughtProduct(TypedDict):
    ingredient: str
    product_id: int
    product_name: str
    package_amount: NotRequired[str]


@mcp.tool()
async def prepare_shopping(
    week_offset: int = 0,
    recipe_ids: list[str] | None = None,
    recipes: list[Recipe] | None = None,
    target_servings: int | None = None,
) -> dict:
    """Build the shopping list for recipes. Start here; do not add amounts up yourself.

    With no arguments it takes the recipes planned in the Cookidoo calendar
    this week (`week_offset: 1` for next week). Pass `recipe_ids` for specific
    Cookidoo recipes, or `recipes` for recipes you read elsewhere, each as
    {"name", "servings", "ingredients": [{"name", "quantity"}]}. Set
    `target_servings` (1 or more) to cook a different number of portions.

    Returns the `recipes` used and three ingredient lists with summed amounts:
    `to_buy`, `check_at_home` (see `check_reason`) and `at_home`. A recipe that
    does not say how many servings it makes is not scaled and carries a `note`.
    Ingredients may carry `usual_product`, what the user bought for them last
    time. Also returns the user's `preferences`, the `failed` recipes with the
    reason, and `pantry_setup_needed`. Ingredient names keep the recipe's form
    (often the Czech genitive, "másla").
    """
    with _tool_errors():
        return await prepare(
            cookidoo,
            current_household(),
            week_offset=week_offset,
            recipe_ids=recipe_ids,
            recipes=recipes,
            target_servings=target_servings,
        )


@mcp.tool()
def plan_purchase(
    items: list[PurchaseItem],
    cart: list[CartLine] | None = None,
    cart_total: float = 0,
    minimum_order: float = DEFAULT_MINIMUM_ORDER,
) -> dict:
    """Work out package counts, leftovers, cart additions and totals. Do not calculate these yourself.

    Pass one item per ingredient with the product you chose: `name`,
    `product_id`, `price` per package, `package_amount` as the shop shows it
    ("500 g", "4 x 125 g", "cca 0,85 kg"), and the ingredient's `quantity` and
    `unit` from the shopping list. Ingredients sharing a product are combined
    into one line; give them the same `price` and `package_amount`, otherwise
    the line is marked inexact and uses the first item's values. Pass the
    current cart as `cart` (`product_id`, `quantity`) with `cart_total`, and the
    shop's `minimum_order` when the cart reports it. `productId` works in place
    of `product_id`; an item or cart line without either is an error.

    Each line has `packages`, `leftover`, `already_in_cart` and `add`. When
    `exact` is false, read `note` and, if needed, call again with `packages`
    set on that item; `packages: 0` buys none. `to_add` is ready for the shop's
    add-to-cart tool; `missing_to_minimum` above zero means the order is below
    the minimum.
    """
    with _tool_errors():
        return plan_purchase_core(items, cart, cart_total, minimum_order)


@mcp.tool()
def record_purchase(products: list[BoughtProduct]) -> dict:
    """Remember the products that were added to the cart after the user confirmed.

    Next time they come back as `usual_product` for the same ingredient.
    """
    return {"remembered": current_household().remember_products(products)}


@mcp.tool()
def forget_product(ingredient: str) -> dict:
    """Forget the usual product for an ingredient, e.g. when the user did not like it."""
    return {"forgotten": current_household().forget_product(ingredient)}


@mcp.tool()
async def get_planned_recipes(week_offset: int = 0) -> dict:
    """List the recipes planned in the Cookidoo calendar for one week.

    `week_offset`: 0 this week, 1 next week, -1 last week. For shopping use
    `prepare_shopping`; this is for looking at the plan.
    """
    with _tool_errors():
        return await cookidoo.week(week_offset)


@mcp.tool()
async def get_recipe_details(recipe_id: str) -> dict:
    """Get one Cookidoo recipe with its ingredients and number of servings."""
    with _tool_errors():
        return await cookidoo.recipe(recipe_id)


@mcp.tool()
def get_pantry() -> dict:
    """List what the user keeps at home: `always_at_home` and `ask_first` items."""
    return current_household().pantry()


@mcp.tool()
def update_pantry(
    always_at_home: list[str] | None = None,
    ask_first: list[str] | None = None,
    remove: list[str] | None = None,
) -> dict:
    """Change the pantry: add items in either mode, switch their mode, or remove them.

    `always_at_home` items are never bought. `ask_first` items are usually at
    home but run out, so the user is asked. Returns the whole pantry.
    """
    return current_household().update_pantry(always_at_home or (), ask_first or (), remove or ())


@mcp.tool()
def get_pantry_questionnaire() -> dict:
    """Get the first-time pantry setup: steps to follow and typical items by category.

    Use it when the pantry is empty or the user wants to set it up again.
    Save the answers with `update_pantry`.
    """
    return {
        "steps": QUESTIONNAIRE_STEPS,
        "categories": QUESTIONNAIRE_CATEGORIES,
        "current_pantry": current_household().pantry(),
    }


@mcp.tool()
def get_shopping_preferences() -> dict:
    """Get the user's lasting preferences and the products they bought before."""
    home = current_household()
    return {"preferences": home.preferences(), "usual_products": home.usual_products()}


@mcp.tool()
def set_shopping_preference(key: str, value: str) -> dict:
    """Store a lasting shopping preference; an empty value removes it.

    Use short keys such as "quality" (bio / cheapest / best value / Rohlik
    brands), "diet" or "avoid". Store only what the user asked you to keep.
    """
    return {"preferences": current_household().set_preference(key, value)}


@mcp.tool()
def get_shopping_guide() -> str:
    """Get the full step-by-step instructions for shopping with this server.

    Read it before the first shopping trip in a conversation if you have not
    seen this server's instructions.
    """
    return INSTRUCTIONS


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health(request: Request) -> Response:
    """Liveness check for the container; reveals nothing and needs no secret."""
    return PlainTextResponse("ok")


_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,}")


def http_settings(env: Mapping[str, str]) -> dict:
    """Read the HTTP settings from the environment, refusing an unsafe setup.

    The server has no login of its own: the secret token in the URL is the
    only thing that keeps strangers out, so a missing or short one is an error.
    """
    token = env.get("MCP_AUTH_TOKEN", "").strip()
    if not _TOKEN.fullmatch(token):
        raise ValueError(
            "MCP_AUTH_TOKEN must be at least 32 characters of letters, digits, '-' or '_'."
            " Generate one with: openssl rand -hex 32"
        )
    settings: dict = {
        "host": env.get("HOST", "127.0.0.1"),
        "port": int(env.get("PORT", "8000")),
        "path": f"/{token}/mcp",
        # No per-connection state: a restart or a second replica does not break clients
        "stateless_http": True,
    }
    domain = env.get("DOMAIN", "").strip()
    if domain:
        # Refuse requests addressed to any other host name (localhost stays allowed)
        settings["host_origin_protection"] = "auto"
        settings["allowed_hosts"] = [domain]
    return settings


class _RedactSecret(logging.Filter):
    """Replace the secret token in log messages, e.g. in the startup URL."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if self._secret in message:
            record.msg, record.args = message.replace(self._secret, "<token>"), ()
        return True


def redact_from_logs(secret: str) -> None:
    """Keep `secret` out of everything the existing log handlers write."""
    redact = _RedactSecret(secret)
    loggers = [logging.getLogger(), *logging.root.manager.loggerDict.values()]
    for logger in loggers:
        for handler in getattr(logger, "handlers", []):
            handler.addFilter(redact)


def main() -> None:
    """Start the server on the transport chosen by MCP_TRANSPORT."""
    if os.getenv("MCP_TRANSPORT", "stdio").strip().lower() == "http":
        try:
            settings = http_settings(os.environ)
        except ValueError as e:
            raise SystemExit(f"Cannot start the HTTP server: {e}") from e
        # The URL contains the secret token, so keep it out of the logs:
        # no startup banner, no per-request access log, and redaction elsewhere.
        redact_from_logs(os.environ["MCP_AUTH_TOKEN"].strip())
        mcp.run(
            transport="http",
            show_banner=False,
            uvicorn_config={"access_log": False},
            **settings,
        )
    else:
        mcp.run()


if __name__ == "__main__":
    main()

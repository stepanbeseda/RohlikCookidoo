---
name: url
description: Shop on Rohlik.cz for a recipe from any web page. Use when the user types /url with a link, or pastes a link to a recipe and asks to buy its ingredients.
argument-hint: "<link to a recipe>"
---

Shop for a recipe from a web page: read the page with whatever web tool you have and extract the recipe name, the number of servings and every ingredient as `{"name": ..., "quantity": ...}`. If you cannot read the page, ask the user to paste the ingredient list. Then call `prepare_shopping` on the kitchen MCP server with the recipe in `recipes` and follow that server's instructions from there.

If you have not seen the kitchen server's instructions in this conversation, call its `get_shopping_guide` tool first. Talk to the user in Czech.

What the user added after the command: $ARGUMENTS

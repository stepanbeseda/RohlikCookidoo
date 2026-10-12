---
name: recept
description: Shop on Rohlik.cz for one Cookidoo recipe. Use when the user types /recept with a recipe ID such as r117476, or asks to buy the ingredients for a specific Cookidoo recipe.
argument-hint: "<recipe ID, e.g. r117476> [počet porcí]"
---

Shop for one Cookidoo recipe: call `prepare_shopping` on the kitchen MCP server with the recipe ID in `recipe_ids` (and `target_servings` if the user gave a number of portions) and follow that server's instructions from there.

If you have not seen the kitchen server's instructions in this conversation, call its `get_shopping_guide` tool first. Talk to the user in Czech.

What the user added after the command: $ARGUMENTS

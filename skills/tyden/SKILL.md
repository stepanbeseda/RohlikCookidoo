---
name: tyden
description: Shop on Rohlik.cz for the recipes planned in the Cookidoo calendar this week or next week. Use when the user types /tyden or asks to buy ingredients for their weekly meal plan ("nákup na tento týden", "nakup podle jídelníčku", "co potřebuju koupit na příští týden").
argument-hint: "[příští]"
---

Shop for the weekly Cookidoo meal plan: call `prepare_shopping` on the kitchen MCP server (`week_offset: 1` if the user said next week, "příští") and follow that server's instructions from there.

If you have not seen the kitchen server's instructions in this conversation, call its `get_shopping_guide` tool first. Talk to the user in Czech.

What the user added after the command: $ARGUMENTS

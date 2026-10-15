# Plan — RohlikCookidoo

Created: 2026-10-15. The plan is extended by `/mao`: every new task gets a
chapter and a table row; existing chapters are never rewritten, only the
"Delivered" blocks and the table status are added.

## 1. Decisions and boundaries

- RohlikCookidoo is one MCP server ("Kitchen") that turns Cookidoo recipes
  into a Rohlik.cz shopping list: meal plan and recipes, summed ingredients,
  the home pantry, package and cart maths, and the user's usual products and
  preferences. It never calls Rohlik itself; the model uses Rohlik's
  official MCP server and passes product data between the two
  (`rohlik_cookidoo/guide.py`).
- Accepted before this plan (GitHub #1–#11): one server instead of two
  (#7), stdio by default and HTTP behind a secret URL (#9), self-hosting
  behind Tailscale Funnel (#10). Python ≥ 3.12, FastMCP 3, no database: the
  state is three files in one data directory (`PANTRY_PATH` / `DATA_DIR`).
- PRs 01–06 come from the architecture review of 2026-10-15. Each one
  deepens a cluster of shallow modules so that its behaviour sits behind one
  small interface and is tested through it. They change structure and fix
  the bugs found in the gaps; they add no features.
- The MCP tool names stay. Tool input and output shapes stay compatible,
  except in PR 06, which changes them on purpose.
- The files of a live deployment (`pantry.txt`, `products.json`,
  `preferences.json`) keep loading after every PR.

## 2. Common PR conditions

- One PR = one chapter; `scripts/check.sh` green (its `CHECK OK` line in the
  reports); CI green.
- Tests for every acceptance criterion that can be verified offline. Every
  bug the chapter names gets a regression test that fails on `main`.
- Replace, don't layer: tests move to the deepened module's interface; tests
  of helpers that become private are deleted, and the PR body says where
  each case now lives.
- No test reaches the network, the repository's `.env` or a real data
  directory; Cookidoo is faked.
- Documentation in the same PR: docstrings, tool docstrings,
  `rohlik_cookidoo/guide.py` when tool behaviour changes, `README.md` when
  something user-visible changes.
- No version bumps inside these PRs; a release commit after the train bumps
  `pyproject.toml`, `.claude-plugin/plugin.json` and `uv.lock` together.

## 3. PR overview

| NN | Name | Depends on | Status |
|---|---|---|---|
| 01 | Purchase plan in one pass | — | planned |
| 02 | Household module | — | planned |
| 03 | Shopping list module | 02 | planned |
| 04 | One ingredient identity | 02 | planned |
| 05 | Amount module | 01 | planned |
| 06 | One ingredient line across the shopping tools | 01, 03 | planned |

Merge order for a batch: 01 and 02 first (independent), then 03, 04 and 05,
then 06.

## 4. PR briefs

### PR 01 — Purchase plan in one pass

`plan_purchase` in `rohlik_cookidoo/cart.py` becomes the only interface of
the purchase plan module. Today it groups the items by product, hands a
reshaped list to `plan_cart_additions`, which groups by product and joins
names a second time, and then stitches the package details back on by
`str(product_id)`. After this PR each product is handled in one pass:
package count and leftover, comparison with the cart, totals and the minimum
order. `plan_cart_additions` and `rohlik_cookidoo/packages.py`
(`packages_needed`, `parse_package_amount`) become private to the module;
the designer decides whether `packages.py` stays as a private module or
merges into `cart.py`.

Bugs fixed here (all reproduced on `main`): items for the same product with
different `package_amount` or `price` silently use the first item's values
("500 g" + "1 kg" → counted against 500 g); `packages: 0` is read as "not
set" and buys one package; an item without a product ID raises a bare
`KeyError: 'productId'`.

Not in this PR: the unit and number model (PR 05) and the comma-joined line
names (PR 06). The `plan_purchase` tool keeps its input and output fields.

**Done when:**
- No module outside the purchase plan module, and no test, imports
  `plan_cart_additions`, `packages_needed` or `parse_package_amount`.
- Items are grouped by product exactly once; the `str(product_id)` stitching
  is gone.
- Items for one product with conflicting `package_amount` or `price` give a
  line with `exact: false` and a `note` naming the conflict; regression
  test.
- `packages: 0` gives a line with 0 packages and nothing in `to_add`;
  regression test.
- An item without `product_id` / `productId` makes the `plan_purchase` tool
  fail with a `ToolError` that names the item; test.
- Every case of today's `tests/test_cart.py` and `tests/test_packages.py`
  survives as a `plan_purchase` case (package sizes such as "4 x 125 g",
  "cca 0,85 kg", "6×0,5 l"); the PR body lists the new home of each.
- The `plan_purchase` tool docstring and `guide.py` match the behaviour.

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate A); written into the plan directly, without `/mao` question
rounds.

### PR 02 — Household module

One Household module owns the user's state in one data directory:
`pantry.txt` (with its `#` comments and `?` ask-first marker),
`products.json` (usual products) and `preferences.json`. It absorbs
`rohlik_cookidoo/pantry.py`, `rohlik_cookidoo/memory.py` and
`pantry_overview` from `rohlik_cookidoo/shopping.py`, and answers what
callers ask: the pantry overview, changing the pantry, whether an
ingredient is at home, the usual product for an ingredient,
remembering and forgetting products, and the preferences.

The data directory is resolved once, with today's rules (`PANTRY_PATH`,
else `DATA_DIR/pantry.txt`, else the repository root; the JSON files next to
the pantry file), and passed in instead of being re-read from the
environment on every call. `memory.py` no longer finds its files through
`pantry.pantry_path()`. The seven server tools that touch this state
(`get_pantry`, `update_pantry`, `get_pantry_questionnaire`,
`record_purchase`, `forget_product`, `get_shopping_preferences`,
`set_shopping_preference`) and `build_shopping_list` go through the
Household; `build_shopping_list` stops reading the global `memory` module
inside its loop. Pantry writes become atomic like the memory writes are
today. Importing `rohlik_cookidoo.server` no longer loads the repository's
`.env` (today `load_dotenv` runs at import time, so tests can pick up real
Cookidoo credentials).

Not in this PR: the rules for matching ingredient names (PR 04), moving the
shopping list orchestration out of `server.py` (PR 03). File formats and
locations do not change.

**Done when:**
- `PANTRY_PATH` and `DATA_DIR` are read in one place; no other module
  resolves the data directory.
- Tests build a Household on `tmp_path`; the autouse `PANTRY_PATH` fixture
  in `tests/conftest.py` is gone.
- `PANTRY_PATH`, `DATA_DIR` and the default location behave as documented in
  `README.md`; tests.
- A `pantry.txt` with comments and `?` lines, a `products.json` and a
  `preferences.json` in today's format load unchanged; fixture test.
- All three files are written atomically (temp file + replace).
- `update_pantry` and `record_purchase` write each file at most once per
  call, however many items they get.
- Importing `rohlik_cookidoo.server` in tests does not read the
  repository's `.env`; test.
- The tool outputs are unchanged.

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate C); written into the plan directly, without `/mao` question
rounds.

### PR 03 — Shopping list module

The first shopping step moves out of `rohlik_cookidoo/server.py`.
`collect_recipes` and `prepare` (recipe sources, failed recipes, servings,
the recipe summary, the pantry, usual products and preferences) join
`build_shopping_list` in the shopping list module
(`rohlik_cookidoo/shopping.py`) behind one entry point. It takes the recipe
source (`CookidooClient` in production, a fake in tests) and the Household
from PR 02 as dependencies. `prepare_shopping` only turns its arguments
into a call and errors into a `ToolError`. The mapping
`CookidooError` → `ToolError`, written three times today, exists once.

Bugs fixed here: `target_servings` is handled in three places that
disagree, so a recipe without `servings` (a web recipe) and
`target_servings: 8` comes back unscaled while `recipes[].servings` reports
8; a recipe fetch that fails with an error other than `CookidooException`
(an aiohttp error, a timeout) escapes as a raw exception. The designer
decides what an unscalable recipe reports (default: its amounts as given,
the servings it really has, and a note).

Not in this PR: changes to the `prepare_shopping` output fields (PR 06).

**Done when:**
- `server.py` has no shopping logic: `prepare_shopping` calls one function
  of the shopping list module and maps errors.
- Tests of the first step call the shopping list module directly with a
  fake recipe source and a Household on `tmp_path`, without the MCP client
  and without monkeypatching `server.cookidoo`; MCP-level tests keep only
  the transport.
- A recipe without `servings` plus `target_servings` no longer reports
  servings it was not scaled to; regression test.
- The `CookidooError` → `ToolError` mapping exists once and all three
  Cookidoo tools use it.
- A recipe fetch failing with `aiohttp.ClientError` or
  `asyncio.TimeoutError` ends up in `failed` with a message, or as a
  `ToolError`, never as a raw exception; test.
- The `prepare_shopping` output keeps its fields (`source`, `week_start`,
  `recipes`, `failed`, `to_buy`, `check_at_home`, `at_home`, `preferences`,
  `pantry_setup_needed`).

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate B); written into the plan directly, without `/mao` question
rounds.

### PR 04 — One ingredient identity

"Is this the same ingredient?" is answered in three places with three
encodings today. Summing (`aggregate_ingredients` in
`rohlik_cookidoo/ingredients.py`) uses `name_key` with a fallback to the
normalized name. The pantry (`match_pantry`) uses `name_key` plus a subset
rule for "similar". Usual products (`_product_key` in
`rohlik_cookidoo/memory.py`, in the Household after PR 02) store
`" ".join(sorted(name_key(...)))` as the key in `products.json`. One
ingredient identity module, grown from `rohlik_cookidoo/text.py`, owns the
key, the fallback for names that stem to nothing (`name_key("čerstvý")` is
empty), and the relation the pantry needs: same, broader, narrower or
unrelated ("olej" vs "sezamový olej").

`products.json` stops depending on the stemmer: today a change to the
stemming rules (a new irregular form, a new preparation word) silently
orphans every stored usual product. Entries are found through the stored
ingredient name, and files written by the current release keep working.

Not in this PR: changing the stemming rules themselves.

**Done when:**
- Summing, pantry matching and usual products ask the identity module and
  build no keys of their own.
- A name made only of preparation words is treated the same way in all
  three places; test.
- Changing the stemmer (simulated in a test) does not lose stored usual
  products; regression test that fails on `main`.
- A `products.json` written by the current release is recalled in any case
  form; fixture test.
- One table test covers case forms, word order, preparation words and the
  broader/narrower relation.

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate E); written into the plan directly, without `/mao` question
rounds.

### PR 05 — Amount module

One Amount module holds the unit and number model that is split today
between `rohlik_cookidoo/ingredients.py` (`_NUM`, `_THOUSANDS`,
`_TO_GRAMS`, `_TO_ML`, `to_base_unit`, `format_quantity`),
`rohlik_cookidoo/packages.py` (its own `_NUM`, the `_PACKAGE` unit regex,
`_BASE_UNIT`) and `rohlik_cookidoo/cart.py` (the unit-group check before
summing). The module parses numbers (decimal comma, thousands dot,
fractions, ranges) and units, converts to base units, adds, compares and
formats. Unit groups are named constants instead of the bare strings
`"weight"`, `"volume"`, `"count"` and `"unspecified"`. The "1 g = 1 ml"
estimate lives in this one place. Ingredient parsing, package-size parsing
and the purchase plan from PR 01 use it.

Bugs fixed here: the package parser reads "1.000 g" as 1 g, while the
ingredient parser reads the same text as 1000 g. Package sizes do not
accept unit words that recipes accept ("2 kusy", "1 litr" → not
recognised).

Not in this PR: new units, density tables for converting grams to
millilitres.

**Done when:**
- There is one number parser and one unit table; `ingredients.py` and the
  package parsing define none of their own.
- No module compares unit groups as bare strings.
- The package size "1.000 g" is 1000 g; regression test.
- Package sizes accept the same unit words as recipe quantities ("2 kusy",
  "1 litr"); test.
- Every existing ingredient and package parsing case still passes; the
  cases that test amounts move to the Amount interface.

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate F); written into the plan directly, without `/mao` question
rounds.

### PR 06 — One ingredient line across the shopping tools

The model carries each ingredient from `prepare_shopping` through
`plan_purchase` to `record_purchase` and has to reshape it at every
hand-off. The ingredient is `name` in two tools and `ingredient` in the
third. `productId` is accepted in `plan_purchase` but not in
`record_purchase`. Plan lines join several ingredients into one name with
", " and lack the `product_name` and `package_amount` that
`record_purchase` requires. `quantity` means a base-unit amount in one
shape and a package count in another. After this PR the three tools share
one vocabulary: the same ingredient field everywhere, both product ID
spellings accepted everywhere, and plan lines that keep their ingredients
as a list and carry what `record_purchase` needs, so a plan line can be
passed back as it is. The shapes are defined once (the TypedDicts in
`rohlik_cookidoo/server.py` and their cart counterparts) and serve as the
MCP schema.

Bug fixed here (reproduced on `main`): recording the plan line
"cibule, žlutá cibule" remembers only "cibule", because `clean_name` drops
everything after a comma.

The designer decides how callers using the old shapes are treated (default:
old input field names still accepted for one release, outputs in the new
shape). The live server is used from claude.ai, so the deploy carries the
new instructions; deploying stays with the user.

**Done when:**
- The ingredient field has the same name in the inputs and outputs of all
  three tools.
- `record_purchase` accepts `product_id` and `productId`.
- Plan lines carry the ingredients as a list plus `product_name` and
  `package_amount`; no ", "-joined names. Two ingredients sharing a product
  ("cibule", "žlutá cibule") are both remembered; regression test.
- A test chains `prepare_shopping` → `plan_purchase` → `record_purchase`
  through the MCP client, using only fields the previous tool returned plus
  product data.
- Old input shapes are handled as the spec decides, with a test.
- `guide.py` `INSTRUCTIONS`, the tool docstrings, `README.md` and
  `skills/*/SKILL.md` describe the new shape; grep for the old field names
  in docs is empty.

**Requested:** 2026-10-15, from the architecture review of the same day
(candidate D); written into the plan directly, without `/mao` question
rounds.

## 5. Open items

- After PR 06: a release commit bumping the version in `pyproject.toml`,
  `.claude-plugin/plugin.json` and `uv.lock` (0.7.1 → 0.8.0), then the user
  redeploys the live server.
- The main checkout's `.git/index` is owned by root
  (`sudo chown ubuntu:ubuntu .git/index`); until then MAO runs work in
  worktrees.

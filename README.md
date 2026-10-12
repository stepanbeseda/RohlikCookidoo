# RohlikCookidoo

Propojuje **Cookidoo** (recepty z Thermomixu) s **Rohlik.cz** (nákup potravin).
Claude přečte týdenní plán receptů, sečte ingredience, odečte suroviny, které máš doma, a zbytek po tvém potvrzení přidá do košíku na Rohlíku.

> Neoficiální osobní projekt. Není spojený se společnostmi Rohlik, Vorwerk, Thermomix ani Cookidoo.
> Objednávku nikdy neodesílá, jen plní košík. Odeslání potvrzuješ ty v e-shopu.

---

## Co potřebuješ

- Python 3.12+
- Node.js (pro `npx`)
- účet na Cookidoo a na Rohlik.cz
- Claude Desktop (macOS: konfigurace v `~/Library/Application Support/Claude/claude_desktop_config.json`)

## Instalace

```bash
git clone https://github.com/stepanbeseda/RohlikCookidoo.git
cd RohlikCookidoo

python -m venv venv
source venv/bin/activate
pip install -e .
```

S nástrojem [uv](https://docs.astral.sh/uv/) stačí `uv sync`; nainstaluje přesně verze ze souboru `uv.lock` do složky `.venv`.

Repo obsahuje dva vlastní MCP servery, nic dalšího se neklonuje:

- `cookidoo_server.py` čte týdenní plán a recepty z Cookidoo. Stojí na neoficiální knihovně [cookidoo-api](https://github.com/miaucl/cookidoo-api) a nic nezapisuje.
- `kitchen_server.py` sčítá ingredience z více receptů, porovnává je se spíží a počítá počet balení. Nepotřebuje žádné heslo ani síť.

### Spíž

```bash
cp pantry.txt.example pantry.txt
```

Uprav `pantry.txt` podle toho, co máš doma. Podrobnosti jsou v sekci [Domácí zásobárna](#domácí-zásobárna-pantrytxt).

---

## Použití v Claude Desktop

### 1. Nastav MCP servery

Do sekce `"mcpServers"` v `claude_desktop_config.json` přidej:

```json
"cookidoo": {
  "command": "/absolutni/cesta/k/projektu/venv/bin/fastmcp",
  "args": ["run", "/absolutni/cesta/k/projektu/cookidoo_server.py"],
  "env": {
    "COOKIDOO_EMAIL": "tvuj@email.com",
    "COOKIDOO_PASSWORD": "tvoje_heslo"
  }
},
"kuchyne": {
  "command": "/absolutni/cesta/k/projektu/venv/bin/fastmcp",
  "args": ["run", "/absolutni/cesta/k/projektu/kitchen_server.py"],
  "env": {
    "PANTRY_PATH": "/absolutni/cesta/k/projektu/pantry.txt"
  }
},
"rohlik": {
  "command": "npx",
  "args": ["-y", "@tomaspavlin/rohlik-mcp@3.3.0"],
  "env": {
    "ROHLIK_USERNAME": "tvuj@email.com",
    "ROHLIK_PASSWORD": "tvoje_heslo",
    "ROHLIK_BASE_URL": "https://www.rohlik.cz"
  }
},
"chrome": {
  "command": "npx",
  "args": ["-y", "chrome-devtools-mcp@1.10.1"]
}
```

Server `chrome` je potřeba jen pro příkaz `/url` a vyžaduje nainstalovaný Google Chrome.

Cookidoo server čte recepty z českého Cookidoo. Jinou zemi nastavíš proměnnými `COOKIDOO_COUNTRY` (výchozí `cz`) a `COOKIDOO_LANGUAGE` (výchozí `cs`) v bloku `env`.

Po uložení Claude Desktop ukonči (Cmd+Q) a znovu otevři.

#### Rohlík: dvě možnosti připojení

| | `@tomaspavlin/rohlik-mcp` (výše) | Oficiální `mcp.rohlik.cz` |
|---|---|---|
| Přihlášení | e-mail a heslo v konfiguraci | OAuth v prohlížeči, bez hesla v souboru |
| Nastavení | `npx`, viz výše | Settings → Connectors → Add custom connector, URL `https://mcp.rohlik.cz/mcp` |
| Stav v tomto projektu | vyzkoušeno | **nevyzkoušeno** |

Instrukce v `claude_project_prompt.md` používají názvy nástrojů a parametrů z balíčku `@tomaspavlin/rohlik-mcp` (`search_products`, `add_to_cart`). Oficiální server je může mít jiné, takže s ním může být potřeba instrukce upravit. Postup připojení popisuje [dokumentace Rohlíku](https://www.rohlik.cz/stranka/mcp-server).

### 2. Nastav Project Instructions

1. V Claude Desktop otevři **Projects** a vytvoř nový projekt (např. „RohlikCookidoo“)
2. Klikni na **Set custom instructions**
3. Vlož obsah souboru `claude_project_prompt.md`

### 3. Příkazy

**`/tyden`** přečte týdenní rozpis z Cookidoo kalendáře, sečte ingredience ze všech receptů, odečte spíž a nabídne nákup na Rohlíku.

```
Ty:     /tyden

Claude: Stahuji týdenní plán z Cookidoo...
        Našel jsem 5 receptů: Svíčková, Rizoto, Kuřecí vývar, ...

        Ingredience k nákupu (po odečtení domácí zásobárny):
        - 800 g hovězího — Hovězí zadní (189 Kč)
        - 400 g rýže — Rýže jasmínová (22 Kč)
        - ...
        Doma by měly být: mouka, sůl, pepř
        Celkem: ~650 Kč

        Přidat do košíku? (ano/ne)

Ty:     ano

Claude: Přidáno 12 produktů do košíku.
```

Nákup na příští týden: napiš „/tyden na příští týden“. Nástroj `get_planned_recipes_this_week` má parametr `week_offset` (0 = tento týden, 1 = příští).

**`/recept <ID>`** udělá totéž pro jeden recept. ID je část adresy receptu na Cookidoo začínající písmenem `r`.

**`/url <odkaz>`** přečte recept z libovolného webu, vytáhne ingredience a nabídne nákup.

Preference kvality (BIO, vlastní značka Rohlíku, poměr cena/kvalita, nejlevnější) se nastavuje v `claude_project_prompt.md`.

---

## Domácí zásobárna (pantry.txt)

Suroviny uvedené v `pantry.txt` se nekupují. Jeden název na řádek, řádky začínající `#` jsou komentáře.

```
sůl
pepř
slunečnicový olej
hladká mouka
```

Porovnání nezávisí na pádu ani na diakritice („másla“ z receptu odpovídá položce „máslo“) a má tři výsledky:

| Recept | Spíž | Výsledek |
|---|---|---|
| másla | máslo | doma, nekupuje se |
| sezamový olej | olej | zkontroluj doma: ve spíži je něco podobného, Claude rozhodne a upozorní tě |
| vepřové plece | | kupuje se |

Spíž nezná množství. Když recepty chtějí 300 g másla, bere se máslo jako „doma“; Claude na větší množství upozorní.

Spíž můžeš měnit i v chatu („rýži mám vždycky doma“, „došla mi mouka“).

---

## Použití jako CLI

```bash
cp .env.example .env    # vyplň přihlašovací údaje
source venv/bin/activate

python main.py              # jeden recept, interaktivní výběr produktů
python main.py --week       # týdenní plán
python main.py --discover   # vypíše dostupné MCP nástroje
python main.py --debug      # při chybě vypíše celý traceback
```

CLI spouští stejný `cookidoo_server.py` jako Claude Desktop a používá stejné jádro pro sčítání a spíž. Suroviny ve stavu „zkontroluj doma“ vypíše a nabídne k nákupu. Cestu ke spíži lze změnit proměnnou `PANTRY_PATH`.

---

## Známá omezení

- **Tvary slov.** Cookidoo vrací ingredience ve 2. pádě („másla“, „soli“). Sčítání a spíž si s tím poradí zjednodušeným odřezáváním koncovek, ne skutečným slovníkem, takže u neobvyklých slov se dvě podoby téže suroviny nemusí spojit. CLI navíc na Rohlíku hledá tvar z receptu („másla“); v Claude Desktop ho model převede.
- **Podobné suroviny se nesčítají.** „Cibule“ a „žlutá cibule“ jsou dvě položky. Stejně tak 2 lžíce oleje a 100 g oleje.
- **Vlastní recepty.** Recepty, které sis v Cookidoo vytvořil sám, mají ingredience jako volný text. Server je vrací, ale není to vyzkoušené; CLI je nepodporuje.
- **Opakované spuštění.** Před přidáním se nekontroluje obsah košíku. Druhé `/tyden` přidá všechno znovu.
- **Počet balení.** Gramy proti litrům se počítají jako 1 g = 1 ml, což sedí pro vodu a mléko, méně pro olej nebo med. Kusy proti kilogramům (3 cibule a síťka 1 kg) spočítat nejde a vychází jedno balení; nástroj to v poznámce uvede.
- **Zachraň jídlo.** CLI kontroluje jen první stránku slev a označení bere podle formátu slevy, ne podle skutečné kategorie Zachraň jídlo.
- **Neoficiální API.** Cookidoo nemá veřejné API. Knihovna `cookidoo-api` i Rohlik MCP balíček používají neveřejná rozhraní, která se mohou kdykoli změnit.

## Bezpečnost

- Hesla v `claude_desktop_config.json` a `.env` leží na disku v čitelné podobě. Soubory nesdílej a necommituj; `.env` i `pantry.txt` jsou v `.gitignore`.
- Verze balíčků spouštěných přes `npx` jsou v návodu zafixované. Při změně verze si ověř, co instaluješ, balíček dostává tvoje heslo.
- Každý MCP server dostává jen své vlastní přihlašovací údaje.

## Řešení problémů

- Servery se v Claude Desktop nezobrazují: zkontroluj logy v `~/Library/Logs/Claude/` a syntaxi JSON v konfiguraci.
- Ověř, že funguje `venv/bin/fastmcp --version` a `npx --version`.
- Chybí nástroj `aggregate_ingredients_for_shopping`: v konfiguraci není server `kuchyne`.
- Cookidoo hlásí „login failed“: zkontroluj `COOKIDOO_EMAIL` a `COOKIDOO_PASSWORD`. Přihlášení si ověříš nástrojem `connect_to_cookidoo`.
- Týdenní plán je prázdný: recepty musí být v kalendáři na webu cookidoo.cz v daném týdnu (pondělí až neděle).

## Vývoj

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

Jádro je v balíčku `rohlik_cookidoo/` (`ingredients.py`, `pantry.py`, `packages.py`, `text.py`) a nemá závislost na síti. Testy a lint běží na GitHubu při každém pull requestu.

## Licence

[MIT](LICENSE)

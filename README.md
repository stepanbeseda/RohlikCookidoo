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
pip install -r requirements.txt
```

### Cookidoo MCP server

Projekt používá [alexandrepa/mcp-cookidoo](https://github.com/alexandrepa/mcp-cookidoo) ve verzi commitu `6d45166` s úpravou z tohoto repa. Úprava přidává nástroje `get_planned_recipes_this_week` a `get_pantry_items` a opravuje výpis množství u ingrediencí. Bez ní příkaz `/tyden` nefunguje.

```bash
git clone https://github.com/alexandrepa/mcp-cookidoo.git mcp-cookidoo
git -C mcp-cookidoo checkout 6d45166
git -C mcp-cookidoo apply ../patches/mcp-cookidoo-tyden.patch
```

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
  "args": ["run", "/absolutni/cesta/k/projektu/mcp-cookidoo/server.py"],
  "env": {
    "COOKIDOO_EMAIL": "tvuj@email.com",
    "COOKIDOO_PASSWORD": "tvoje_heslo",
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

Piš položky konkrétně. Porovnání je částečné a bez diakritiky, takže obecná položka `olej` vyřadí z nákupu i sezamový olej a `máslo` vyřadí i arašídové máslo.

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

CLI vyžaduje naklonovaný a upravený `mcp-cookidoo` stejně jako Claude Desktop.

---

## Známá omezení

- **Jazyk receptů.** Použitý Cookidoo server se přihlašuje s francouzskou lokalizací (`fr-FR`). Recepty z kalendáře se vrací, ale názvy ingrediencí nemusí být česky a hledání na Rohlíku pak selže.
- **Opakované spuštění.** Před přidáním se nekontroluje obsah košíku. Druhé `/tyden` přidá všechno znovu.
- **Počet balení.** Odhaduje se jen tam, kde recept i produkt používají hmotnost nebo objem. Cookidoo uvádí tekutiny v gramech, Rohlík v litrech, v takovém případě se přidá jedno balení.
- **Zápis množství.** Parser v CLI nezvládne tvary jako `200g` bez mezery, rozsah `1-2` nebo `½`.
- **Zachraň jídlo.** CLI kontroluje jen první stránku slev a označení bere podle formátu slevy, ne podle skutečné kategorie Zachraň jídlo.
- **Licence závislosti.** Repozitář `alexandrepa/mcp-cookidoo` nemá licenční soubor.

## Bezpečnost

- Hesla v `claude_desktop_config.json` a `.env` leží na disku v čitelné podobě. Soubory nesdílej a necommituj; `.env` i `pantry.txt` jsou v `.gitignore`.
- Verze balíčků spouštěných přes `npx` jsou v návodu zafixované. Při změně verze si ověř, co instaluješ, balíček dostává tvoje heslo.
- Rohlik MCP balíček používá neveřejné API Rohlíku. Služba se může kdykoli změnit.

## Řešení problémů

- Servery se v Claude Desktop nezobrazují: zkontroluj logy v `~/Library/Logs/Claude/` a syntaxi JSON v konfiguraci.
- Ověř, že funguje `venv/bin/fastmcp --version` a `npx --version`.
- Claude hlásí „Not connected“: Cookidoo nástroje vyžadují nejdřív `connect_to_cookidoo`. S nastavenými Project Instructions to Claude dělá sám.
- Chybí nástroj `get_planned_recipes_this_week`: na `mcp-cookidoo` není aplikovaná úprava z `patches/`.

## Vývoj

```bash
pip install pytest
python -m pytest
```

## Licence

[MIT](LICENSE)

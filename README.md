# RohlikCookidoo

Propojuje **Cookidoo** (recepty z Thermomixu) s **Rohlik.cz** (nákup potravin).
Claude přečte týdenní plán receptů, sečte ingredience a nakoupí je na Rohlíku — včetně odfiltrování surovin, které už máš doma.

---

## Instalace

```bash
git clone https://github.com/stepanbeseda/RohlikCookidoo.git
cd RohlikCookidoo

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

git clone https://github.com/alexandrepa/mcp-cookidoo.git mcp-cookidoo
pip install -r mcp-cookidoo/requirements.txt

cp .env.example .env
# Vyplň .env — Cookidoo email+heslo, Rohlik email+heslo

cp pantry.txt.example pantry.txt
# Uprav pantry.txt — suroviny, které máš doma (sůl, olej, mouka...)
```

Potřebuješ: Python 3.11+, Node.js (pro `npx`)

---

## Použití v Claude Desktop

### 1. Nastav MCP servery

Otevři `~/Library/Application Support/Claude/claude_desktop_config.json` a přidej:

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
  "args": ["-y", "@tomaspavlin/rohlik-mcp"],
  "env": {
    "ROHLIK_USERNAME": "tvuj@email.com",
    "ROHLIK_PASSWORD": "tvoje_heslo",
    "ROHLIK_BASE_URL": "https://www.rohlik.cz"
  }
},
"chrome": {
  "command": "npx",
  "args": ["-y", "chrome-devtools-mcp@latest"]
}
```

> **Proč `@tomaspavlin/rohlik-mcp` a ne `mcp.rohlik.cz`?**
> Rohlik provozuje vlastní hostovaný MCP server na `mcp.rohlik.cz`, ale jeho interní
> autentizační endpoint vrací 401 i pro validní přihlašovací údaje — nástroje tudíž
> vracejí prázdné výsledky. Self-hosted balíček `@tomaspavlin/rohlik-mcp` volá
> přímo veřejné Rohlik API a funguje spolehlivě.

Restartuj Claude Desktop (Cmd+Q a znovu otevři).

### 2. Nastav Project Instructions

1. V Claude Desktop otevři **Projects** → vytvoř nový projekt (např. "RohlikCookidoo")
2. Klikni na **Set custom instructions**
3. Vlož obsah souboru `claude_project_prompt.md`

### 3. Použití

Otevři projekt v Claude Desktop a piš do chatu:

**`/tyden`** — přečte týdenní rozpis receptů z Cookidoo kalendáře, sečte všechny ingredience dohromady (např. mouka ze svíčkové + mouka z koláče = 700 g), odečte co máš doma (pantry.txt) a nakoupí zbytek na Rohlíku

```
Ty:     /tyden

Claude: Stahuji týdenní plán z Cookidoo...
        Našel jsem 5 receptů: Svíčková, Rizoto, Kuřecí vývar, ...

        Sečtené ingredience ze všech receptů:
        - hovězí maso 800 g
        - mrkev 4 ks
        - rýže 400 g
        - mouka 700 g ← mám doma, přeskakuji
        - sůl, pepř ← mám doma, přeskakuji
        - ...

        Ingredience k nákupu (po odečtení domácí zásobárny):
        - 800 g hovězího — Rohlik Hovězí zadní (189 Kč)
        - 400 g rýže — Kitchin Rýže jasmínová (22 Kč)
        - ...
        Celkem: ~650 Kč

        Přidat do košíku? (ano/ne)

Ty:     ano

Claude: Přidáno 12 produktů do košíku.
```

**`/recept r59322`** — jeden recept podle ID z Cookidoo URL

**`/url https://www.toprecepty.cz/recept/...`** — recept z libovolného webu

```
Ty:     /url https://www.toprecepty.cz/recept/svickova-na-smetane

Claude: Čtu stránku...
        Našel jsem ingredience: hovězí kýta 1 kg, mrkev 2 ks, ...
        (Mouka a cukr — mám doma, přeskakuji)

        Ingredience k nákupu: ...
```

Preference kvality (BIO / nejlepší poměr / nejlevnější) se nastaví v `claude_project_prompt.md`. Claude produkt vybere automaticky a zeptá se jen na potvrzení před přidáním do košíku.

---

## Domácí zásobárna (pantry.txt)

Suroviny v `pantry.txt` se automaticky přeskočí při nákupu — Claude je nehledá na Rohlíku.

```
# pantry.txt — jeden název na řádek, # jsou komentáře
sůl
pepř
olej
mouka
```

Porovnání je fuzzy (bez diakritiky, částečná shoda) — "olivový olej" v receptu matchne "olej" v pantry.

---

## Použití jako CLI

```bash
source venv/bin/activate

# Jeden recept (interaktivní výběr)
python main.py

# Týdenní plán
python main.py --week

# Zobraz dostupné MCP nástroje
python main.py --discover
```

---

## Použití v ChatGPT Desktop

1. **Settings** → **Beta features** → zapni **MCP Servers**
2. **Settings** → **MCP Servers** → **Add Server**
3. Přidej Cookidoo server:
   - Command: `/absolutni/cesta/venv/bin/fastmcp`
   - Arguments: `run /absolutni/cesta/mcp-cookidoo/server.py`
   - Environment: `COOKIDOO_EMAIL`, `COOKIDOO_PASSWORD`, `PANTRY_PATH`
4. Přidej Rohlik server:
   - Command: `npx`
   - Arguments: `-y @tomaspavlin/rohlik-mcp`
   - Environment: `ROHLIK_USERNAME`, `ROHLIK_PASSWORD`, `ROHLIK_BASE_URL=https://www.rohlik.cz`
5. Restartuj ChatGPT

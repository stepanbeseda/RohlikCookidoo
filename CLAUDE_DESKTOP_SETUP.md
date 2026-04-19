# Nastaveni pro Claude Desktop (macOS)

Tato aplikace se da pouzit primo v Claude Desktop app — Claude bude mit pristup
k Cookidoo receptum a Rohlik kosiku pres MCP servery.

## 1. Najdi konfiguracni soubor

Otevri v editoru:

```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Nebo v terminalu:

```bash
open ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

## 2. Pridej MCP servery

Do sekce `"mcpServers"` pridej tri nove servery (za existujici, s carkou):

```json
"cookidoo": {
  "command": "/CESTA/K/PROJEKTU/venv/bin/fastmcp",
  "args": ["run", "/CESTA/K/PROJEKTU/mcp-cookidoo/server.py"],
  "env": {
    "COOKIDOO_EMAIL": "tvuj_cookidoo_email@example.com",
    "COOKIDOO_PASSWORD": "tvoje_cookidoo_heslo",
    "PANTRY_PATH": "/CESTA/K/PROJEKTU/pantry.txt"
  }
},
"rohlik": {
  "command": "npx",
  "args": ["-y", "@tomaspavlin/rohlik-mcp"],
  "env": {
    "ROHLIK_USERNAME": "tvuj_rohlik_email@example.com",
    "ROHLIK_PASSWORD": "tvoje_rohlik_heslo",
    "ROHLIK_BASE_URL": "https://www.rohlik.cz"
  }
},
"chrome": {
  "command": "npx",
  "args": ["-y", "chrome-devtools-mcp@latest"]
}
```

**Dulezite:**
- Nahrad `/CESTA/K/PROJEKTU` absolutni cestou k tomuto repozitari
  (napr. `/Users/jmeno/RohlikCookidoo`)
- Doplni sve skutecne prihlasovaci udaje
- `PANTRY_PATH` ukazuje na seznam surovin, ktere mas doma (viz `pantry.txt`)
- Tento soubor je POUZE na tvem disku — na GitHub se nedostane

## 3. Predpoklady

- Python venv s nainstalovanymi zavislostmi:
  ```bash
  python -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- Naklonvany `mcp-cookidoo` server:
  ```bash
  git clone https://github.com/alexandrepa/mcp-cookidoo.git mcp-cookidoo
  pip install -r mcp-cookidoo/requirements.txt
  ```
- Node.js (pro `npx mcp-remote` a Chrome MCP)
- Google Chrome (musi bezet na pozadi pro `/url` prikaz)

## 4. Restartuj Claude Desktop

Po ulozeni konfigurace:
1. **Cmd+Q** — ukonci Claude Desktop
2. Znovu otevri Claude Desktop
3. V nove konverzaci by se melo zobrazit kladivko (MCP nastroje)

## 5. Nastaveni projektu (prikazy /tyden a /recept)

Aby Claude rozumel prikazum `/tyden` a `/recept`, nastav Project Instructions:

1. V Claude Desktop otevri **Projects** (levy panel)
2. Vytvor novy projekt (napr. "RohlikCookidoo")
3. Klikni na **Set custom instructions**
4. Vloz obsah souboru `claude_project_prompt.md` z tohoto repozitare
5. Uloz

Ted v tomto projektu staci napsat:
- **`/tyden`** — stahne tydenny plan z Cookidoo, secte ingredience, odfiltruje domaci zasobarnu, nakoupi na Rohliku
- **`/recept r59322`** — to same pro jeden konkretni recept
- **`/url https://www.toprecepty.cz/recept/...`** — precte recept z libovolneho webu pres Chrome, extrahuje ingredience a nakoupi na Rohliku

## 6. Dalsi priklady promptu

- **"Vyhledej na Rohliku mleko a maslo"**
- **"Co mam naplanovano na tento tyden?"**
- **"Pridej do kosiku 2x mleko a 1x maslo"**

**Pozor:** Claude musi nejdrive zavolat `connect_to_cookidoo` pred pouzitim
ostatnich Cookidoo nastroju. S project instructions to dela automaticky.

## 7. Reseni problemu

Pokud se servery nezobrazuji:
- Zkontroluj logy: `~/Library/Logs/Claude/`
- Over, ze `fastmcp` funguje: `/CESTA/K/PROJEKTU/venv/bin/fastmcp --version`
- Over, ze `npx` je dostupny: `npx --version`
- Zkontroluj JSON syntax v config souboru (zadna chybejici carka, zadna extra)

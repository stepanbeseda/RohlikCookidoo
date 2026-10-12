# RohlikCookidoo

Propojuje **Cookidoo** (recepty z Thermomixu) s **Rohlik.cz** (nákup potravin).
Claude přečte týdenní plán receptů, sečte ingredience, odečte suroviny, které máš doma, a zbytek po tvém potvrzení přidá do košíku na Rohlíku.

> Neoficiální osobní projekt. Není spojený se společnostmi Rohlik, Vorwerk, Thermomix ani Cookidoo.
> Objednávku nikdy neodesílá, jen plní košík. Odeslání potvrzuješ ty v e-shopu.

---

## Jak to funguje

Repo je plugin pro Claude Code. Obsahuje tři příkazy a tři MCP servery:

| Server | Co dělá | Přihlášení |
|---|---|---|
| `cookidoo` | čte týdenní plán a recepty z Cookidoo, nic nezapisuje | e-mail a heslo ke Cookidoo |
| `kitchen` | sčítá ingredience z více receptů, porovnává je se spíží, počítá počet balení a co v košíku ještě chybí, pamatuje si tvoje obvyklé produkty | žádné |
| `rohlik` | hledá produkty a plní košík; oficiální server Rohlíku `mcp.rohlik.cz` | OAuth v prohlížeči, bez hesla |

Sčítání a porovnání se spíží dělá kód, Claude vybírá produkty. Postup, kterým se Claude řídí, je v [shared/shopping-guide.md](shared/shopping-guide.md).

## Co potřebuješ

- Claude Code (terminál nebo záložka Code v desktopové aplikaci)
- [uv](https://docs.astral.sh/uv/) – spouští oba Python servery a samo nainstaluje závislosti podle `uv.lock`
- účet na Cookidoo a na Rohlik.cz

## Instalace pluginu

V Claude Code:

```
/plugin marketplace add stepanbeseda/RohlikCookidoo
/plugin install rohlik-cookidoo@rohlik-cookidoo
```

Při instalaci se Claude Code zeptá na e-mail a heslo ke Cookidoo. Heslo ukládá do systémového úložiště hesel, ne do souboru. Později ho změníš přes `/plugin configure rohlik-cookidoo`.

K Rohlíku se přihlásíš bez hesla: zadej `/mcp`, vyber server `rohlik` a projdi přihlášením v prohlížeči. Při prvním připojení může Rohlík poslat e-mail s potvrzením nového přihlášení.

První spuštění trvá déle, protože `uv` stahuje závislosti. Stav serverů ukáže `/mcp`.

## Příkazy

**`/tyden`** přečte recepty z Cookidoo kalendáře na tento týden, sečte ingredience, odečte spíž a nabídne nákup. Pro příští týden napiš `/tyden příští`.

```
Ty:     /tyden

Claude: V plánu jsou 4 recepty: Zelný hrnec s vepřovým masem, Gnocchi s rajčatovou omáčkou, ...

        Koupíme (26 položek): cibule 280 g, vepřová plec 700 g, kysané zelí 250 g, ...
        Doma máš: máslo (300 g ze 4 receptů – máš dost?), sůl, voda, hladká mouka
        Zkontroluj doma: mletý černý pepř (ve spíži je „pepř“, nekupuji)

        | Surovina      | Produkt                          | Balení      | Ks | Cena   |
        | vepřová plec  | MASO! Vepřová plec v celku       | cca 0,85 kg | 1  | 211 Kč |
        | kysané zelí   | Samir Zelí kysané bílé           | 500 g       | 1  | 28 Kč  |
        | ...

        Přidat do košíku?

Ty:     ano

Claude: Přidáno. Košík zkontroluj a objednávku odešli na rohlik.cz.
```

**`/recept <ID>`** udělá totéž pro jeden recept. ID je část adresy receptu na Cookidoo začínající písmenem `r`, například `/recept r117476`.

**`/url <odkaz>`** přečte recept z libovolného webu, vytáhne ingredience a nabídne nákup.

Kdyby se krátký tvar tloukl s jiným příkazem, použij tvar s předponou pluginu (`/rohlik-cookidoo:tyden`). Claude postup spustí i na běžnou větu („nakup mi na tento týden“).

Dál můžeš říct:

- **počet porcí:** „/recept r117476 pro 3 porce“
- **preferenci:** „ber BIO“, „nejlevnější“, „značky Rohlíku“; výchozí je rozumný poměr ceny a kvality
- **trvalou preferenci nebo dietu:** „vždycky ber BIO“, „nejím lepek“ – Claude si ji uloží a příště se podle ní řídí
- **spíž:** „rýži mám vždycky doma“, „na máslo se mě vždycky zeptej“, „mouku už doma nedržím“
- **produkt se ti nelíbil:** „tu smetanu už nekupuj“

## Co si plugin pamatuje

Vedle spíže si plugin ukládá dva malé soubory na tvém počítači, nikam je neposílá:

- **Obvyklé produkty** (`products.json`). Po potvrzeném nákupu si Claude zapíše, který produkt jsi pro danou surovinu koupil. Příště ho nabídne jako první, pokud je stále v nabídce.
- **Preference** (`preferences.json`). Jen to, o co ho výslovně požádáš: kvalita, dieta, čemu se vyhnout.

Oba soubory leží vedle spíže a dají se smazat nebo ručně upravit.

## Co počítá kód, ne model

- **Součty ingrediencí** napříč recepty včetně převodů jednotek a přepočtu porcí.
- **Počet balení** a **zbytek po uvaření**: když recept chce 200 g a balení má 1 kg, dozvíš se, že 800 g zbyde.
- **Rozdíl proti košíku**: co už v košíku je, se nepřidá znovu. Opakované `/tyden` tak košík nezdvojí.
- **Cena nákupu** a kolik chybí do minimální objednávky Rohlíku. Limit se bere z košíku (v říjnu 2026 to je 749 Kč při doručení domů).

## Domácí zásobárna

Suroviny ve spíži se nekupují. Spíž je textový soubor, jedna surovina na řádek. Plugin ho drží ve své datové složce (`~/.claude/plugins/data/…/pantry.txt`), kde přežije aktualizace. Nejsnáz ho plníš v chatu; jako vzor poslouží [pantry.txt.example](pantry.txt.example).

Porovnání nezávisí na pádu ani na diakritice a má tři výsledky:

| Recept | Spíž | Výsledek |
|---|---|---|
| másla | máslo | doma, nekupuje se |
| sezamový olej | olej | zkontroluj doma: ve spíži je něco podobného, Claude rozhodne a řekne ti to |
| vepřové plece | | kupuje se |
| másla | ? máslo | zeptá se: obvykle doma je, ale dochází |

Řádek začínající otazníkem (`? máslo`) znamená „obvykle doma mám, ale zeptej se“. Hodí se na máslo, vejce nebo mléko. V chatu to nastavíš větou „na máslo se mě vždycky zeptej“.

Spíž nezná množství. Když recepty chtějí 300 g másla, bere se máslo jako „doma“ a Claude na větší množství upozorní.

## Bez pluginu: Claude Desktop (chat)

Chat v Claude Desktop lokální servery z pluginu nenačítá, ale jdou připojit ručně.

```bash
git clone https://github.com/stepanbeseda/RohlikCookidoo.git
cd RohlikCookidoo
uv sync
cp pantry.txt.example pantry.txt
```

Do sekce `"mcpServers"` v `~/Library/Application Support/Claude/claude_desktop_config.json` přidej:

```json
"cookidoo": {
  "command": "/absolutni/cesta/k/projektu/.venv/bin/python",
  "args": ["/absolutni/cesta/k/projektu/cookidoo_server.py"],
  "env": {
    "COOKIDOO_EMAIL": "tvuj@email.com",
    "COOKIDOO_PASSWORD": "tvoje_heslo"
  }
},
"kitchen": {
  "command": "/absolutni/cesta/k/projektu/.venv/bin/python",
  "args": ["/absolutni/cesta/k/projektu/kitchen_server.py"],
  "env": {
    "PANTRY_PATH": "/absolutni/cesta/k/projektu/pantry.txt"
  }
}
```

Starší zápis přes `fastmcp run .../cookidoo_server.py` funguje dál. Po uložení Claude Desktop ukonči (Cmd+Q) a znovu otevři.

Rohlík přidej jako konektor: **Settings → Connectors → Add custom connector**, URL `https://mcp.rohlik.cz/mcp`, a přihlas se v prohlížeči.

Potom v Claude Desktop vytvoř projekt a do **Project Instructions** vlož obsah souboru [shared/shopping-guide.md](shared/shopping-guide.md). V chatu pak piš `/tyden`, `/recept <ID>` nebo `/url <odkaz>`.

Cookidoo server čte z českého Cookidoo. Jinou zemi nastavíš proměnnými `COOKIDOO_COUNTRY` (výchozí `cz`) a `COOKIDOO_LANGUAGE` (výchozí `cs`).

## Rohlík MCP

Plugin používá oficiální server Rohlíku na `https://mcp.rohlik.cz/mcp`. Přihlašuje se přes OAuth, takže heslo k Rohlíku nikde neleží. Rohlík službu označuje jako experimentální a může ji kdykoli změnit; podmínky jsou v [dokumentaci Rohlíku](https://www.rohlik.cz/stranka/mcp-server).

Server umí víc než nákup: rušit objednávky, měnit doručení, podávat reklamace. Postup v `shared/shopping-guide.md` Claudovi říká, aby tyto nástroje při nákupu nepoužíval, pokud o to výslovně nepožádáš.

Komunitní balíček [@tomaspavlin/rohlik-mcp](https://github.com/tomaspavlin/rohlik-mcp) funguje jako náhrada (postup zná i jeho nástroje), ale vyžaduje e-mail a heslo v konfiguraci.

## Známá omezení

- **Tvary slov.** Cookidoo vrací ingredience ve 2. pádě („másla“, „soli“). Sčítání a spíž si s tím poradí zjednodušeným odřezáváním koncovek, ne skutečným slovníkem, takže u neobvyklých slov se dvě podoby téže suroviny nemusí spojit.
- **Podobné suroviny se nesčítají.** „Cibule“ a „žlutá cibule“ jsou dvě položky, stejně tak 2 lžíce oleje a 100 g oleje. Claude je při výběru produktu může spojit a řekne to.
- **Počet balení.** Gramy proti litrům se počítají jako 1 g = 1 ml, což sedí pro vodu a mléko, méně pro olej nebo med. Kusy proti kilogramům (3 cibule a síťka 1 kg) spočítat nejde; nástroj to přizná a rozhodne Claude.
- **Vlastní recepty.** Recepty, které sis v Cookidoo vytvořil sám, mají ingredience jako volný text. Server je vrací, ale není to vyzkoušené.
- **Košík.** Rozdíl proti košíku počítá kód, ale obsah košíku mu předává Claude z textového výpisu Rohlíku. Před potvrzením si tabulku zkontroluj.
- **Přihlášení k Rohlíku z pluginu.** Server a postup jsou ověřené přes konektor v aplikaci. Přihlášení přes `/mcp` u serveru deklarovaného pluginem vyzkoušené není.
- **Neoficiální API.** Cookidoo nemá veřejné API; knihovna `cookidoo-api` používá neveřejné rozhraní, které se může kdykoli změnit.

## Bezpečnost

- K Rohlíku se přihlašuje přes OAuth, heslo plugin nezná.
- Heslo ke Cookidoo ukládá plugin do systémového úložiště hesel. Při ručním nastavení v `claude_desktop_config.json` leží na disku v čitelné podobě; soubor nesdílej.
- Každý server dostává jen své vlastní přihlašovací údaje. Server `kitchen` nedostává žádné.
- Oficiální server Rohlíku žádá u každého volání krátký popis účelu pro analytiku. Postup Claudovi ukládá psát ho obecně, bez osobních údajů.
- `.env`, `pantry.txt`, `products.json` a `preferences.json` jsou v `.gitignore`.

## Řešení problémů

- Server se nespustí: `/mcp` v Claude Code ukáže chybu. Ověř, že funguje `uv --version`.
- Rohlík hlásí „Needs authentication“: v `/mcp` vyber server `rohlik` a přihlas se.
- Cookidoo hlásí „login failed“: zkontroluj e-mail a heslo (`/plugin configure rohlik-cookidoo`).
- Týdenní plán je prázdný: recepty musí být v kalendáři na webu cookidoo.cz v daném týdnu (pondělí až neděle).
- V Claude Desktop se servery nezobrazují: zkontroluj logy v `~/Library/Logs/Claude/` a syntaxi JSON v konfiguraci.

## Vývoj

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest
claude plugin validate . --strict
```

Plugin z pracovní složky vyzkoušíš příkazem `claude --plugin-dir .`.

- `rohlik_cookidoo/` – jádro bez závislosti na síti (`ingredients.py`, `pantry.py`, `packages.py`, `cart.py`, `memory.py`, `text.py`) a oba servery
- `skills/` – příkazy `/tyden`, `/recept`, `/url`
- `shared/shopping-guide.md` – postup, kterým se Claude řídí
- `.claude-plugin/` – manifest pluginu a marketplace

Testy a lint běží na GitHubu při každém pull requestu.

## Licence

[MIT](LICENSE)

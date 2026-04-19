"""Konfigurace aplikace — načtení přihlašovacích údajů a uživatelských preferencí."""

import os
import unicodedata
from enum import Enum
from dataclasses import dataclass

from dotenv import load_dotenv


class QualityPreference(str, Enum):
    """Preference kvality potravin při nákupu na Rohlíku."""
    BIO = "bio"
    STANDARD = "standard"
    ZACHRAN_JIDLO = "zachran_jidlo"
    CHEAPEST = "cheapest"


@dataclass
class AppConfig:
    """Konfigurace aplikace s přihlašovacími údaji."""
    cookidoo_email: str
    cookidoo_password: str
    rohlik_email: str
    rohlik_password: str
    cookidoo_server_path: str


def load_config() -> AppConfig:
    """Načte konfiguraci z .env souboru.

    Raises:
        ValueError: Pokud chybí povinná proměnná prostředí.
    """
    load_dotenv()

    required_vars = {
        "COOKIDOO_EMAIL": os.getenv("COOKIDOO_EMAIL"),
        "COOKIDOO_PASSWORD": os.getenv("COOKIDOO_PASSWORD"),
        "RHL_EMAIL": os.getenv("RHL_EMAIL"),
        "RHL_PASS": os.getenv("RHL_PASS"),
    }

    missing = [name for name, value in required_vars.items() if not value]
    if missing:
        raise ValueError(
            f"Chybí proměnné prostředí: {', '.join(missing)}\n"
            f"Zkopíruj .env.example do .env a vyplň své údaje."
        )

    return AppConfig(
        cookidoo_email=required_vars["COOKIDOO_EMAIL"],
        cookidoo_password=required_vars["COOKIDOO_PASSWORD"],
        rohlik_email=required_vars["RHL_EMAIL"],
        rohlik_password=required_vars["RHL_PASS"],
        cookidoo_server_path=os.getenv("COOKIDOO_SERVER_PATH", "./mcp-cookidoo"),
    )


def get_quality_preference() -> QualityPreference:
    """Interaktivně se zeptá uživatele na preferenci kvality potravin."""
    print("\nJakou kvalitu potravin preferuješ?")
    print("  1. BIO / organické produkty")
    print("  2. Standardní (výchozí)")
    print("  3. Zachraň jídlo (zlevněné, blížící se expiraci)")
    print("  4. Nejlevnější varianta")

    choices = {
        "1": QualityPreference.BIO,
        "2": QualityPreference.STANDARD,
        "3": QualityPreference.ZACHRAN_JIDLO,
        "4": QualityPreference.CHEAPEST,
    }

    while True:
        choice = input("\nZadej číslo (1-4) [2]: ").strip() or "2"
        if choice in choices:
            selected = choices[choice]
            print(f"Vybrána preference: {selected.value}")
            return selected
        print("Neplatná volba, zkus to znovu.")


def _normalize(text: str) -> str:
    """Odstraní diakritiku a převede na malá písmena."""
    normalized = unicodedata.normalize("NFD", text)
    without_diacritics = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )
    return without_diacritics.lower().strip()


def load_pantry(path: str = "pantry.txt") -> set[str]:
    """Nacte seznam surovin, ktere mame doma, z pantry.txt.

    Vraci set normalizovanych nazvu (bez diakritiky, lowercase).
    Pokud soubor neexistuje, vraci prazdny set.
    """
    pantry_path = os.path.join(os.path.dirname(__file__), path)
    if not os.path.exists(pantry_path):
        return set()

    items = set()
    with open(pantry_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                items.add(_normalize(line))
    return items


def is_pantry_item(name: str, pantry: set[str]) -> bool:
    """Zjisti, zda ingredience odpovida necemu v domaci zasobarni.

    Pouziva castecne matchovani — "extra panensky olivovy olej"
    matchne "olivovy olej" z pantry a naopak.
    """
    norm = _normalize(name)
    for item in pantry:
        if item in norm or norm in item:
            return True
    return False


# Pokud spustíš tento soubor přímo, otestuje se načtení konfigurace
if __name__ == "__main__":
    try:
        config = load_config()
        print("Konfigurace načtena úspěšně!")
        print(f"  Cookidoo email: {config.cookidoo_email.split('@')[0][:3]}***@{config.cookidoo_email.split('@')[-1]}")
        print(f"  Rohlik email: {config.rohlik_email.split('@')[0][:3]}***@{config.rohlik_email.split('@')[-1]}")
        print(f"  Cookidoo server: {config.cookidoo_server_path}")
    except ValueError as e:
        print(f"Chyba: {e}")

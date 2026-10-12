"""Application configuration: credentials and user preferences."""

import os
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv


class QualityPreference(str, Enum):
    """Food quality preference used when picking products on Rohlik."""
    BIO = "bio"
    STANDARD = "standard"
    FOOD_RESCUE = "food_rescue"
    CHEAPEST = "cheapest"


@dataclass
class AppConfig:
    """Application configuration with credentials."""
    cookidoo_email: str
    cookidoo_password: str
    rohlik_email: str
    rohlik_password: str


def load_config() -> AppConfig:
    """Load configuration from the .env file.

    Raises:
        ValueError: If a required environment variable is missing.
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
    )


def get_quality_preference() -> QualityPreference:
    """Ask the user interactively for their food quality preference."""
    print("\nJakou kvalitu potravin preferuješ?")
    print("  1. BIO / organické produkty")
    print("  2. Standardní (výchozí)")
    print("  3. Zachraň jídlo (zlevněné, blížící se expiraci)")
    print("  4. Nejlevnější varianta")

    choices = {
        "1": QualityPreference.BIO,
        "2": QualityPreference.STANDARD,
        "3": QualityPreference.FOOD_RESCUE,
        "4": QualityPreference.CHEAPEST,
    }

    while True:
        choice = input("\nZadej číslo (1-4) [2]: ").strip() or "2"
        if choice in choices:
            selected = choices[choice]
            print(f"Vybrána preference: {selected.value}")
            return selected
        print("Neplatná volba, zkus to znovu.")


# Running this file directly checks that the configuration loads
if __name__ == "__main__":
    try:
        config = load_config()
        print("Konfigurace načtena úspěšně!")
        print(f"  Cookidoo email: {config.cookidoo_email.split('@')[0][:3]}***@{config.cookidoo_email.split('@')[-1]}")
        print(f"  Rohlik email: {config.rohlik_email.split('@')[0][:3]}***@{config.rohlik_email.split('@')[-1]}")
    except ValueError as e:
        print(f"Chyba: {e}")

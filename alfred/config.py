"""Lettura della configurazione utente (~/.config/alfred/config.toml)."""

import os
import tomllib
from pathlib import Path

CARTELLA_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "alfred"
FILE_CONFIG = CARTELLA_CONFIG / "config.toml"
CARTELLA_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/alfred-{os.getuid()}")) / "alfred"

PREDEFINITI = {
    "generale": {"appellativo": "signore", "porta": 7878},
    "meteo": {"citta": ""},
    "cervello": {"modello": "sonnet"},
}


def carica() -> dict:
    config = {sezione: dict(valori) for sezione, valori in PREDEFINITI.items()}
    if FILE_CONFIG.exists():
        with FILE_CONFIG.open("rb") as f:
            for sezione, valori in tomllib.load(f).items():
                config.setdefault(sezione, {}).update(valori)
    return config


def url_core(config: dict | None = None) -> str:
    config = config or carica()
    return f"http://127.0.0.1:{config['generale']['porta']}"

"""Lettura della configurazione utente (~/.config/alfred/config.toml)."""

import os
import tomllib
from pathlib import Path

CARTELLA_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "alfred"
FILE_CONFIG = CARTELLA_CONFIG / "config.toml"
CARTELLA_STATO = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "alfred"
CARTELLA_RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/alfred-{os.getuid()}")) / "alfred"

PREDEFINITI = {
    "generale": {"appellativo": "signore", "porta": 7878},
    "meteo": {"citta": ""},
    "cervello": {"quotidiano": "haiku", "profondo": "sonnet"},
    "economia": {
        "parsimonia_settimana": 0.5,
        "austerita_settimana": 0.8,
        "austerita_sessione": 0.9,
        "anticipo_sul_ritmo": 0.15,
    },
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

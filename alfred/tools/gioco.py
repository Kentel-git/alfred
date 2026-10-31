"""Modalità gioco: lancia il comando configurato (es. Battle.net da Steam).

Su ogni macchina il "come" è diverso, quindi è tutto in config.toml:
  [gioco]
  comando = ["steam", "-silent", "steam://rungameid/…"]
  processo = "Battle.net"   # nome del processo per capire se è già aperto
"""

import subprocess

import psutil


def in_corso(config_gioco: dict) -> bool:
    nome = config_gioco.get("processo", "").lower()
    if not nome:
        return False
    for processo in psutil.process_iter(["name"]):
        if nome in (processo.info["name"] or "").lower():
            return True
    return False


def avvia(config_gioco: dict) -> dict:
    comando = config_gioco.get("comando")
    if not comando:
        return {"ok": False, "motivo": "non_configurata"}
    if in_corso(config_gioco):
        return {"ok": False, "motivo": "gia_in_corso"}
    subprocess.Popen(
        comando,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True}

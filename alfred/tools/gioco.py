"""Modalità gioco: apre le applicazioni configurate (es. Battle.net e CurseForge).

Su ogni macchina il "come" è diverso, quindi è tutto in config.toml:

  [[gioco.app]]
  nome = "Battle.net"
  avvio = "battlenet.desktop"   # voce di menu (.desktop) oppure comando ["…"]
  processo = "Battle.net"       # nome del processo, per sapere se è già aperta
"""

import shutil
import subprocess

import psutil


def _aperta(processo: str) -> bool:
    processo = processo.lower()
    for p in psutil.process_iter(["name", "cmdline"]):
        nome = (p.info["name"] or "").lower()
        riga = " ".join(p.info["cmdline"] or []).lower()
        if processo in nome or (processo in riga and "alfred" not in riga):
            return True
    return False


def _lancia(avvio: str | list[str]) -> None:
    if isinstance(avvio, str) and avvio.endswith(".desktop"):
        # gtk-launch apre la voce di menu esattamente come il lanciatore.
        comando = [shutil.which("gtk-launch") or "gtk-launch", avvio.removesuffix(".desktop")]
    else:
        comando = [avvio] if isinstance(avvio, str) else avvio
    subprocess.Popen(
        comando,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def avvia(config_gioco: dict) -> dict:
    """Apre le app che non sono già aperte. {"aperte": [...], "gia_aperte": [...]}."""
    app = config_gioco.get("app") or []
    aperte, gia_aperte = [], []
    for a in app:
        if a.get("processo") and _aperta(a["processo"]):
            gia_aperte.append(a["nome"])
        else:
            _lancia(a["avvio"])
            aperte.append(a["nome"])
    return {"configurata": bool(app), "aperte": aperte, "gia_aperte": gia_aperte}

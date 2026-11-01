"""Limiti di utilizzo dell'abbonamento Claude (finestra di 5 ore e settimanale).

Claude Code li comunica in ogni risposta con un evento `rate_limit_event`.
Li raccogliamo dalle risposte di Alfred e, quando sono vecchi, con una sonda:
una richiesta minima a Haiku che costa pochissimo.
I valori sono quelli dell'intero account: comprendono anche l'uso di Claude
fuori da Alfred.
"""

import asyncio
import logging
import time
from datetime import date

from alfred import config

log = logging.getLogger("alfred.limiti")

_stato: dict = {"sessione": None, "settimana": None, "aggiornato": 0, "oggi": None}
_sonda_in_corso = asyncio.Lock()


def _salva() -> None:
    config.salva_stato("limiti.json", **_stato)


_stato.update(config.leggi_stato("limiti.json"))


def stato() -> dict:
    oggi = _stato.get("oggi") or {}
    if oggi.get("data") != date.today().isoformat():
        oggi = {"data": date.today().isoformat(), "messaggi": 0, "token": 0}
    risultato = {"tipo": "limiti", **_stato, "oggi": oggi}
    if _economo:
        risultato["regime"] = _economo.regime(risultato)
    return risultato


_economo = None


def collega_economo(economo) -> None:
    """Così lo stato delle riserve riporta anche il regime dell'economo."""
    global _economo
    _economo = economo


def eta_s() -> float:
    return time.time() - _stato.get("aggiornato", 0)


def aggiorna(info: dict) -> bool:
    """Registra un rate_limit_info di Claude Code. True se è cambiato qualcosa."""
    finestre = info.get("unifiedWindows") or {}
    nuovo = {}
    for chiave, nome in (("sessione", "five_hour"), ("settimana", "seven_day")):
        f = finestre.get(nome)
        if f:
            nuovo[chiave] = {
                "uso": f.get("utilization"),
                "rinnovo": f.get("resetsAt"),
                "stato": f.get("status"),
            }
    if not nuovo:
        return False
    _stato.update(nuovo, aggiornato=time.time())
    _salva()
    return True


def conta_messaggio(token: int) -> None:
    """Consumo di Alfred nella giornata (solo indicativo)."""
    oggi = stato()["oggi"]
    oggi["messaggi"] += 1
    oggi["token"] += token
    _stato["oggi"] = oggi
    _salva()


async def sonda() -> bool:
    """Chiede a Claude i limiti attuali con una richiesta minima."""
    if _sonda_in_corso.locked():
        return False
    async with _sonda_in_corso:
        from alfred.brain.claude import chiedi_una_volta

        try:
            _, info = await chiedi_una_volta("ok", "Rispondi solo: ok")
        except (OSError, TimeoutError) as errore:
            log.warning("sonda dei limiti fallita: %s", errore)
            return False
        return aggiorna(info)

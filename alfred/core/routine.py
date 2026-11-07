"""Le routine del second brain: briefing con le attività, chiusura serale,
revisione settimanale dell'Inbox.

Tutto a costo zero: il mattino Alfred fotografa le attività aperte; la sera
confronta e trova quelle spuntate ("Fatto oggi"), guarda domani (agenda e
attività) e scrive nella nota del giorno. La domenica sera, se l'Inbox non è
vuota, propone di smistarla: lì, ragionando riga per riga con Pietro, lavora
il cervello (Haiku basta).
"""

import logging
from datetime import date, datetime, timedelta

from alfred import config
from alfred.core import parole
from alfred.tools import agenda, vault

log = logging.getLogger("alfred.routine")
FILE = "routine.json"
NOMINATE = 4  # attività dette per nome; le altre solo contate


def impostazioni() -> dict:
    return {"chiusura": 22, "revisione_giorno": 6} | config.carica().get("routine", {})  # 6 = domenica


def _elenco(attivita: list[dict]) -> str:
    nomi = [a["testo"] for a in attivita[:NOMINATE]]
    altre = len(attivita) - len(nomi)
    testo = ", ".join(nomi[:-1]) + (" e " if len(nomi) > 1 else "") + nomi[-1] if nomi else ""
    return testo + (f" e altre {altre}" if altre else "")


def frase_attivita(attivita: list[dict], giorno: date) -> str:
    """Per il briefing: le attività che scadono oggi e quelle già scadute."""
    if not attivita:
        return ""
    scadute = [a for a in attivita if a["scadenza"] < giorno.isoformat()]
    di_oggi = [a for a in attivita if a["scadenza"] == giorno.isoformat()]
    parti = []
    if di_oggi:
        parti.append(f"Attività in scadenza oggi: {_elenco(di_oggi)}.")
    if scadute:
        parti.append(f"Già scadute: {_elenco(scadute)}.")
    return " ".join(parti)


def mattino(giorno: date, testo_briefing: str, attivita: list[dict]) -> None:
    """Scrive il briefing nella nota del giorno e fotografa le attività aperte."""
    if not vault.radice():
        return
    righe = [f"- {testo_briefing}"] + [
        f"- da fare: {a['testo']} ({vault.collegamento(a['nota'])}, scadenza {a['scadenza']})" for a in attivita]
    vault.scrivi_sezione(giorno, "Briefing", righe)
    aperte = [[a["nota"], a["testo"]] for a in vault.attivita()]
    config.salva_stato(FILE, giorno=giorno.isoformat(), aperte=aperte)


async def chiusura(adesso: datetime) -> tuple[str, bool]:
    """(testo da dire, se proporre la revisione dell'Inbox). Scrive "Fatto oggi"."""
    if not vault.radice():
        raise vault.VaultNonPronto("il second brain non è collegato")
    oggi, domani = adesso.date(), adesso.date() + timedelta(days=1)
    stato = config.leggi_stato(FILE)
    fatte = (vault.attivita_fatte({tuple(a) for a in stato.get("aperte", [])})
             if stato.get("giorno") == oggi.isoformat() else [])
    if fatte:
        vault.scrivi_sezione(oggi, "Fatto oggi", [f"- {a['testo']} ({vault.collegamento(a['nota'])})" for a in fatte])
    config.salva_stato(FILE, chiusura=oggi.isoformat())

    parti = ["Chiudiamo la giornata, signore."]
    if fatte:
        parti.append(f"Oggi ha completato {len(fatte)} attività: {_elenco(fatte)}.")
    eventi = None
    if agenda.pronta():
        inizio = datetime.combine(domani, datetime.min.time()).astimezone()
        try:
            eventi = await agenda.eventi(inizio, inizio + timedelta(days=1))
        except Exception as errore:
            log.warning("agenda di domani non letta: %s", errore)
    if eventi is not None:
        parti.append(parole.elenco_eventi(eventi, "domani").replace("Domani, signore:", "Domani:"))
    da_fare = vault.attivita(fino_a=domani)
    if da_fare:
        parti.append(f"Attività in scadenza entro domani: {_elenco(da_fare)}.")
    inbox = vault.righe_inbox()
    revisione = bool(inbox) and oggi.weekday() == impostazioni()["revisione_giorno"]
    if revisione:
        parti.append(f"È domenica e nell'Inbox ci sono {len(inbox)} righe: vuole che le smistiamo insieme?")
    elif inbox:
        parti.append(f"Nell'Inbox ci sono {len(inbox)} righe in attesa.")
    if not revisione:
        parti.append("Buonanotte, signore.")
    return " ".join(parti), revisione


def testo_revisione() -> str:
    righe = vault.righe_inbox()
    if not righe:
        return "L'Inbox è vuota, signore: niente da smistare."
    elenco = " ".join(f"{i}) {r}." for i, r in enumerate(righe, 1))
    return (f"Ecco l'Inbox, signore: {elenco} Per ciascuna mi dica dove va: un'attività in un "
            "progetto o in un'area, una nota tra le risorse, oppure via.")

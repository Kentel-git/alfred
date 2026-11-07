"""Alfred di sua iniziativa: promemoria, preparazione delle dirette, briefing e diario.

Ogni minuto Alfred si chiede due cose: Pietro è al computer (schermo sbloccato)?
Ed è l'ora del silenzio (per Pietro dalle 23 alle 8)? Da lì decide come farsi
sentire: a voce, con una notifica, o su Telegram. Promemoria e briefing sono
composti senza modello; solo il riassunto del giorno chiede una riga a Haiku.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime, timedelta

from alfred import config
from alfred.core import parole, routine
from alfred.tools import agenda

log = logging.getLogger("alfred.iniziativa")
CONTROLLO_OGNI_S = 60
AGENDA_OGNI_S = 5 * 60


def _impostazioni() -> dict:
    return {
        "silenzio": [23, 8],  # dalle 23 alle 8: niente voce di sua iniziativa
        "anticipo_minuti": 15,
        "anticipi": {},  # per calendario, es. {"Turni" = 60}
        "calendario_dirette": "",  # i suoi eventi ricevono la preparazione della diretta
        "anticipo_dirette": 30,
    } | config.carica().get("iniziativa", {})


def ora_di_silenzio(adesso: datetime | None = None) -> bool:
    inizio, fine = _impostazioni()["silenzio"]
    ora = (adesso or datetime.now()).hour
    return (ora >= inizio or ora < fine) if inizio > fine else inizio <= ora < fine


def schermo_bloccato() -> bool:
    """Dal blocco schermo di logind (lo tiene aggiornato il desktop). Senza sessione
    grafica Pietro non è al computer."""
    def chiedi(*argomenti):
        return subprocess.run(["loginctl", *argomenti], capture_output=True, text=True, timeout=5).stdout.strip()
    try:
        sessione = chiedi("show-user", str(os.getuid()), "-p", "Display", "--value")
        return not sessione or chiedi("show-session", sessione, "-p", "LockedHint", "--value") == "yes"
    except (OSError, subprocess.TimeoutExpired):
        return False


def da_avvisare(eventi: list[dict], adesso: datetime, gia_avvisati: set[str], imp: dict) -> list[tuple[dict, bool]]:
    """Eventi entrati nella loro finestra di preavviso: (evento, è_una_diretta)."""
    risultati = []
    for e in eventi:
        if e["tutto_il_giorno"] or e["id"] in gia_avvisati:
            continue
        diretta = bool(imp["calendario_dirette"]) and e["nome_calendario"] == imp["calendario_dirette"]
        minuti = imp["anticipo_dirette"] if diretta else imp["anticipi"].get(e["nome_calendario"], imp["anticipo_minuti"])
        inizio = datetime.fromisoformat(e["inizio"])
        if inizio - timedelta(minutes=minuti) <= adesso < inizio:
            risultati.append((e, diretta))
    return risultati


def da_proporre_chiusura(adesso: datetime, stato: dict, stato_routine: dict) -> bool:
    """Dall'ora della chiusura al silenzio, una volta al giorno, se non l'ha già fatta
    e se oggi è passato dal computer (briefing fatto) e il second brain c'è."""
    from alfred.tools import vault

    oggi = adesso.date().isoformat()
    return (adesso.hour >= routine.impostazioni()["chiusura"] and not ora_di_silenzio(adesso)
            and stato.get("briefing") == oggi and stato.get("chiusura_proposta") != oggi
            and stato_routine.get("chiusura") != oggi and vault.radice() is not None)


def testo_promemoria(e: dict, adesso: datetime, diretta: bool) -> str:
    tra = parole.tra(round((datetime.fromisoformat(e["inizio"]) - adesso).total_seconds() / 60))
    if diretta:
        return (f"Signore, {tra} si va in onda con «{e['titolo']}». Apro la regia: prima di partire "
                "passiamo in rassegna le fonti, il link della chat e il microfono?")
    return f"Signore, {tra}: «{e['titolo']}»."


def testo_briefing(adesso: datetime, eventi: list[dict] | None, meteo: dict | None, riserve: dict,
                   attivita: list[dict] | None = None) -> str:
    saluto = "Buongiorno" if adesso.hour < 13 else "Buon pomeriggio" if adesso.hour < 18 else "Buonasera"
    parti = [f"{saluto}, signore. Sono le {parole.orario(adesso)}."]
    if meteo:
        parti.append(f"Fuori ci sono {meteo['temperatura']} gradi, {meteo['descrizione']}.")
    if eventi is not None:  # agenda non collegata: meglio tacere che dire "nessun impegno"
        parti.append(parole.elenco_eventi(eventi, "oggi").replace("Oggi, signore:", "Oggi:"))
    if attivita:
        parti.append(routine.frase_attivita(attivita, adesso.date()))
    if (regime := riserve.get("regime", {})).get("nome", "normale") != "normale":
        parti.append(f"Le riserve della settimana chiedono {regime['nome']}: {regime['motivo']}.")
    return " ".join(parti)


class Iniziativa:
    def __init__(self, conversazione):
        self.conversazione = conversazione
        self._eventi: list[dict] = []
        self._agenda_letta = 0.0

    async def _prossimi_eventi(self, adesso: datetime, imp: dict) -> list[dict]:
        if agenda.pronta() and adesso.timestamp() - self._agenda_letta > AGENDA_OGNI_S:
            # I calendari personali più quello delle dirette (che di solito non è tra i personali).
            personali = config.carica().get("agenda", {}).get("calendari")
            richiesti = [*personali, imp["calendario_dirette"]] if personali and imp["calendario_dirette"] else None
            try:
                self._eventi = await agenda.eventi(adesso, adesso + timedelta(hours=2), richiesti)
                self._agenda_letta = adesso.timestamp()
            except Exception as errore:
                log.warning("agenda non letta: %s", errore)
        return self._eventi

    async def ciclo(self) -> None:
        while True:
            try:
                await self._giro()
            except Exception:
                log.exception("l'iniziativa si è inceppata")
            await asyncio.sleep(CONTROLLO_OGNI_S)

    async def _giro(self) -> None:
        adesso, imp = datetime.now().astimezone(), _impostazioni()
        bloccato = schermo_bloccato()
        stato = config.leggi_stato("iniziativa.json")

        avvisati = set(stato.get("avvisati", []))
        for evento, diretta in da_avvisare(await self._prossimi_eventi(adesso, imp), adesso, avvisati, imp):
            avvisati.add(evento["id"])
            config.salva_stato("iniziativa.json", avvisati=sorted(avvisati)[-200:])
            if diretta:
                await self.conversazione.azioni.richiedi("apri_obs")
            await self.conversazione.di_sua_iniziativa(testo_promemoria(evento, adesso, diretta), bloccato)

        oggi = adesso.date().isoformat()
        if not bloccato and not ora_di_silenzio(adesso) and stato.get("briefing") != oggi:
            config.salva_stato("iniziativa.json", briefing=oggi)
            await self.conversazione.nuovo_giorno(adesso)
        elif not bloccato and da_proporre_chiusura(adesso, stato, config.leggi_stato(routine.FILE)):
            config.salva_stato("iniziativa.json", chiusura_proposta=oggi)
            esito = await self.conversazione.azioni.richiedi("proponi_chiusura")
            await self.conversazione.di_sua_iniziativa(esito["messaggio"], bloccato)

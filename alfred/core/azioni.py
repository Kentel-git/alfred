"""Le azioni di Alfred: cosa sa fare, cosa chiede di confermare, cosa risponde.

Un'azione si può chiedere in tre modi, e passa sempre da qui:
- comando diretto riconosciuto in locale ("avvia la diretta"): zero token;
- il cervello, tramite gli strumenti MCP;
- un pulsante dell'HUD.

Le azioni delicate (sensibile=True) non partono subito: Alfred chiede conferma
e l'HUD mostra la richiesta. Si conferma con un pulsante o dicendo "sì".
Le risposte sono già scritte, in personaggio, così l'esito di un'azione non
costa nulla.
"""

import difflib
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from alfred import config
from alfred.tools import gioco, obs, telegram

log = logging.getLogger("alfred.azioni")
SCADENZA_CONFERMA_S = 120


def _una(*frasi: str) -> str:
    return random.choice(frasi)


# --- Esecutori ---------------------------------------------------------------
# Ognuno restituisce {"ok": bool, "messaggio": frase di Alfred, ...}.

def _elenco(nomi: list[str]) -> str:
    return nomi[0] if len(nomi) == 1 else ", ".join(nomi[:-1]) + " e " + nomi[-1]


async def _modalita_gioco(_parametri: dict) -> dict:
    esito = gioco.avvia(config.carica().get("gioco", {}))
    if not esito["configurata"]:
        return {"ok": False, "messaggio": "Temo che la modalità gioco non sia ancora configurata su questa macchina, signore."}
    aperte, gia = esito["aperte"], esito["gia_aperte"]
    if not aperte:
        return {"ok": False, "messaggio": f"{_elenco(gia)} {'è' if len(gia) == 1 else 'sono'} già aperti, signore. La battaglia la attende."}
    frase = _una(
        f"Modalità gioco, signore. {_elenco(aperte)} in arrivo.",
        f"Preparo il campo di battaglia, signore: {_elenco(aperte)} a momenti.",
    )
    if "CurseForge" in aperte:
        frase += " Dia un'occhiata agli addon prima di partire: un'interfaccia aggiornata è mezza vittoria."
    elif gia:
        frase += f" {_elenco(gia)} era già aperto."
    return {"ok": True, "messaggio": frase}


async def _apri_obs(_parametri: dict) -> dict:
    cfg = config.carica().get("obs", {})
    if (await obs.stato(cfg))["aperto"]:
        return {"ok": False, "messaggio": "OBS è già aperto, signore."}
    if not obs.apri(cfg):
        return {"ok": False, "messaggio": "Non so ancora come aprire OBS su questa macchina, signore."}
    return {"ok": True, "messaggio": _una(
        "Apro OBS, signore. La regia sarà pronta tra qualche istante.",
        "OBS in arrivo, signore. Accendo le luci dello studio.",
    )}


def _obs(tipo: str, dati: dict | None, riuscito: Callable[[], str], gia: str | None = None):
    """Esecutore per una richiesta OBS, con le frasi per esito e problemi."""
    async def esegui(_parametri: dict) -> dict:
        try:
            r = await obs.esegui(config.carica().get("obs", {}), tipo, dati)
        except obs.ObsNonRaggiungibile:
            return {"ok": False, "obs_chiuso": True, "messaggio": "OBS non è aperto, signore. Se desidera, lo apro io: mi basta dirmelo."}
        if r["_ok"]:
            return {"ok": True, "messaggio": riuscito()}
        log.warning("OBS ha rifiutato %s: %s", tipo, r["_errore"])
        return {"ok": False, "messaggio": gia or f"OBS si è rifiutato, signore: {r['_errore'] or 'senza spiegazioni'}."}
    return esegui


async def _cambia_scena(parametri: dict) -> dict:
    cfg = config.carica().get("obs", {})
    stato = await obs.stato(cfg)
    if not stato["aperto"]:
        return {"ok": False, "obs_chiuso": True, "messaggio": "OBS non è aperto, signore. Se desidera, lo apro io."}
    richiesta = (parametri.get("scena") or "").strip()
    scene = stato["scene"]
    per_nome = {s.lower(): s for s in scene}
    # Corrispondenza esatta, poi parziale, poi per somiglianza.
    scelta = per_nome.get(richiesta.lower())
    if not scelta:
        parziali = [s for s in scene if richiesta.lower() in s.lower()]
        scelta = parziali[0] if len(parziali) == 1 else None
    if not scelta:
        simili = difflib.get_close_matches(richiesta.lower(), list(per_nome), n=1, cutoff=0.5)
        scelta = per_nome[simili[0]] if simili else None
    if not scelta:
        return {"ok": False, "messaggio": f"Non trovo una scena che somigli a «{richiesta}», signore. Ho: {', '.join(scene)}."}
    if scelta == stato["scena_attuale"]:
        return {"ok": False, "messaggio": f"Siamo già sulla scena «{scelta}», signore."}
    await obs.esegui(cfg, "SetCurrentProgramScene", {"sceneName": scelta})
    return {"ok": True, "messaggio": _una(f"Scena «{scelta}», signore.", f"Ecco «{scelta}», signore.")}


async def _invia_telegram(parametri: dict) -> dict:
    testo = (parametri.get("testo") or "").strip()
    if not testo:
        return {"ok": False, "messaggio": "Cosa desidera che le scriva, signore?"}
    try:
        await telegram.invia(testo)
    except telegram.TelegramNonPronto as errore:
        log.warning("Telegram: %s", errore)
        return {"ok": False, "messaggio": "Telegram non è ancora collegato, signore: manca il bot, o non mi ha ancora scritto /start."}
    return {"ok": True, "messaggio": _una("Messaggio inviato su Telegram, signore.", "Fatto, signore: lo troverà su Telegram.")}


# --- Registro ----------------------------------------------------------------

@dataclass
class Azione:
    nome: str
    descrizione: str  # per il cervello
    domanda: str  # richiesta di conferma, se sensibile
    esegui: Callable[[dict], Awaitable[dict]]
    sensibile: bool = False


AZIONI = {a.nome: a for a in [
    Azione("modalita_gioco", "Avvia la modalità gioco (apre Battle.net e CurseForge).", "", _modalita_gioco),
    Azione("apri_obs", "Apre OBS Studio.", "", _apri_obs),
    Azione(
        "avvia_diretta", "Avvia la diretta in OBS.", "Avvio la diretta, signore? Mi basta un sì.",
        _obs("StartStream", None, lambda: _una("In onda, signore. Il pubblico è tutto suo.", "Diretta avviata, signore. Si va in scena."),
             "La diretta è già in corso, signore."),
        sensibile=True,
    ),
    Azione(
        "ferma_diretta", "Termina la diretta in OBS.", "Chiudo la diretta, signore? Mi basta un sì.",
        _obs("StopStream", None, lambda: _una("Diretta conclusa, signore. Un'altra serata consegnata ai posteri.", "Siamo fuori onda, signore. Ottimo lavoro."),
             "Non c'è nessuna diretta in corso, signore."),
        sensibile=True,
    ),
    Azione("avvia_registrazione", "Avvia la registrazione in OBS.", "",
           _obs("StartRecord", None, lambda: _una("Registrazione avviata, signore.", "Si registra, signore. Ogni parola sarà conservata."),
                "Sto già registrando, signore.")),
    Azione("ferma_registrazione", "Ferma la registrazione in OBS.", "",
           _obs("StopRecord", None, lambda: "Registrazione fermata e messa al sicuro, signore.",
                "Non c'è nessuna registrazione in corso, signore.")),
    Azione("pausa_registrazione", "Mette in pausa la registrazione in OBS.", "",
           _obs("PauseRecord", None, lambda: "Registrazione in pausa, signore.",
                "Non c'è una registrazione da mettere in pausa, signore.")),
    Azione("riprendi_registrazione", "Riprende la registrazione in pausa in OBS.", "",
           _obs("ResumeRecord", None, lambda: "Riprendo a registrare, signore.",
                "Non c'è una registrazione in pausa, signore.")),
    Azione("invia_telegram", "Invia un messaggio Telegram a Pietro. Parametro: testo.", "", _invia_telegram),
    Azione("cambia_scena", "Cambia la scena di OBS. Parametro: scena (nome, anche approssimativo).", "", _cambia_scena),
]}


class Gestore:
    """Esegue le azioni e custodisce quella in attesa di conferma."""

    def __init__(self, invia: Callable[[dict], Awaitable[None]], annuncia: Callable[[str, dict], Awaitable[None]]):
        self._invia = invia  # messaggi agli HUD
        self._annuncia = annuncia  # esito come messaggio di Alfred nella conversazione
        self.in_attesa: dict | None = None

    def _attesa_valida(self) -> dict | None:
        if self.in_attesa and time.time() > self.in_attesa["scadenza"]:
            self.in_attesa = None
        return self.in_attesa

    async def richiedi(self, nome: str, parametri: dict | None = None) -> dict:
        """Chiede un'azione. Le sensibili restano in attesa di conferma."""
        azione = AZIONI.get(nome)
        if not azione:
            return {"ok": False, "messaggio": f"Non conosco l'azione «{nome}», signore."}
        parametri = parametri or {}
        if azione.sensibile:
            self.in_attesa = {
                "id": uuid.uuid4().hex[:8], "nome": nome, "parametri": parametri,
                "domanda": azione.domanda, "scadenza": time.time() + SCADENZA_CONFERMA_S,
            }
            await self._invia({"tipo": "conferma", "id": self.in_attesa["id"], "domanda": azione.domanda})
            return {"ok": True, "azione": nome, "in_attesa_di_conferma": True, "messaggio": azione.domanda}
        return await self._esegui(azione, parametri)

    async def _esegui(self, azione: Azione, parametri: dict) -> dict:
        try:
            esito = await azione.esegui(parametri)
        except Exception as errore:
            log.exception("azione %s fallita", azione.nome)
            esito = {"ok": False, "messaggio": f"Qualcosa è andato storto, signore: {errore}."}
        esito["azione"] = azione.nome
        return esito

    async def conferma(self, si: bool, id_attesa: str | None = None) -> dict | None:
        """Risposta alla richiesta in attesa. None se non c'era nulla da confermare."""
        attesa = self._attesa_valida()
        if not attesa or (id_attesa and id_attesa != attesa["id"]):
            return None
        self.in_attesa = None
        await self._invia({"tipo": "conferma_chiusa", "id": attesa["id"]})
        if not si:
            return {"ok": True, "azione": attesa["nome"], "annullata": True,
                    "messaggio": _una("Come non detto, signore.", "Lascio stare, signore.")}
        return await self._esegui(AZIONI[attesa["nome"]], attesa["parametri"])

    async def conferma_da_hud(self, si: bool, id_attesa: str) -> None:
        esito = await self.conferma(si, id_attesa)
        if esito:
            await self._annuncia(esito["messaggio"], esito)

    def stato_attesa(self) -> dict | None:
        attesa = self._attesa_valida()
        return {"tipo": "conferma", "id": attesa["id"], "domanda": attesa["domanda"]} if attesa else None


def descrizione_per_riferire(esito: dict) -> str:
    """Riga per informare il cervello di ciò che è successo senza di lui."""
    if esito.get("in_attesa_di_conferma"):
        stato = "in attesa di conferma"
    elif esito.get("annullata"):
        stato = "annullata"
    else:
        stato = "riuscita" if esito.get("ok") else "non riuscita"
    return f"azione {esito.get('azione')} {stato}: «{esito.get('messaggio')}»"

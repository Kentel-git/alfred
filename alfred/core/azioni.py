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

import asyncio
import difflib
import logging
import random
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from alfred import brain, config
from alfred.core import attivita, parole, veglia
from alfred.tools import agenda, gioco, notion, obs, pc, telegram

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


ID_VIDEO = re.compile(r"(?:v=|/live/|youtu\.be/|/shorts/)([\w-]{11})|^([\w-]{11})$")


async def _aggiorna_chat(parametri: dict) -> dict:
    """Mette il link della chat della nuova diretta in tutte le fonti della chat."""
    cfg = config.carica().get("obs", {})
    fonti = cfg.get("fonti_chat", [])
    if not fonti:
        return {"ok": False, "messaggio": "Non so quali fonti di OBS mostrino la chat, signore: manca fonti_chat nella configurazione."}
    trovato = ID_VIDEO.search((parametri.get("link") or "").strip())
    if not trovato:
        return {"ok": False, "messaggio": "Non riconosco quel link, signore. Mi basta quello della diretta su YouTube."}
    url = f"https://www.youtube.com/live_chat?is_popout=1&v={trovato[1] or trovato[2]}"
    try:
        esiti = [await obs.esegui(cfg, "SetInputSettings", {"inputName": f, "inputSettings": {"url": url}}) for f in fonti]
    except obs.ObsNonRaggiungibile:
        return {"ok": False, "messaggio": "OBS non è aperto, signore. Lo apro?"}
    mancanti = [f for f, e in zip(fonti, esiti) if not e["_ok"]]
    if mancanti:
        return {"ok": False, "messaggio": f"Non trovo in OBS le fonti {', '.join(mancanti)}, signore: la collezione di scene è quella giusta?"}
    return {"ok": True, "messaggio": f"Chat aggiornata in {_elenco(fonti)}, signore."}


async def _ricorda(parametri: dict) -> dict:
    fatto = (parametri.get("fatto") or "").strip()
    if not fatto:
        return {"ok": False, "messaggio": "Cosa devo ricordare, signore?"}
    brain.ricorda(fatto)
    return {"ok": True, "messaggio": _una("Lo terrò a mente, signore.", "Annotato, signore.")}


async def _impara_pronuncia(parametri: dict) -> dict:
    from alfred.voce import parola

    inglese = parametri.get("inglese", True)
    nuove = parola.impara(parametri.get("parole") or [], inglese)
    if not nuove:
        return {"ok": True, "messaggio": "Le conoscevo già, signore."}
    elenco = ", ".join(f"«{p}»" for p in nuove)
    return {"ok": True, "messaggio": f"D'ora in poi pronuncerò {elenco} all'inglese, signore." if inglese
            else f"Lascerò {elenco} all'italiana, signore, e non glielo chiederò più."}


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


GIORNI_AGENDA_HUD = 4


async def agenda_per_hud() -> dict:
    """Eventi di oggi e dei prossimi giorni per il riquadro dell'HUD."""
    if not agenda.pronta():
        return {"tipo": "agenda", "pronta": False}
    oggi = datetime.combine(date.today(), datetime.min.time()).astimezone()
    try:
        eventi = await agenda.eventi(oggi, oggi + timedelta(days=GIORNI_AGENDA_HUD))
    except Exception as errore:
        log.warning("agenda non disponibile: %s", errore)
        return {"tipo": "agenda", "pronta": True, "errore": str(errore)}
    return {"tipo": "agenda", "pronta": True, "eventi": eventi}


NON_PRONTA = "L'agenda non è ancora collegata, signore: manca l'autorizzazione di Google."


def _agenda(funzione):
    """Gestisce in un solo punto agenda non collegata ed errori di Google."""
    async def esegui(parametri: dict) -> dict:
        try:
            return await funzione(parametri)
        except agenda.AgendaNonPronta as errore:
            log.warning("agenda: %s", errore)
            if not agenda.pronta():
                return {"ok": False, "messaggio": NON_PRONTA}
            return {"ok": False, "messaggio": f"Google ha obiettato, signore: {errore}."}
    return esegui


ORA_DEL_RISVEGLIO = 5


def notte_fonda() -> bool:
    """Tra mezzanotte e le 5 "domani" vuol dire il giorno che sta per cominciare."""
    return datetime.now().hour < ORA_DEL_RISVEGLIO


def giorno_richiesto(testo: str | None) -> date:
    testo = (testo or "oggi").strip().lower()
    scorciatoie = {"oggi": 0, "domani": 1, "dopodomani": 2}
    if testo in scorciatoie:
        spostamento = scorciatoie[testo] - (1 if notte_fonda() and testo != "oggi" else 0)
        return date.today() + timedelta(days=spostamento)
    if testo in parole.GIORNI:  # il prossimo giorno con quel nome
        avanti = (parole.GIORNI.index(testo) - date.today().weekday()) % 7 or 7
        return date.today() + timedelta(days=avanti)
    return date.fromisoformat(testo[:10])


@_agenda
async def _leggi_agenda(parametri: dict) -> dict:
    giorno = giorno_richiesto(parametri.get("giorno"))
    inizio = datetime.combine(giorno, datetime.min.time()).astimezone()
    trovati = await agenda.eventi(inizio, inizio + timedelta(days=1))
    # Di notte "oggi" e "domani" si confondono: meglio dire la data per esteso.
    etichetta = parole.giorno_esteso(giorno) if notte_fonda() else parole.giorno(giorno)
    return {"ok": True, "messaggio": parole.elenco_eventi(trovati, etichetta)}


@_agenda
async def _crea_evento(parametri: dict) -> dict:
    e = await agenda.crea(**{k: v for k, v in parametri.items() if v is not None})
    return {"ok": True, "evento": e, "messaggio": _una(
        f"Ho segnato «{e['titolo']}» per {parole.quando(e)}, signore.",
        f"Fatto, signore: «{e['titolo']}», {parole.quando(e)}.",
    )}


@_agenda
async def _sposta_evento(parametri: dict) -> dict:
    e = await agenda.sposta(parametri["id"], parametri["inizio"], parametri.get("fine"),
                            parametri.get("calendario") or "primary")
    return {"ok": True, "evento": e, "messaggio": f"«{e['titolo']}» spostato a {parole.quando(e)}, signore."}


@_agenda
async def _elimina_evento(parametri: dict) -> dict:
    await agenda.elimina(parametri["id"], parametri.get("calendario") or "primary")
    titolo = parametri.get("_titolo")  # messo da _domanda_elimina
    return {"ok": True, "messaggio": f"«{titolo}» eliminato dall'agenda, signore." if titolo
            else "Evento eliminato dall'agenda, signore."}


async def _domanda_elimina(parametri: dict) -> str:
    e = await agenda.evento(parametri["id"], parametri.get("calendario") or "primary")
    parametri["_titolo"] = e["titolo"]
    return f"Elimino «{e['titolo']}» di {parole.quando(e)}, signore? Mi basta un sì."


# --- Notion -----------------------------------------------------------------------

def _notion(funzione):
    """Notion non collegato ed errori dell'API in un solo punto."""
    async def esegui(parametri: dict) -> dict:
        if not notion.pronto():
            return {"ok": False, "messaggio": "Notion non è ancora collegato, signore: manca il token dell'integrazione."}
        try:
            return await funzione(parametri)
        except notion.NotionNonPronto as errore:
            log.warning("notion: %s", errore)
            return {"ok": False, "messaggio": f"Notion ha obiettato, signore: {errore}."}
    return esegui


@_notion
async def _notion_cerca(p: dict) -> dict:
    trovati = await notion.cerca(p.get("testo", ""))
    return {"ok": True, "risultati": trovati, "messaggio": f"Ho trovato {len(trovati)} risultati su Notion, signore."
            if trovati else "Su Notion non trovo nulla, signore, almeno tra le pagine che mi ha condiviso."}


@_notion
async def _notion_leggi(p: dict) -> dict:
    return {"ok": True, **await notion.leggi(p["id"]), "messaggio": "Letto, signore."}


@_notion
async def _notion_crea(p: dict) -> dict:
    v = await notion.crea(p["genitore"], p["titolo"], p.get("testo") or "", p.get("proprieta"))
    return {"ok": True, "pagina": v, "messaggio": f"Ho creato «{v['titolo']}» su Notion, signore."}


@_notion
async def _notion_aggiungi(p: dict) -> dict:
    n = await notion.aggiungi(p["id"], p["testo"])
    return {"ok": True, "messaggio": f"Annotato su Notion, signore ({n} righe)."}


@_notion
async def _notion_aggiorna(p: dict) -> dict:
    v = await notion.aggiorna(p["id"], p["proprieta"])
    return {"ok": True, "messaggio": f"Aggiornato «{v['titolo']}» su Notion, signore."}


@_notion
async def _notion_riscrivi(p: dict) -> dict:
    await notion.riscrivi(p["id"], p["testo"])
    return {"ok": True, "messaggio": "Riscritto su Notion, signore."}


@_notion
async def _notion_elimina(p: dict) -> dict:
    await notion.elimina(p["id"])
    return {"ok": True, "messaggio": f"Eliminato da Notion, signore: {p.get('_cosa', 'fatto')}. Resta nel cestino per 30 giorni."}


async def _domanda_riscrivi(p: dict) -> str:
    vecchio = await notion.blocco(p["id"])
    return f"Su Notion sostituisco «{vecchio[:80]}» con «{p['testo'][:80]}», signore? Mi basta un sì."


async def _domanda_elimina_notion(p: dict) -> str:
    p["_cosa"] = await notion.descrivi(p["id"])
    return f"Elimino da Notion {p['_cosa']}, signore? Finirà nel cestino. Mi basta un sì."


# --- Il computer: app, cartelle, volume, musica, timer ------------------------------

async def _apri(p: dict) -> dict:
    cosa = (p.get("cosa") or "").strip()
    trovato = pc.trova(cosa)
    if not trovato:
        return {"ok": False, "messaggio": f"Non trovo «{cosa}» tra le app e le cartelle, signore."}
    tipo, obiettivo, nome = trovato
    pc.apri(tipo, obiettivo)
    return {"ok": True, "messaggio": _una(f"Apro {nome}, signore.", f"Ecco {nome}, signore.")}


async def _volume(p: dict) -> dict:
    livello, muto = pc.volume(p.get("azione") or "imposta", p.get("livello"))
    return {"ok": True, "messaggio": "Audio silenziato, signore." if muto else f"Volume al {livello} per cento, signore."}


async def _riproduzione(p: dict) -> dict:
    azione = p.get("azione") or "pausa"
    lettore = pc.riproduzione(azione)
    if not lettore:
        return {"ok": False, "messaggio": "Non c'è nulla in riproduzione, signore."}
    detto = {"pausa": "In pausa", "play": "Riprendo", "avanti": "Avanti", "indietro": "Torno indietro"}[azione]
    return {"ok": True, "messaggio": f"{detto}, signore."}


async def _timer(p: dict) -> dict:
    return await _sorveglia({"tipo": "timer", "soglia": p.get("minuti"), "etichetta": p.get("etichetta")})


async def _sorveglia(p: dict) -> dict:
    try:
        a = await attivita.istanza().aggiungi(p.get("tipo") or "", p.get("valore"), p.get("soglia"),
                                              p.get("etichetta") or "")
    except attivita.AttivitaNonValida as errore:
        return {"ok": False, "messaggio": f"Non posso, signore: {errore}."}
    if a["tipo"] == "timer":
        return {"ok": True, "id": a["id"], "messaggio": f"Timer di {parole.durata(a['secondi'])} avviato, signore."}
    return {"ok": True, "id": a["id"], "messaggio": f"Terrò d'occhio: {attivita.descrizione(a)}, signore."}


async def _annulla_attivita(p: dict) -> dict:
    n = await attivita.istanza().annulla(p.get("id"), p.get("tipo"))
    cosa = "timer" if p.get("tipo") == "timer" else "attività"
    if not n:
        return {"ok": True, "messaggio": f"Non c'erano {cosa} da annullare, signore."}
    return {"ok": True, "messaggio": "Annullato, signore." if n == 1 else f"{n} {cosa} annullati, signore."}


async def _sveglia(accesa: bool) -> dict:
    from alfred.voce import sveglia

    if sveglia.istanza is None or not sveglia.disponibile():
        return {"ok": False, "messaggio": "Non ho ancora le orecchie per il mio nome su questa macchina, signore."}
    sveglia.istanza.attiva = accesa
    if accesa:
        return {"ok": True, "messaggio": "Sono di nuovo all'ascolto, signore: mi basta sentire il mio nome."}
    return {"ok": True, "messaggio": "Smetto di ascoltare, signore. Per chiamarmi resta il tasto, o mi dica di tornare ad ascoltare."}


async def _sospendi(_parametri: dict) -> dict:
    asyncio.create_task(veglia.istanza().sospendi_ora())
    return {"ok": True, "messaggio": "Buonanotte, signore. Spengo le luci."}


async def _consenti_standby(_parametri: dict) -> dict:
    veglia.istanza().imposta(False)
    return {"ok": True, "messaggio": "Come desidera, signore: il computer potrà riposare quando vorrà. Se mi serve sveglio, me lo dica."}


async def _impedisci_standby(_parametri: dict) -> dict:
    veglia.istanza().imposta(True)
    return {"ok": True, "messaggio": "Resterò di guardia, signore: con l'alimentatore collegato il computer non andrà in standby da solo."}


# --- Registro ----------------------------------------------------------------

@dataclass
class Azione:
    nome: str
    # Richiesta di conferma, se sensibile: testo fisso o funzione che lo
    # prepara dai parametri (es. il titolo dell'evento da eliminare).
    domanda: str | Callable[[dict], Awaitable[str]]
    esegui: Callable[[dict], Awaitable[dict]]
    sensibile: bool = False


AZIONI = {a.nome: a for a in [
    Azione("modalita_gioco", "", _modalita_gioco),
    Azione("apri_obs", "", _apri_obs),
    Azione("avvia_diretta", "Avvio la diretta, signore? Mi basta un sì.",
        _obs("StartStream", None, lambda: _una("In onda, signore. Il pubblico è tutto suo.", "Diretta avviata, signore. Si va in scena."),
             "La diretta è già in corso, signore."),
        sensibile=True,
    ),
    Azione("ferma_diretta", "Chiudo la diretta, signore? Mi basta un sì.",
        _obs("StopStream", None, lambda: _una("Diretta conclusa, signore. Un'altra serata consegnata ai posteri.", "Siamo fuori onda, signore. Ottimo lavoro."),
             "Non c'è nessuna diretta in corso, signore."),
        sensibile=True,
    ),
    Azione("avvia_registrazione", "",
           _obs("StartRecord", None, lambda: _una("Registrazione avviata, signore.", "Si registra, signore. Ogni parola sarà conservata."),
                "Sto già registrando, signore.")),
    Azione("ferma_registrazione", "",
           _obs("StopRecord", None, lambda: "Registrazione fermata e messa al sicuro, signore.",
                "Non c'è nessuna registrazione in corso, signore.")),
    Azione("pausa_registrazione", "",
           _obs("PauseRecord", None, lambda: "Registrazione in pausa, signore.",
                "Non c'è una registrazione da mettere in pausa, signore.")),
    Azione("riprendi_registrazione", "",
           _obs("ResumeRecord", None, lambda: "Riprendo a registrare, signore.",
                "Non c'è una registrazione in pausa, signore.")),
    Azione("invia_telegram", "", _invia_telegram),
    Azione("leggi_agenda", "", _leggi_agenda),
    Azione("crea_evento", "", _crea_evento),
    Azione("sposta_evento", "", _sposta_evento),
    Azione("elimina_evento", _domanda_elimina, _elimina_evento, sensibile=True),
    Azione("sveglia_spenta", "",
           lambda _p: _sveglia(False)),
    Azione("sveglia_accesa", "", lambda _p: _sveglia(True)),
    Azione("sospendi_computer", "Metto il computer in standby, signore? Da quel momento non potrò risponderle, nemmeno su Telegram.",
           _sospendi, sensibile=True),
    Azione("consenti_standby", "", _consenti_standby),
    Azione("impedisci_standby", "", _impedisci_standby),
    Azione("aggiorna_chat", "", _aggiorna_chat),
    Azione("ricorda", "", _ricorda),
    Azione("impara_pronuncia", "", _impara_pronuncia),
    Azione("apri", "", _apri),
    Azione("volume", "", _volume),
    Azione("riproduzione", "", _riproduzione),
    Azione("timer", "", _timer),
    Azione("sorveglia", "", _sorveglia),
    Azione("annulla_attivita", "", _annulla_attivita),
    Azione("cambia_scena", "", _cambia_scena),
    Azione("notion_cerca", "", _notion_cerca),
    Azione("notion_leggi", "", _notion_leggi),
    Azione("notion_crea", "", _notion_crea),
    Azione("notion_aggiungi", "", _notion_aggiungi),
    Azione("notion_aggiorna", "", _notion_aggiorna),
    Azione("notion_riscrivi", _domanda_riscrivi, _notion_riscrivi, sensibile=True),
    Azione("notion_elimina", _domanda_elimina_notion, _notion_elimina, sensibile=True),
]}


class Gestore:
    """Esegue le azioni e custodisce quella in attesa di conferma."""

    def __init__(self, invia: Callable[[dict], Awaitable[None]]):
        self._invia = invia  # richieste di conferma agli HUD (e a Telegram)
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
            if isinstance(azione.domanda, str):
                domanda = azione.domanda
            else:
                try:
                    domanda = await azione.domanda(parametri)
                except Exception as errore:
                    log.warning("conferma di %s non preparata: %s", nome, errore)
                    return {"ok": False, "azione": nome, "messaggio": f"Non riesco a trovare ciò che mi chiede, signore: {errore}."}
            self.in_attesa = {
                "id": uuid.uuid4().hex[:8], "nome": nome, "parametri": parametri,
                "domanda": domanda, "scadenza": time.time() + SCADENZA_CONFERMA_S,
            }
            await self._invia({"tipo": "conferma", "id": self.in_attesa["id"], "domanda": domanda})
            return {"ok": True, "azione": nome, "in_attesa_di_conferma": True, "messaggio": domanda}
        return await self._esegui(azione, parametri)

    async def _esegui(self, azione: Azione, parametri: dict) -> dict:
        try:
            esito = await azione.esegui(parametri)
        except Exception as errore:
            log.exception("azione %s fallita", azione.nome)
            esito = {"ok": False, "messaggio": f"Qualcosa è andato storto, signore: {errore}."}
        esito["azione"] = azione.nome
        if esito.get("ok") and azione.nome in ("crea_evento", "sposta_evento", "elimina_evento"):
            await self._invia(await agenda_per_hud())  # l'HUD si aggiorna subito
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

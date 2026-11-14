"""alfred-core: il servizio sempre attivo che serve l'HUD e i suoi dati.

L'HUD riceve tutto da un WebSocket (/ws): il servizio spinge i dati di sistema
e il meteo, e osserva i file del progetto e la configurazione:
- grafica modificata (ui/) → l'HUD si aggiorna da solo;
- config.toml modificata → nuova configurazione applicata subito;
- codice Python modificato → il servizio si riavvia, l'HUD si ricollega;
- personalità o scheda personale modificate → il cervello riparte con la
  stessa conversazione.

Dallo stesso WebSocket arrivano i messaggi per Alfred e partono le risposte,
parola per parola, a tutti gli HUD collegati.
"""

import asyncio
import contextlib
import logging
import os
import sys
import uuid
import warnings
from datetime import date, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from watchfiles import awatch

from alfred import __version__, config
from alfred.brain import FILE_PERSONALITA, FILE_SCHEDA
from alfred.core import attivita, compiti, limiti, meteo, sistema, telegram_ponte, veglia
from alfred.core.iniziativa import Iniziativa
from alfred.core.azioni import agenda_per_hud
from alfred.core.conversazione import Conversazione
from alfred.voce import ascolto, parola
from alfred.tools import agenda, obs, vault

CARTELLA_PROGETTO = Path(__file__).resolve().parents[2]
CARTELLA_UI = CARTELLA_PROGETTO / "ui"
CARTELLA_CODICE = CARTELLA_PROGETTO / "alfred"

INTERVALLO_SISTEMA_S = 2
INTERVALLO_METEO_S = 10 * 60
INTERVALLO_LIMITI_S = 30 * 60
INTERVALLO_REGIA_S = 3
INTERVALLO_AGENDA_S = 5 * 60

LIMITI_VECCHI_S = 5 * 60

# Cambia a ogni avvio: l'HUD lo usa per capire che il servizio è stato aggiornato.
ID_AVVIO = uuid.uuid4().hex
log = logging.getLogger("alfred.core")


class Diffusore:
    """Tiene traccia degli HUD collegati e manda loro i messaggi."""

    def __init__(self):
        self.client: set[WebSocket] = set()

    async def invia(self, messaggio: dict, solo: WebSocket | None = None) -> None:
        for ws in [solo] if solo else list(self.client):
            try:
                await ws.send_json(messaggio)
            except Exception:
                self.client.discard(ws)


diffusore = Diffusore()
conversazione: Conversazione | None = None


def _stato() -> dict:
    cfg = config.carica()
    return {"versione": __version__, "appellativo": cfg["generale"]["appellativo"]}


async def _meteo() -> dict:
    try:
        return {"tipo": "meteo", "dati": await meteo.leggi(config.carica()["meteo"])}
    except Exception as errore:
        log.warning("meteo non disponibile: %s", errore)
        return {"tipo": "meteo", "errore": str(errore)}


async def _ciclo_sistema() -> None:
    while True:
        if diffusore.client:
            await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()})
        await asyncio.sleep(INTERVALLO_SISTEMA_S)


async def _ciclo_meteo() -> None:
    while True:
        await asyncio.sleep(INTERVALLO_METEO_S)
        if diffusore.client:
            await diffusore.invia(await _meteo())


async def _ciclo_regia() -> None:
    """Stato di OBS per l'HUD (locale, nessun costo)."""
    while True:
        if diffusore.client:
            await diffusore.invia({"tipo": "regia", "dati": await obs.stato(config.carica().get("obs", {}))})
        await asyncio.sleep(INTERVALLO_REGIA_S)


async def _ciclo_agenda() -> None:
    while True:
        if diffusore.client:
            await diffusore.invia(await agenda_per_hud())
        await asyncio.sleep(INTERVALLO_AGENDA_S)


async def _aggiorna_limiti() -> None:
    if await limiti.sonda():
        await diffusore.invia(limiti.stato())


async def _ciclo_limiti() -> None:
    while True:
        if diffusore.client and limiti.eta_s() > INTERVALLO_LIMITI_S:
            await _aggiorna_limiti()
        await asyncio.sleep(60)


def _riavvia() -> None:
    log.info("codice modificato: mi riavvio")
    os.execv(sys.executable, [sys.executable, "-m", "alfred", "core"])


async def _osserva_file() -> None:
    cartelle = [CARTELLA_UI, CARTELLA_CODICE]
    if config.CARTELLA_CONFIG.is_dir():
        cartelle.append(config.CARTELLA_CONFIG)
    file_contesto = None
    if radice := vault.radice():  # solo la cartella di Alfred, non tutto il vault
        cartelle.append(radice / "wiki" / "Alfred")
        file_contesto = radice / "wiki" / "Alfred" / "contesto.md"
    async for modifiche in awatch(*cartelle, debounce=300):
        percorsi = [Path(p) for _, p in modifiche]
        if any(p.suffix == ".py" and CARTELLA_CODICE in p.parents for p in percorsi):
            _riavvia()
        if config.FILE_CONFIG in percorsi:
            log.info("configurazione modificata")
            meteo.svuota_cache()
            await diffusore.invia({"tipo": "stato", "dati": _stato()})
            await diffusore.invia(await _meteo())
        # Memoria, diario e pronunce no: il prompt li rilegge alla conversazione nuova del mattino.
        if {config.FILE_CONFIG, FILE_PERSONALITA, FILE_SCHEDA, file_contesto} & set(percorsi):
            compiti.lancia(conversazione.riavvia_cervello())
        modifiche_ui = [p for p in percorsi if CARTELLA_UI in p.parents]
        if modifiche_ui:
            solo_stile = all(p.suffix == ".css" for p in modifiche_ui)
            await diffusore.invia({"tipo": "aggiorna", "solo_stile": solo_stile})


@contextlib.asynccontextmanager
async def ciclo_di_vita(_app: FastAPI):
    global conversazione
    conversazione = Conversazione(diffusore.invia)
    attivita.istanza().diffondi = diffusore.invia
    compiti = [
        asyncio.create_task(_ciclo_sistema()),
        asyncio.create_task(_ciclo_meteo()),
        asyncio.create_task(_ciclo_limiti()),
        asyncio.create_task(_ciclo_regia()),
        asyncio.create_task(_ciclo_agenda()),
        asyncio.create_task(veglia.istanza().sorveglia(diffusore.invia)),
        asyncio.create_task(ascolto.prepara()),
        asyncio.create_task(ascolto.riposa()),
        asyncio.create_task(parola.prepara()),
        asyncio.create_task(conversazione.cervello.prepara()),
        asyncio.create_task(conversazione.sveglia.ascolta_sempre()),
        asyncio.create_task(telegram_ponte.ciclo(conversazione)),
        asyncio.create_task(Iniziativa(conversazione).ciclo()),
        asyncio.create_task(_osserva_file()),
        asyncio.create_task(attivita.istanza().ciclo()),
    ]
    yield
    for compito in compiti:
        compito.cancel()
    await conversazione.chiudi()
    veglia.istanza().chiudi()


app = FastAPI(
    title="Alfred", version=__version__, docs_url=None, redoc_url=None, lifespan=ciclo_di_vita
)
# Solo "localhost" come host: blocca i siti che si fingono localhost (DNS rebinding).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])


def origine_fidata(origine: str | None) -> bool:
    """I browser mandano sempre Origin: deve essere l'HUD di Alfred. Senza Origin
    è un programma locale (server MCP, script), che può già fare ben altro."""
    porta = config.carica()["generale"]["porta"]
    return origine is None or origine in (f"http://127.0.0.1:{porta}", f"http://localhost:{porta}")


@app.middleware("http")
async def solo_da_alfred(richiesta, prosegui):
    if not origine_fidata(richiesta.headers.get("origin")):
        return JSONResponse({"errore": "origine non ammessa"}, status_code=403)
    risposta = await prosegui(richiesta)
    # L'HUD cambia spesso: il browser ricontrolla sempre (le risposte restano 304 se nulla è cambiato).
    risposta.headers["Cache-Control"] = "no-cache"
    return risposta


@app.websocket("/ws")
async def canale(ws: WebSocket):
    if not origine_fidata(ws.headers.get("origin")):
        await ws.close(code=1008)  # "violazione delle regole": pagina di un altro sito
        return
    await ws.accept()
    diffusore.client.add(ws)
    await diffusore.invia({"tipo": "benvenuto", "avvio": ID_AVVIO, "dati": _stato()}, solo=ws)
    await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()}, solo=ws)
    await diffusore.invia(conversazione.stato(), solo=ws)
    await diffusore.invia(limiti.stato(), solo=ws)
    await diffusore.invia(veglia.istanza().stato(), solo=ws)
    await diffusore.invia(await agenda_per_hud(), solo=ws)
    await diffusore.invia(attivita.istanza().per_hud(), solo=ws)
    if attesa := conversazione.azioni.stato_attesa():
        await diffusore.invia(attesa, solo=ws)
    await diffusore.invia(await _meteo(), solo=ws)
    try:
        while True:
            messaggio = await ws.receive_json()
            match messaggio.get("tipo"):
                case "aggiornami":
                    # La finestra è appena stata richiamata: dati freschi subito.
                    await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()}, solo=ws)
                    await diffusore.invia(await _meteo(), solo=ws)
                    if limiti.eta_s() > LIMITI_VECCHI_S:
                        compiti.lancia(_aggiorna_limiti())
                case "chat":
                    await conversazione.ricevi(str(messaggio.get("testo", "")))
                case "nuova_conversazione":
                    await conversazione.nuova()
                case "azione":
                    # Pulsanti dell'HUD: stessa strada dei comandi diretti.
                    await conversazione.azione_da_hud(str(messaggio.get("nome")), messaggio.get("parametri") or {})
                case "ascolta":
                    await conversazione.ascolta()
                case "conferma_azione":
                    await conversazione.conferma_da_hud(bool(messaggio.get("si")), str(messaggio.get("id")))
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: il client se n'è andato mentre gli scrivevamo.
        pass
    finally:
        diffusore.client.discard(ws)


@app.get("/api/sistema")
def dati_sistema():
    return sistema.leggi()


@app.get("/api/meteo")
async def dati_meteo():
    risposta = await _meteo()
    if "errore" in risposta:
        return JSONResponse({"errore": risposta["errore"]}, status_code=503)
    return risposta["dati"]


@app.get("/api/agenda")
async def eventi_agenda(da: str, a: str, calendari: str = ""):
    """calendari: nomi separati da virgola, "tutti", o vuoto per quelli personali."""
    try:
        inizio = datetime.combine(date.fromisoformat(da), datetime.min.time()).astimezone()
        fine = datetime.combine(date.fromisoformat(a), datetime.min.time()).astimezone()
        richiesti = [c.strip() for c in calendari.split(",") if c.strip()] or None
        consultati, altri = await agenda.scegli_calendari(richiesti)
        return {
            "eventi": await agenda.eventi_di(consultati, inizio, fine),
            "calendari_consultati": [c["nome"] for c in consultati],
            "altri_calendari": [c["nome"] for c in altri],
        }
    except agenda.AgendaNonPronta as errore:
        return {"errore": str(errore), "pronta": agenda.pronta()}


@app.post("/api/azioni/{nome}")
async def azione(nome: str, parametri: dict | None = None):
    """Usato dal cervello (strumenti MCP): le azioni sensibili restano in attesa di conferma."""
    return await conversazione.azioni.richiedi(nome, parametri or {}, dal_cervello=True)


@app.post("/api/ascolta")
async def ascolta():
    """Scorciatoia da tastiera: apre il microfono per una frase (o lo chiude)."""
    await conversazione.ascolta()
    return {"ok": True}


@app.get("/api/attivita")
def elenco_attivita():
    return attivita.istanza().per_hud()


@app.get("/api/processi")
async def processi():
    return {"processi": await asyncio.to_thread(attivita.processi_pesanti)}


@app.post("/api/detta")
async def detta():
    """Scorciatoia da tastiera: dettatura nella finestra attiva."""
    await conversazione.detta()
    return {"ok": True}


@app.get("/api/obs/fonti")
async def fonti_obs():
    try:
        return await obs.fonti(config.carica().get("obs", {}))
    except obs.ObsNonRaggiungibile:
        return {"errore": "OBS è chiuso"}


@app.get("/api/obs")
async def stato_obs():
    return await obs.stato(config.carica().get("obs", {}))


app.mount("/", StaticFiles(directory=CARTELLA_UI, html=True), name="ui")


def avvia() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    # httpx registra gli indirizzi completi, e quelli di Telegram contengono il token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # usato da Hugging Face
    logging.getLogger("pocket_tts").setLevel(logging.WARNING)  # statistiche a ogni frase
    # Avvisi innocui delle librerie vocali (cambi di lingua, pkg_resources).
    logging.getLogger("phonemizer").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
    porta = config.carica()["generale"]["porta"]
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")

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
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from watchfiles import awatch

from alfred import __version__, config
from alfred.brain import FILE_PERSONALITA, FILE_SCHEDA
from alfred.core import limiti, meteo, sistema, telegram_ponte
from alfred.core.conversazione import Conversazione
from alfred.tools import obs

CARTELLA_PROGETTO = Path(__file__).resolve().parents[2]
CARTELLA_UI = CARTELLA_PROGETTO / "ui"
CARTELLA_CODICE = CARTELLA_PROGETTO / "alfred"

INTERVALLO_SISTEMA_S = 2
INTERVALLO_METEO_S = 10 * 60
INTERVALLO_LIMITI_S = 30 * 60
INTERVALLO_REGIA_S = 3
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
    async for modifiche in awatch(*cartelle, debounce=300):
        percorsi = [Path(p) for _, p in modifiche]
        if any(p.suffix == ".py" and CARTELLA_CODICE in p.parents for p in percorsi):
            _riavvia()
        if config.FILE_CONFIG in percorsi:
            log.info("configurazione modificata")
            meteo.svuota_cache()
            await diffusore.invia({"tipo": "stato", "dati": _stato()})
            await diffusore.invia(await _meteo())
        if {config.FILE_CONFIG, FILE_PERSONALITA, FILE_SCHEDA} & set(percorsi):
            asyncio.create_task(conversazione.riavvia_cervello())
        modifiche_ui = [p for p in percorsi if CARTELLA_UI in p.parents]
        if modifiche_ui:
            solo_stile = all(p.suffix == ".css" for p in modifiche_ui)
            await diffusore.invia({"tipo": "aggiorna", "solo_stile": solo_stile})


@contextlib.asynccontextmanager
async def ciclo_di_vita(_app: FastAPI):
    global conversazione
    conversazione = Conversazione(diffusore.invia)
    compiti = [
        asyncio.create_task(_ciclo_sistema()),
        asyncio.create_task(_ciclo_meteo()),
        asyncio.create_task(_ciclo_limiti()),
        asyncio.create_task(_ciclo_regia()),
        asyncio.create_task(telegram_ponte.ciclo(conversazione)),
        asyncio.create_task(_osserva_file()),
    ]
    yield
    for compito in compiti:
        compito.cancel()
    await conversazione.chiudi()


app = FastAPI(
    title="Alfred", version=__version__, docs_url=None, redoc_url=None, lifespan=ciclo_di_vita
)


@app.websocket("/ws")
async def canale(ws: WebSocket):
    await ws.accept()
    diffusore.client.add(ws)
    await diffusore.invia({"tipo": "benvenuto", "avvio": ID_AVVIO, "dati": _stato()}, solo=ws)
    await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()}, solo=ws)
    await diffusore.invia(conversazione.stato(), solo=ws)
    await diffusore.invia(limiti.stato(), solo=ws)
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
                        asyncio.create_task(_aggiorna_limiti())
                case "chat":
                    await conversazione.ricevi(str(messaggio.get("testo", "")))
                case "nuova_conversazione":
                    await conversazione.nuova()
                case "azione":
                    # Pulsanti dell'HUD: stessa strada dei comandi diretti.
                    await conversazione.azione_da_hud(str(messaggio.get("nome")), messaggio.get("parametri") or {})
                case "conferma_azione":
                    await conversazione.conferma_da_hud(bool(messaggio.get("si")), str(messaggio.get("id")))
    except (WebSocketDisconnect, RuntimeError):
        # RuntimeError: il client se n'è andato mentre gli scrivevamo.
        pass
    finally:
        diffusore.client.discard(ws)


@app.get("/api/stato")
def stato():
    return _stato()


@app.get("/api/sistema")
def dati_sistema():
    return sistema.leggi()


@app.get("/api/meteo")
async def dati_meteo():
    risposta = await _meteo()
    if "errore" in risposta:
        return JSONResponse({"errore": risposta["errore"]}, status_code=503)
    return risposta["dati"]


@app.post("/api/azioni/{nome}")
async def azione(nome: str, parametri: dict | None = None):
    """Usato dal cervello (strumenti MCP): le azioni sensibili restano in attesa di conferma."""
    return await conversazione.azioni.richiedi(nome, parametri or {})


@app.get("/api/obs")
async def stato_obs():
    return await obs.stato(config.carica().get("obs", {}))


app.mount("/", StaticFiles(directory=CARTELLA_UI, html=True), name="ui")


def avvia() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    # httpx registra gli indirizzi completi, e quelli di Telegram contengono il token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    porta = config.carica()["generale"]["porta"]
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")

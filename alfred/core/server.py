"""alfred-core: il servizio sempre attivo che serve l'HUD e i suoi dati.

L'HUD riceve tutto da un WebSocket (/ws): il servizio spinge i dati di sistema
e il meteo, e osserva i file del progetto e la configurazione:
- grafica modificata (ui/) → l'HUD si aggiorna da solo;
- config.toml modificata → nuova configurazione applicata subito;
- codice Python modificato → il servizio si riavvia, l'HUD si ricollega.
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
from alfred.core import meteo, sistema

CARTELLA_PROGETTO = Path(__file__).resolve().parents[2]
CARTELLA_UI = CARTELLA_PROGETTO / "ui"
CARTELLA_CODICE = CARTELLA_PROGETTO / "alfred"

INTERVALLO_SISTEMA_S = 2
INTERVALLO_METEO_S = 10 * 60

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
        modifiche_ui = [p for p in percorsi if CARTELLA_UI in p.parents]
        if modifiche_ui:
            solo_stile = all(p.suffix == ".css" for p in modifiche_ui)
            await diffusore.invia({"tipo": "aggiorna", "solo_stile": solo_stile})


@contextlib.asynccontextmanager
async def ciclo_di_vita(_app: FastAPI):
    compiti = [
        asyncio.create_task(_ciclo_sistema()),
        asyncio.create_task(_ciclo_meteo()),
        asyncio.create_task(_osserva_file()),
    ]
    yield
    for compito in compiti:
        compito.cancel()


app = FastAPI(
    title="Alfred", version=__version__, docs_url=None, redoc_url=None, lifespan=ciclo_di_vita
)


@app.websocket("/ws")
async def canale(ws: WebSocket):
    await ws.accept()
    diffusore.client.add(ws)
    await diffusore.invia({"tipo": "benvenuto", "avvio": ID_AVVIO, "dati": _stato()}, solo=ws)
    await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()}, solo=ws)
    await diffusore.invia(await _meteo(), solo=ws)
    try:
        while True:
            messaggio = await ws.receive_json()
            if messaggio.get("tipo") == "aggiornami":
                # La finestra è appena stata richiamata: dati freschi subito.
                await diffusore.invia({"tipo": "sistema", "dati": sistema.leggi()}, solo=ws)
                await diffusore.invia(await _meteo(), solo=ws)
    except WebSocketDisconnect:
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


app.mount("/", StaticFiles(directory=CARTELLA_UI, html=True), name="ui")


def avvia() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    porta = config.carica()["generale"]["porta"]
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")

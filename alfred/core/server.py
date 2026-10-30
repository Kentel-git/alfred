"""alfred-core: il servizio sempre attivo che serve l'HUD e i suoi dati."""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from alfred import __version__, config
from alfred.core import meteo, sistema

CARTELLA_UI = Path(__file__).resolve().parents[2] / "ui"
log = logging.getLogger("alfred.core")

app = FastAPI(title="Alfred", version=__version__, docs_url=None, redoc_url=None)


@app.get("/api/stato")
def stato():
    cfg = config.carica()
    return {
        "versione": __version__,
        "appellativo": cfg["generale"]["appellativo"],
    }


@app.get("/api/sistema")
def dati_sistema():
    return sistema.leggi()


@app.get("/api/meteo")
async def dati_meteo():
    try:
        return await meteo.leggi(config.carica()["meteo"])
    except Exception as errore:
        log.warning("meteo non disponibile: %s", errore)
        return JSONResponse({"errore": str(errore)}, status_code=503)


app.mount("/", StaticFiles(directory=CARTELLA_UI, html=True), name="ui")


def avvia() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    porta = config.carica()["generale"]["porta"]
    uvicorn.run(app, host="127.0.0.1", port=porta, log_level="warning")

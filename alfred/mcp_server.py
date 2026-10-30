"""Server MCP che espone gli strumenti di Alfred al cervello (claude -p).

È un ponte sottile: ogni strumento interroga alfred-core, che ha già i dati.
"""

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from alfred import config

server = MCPServer("alfred", instructions="Gli strumenti del maggiordomo Alfred.")
SOLA_LETTURA = ToolAnnotations(readOnlyHint=True)


async def _chiedi_al_core(percorso: str) -> dict:
    async with httpx.AsyncClient(base_url=config.url_core(), timeout=30) as client:
        risposta = await client.get(percorso)
        return risposta.json()


@server.tool(annotations=SOLA_LETTURA)
async def stato_computer() -> dict:
    """Stato del computer di casa: uso e temperatura del processore, frequenza
    della grafica, memoria, disco libero, batteria, velocità di rete e da quanti
    secondi è acceso."""
    return await _chiedi_al_core("/api/sistema")


@server.tool(annotations=SOLA_LETTURA)
async def meteo() -> dict:
    """Meteo attuale e dei prossimi tre giorni nel luogo in cui si trova il
    computer."""
    return await _chiedi_al_core("/api/meteo")


@server.tool(annotations=SOLA_LETTURA)
async def stato_obs() -> dict:
    """Stato di OBS Studio: se è aperto, se la diretta o la registrazione sono
    attive e da quanto, la scena attuale e l'elenco delle scene."""
    return await _chiedi_al_core("/api/obs")


def avvia() -> None:
    server.run("stdio")

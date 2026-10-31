"""Server MCP che espone gli strumenti di Alfred al cervello (claude -p).

È un ponte sottile: ogni strumento interroga alfred-core, che ha già i dati.
"""

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from alfred import config

server = MCPServer("alfred", instructions="Gli strumenti del maggiordomo Alfred.")
SOLA_LETTURA = ToolAnnotations(readOnlyHint=True)
AZIONE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


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


async def _azione(nome: str, parametri: dict | None = None) -> dict:
    async with httpx.AsyncClient(base_url=config.url_core(), timeout=60) as client:
        risposta = await client.post(f"/api/azioni/{nome}", json=parametri or {})
        return risposta.json()


# Ogni azione restituisce "messaggio": una frase già pronta che descrive
# l'esito. Se c'è "in_attesa_di_conferma", l'azione NON è ancora avvenuta.

@server.tool(annotations=AZIONE)
async def modalita_gioco() -> dict:
    """Avvia la modalità gioco: apre Battle.net (e World of Warcraft); la
    macchina prepara da sola schermi e prestazioni."""
    return await _azione("modalita_gioco")


@server.tool(annotations=AZIONE)
async def apri_obs() -> dict:
    """Apre OBS Studio. Dopo l'apertura servono alcuni secondi prima che
    risponda ai comandi."""
    return await _azione("apri_obs")


@server.tool(annotations=AZIONE)
async def avvia_diretta() -> dict:
    """Chiede di avviare la diretta in OBS. Richiede sempre la conferma di
    Pietro: l'HUD gliela chiede, e a lui basta rispondere "sì"."""
    return await _azione("avvia_diretta")


@server.tool(annotations=AZIONE)
async def ferma_diretta() -> dict:
    """Chiede di terminare la diretta in OBS. Richiede sempre la conferma di
    Pietro."""
    return await _azione("ferma_diretta")


@server.tool(annotations=AZIONE)
async def registrazione(azione: str) -> dict:
    """Controlla la registrazione di OBS. azione: "avvia", "ferma", "pausa"
    oppure "riprendi"."""
    nomi = {"avvia": "avvia_registrazione", "ferma": "ferma_registrazione",
            "pausa": "pausa_registrazione", "riprendi": "riprendi_registrazione"}
    if azione not in nomi:
        return {"ok": False, "messaggio": f"Azione sconosciuta: {azione}. Usa avvia, ferma, pausa o riprendi."}
    return await _azione(nomi[azione])


@server.tool(annotations=AZIONE)
async def cambia_scena(scena: str) -> dict:
    """Cambia la scena di OBS. Il nome può essere approssimativo: viene
    confrontato con le scene esistenti (vedi stato_obs)."""
    return await _azione("cambia_scena", {"scena": scena})


def avvia() -> None:
    server.run("stdio")

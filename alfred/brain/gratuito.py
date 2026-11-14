"""Cervello gratuito: un endpoint compatibile con le API OpenAI (es. FreeLLMAPI
in locale, Ollama, llama.cpp).

Non ha sessione: serve quando le riserve Claude sono esaurite (austerità) e per
i lavori di fondo come il diario, così non costano riserve. In austerità ha un
piccolo sottoinsieme degli strumenti di Alfred (STRUMENTI_IN_AUSTERITA), presi
dal server MCP ed eseguiti dentro il processo: passano dalle stesse rotte del
cervello Claude, quindi chiedono le stesse conferme. Serve un modello che sappia
chiamare strumenti. Spento se in config.toml manca l'url.
"""

import json
import logging

import httpx

from alfred import config

log = logging.getLogger("alfred.cervello.gratuito")

# Pochi e semplici: i modelli gratuiti sbagliano più spesso con tanti strumenti.
STRUMENTI_IN_AUSTERITA = ("meteo", "agenda_eventi", "crea_evento", "sposta_evento", "apri",
                          "volume", "timer", "cattura", "attivita_di_oggi")
GIRI_MASSIMI = 5  # giri modello → strumenti; poi risponde senza


async def _strumenti() -> list[dict]:
    # Import tardivo: MCPServer() chiama logging.basicConfig, che a core avviato non fa più nulla.
    from alfred.mcp_server import server

    return [{"type": "function", "function": {
                "name": s.name, "description": s.description or "",
                "parameters": {k: v for k, v in s.input_schema.items() if k != "title"}}}
            for s in await server.list_tools() if s.name in STRUMENTI_IN_AUSTERITA]


async def _esegui(funzione: dict) -> str:
    """Esito di una chiamata a strumento, come testo per il modello (anche gli errori)."""
    from alfred.mcp_server import server

    nome = funzione.get("name", "")
    if nome not in STRUMENTI_IN_AUSTERITA:
        return f"Errore: lo strumento «{nome}» non è disponibile."
    try:
        argomenti = json.loads(funzione.get("arguments") or "{}")
        esito = await server.call_tool(nome, argomenti)
        return "\n".join(c.text for c in esito.content if getattr(c, "text", None)) or "{}"
    except Exception as errore:  # argomenti sbagliati, core irraggiungibile, strumento fallito
        log.warning("strumento %s dal cervello gratuito: %s", nome, errore)
        return f"Errore: {errore}"


async def chiedi(messaggi: list[dict], sistema: str, strumenti: bool = False) -> str | None:
    """Risposta del cervello gratuito, o None se è spento o non risponde.
    strumenti: può usare STRUMENTI_IN_AUSTERITA (se non spenti in config)."""
    cfg = config.carica()["cervello_gratuito"]
    if not cfg["url"]:
        return None
    chiave = config.segreto("ALFRED_GRATUITO_CHIAVE") or ""
    conversazione = [{"role": "system", "content": sistema}, *messaggi]
    try:
        elenco = await _strumenti() if strumenti and cfg["strumenti"] else []
        async with httpx.AsyncClient(timeout=cfg["attesa_massima"]) as client:
            for giro in range(GIRI_MASSIMI + 1):
                corpo = {"model": cfg["modello"], "messages": conversazione}
                if elenco and giro < GIRI_MASSIMI:
                    corpo["tools"] = elenco
                r = await client.post(f"{cfg['url'].rstrip('/')}/chat/completions",
                                      headers={"Authorization": f"Bearer {chiave}"}, json=corpo)
                r.raise_for_status()
                messaggio = r.json()["choices"][0]["message"]
                chiamate = messaggio.get("tool_calls") or []
                if not chiamate or "tools" not in corpo:
                    return (messaggio.get("content") or "").strip() or None
                conversazione.append({"role": "assistant", "content": messaggio.get("content") or "",
                                      "tool_calls": chiamate})
                for chiamata in chiamate:
                    conversazione.append({"role": "tool", "tool_call_id": chiamata["id"],
                                          "content": await _esegui(chiamata["function"])})
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as errore:
        log.warning("cervello gratuito non disponibile: %s", errore)
    return None

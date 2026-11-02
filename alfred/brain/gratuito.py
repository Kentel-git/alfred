"""Cervello gratuito: un endpoint compatibile con le API OpenAI (es. FreeLLMAPI
in locale, Ollama, llama.cpp).

Non ha strumenti né sessione: serve quando le riserve Claude sono esaurite
(austerità) e per i lavori di fondo come il diario, così non costano riserve.
Spento se in config.toml manca l'url.
"""

import logging

import httpx

from alfred import config

log = logging.getLogger("alfred.cervello.gratuito")


async def chiedi(messaggi: list[dict], sistema: str) -> str | None:
    """Risposta del cervello gratuito, o None se è spento o non risponde."""
    cfg = config.carica()["cervello_gratuito"]
    if not cfg["url"]:
        return None
    chiave = config.segreto("ALFRED_GRATUITO_CHIAVE") or ""
    try:
        async with httpx.AsyncClient(timeout=cfg["attesa_massima"]) as client:
            r = await client.post(
                f"{cfg['url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {chiave}"},
                json={"model": cfg["modello"], "messages": [{"role": "system", "content": sistema}, *messaggi]},
            )
            r.raise_for_status()
            return (r.json()["choices"][0]["message"]["content"] or "").strip() or None
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as errore:
        log.warning("cervello gratuito non disponibile: %s", errore)
        return None

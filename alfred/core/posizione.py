"""Posizione del computer tramite GeoClue (il servizio di localizzazione libero
di freedesktop), con il nome del luogo da OpenStreetMap (Nominatim).

GeoClue usa le reti WiFi vicine (BeaconDB) e, se non bastano, l'indirizzo IP.
Se GeoClue non c'è o nega l'accesso, la posizione resta sconosciuta.
"""

import asyncio
import logging
import time

import httpx

from alfred import __version__

DURATA_CACHE_S = 30 * 60
log = logging.getLogger("alfred.posizione")

_cache: dict = {"quando": 0.0, "dati": None}
_nomi: dict[tuple[float, float], str] = {}


def _chiedi_a_geoclue() -> tuple[float, float, float]:
    import gi

    gi.require_version("Geoclue", "2.0")
    from gi.repository import Geoclue

    # "alfred" è l'id con cui GeoClue (e il suo agente) riconosce l'app.
    semplice = Geoclue.Simple.new_sync("alfred", Geoclue.AccuracyLevel.CITY, None)
    luogo = semplice.get_location()
    return luogo.props.latitude, luogo.props.longitude, luogo.props.accuracy


async def _nome_luogo(lat: float, lon: float) -> str:
    chiave = (round(lat, 2), round(lon, 2))
    if chiave not in _nomi:
        async with httpx.AsyncClient(
            timeout=10, headers={"User-Agent": f"Alfred/{__version__} (maggiordomo digitale FOSS)"}
        ) as client:
            risposta = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "zoom": 10, "format": "jsonv2", "accept-language": "it"},
            )
            risposta.raise_for_status()
            _nomi[chiave] = risposta.json().get("name") or f"{lat:.2f}, {lon:.2f}"
    return _nomi[chiave]


async def trova() -> dict | None:
    """Restituisce {latitudine, longitudine, precisione_m, luogo} o None."""
    if _cache["dati"] and time.monotonic() - _cache["quando"] < DURATA_CACHE_S:
        return _cache["dati"]
    try:
        lat, lon, precisione = await asyncio.wait_for(asyncio.to_thread(_chiedi_a_geoclue), 30)
    except Exception as errore:
        log.warning("posizione non disponibile da GeoClue: %s", errore)
        return _cache["dati"]
    try:
        luogo = await _nome_luogo(lat, lon)
    except Exception as errore:
        log.warning("nome del luogo non disponibile: %s", errore)
        luogo = f"{lat:.2f}, {lon:.2f}"
    dati = {"latitudine": lat, "longitudine": lon, "precisione_m": round(precisione), "luogo": luogo}
    _cache.update(quando=time.monotonic(), dati=dati)
    return dati

"""Meteo da Open-Meteo (gratuito, senza chiave), con cache di 15 minuti."""

import math
import time

import httpx

from alfred.core import posizione

DURATA_CACHE_S = 15 * 60
# Entro questa distanza dalla città di casa (o entro l'errore di GeoClue, se
# maggiore) Alfred considera di essere a casa.
RAGGIO_CASA_KM = 20

# Codici WMO usati da Open-Meteo.
DESCRIZIONI = {
    0: "sereno", 1: "prevalentemente sereno", 2: "parzialmente nuvoloso", 3: "coperto",
    45: "nebbia", 48: "nebbia con brina",
    51: "pioviggine leggera", 53: "pioviggine", 55: "pioviggine intensa",
    56: "pioviggine gelata", 57: "pioviggine gelata intensa",
    61: "pioggia leggera", 63: "pioggia", 65: "pioggia forte",
    66: "pioggia gelata", 67: "pioggia gelata forte",
    71: "neve leggera", 73: "neve", 75: "neve forte", 77: "granelli di neve",
    80: "rovesci leggeri", 81: "rovesci", 82: "rovesci violenti",
    85: "rovesci di neve", 86: "forti rovesci di neve",
    95: "temporale", 96: "temporale con grandine", 99: "temporale con forte grandine",
}

_cache: dict = {"quando": 0.0, "dati": None, "luogo": None}
_coordinate: dict[str, tuple[float, float, str]] = {}


def svuota_cache() -> None:
    _cache.update(quando=0.0, dati=None)


async def _trova_coordinate(client: httpx.AsyncClient, citta: str) -> tuple[float, float, str]:
    if citta not in _coordinate:
        risposta = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": citta, "count": 1, "language": "it"},
        )
        risposta.raise_for_status()
        risultati = risposta.json().get("results")
        if not risultati:
            raise ValueError(f"Città non trovata: {citta}")
        r = risultati[0]
        _coordinate[citta] = (r["latitude"], r["longitude"], r["name"])
    return _coordinate[citta]


def _distanza_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


async def leggi(config_meteo: dict) -> dict | None:
    """Priorità: coordinate in config, poi città in config, poi posizione del computer.

    Con la posizione del computer, se ci si trova nei dintorni della città di
    casa (`casa` in config) si usa quella al posto del paese rilevato.
    """
    citta = config_meteo.get("citta", "").strip()
    lat, lon = config_meteo.get("latitudine"), config_meteo.get("longitudine")
    nome = citta or (f"{lat:.2f}, {lon:.2f}" if lat is not None and lon is not None else "")

    async with httpx.AsyncClient(timeout=10) as client:
        if lat is None or lon is None:
            if citta:
                lat, lon, nome = await _trova_coordinate(client, citta)
            else:
                pos = await posizione.trova()
                if not pos:
                    return None
                lat, lon, nome = pos["latitudine"], pos["longitudine"], pos["luogo"]
                casa = config_meteo.get("casa", "").strip()
                if casa:
                    lat_casa, lon_casa, nome_casa = await _trova_coordinate(client, casa)
                    raggio = max(RAGGIO_CASA_KM, pos["precisione_m"] / 1000)
                    if _distanza_km(lat, lon, lat_casa, lon_casa) <= raggio:
                        lat, lon, nome = lat_casa, lon_casa, nome_casa

        luogo = (round(lat, 2), round(lon, 2))
        if (
            _cache["dati"]
            and _cache["luogo"] == luogo
            and time.monotonic() - _cache["quando"] < DURATA_CACHE_S
        ):
            return _cache["dati"]

        risposta = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m,is_day",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": 3,
            },
        )
        risposta.raise_for_status()
        d = risposta.json()

    attuale, giorni = d["current"], d["daily"]
    dati = {
        "luogo": nome,
        "temperatura": round(attuale["temperature_2m"]),
        "percepita": round(attuale["apparent_temperature"]),
        "umidita": attuale["relative_humidity_2m"],
        "vento_kmh": round(attuale["wind_speed_10m"]),
        "codice": attuale["weather_code"],
        "giorno": bool(attuale["is_day"]),
        "descrizione": DESCRIZIONI.get(attuale["weather_code"], "tempo indecifrabile"),
        "prossimi_giorni": [
            {
                "data": giorni["time"][i],
                "min": round(giorni["temperature_2m_min"][i]),
                "max": round(giorni["temperature_2m_max"][i]),
                "pioggia": giorni["precipitation_probability_max"][i],
                "codice": giorni["weather_code"][i],
                "descrizione": DESCRIZIONI.get(giorni["weather_code"][i], ""),
            }
            for i in range(len(giorni["time"]))
        ],
    }
    _cache.update(quando=time.monotonic(), dati=dati, luogo=luogo)
    return dati

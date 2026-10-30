"""Meteo da Open-Meteo (gratuito, senza chiave), con cache di 15 minuti."""

import time

import httpx

DURATA_CACHE_S = 15 * 60

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

_cache: dict = {"quando": 0.0, "dati": None}
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


async def leggi(config_meteo: dict) -> dict | None:
    citta = config_meteo.get("citta", "").strip()
    lat, lon = config_meteo.get("latitudine"), config_meteo.get("longitudine")
    if not citta and (lat is None or lon is None):
        return None

    if _cache["dati"] and time.monotonic() - _cache["quando"] < DURATA_CACHE_S:
        return _cache["dati"]

    async with httpx.AsyncClient(timeout=10) as client:
        nome = citta
        if lat is None or lon is None:
            lat, lon, nome = await _trova_coordinate(client, citta)
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
    _cache.update(quando=time.monotonic(), dati=dati)
    return dati

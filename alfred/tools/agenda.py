"""Agenda: Google Calendar tramite le sue API, senza librerie di Google.

Configurazione una tantum (vedi docs/AGENDA.md): un client OAuth "App desktop"
creato su Google Cloud, salvato in ~/.config/alfred/google-client.json. Poi
`alfred google` apre il browser per l'autorizzazione (flusso OAuth con PKCE e
indirizzo di ritorno locale) e salva il token di rinnovo nello stato di Alfred.

Leggere e scrivere l'agenda non costa nulla in termini di riserve: il modello
serve solo a capire le richieste a parole libere.
"""

import asyncio
import base64
import hashlib
import json
import secrets
import time
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse

import httpx

from alfred import config

FILE_CLIENT = config.CARTELLA_CONFIG / "google-client.json"
FILE_TOKEN = config.CARTELLA_STATO / "google-token.json"
AMBITI = " ".join([
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
])
API = "https://www.googleapis.com/calendar/v3"


class AgendaNonPronta(Exception):
    pass


# --- Autorizzazione ----------------------------------------------------------

def _client() -> dict:
    try:
        dati = json.loads(FILE_CLIENT.read_text())
    except (OSError, ValueError) as errore:
        raise AgendaNonPronta(f"manca {FILE_CLIENT}") from errore
    return dati.get("installed") or dati.get("web") or dati


def pronta() -> bool:
    return FILE_CLIENT.exists() and FILE_TOKEN.exists()


def _salva_token(token: dict) -> None:
    config.CARTELLA_STATO.mkdir(parents=True, exist_ok=True)
    FILE_TOKEN.touch(mode=0o600, exist_ok=True)
    FILE_TOKEN.write_text(json.dumps(token))


def autorizza() -> None:
    """Flusso interattivo: apre il browser e attende il ritorno su 127.0.0.1."""
    client = _client()
    verificatore = secrets.token_urlsafe(64)
    sfida = base64.urlsafe_b64encode(hashlib.sha256(verificatore.encode()).digest()).rstrip(b"=").decode()
    stato = secrets.token_urlsafe(16)
    ricevuto: dict = {}

    class Ritorno(BaseHTTPRequestHandler):
        def do_GET(self):
            ricevuto.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p style='font-family:serif;font-size:1.4rem'>Grazie, signore. "
                             "Può chiudere questa pagina.</p>".encode())

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Ritorno)
    ritorno = f"http://127.0.0.1:{server.server_port}"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client["client_id"], "redirect_uri": ritorno, "response_type": "code",
        "scope": AMBITI, "access_type": "offline", "prompt": "consent", "state": stato,
        "code_challenge": sfida, "code_challenge_method": "S256",
    })
    print("Apro il browser per l'autorizzazione. Se non si apre, visita:\n" + url)
    webbrowser.open(url)
    server.timeout = 300
    server.handle_request()
    server.server_close()

    if ricevuto.get("state") != stato or "code" not in ricevuto:
        raise AgendaNonPronta(f"autorizzazione non riuscita: {ricevuto.get('error', 'nessuna risposta')}")
    risposta = httpx.post(client.get("token_uri", "https://oauth2.googleapis.com/token"), data={
        "code": ricevuto["code"], "client_id": client["client_id"],
        "client_secret": client.get("client_secret", ""), "redirect_uri": ritorno,
        "grant_type": "authorization_code", "code_verifier": verificatore,
    }, timeout=30)
    token = risposta.json()
    if "refresh_token" not in token:
        raise AgendaNonPronta(f"Google non ha concesso l'accesso: {token}")
    token["scade"] = time.time() + token.get("expires_in", 3600) - 60
    _salva_token(token)
    print("Agenda collegata.")


_blocco_token = asyncio.Lock()


async def _token_accesso(client_http: httpx.AsyncClient) -> str:
    async with _blocco_token:
        try:
            token = json.loads(FILE_TOKEN.read_text())
        except (OSError, ValueError) as errore:
            raise AgendaNonPronta("agenda non autorizzata: eseguire `alfred google`") from errore
        if time.time() < token.get("scade", 0):
            return token["access_token"]
        client = _client()
        risposta = await client_http.post(client.get("token_uri", "https://oauth2.googleapis.com/token"), data={
            "client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
            "refresh_token": token["refresh_token"], "grant_type": "refresh_token",
        })
        nuovo = risposta.json()
        if "access_token" not in nuovo:
            raise AgendaNonPronta(f"rinnovo dell'accesso rifiutato: {nuovo.get('error')}")
        token.update(access_token=nuovo["access_token"], scade=time.time() + nuovo.get("expires_in", 3600) - 60)
        _salva_token(token)
        return token["access_token"]


def _id(valore: str) -> str:
    """Id nell'indirizzo: quelli di Google possono contenere "#" (es. le festività)."""
    return quote(valore, safe="@")


async def _chiama(metodo: str, percorso: str, **richiesta) -> dict:
    async with httpx.AsyncClient(base_url=API, timeout=30) as client:
        intestazioni = {"Authorization": f"Bearer {await _token_accesso(client)}"}
        risposta = await client.request(metodo, percorso, headers=intestazioni, **richiesta)
    if risposta.status_code == 204:
        return {}
    dati = risposta.json()
    if risposta.status_code >= 400:
        raise AgendaNonPronta(dati.get("error", {}).get("message", f"errore {risposta.status_code}"))
    return dati


# --- Lettura e scrittura -----------------------------------------------------

def _fuso() -> str:
    """Fuso orario del sistema in forma IANA (es. Europe/Rome)."""
    percorso = str(Path("/etc/localtime").resolve())
    return percorso.split("zoneinfo/", 1)[1] if "zoneinfo/" in percorso else "UTC"


async def calendari() -> list[dict]:
    dati = await _chiama("GET", "/users/me/calendarList")
    return [{"id": c["id"], "nome": c.get("summaryOverride") or c.get("summary"),
             "principale": c.get("primary", False), "visibile": c.get("selected", False),
             "scrivibile": c.get("accessRole") in ("owner", "writer")}
            for c in dati.get("items", [])]


def _i_miei_calendari() -> list[str]:
    """Calendari "personali" da config (nomi o id); vuoto = tutti i visibili."""
    return [c.lower() for c in config.carica().get("agenda", {}).get("calendari", [])]


def _corrisponde(calendario: dict, nomi: list[str]) -> bool:
    return calendario["id"].lower() in nomi or (calendario["nome"] or "").lower() in nomi


async def scegli_calendari(richiesti: list[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(da consultare, altri). Senza richiesta: i calendari personali.
    ["tutti"] = tutti i visibili; altrimenti nomi o id."""
    visibili = [c for c in await calendari() if c["visibile"]]
    nomi = [n.lower() for n in richiesti] if richiesti else _i_miei_calendari()
    if not nomi or "tutti" in nomi:
        return visibili, []
    scelti = [c for c in visibili if _corrisponde(c, nomi)]
    return scelti, [c for c in visibili if c not in scelti]


def _evento(e: dict, calendario: str, nome_calendario: str) -> dict:
    inizio, fine = e.get("start", {}), e.get("end", {})
    return {
        "id": e["id"], "calendario": calendario, "nome_calendario": nome_calendario,
        "titolo": e.get("summary", "(senza titolo)"),
        "inizio": inizio.get("dateTime") or inizio.get("date"),
        "fine": fine.get("dateTime") or fine.get("date"),
        "tutto_il_giorno": "date" in inizio,
        "luogo": e.get("location"), "descrizione": e.get("description"),
    }


async def eventi(da: datetime, a: datetime, richiesti: list[str] | None = None) -> list[dict]:
    """Eventi tra due istanti dai calendari personali (o da quelli richiesti)."""
    return await eventi_di((await scegli_calendari(richiesti))[0], da, a)


async def eventi_di(elenco: list[dict], da: datetime, a: datetime) -> list[dict]:
    risultati = []
    for c in elenco:
        dati = await _chiama("GET", f"/calendars/{_id(c['id'])}/events", params={
            "timeMin": da.astimezone().isoformat(), "timeMax": a.astimezone().isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 100,
        })
        risultati += [_evento(e, c["id"], c["nome"]) for e in dati.get("items", []) if e.get("status") != "cancelled"]
    return sorted(risultati, key=lambda e: e["inizio"])


async def evento(id_evento: str, calendario: str = "primary") -> dict:
    return _evento(await _chiama("GET", f"/calendars/{_id(calendario)}/events/{_id(id_evento)}"), calendario, "")


def _orario(valore: str, tutto_il_giorno: bool) -> dict:
    if tutto_il_giorno:
        return {"date": valore[:10]}
    istante = datetime.fromisoformat(valore)
    if istante.tzinfo is None:
        istante = istante.astimezone()  # ora locale
    return {"dateTime": istante.isoformat(), "timeZone": _fuso()}


async def crea(titolo: str, inizio: str, fine: str | None = None, tutto_il_giorno: bool = False,
               luogo: str | None = None, descrizione: str | None = None, calendario: str = "primary") -> dict:
    """inizio/fine in ISO 8601 (es. 2026-11-02T21:00). Senza fine: un'ora (o un giorno)."""
    if not fine:
        if tutto_il_giorno:
            fine = (date.fromisoformat(inizio[:10]) + timedelta(days=1)).isoformat()
        else:
            fine = (datetime.fromisoformat(inizio) + timedelta(hours=1)).isoformat()
    corpo = {"summary": titolo, "start": _orario(inizio, tutto_il_giorno), "end": _orario(fine, tutto_il_giorno)}
    if luogo:
        corpo["location"] = luogo
    if descrizione:
        corpo["description"] = descrizione
    return _evento(await _chiama("POST", f"/calendars/{_id(calendario)}/events", json=corpo), calendario, "")


async def sposta(id_evento: str, inizio: str, fine: str | None = None, calendario: str = "primary") -> dict:
    """Nuovo orario; senza fine mantiene la durata originale."""
    attuale = await evento(id_evento, calendario)
    tutto_il_giorno = attuale["tutto_il_giorno"]
    if not fine:
        if tutto_il_giorno:
            durata = date.fromisoformat(attuale["fine"]) - date.fromisoformat(attuale["inizio"])
            fine = (date.fromisoformat(inizio[:10]) + durata).isoformat()
        else:
            durata = datetime.fromisoformat(attuale["fine"]) - datetime.fromisoformat(attuale["inizio"])
            fine = (datetime.fromisoformat(inizio) + durata).isoformat()
    corpo = {"start": _orario(inizio, tutto_il_giorno), "end": _orario(fine, tutto_il_giorno)}
    return _evento(await _chiama("PATCH", f"/calendars/{_id(calendario)}/events/{_id(id_evento)}", json=corpo), calendario, "")


async def elimina(id_evento: str, calendario: str = "primary") -> None:
    await _chiama("DELETE", f"/calendars/{_id(calendario)}/events/{_id(id_evento)}")

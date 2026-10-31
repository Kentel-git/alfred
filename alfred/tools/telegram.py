"""Telegram: Pietro e Alfred si scrivono tramite un bot dedicato (Bot API).

Il bot si crea con @BotFather; il token va in secrets.env come
ALFRED_TELEGRAM_TOKEN. Il primo /start ricevuto collega la chat del
proprietario: da quel momento il bot parla solo con lei e ignora chiunque altro.
"""

import json

import httpx

from alfred import config

FILE_STATO = config.CARTELLA_STATO / "telegram.json"
API = "https://api.telegram.org/bot{token}/{metodo}"
MAX_LUNGHEZZA = 4000  # Telegram accetta fino a 4096 caratteri per messaggio


class TelegramNonPronto(Exception):
    pass


def token() -> str | None:
    return config.segreto("ALFRED_TELEGRAM_TOKEN")


def _stato() -> dict:
    try:
        return json.loads(FILE_STATO.read_text())
    except (OSError, ValueError):
        return {}


def _salva_stato(**valori) -> None:
    stato = _stato() | valori
    config.CARTELLA_STATO.mkdir(parents=True, exist_ok=True)
    FILE_STATO.write_text(json.dumps(stato))


def chat_collegata() -> int | None:
    return _stato().get("chat_id")


def collega_chat(chat: dict) -> None:
    _salva_stato(chat_id=chat["id"], nome=chat.get("first_name"))


def ultimo_aggiornamento() -> int:
    return _stato().get("offset", 0)


def segna_letti(offset: int) -> None:
    _salva_stato(offset=offset)


async def chiama(metodo: str, attesa_http: float = 40, **parametri) -> dict | list | bool:
    """Chiama un metodo della Bot API. I parametri vanno a Telegram così come sono."""
    chiave = token()
    if not chiave:
        raise TelegramNonPronto("manca ALFRED_TELEGRAM_TOKEN in secrets.env")
    async with httpx.AsyncClient(timeout=attesa_http) as client:
        risposta = await client.post(API.format(token=chiave, metodo=metodo), json=parametri)
        dati = risposta.json()
    if not dati.get("ok"):
        raise TelegramNonPronto(dati.get("description", "errore sconosciuto"))
    return dati["result"]


async def invia(testo: str, conferma_id: str | None = None) -> None:
    """Scrive a Pietro. Con conferma_id aggiunge i pulsanti Sì / No."""
    chat = chat_collegata()
    if not chat:
        raise TelegramNonPronto("chat non collegata: scrivere /start al bot")
    pezzi = [testo[i:i + MAX_LUNGHEZZA] for i in range(0, len(testo), MAX_LUNGHEZZA)] or [""]
    for i, pezzo in enumerate(pezzi):
        parametri = {"chat_id": chat, "text": pezzo}
        if conferma_id and i == len(pezzi) - 1:
            parametri["reply_markup"] = {"inline_keyboard": [[
                {"text": "Sì", "callback_data": f"conferma:{conferma_id}:1"},
                {"text": "No", "callback_data": f"conferma:{conferma_id}:0"},
            ]]}
        await chiama("sendMessage", **parametri)


async def invia_vocale(percorso, didascalia: str = "") -> None:
    """Un vocale (Ogg/Opus) con il testo come didascalia, o a parte se lungo."""
    chat = chat_collegata()
    if not chat:
        raise TelegramNonPronto("chat non collegata: scrivere /start al bot")
    chiave = token()
    corta = didascalia if len(didascalia) <= 1000 else ""
    async with httpx.AsyncClient(timeout=60) as client:
        risposta = await client.post(
            API.format(token=chiave, metodo="sendVoice"),
            data={"chat_id": str(chat), "caption": corta},
            files={"voice": ("alfred.ogg", percorso.read_bytes(), "audio/ogg")},
        )
    if not risposta.json().get("ok"):
        raise TelegramNonPronto(risposta.json().get("description", "vocale non inviato"))
    if didascalia and not corta:
        await invia(didascalia)


async def scarica(file_id: str, destinazione) -> None:
    """Scarica un file ricevuto (es. un vocale) dai server di Telegram."""
    info = await chiama("getFile", file_id=file_id)
    async with httpx.AsyncClient(timeout=60) as client:
        risposta = await client.get(f"https://api.telegram.org/file/bot{token()}/{info['file_path']}")
        risposta.raise_for_status()
    destinazione.write_bytes(risposta.content)


async def sta_scrivendo() -> None:
    chat = chat_collegata()
    if chat:
        await chiama("sendChatAction", chat_id=chat, action="typing")

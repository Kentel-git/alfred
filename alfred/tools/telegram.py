"""Telegram: Alfred scrive a Pietro tramite un bot dedicato (Bot API ufficiale).

Il bot si crea con @BotFather; il token va in secrets.env come
ALFRED_TELEGRAM_TOKEN. Poi `alfred telegram` collega la chat: si scrive /start
al bot e Alfred memorizza a chi deve scrivere. Il bot scrive solo a quella chat.
"""

import json

import httpx

from alfred import config

FILE_CHAT = config.CARTELLA_STATO / "telegram.json"
API = "https://api.telegram.org/bot{token}/{metodo}"


class TelegramNonPronto(Exception):
    pass


def _token() -> str:
    token = config.segreto("ALFRED_TELEGRAM_TOKEN")
    if not token:
        raise TelegramNonPronto("manca ALFRED_TELEGRAM_TOKEN in secrets.env")
    return token


def chat_collegata() -> int | None:
    try:
        return json.loads(FILE_CHAT.read_text())["chat_id"]
    except (OSError, ValueError, KeyError):
        return None


async def _chiama(metodo: str, **parametri) -> dict:
    async with httpx.AsyncClient(timeout=40) as client:
        risposta = await client.post(API.format(token=_token(), metodo=metodo), json=parametri)
        dati = risposta.json()
    if not dati.get("ok"):
        raise TelegramNonPronto(dati.get("description", "errore sconosciuto"))
    return dati["result"]


async def invia(testo: str) -> None:
    chat = chat_collegata()
    if not chat:
        raise TelegramNonPronto("chat non collegata: eseguire `alfred telegram`")
    await _chiama("sendMessage", chat_id=chat, text=testo)


async def collega() -> None:
    """Aspetta il /start del proprietario e memorizza la sua chat."""
    bot = await _chiama("getMe")
    print(f"Bot: @{bot['username']}. Scrivigli /start da Telegram (attendo 2 minuti)…")
    ultimo = 0
    for _ in range(4):
        for aggiornamento in await _chiama("getUpdates", offset=ultimo, timeout=30):
            ultimo = aggiornamento["update_id"] + 1
            messaggio = aggiornamento.get("message") or {}
            if (messaggio.get("text") or "").startswith("/start"):
                chat = messaggio["chat"]
                config.CARTELLA_STATO.mkdir(parents=True, exist_ok=True)
                FILE_CHAT.write_text(json.dumps({"chat_id": chat["id"], "nome": chat.get("first_name")}))
                await _chiama("getUpdates", offset=ultimo)  # segna come letti
                await _chiama("sendMessage", chat_id=chat["id"],
                              text="Buonasera, signore. Da questo momento potrò scriverle anche qui.")
                print(f"Collegato a {chat.get('first_name')} (chat {chat['id']}).")
                return
    print("Nessun /start ricevuto: riprova.")

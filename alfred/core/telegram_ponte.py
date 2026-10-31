"""Ponte Telegram: porta i messaggi di Pietro dal bot alla conversazione.

Ascolta il bot con il long polling (nessun server esposto su internet).
Accetta solo la chat collegata; il primo /start, se nessuna chat è ancora
collegata, collega quella di chi lo manda.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from alfred import config
from alfred.tools import telegram

log = logging.getLogger("alfred.telegram")


async def _gestisci(aggiornamento: dict, conversazione) -> None:
    chat_collegata = telegram.chat_collegata()

    if pulsante := aggiornamento.get("callback_query"):
        if pulsante["message"]["chat"]["id"] != chat_collegata:
            return
        await telegram.chiama("answerCallbackQuery", callback_query_id=pulsante["id"])
        # Toglie i pulsanti dal messaggio, così non si premono due volte.
        await telegram.chiama(
            "editMessageReplyMarkup", chat_id=chat_collegata,
            message_id=pulsante["message"]["message_id"], reply_markup={"inline_keyboard": []},
        )
        _, id_attesa, si = (pulsante.get("data") or "::").split(":")
        await conversazione.conferma_da_telegram(si == "1", id_attesa)
        return

    messaggio = aggiornamento.get("message") or {}
    chat, testo = messaggio.get("chat") or {}, (messaggio.get("text") or "").strip()
    if not chat:
        return

    if chat_collegata is None:
        if testo.startswith("/start"):
            telegram.collega_chat(chat)
            log.info("Telegram collegato a %s (chat %s)", chat.get("first_name"), chat["id"])
            await telegram.invia(
                "Buonasera, signore. Da questo momento può scrivermi anche qui: "
                "le rispondo come se fossimo a casa."
            )
        return
    if chat["id"] != chat_collegata:
        log.warning("messaggio Telegram ignorato da una chat sconosciuta (%s)", chat["id"])
        return

    vocale = messaggio.get("voice") or messaggio.get("audio")
    if testo.startswith("/start"):
        await telegram.invia("Sono qui, signore.")
    elif testo:
        await conversazione.ricevi(testo, origine="telegram")
    elif vocale:
        await telegram.sta_scrivendo()
        config.CARTELLA_RUNTIME.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=config.CARTELLA_RUNTIME) as cartella:
            percorso = Path(cartella) / "vocale"
            await telegram.scarica(vocale["file_id"], percorso)
            await conversazione.vocale_telegram(str(percorso))
    else:
        await telegram.invia("Temo di saper leggere solo testi e ascoltare vocali, signore.")


async def ciclo(conversazione) -> None:
    attesa_errore = 5
    while True:
        if not telegram.token():
            await asyncio.sleep(30)  # il token si può aggiungere a servizio acceso
            continue
        try:
            # Long polling: Telegram tiene aperta la richiesta fino a 30 s.
            aggiornamenti = await telegram.chiama(
                "getUpdates", attesa_http=45, timeout=30, offset=telegram.ultimo_aggiornamento(),
                allowed_updates=["message", "callback_query"],
            )
            attesa_errore = 5
        except Exception as errore:
            log.warning("Telegram non raggiungibile: %s", errore)
            await asyncio.sleep(attesa_errore)
            attesa_errore = min(attesa_errore * 2, 300)
            continue
        for aggiornamento in aggiornamenti:
            telegram.segna_letti(aggiornamento["update_id"] + 1)
            try:
                await _gestisci(aggiornamento, conversazione)
            except Exception:
                log.exception("messaggio Telegram non gestito")

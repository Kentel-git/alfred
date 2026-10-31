"""La conversazione con Alfred: cervello, cronologia e contesto.

La cronologia e l'id di sessione del cervello sono salvati su disco, così la
conversazione sopravvive ai riavvii del servizio e l'HUD la ritrova intatta.
"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime

from alfred import config
from alfred.brain.claude import CervelloClaude
from alfred.brain.economo import RISPOSTE_AUSTERITA, Economo
from alfred.config import CARTELLA_STATO
from alfred.core import limiti, meteo

FILE_CONVERSAZIONE = CARTELLA_STATO / "conversazione.json"
MAX_MESSAGGI = 100

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

log = logging.getLogger("alfred.conversazione")


def _contesto() -> str:
    adesso = datetime.now()
    testo = (f"{GIORNI[adesso.weekday()]} {adesso.day} {MESI[adesso.month - 1]} {adesso.year}, "
             f"ore {adesso.hour}:{adesso.minute:02d}")
    luogo = (meteo.ultimo() or {}).get("luogo")
    return f"[{testo} · {luogo}]" if luogo else f"[{testo}]"


class Conversazione:
    def __init__(self, invia: Callable[[dict], Awaitable[None]]):
        self._invia = invia
        self.messaggi: list[dict] = []
        self._sessione: str | None = None
        self._carica()
        cfg = config.carica()
        self.economo = Economo(cfg)
        limiti.collega_economo(self.economo)
        self.cervello = CervelloClaude(
            modello=cfg["cervello"]["quotidiano"],
            appellativo=cfg["generale"]["appellativo"],
            sessione=self._sessione,
        )
        self.occupato = False

    def _carica(self) -> None:
        try:
            dati = json.loads(FILE_CONVERSAZIONE.read_text())
            self.messaggi, self._sessione = dati.get("messaggi", []), dati.get("sessione")
        except (OSError, ValueError):
            pass

    def _salva(self) -> None:
        CARTELLA_STATO.mkdir(parents=True, exist_ok=True)
        self.messaggi = self.messaggi[-MAX_MESSAGGI:]
        temporaneo = FILE_CONVERSAZIONE.with_suffix(".tmp")
        temporaneo.write_text(json.dumps(
            {"sessione": self.cervello.sessione, "messaggi": self.messaggi}, ensure_ascii=False
        ))
        temporaneo.replace(FILE_CONVERSAZIONE)

    def stato(self) -> dict:
        return {"tipo": "cronologia", "messaggi": self.messaggi, "occupato": self.occupato}

    async def ricevi(self, testo: str) -> None:
        """Messaggio di Pietro: lo mostra subito a tutti gli HUD e fa rispondere Alfred."""
        testo = testo.strip()
        if not testo:
            return
        domanda = {"chi": "utente", "testo": testo, "quando": time.time()}
        self.messaggi.append(domanda)
        self._salva()
        await self._invia({"tipo": "messaggio", "messaggio": domanda})
        asyncio.create_task(self._rispondi(testo))

    async def _rispondi(self, testo: str) -> None:
        modello = self.economo.scegli(testo, limiti.stato())
        if modello is None:
            # Austerità: Alfred risponde da sé, senza spendere riserve.
            messaggio = {"chi": "alfred", "testo": RISPOSTE_AUSTERITA[0], "quando": time.time(), "modello": None}
            self.messaggi.append(messaggio)
            self._salva()
            await self._invia({"tipo": "risposta_fine", "messaggio": messaggio})
            return

        self.occupato = True
        await self._invia({"tipo": "risposta_inizio", "modello": modello})
        risposta, errore = "", None
        try:
            async for evento in self.cervello.chiedi(f"{_contesto()}\n{testo}", modello):
                match evento["tipo"]:
                    case "parziale":
                        await self._invia({"tipo": "risposta_parziale", "testo": evento["testo"]})
                    case "strumento":
                        await self._invia({"tipo": "risposta_strumento", "nome": evento["nome"]})
                    case "sessione":
                        self._salva()
                    case "limiti":
                        if limiti.aggiorna(evento["dati"]):
                            await self._invia(limiti.stato())
                    case "fine":
                        risposta, errore = evento["testo"], evento["errore"]
                        limiti.conta_messaggio(evento.get("token", 0))
                        await self._invia(limiti.stato())
        except Exception as e:
            log.exception("il cervello si è inceppato")
            errore = str(e)

        self.occupato = False
        messaggio = {
            "chi": "alfred",
            "testo": risposta.strip() or "Perdoni, signore: ho perso il filo del discorso. Può ripetere?",
            "quando": time.time(),
            "modello": modello,
        }
        if errore:
            log.warning("risposta con errore: %s", errore)
            messaggio["errore"] = errore
        self.messaggi.append(messaggio)
        self._salva()
        await self._invia({"tipo": "risposta_fine", "messaggio": messaggio})

    async def nuova(self) -> None:
        await self.cervello.nuova_conversazione()
        self.messaggi = []
        self._salva()
        await self._invia(self.stato())

    async def riavvia_cervello(self) -> None:
        """Personalità o scheda cambiate: il cervello riparte con la stessa conversazione."""
        cfg = config.carica()
        self.cervello.appellativo = cfg["generale"]["appellativo"]
        self.economo.aggiorna_config(cfg)
        await self.cervello.riavvia()
        log.info("cervello riavviato con la nuova personalità")

    async def chiudi(self) -> None:
        await self.cervello.ferma()

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
from alfred.core import comandi, limiti, meteo
from alfred.core.azioni import Gestore, descrizione_per_riferire
from alfred.tools import telegram

FILE_CONVERSAZIONE = CARTELLA_STATO / "conversazione.json"
MAX_MESSAGGI = 100

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]

log = logging.getLogger("alfred.conversazione")


def _contesto(origine: str) -> str:
    adesso = datetime.now()
    parti = [f"{GIORNI[adesso.weekday()]} {adesso.day} {MESI[adesso.month - 1]} {adesso.year}, "
             f"ore {adesso.hour}:{adesso.minute:02d}"]
    if luogo := (meteo.ultimo() or {}).get("luogo"):
        parti.append(f"computer a {luogo}")
    if origine == "telegram":
        parti.append("ti scrive da Telegram, probabilmente lontano dal computer")
    return "[" + " · ".join(parti) + "]"


async def _a_telegram(testo: str, conferma_id: str | None = None) -> None:
    try:
        await telegram.invia(testo, conferma_id)
    except Exception as errore:
        log.warning("risposta Telegram non inviata: %s", errore)


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
        self.azioni = Gestore(self._invia_da_azioni)
        # Da dove arriva l'ultimo messaggio di Pietro ("hud" o "telegram"):
        # risposte ed esiti tornano lì.
        self._origine = "hud"
        # Ciò che è successo senza il cervello (comandi diretti, conferme):
        # glielo si racconta al messaggio successivo, così resta coerente.
        self._da_riferire: list[str] = []

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

    async def _invia_da_azioni(self, messaggio: dict) -> None:
        await self._invia(messaggio)
        if messaggio["tipo"] == "conferma" and self._origine == "telegram":
            await _a_telegram(messaggio["domanda"], conferma_id=messaggio["id"])

    async def ricevi(self, testo: str, origine: str = "hud") -> None:
        """Messaggio di Pietro: lo mostra subito a tutti gli HUD e fa rispondere Alfred."""
        testo = testo.strip()
        if not testo:
            return
        self._origine = origine
        domanda = {"chi": "utente", "testo": testo, "quando": time.time()}
        if origine != "hud":
            domanda["origine"] = origine
        self.messaggi.append(domanda)
        self._salva()
        await self._invia({"tipo": "messaggio", "messaggio": domanda})

        # Prima i comandi diretti: zero token, risposta immediata.
        comando = comandi.riconosci(testo)
        if comando:
            nome, parametri = comando
            if nome in ("conferma", "annulla"):
                esito = await self.azioni.conferma(nome == "conferma")
                if esito:
                    await self.annuncia(esito["messaggio"], esito)
                    return
                # Nessuna conferma in attesa: è conversazione, ci pensa il cervello.
            else:
                esito = await self.azioni.richiedi(nome, parametri)
                # Su Telegram la domanda di conferma è già partita, con i pulsanti.
                await self.annuncia(esito["messaggio"], esito, a_telegram=not esito.get("in_attesa_di_conferma"))
                return
        asyncio.create_task(self._rispondi(testo))

    async def annuncia(self, testo: str, esito: dict | None = None, a_telegram: bool = True) -> None:
        """Messaggio di Alfred senza cervello (esito di un'azione)."""
        messaggio = {"chi": "alfred", "testo": testo, "quando": time.time(), "modello": None}
        self.messaggi.append(messaggio)
        self._salva()
        if esito:
            self._da_riferire.append(descrizione_per_riferire(esito))
        await self._invia({"tipo": "messaggio", "messaggio": messaggio})
        if a_telegram and self._origine == "telegram":
            await _a_telegram(testo)

    async def azione_da_hud(self, nome: str, parametri: dict) -> None:
        """Pulsanti dell'HUD."""
        self._origine = "hud"
        esito = await self.azioni.richiedi(nome, parametri)
        if not esito.get("in_attesa_di_conferma"):
            await self.annuncia(esito["messaggio"], esito)

    async def conferma_da_hud(self, si: bool, id_attesa: str) -> None:
        self._origine = "hud"
        if esito := await self.azioni.conferma(si, id_attesa):
            await self.annuncia(esito["messaggio"], esito)

    async def conferma_da_telegram(self, si: bool, id_attesa: str) -> None:
        self._origine = "telegram"
        if esito := await self.azioni.conferma(si, id_attesa):
            await self.annuncia(esito["messaggio"], esito)
        else:
            await _a_telegram("Quella richiesta è scaduta o è già stata decisa, signore.")

    async def _rispondi(self, testo: str) -> None:
        origine = self._origine
        modello = self.economo.scegli(testo, limiti.stato())
        if modello is None:
            # Austerità: Alfred risponde da sé, senza spendere riserve.
            messaggio = {"chi": "alfred", "testo": RISPOSTE_AUSTERITA[0], "quando": time.time(), "modello": None}
            self.messaggi.append(messaggio)
            self._salva()
            await self._invia({"tipo": "risposta_fine", "messaggio": messaggio})
            if origine == "telegram":
                await _a_telegram(messaggio["testo"])
            return

        scrivendo = asyncio.create_task(self._sta_scrivendo()) if origine == "telegram" else None
        self.occupato = True
        await self._invia({"tipo": "risposta_inizio", "modello": modello})
        risposta, errore = "", None
        try:
            riferimenti = ""
            if self._da_riferire:
                riferimenti = ("[Comandi che " + self.cervello.appellativo + " ti ha dato nel frattempo, "
                               "eseguiti direttamente: " + "; ".join(self._da_riferire) + "]\n")
                self._da_riferire = []
            async for evento in self.cervello.chiedi(f"{_contesto(origine)}\n{riferimenti}{testo}", modello):
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
        if scrivendo:
            scrivendo.cancel()
            await _a_telegram(messaggio["testo"])

    @staticmethod
    async def _sta_scrivendo() -> None:
        """Su Telegram, "sta scrivendo…" finché la risposta non è pronta."""
        while True:
            try:
                await telegram.sta_scrivendo()
            except Exception:
                pass
            await asyncio.sleep(4)

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

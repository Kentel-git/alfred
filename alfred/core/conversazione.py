"""La conversazione con Alfred: cervello, cronologia e contesto.

La cronologia e l'id di sessione del cervello sono salvati su disco, così la
conversazione sopravvive ai riavvii del servizio e l'HUD la ritrova intatta.
"""

import asyncio
import json
import logging
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

from alfred import brain, config
from alfred.brain.claude import CervelloClaude, chiedi_una_volta
from alfred.brain.economo import RISPOSTE_AUSTERITA, Economo
from alfred.config import CARTELLA_STATO
from alfred.core import comandi, iniziativa, limiti, meteo, parole
from alfred.core.azioni import Gestore, descrizione_per_riferire
from alfred.finestra import avvisa_desktop
from alfred.tools import agenda, telegram
from alfred.voce import ascolto, parola, sveglia

FILE_CONVERSAZIONE = CARTELLA_STATO / "conversazione.json"
MAX_MESSAGGI = 100

log = logging.getLogger("alfred.conversazione")


def _contesto(origine: str) -> str:
    adesso = datetime.now()
    parti = [f"{parole.giorno_esteso(adesso.date())} {adesso.year}, ore {adesso.hour}:{adesso.minute:02d}"]
    if luogo := (meteo.ultimo() or {}).get("luogo"):
        parti.append(f"computer a {luogo}")
    if origine == "telegram":
        parti.append("ti scrive da Telegram, probabilmente lontano dal computer")
    elif origine == "voce":
        parti.append("ti parla a voce: la tua risposta sarà ascoltata, non letta")
    return "[" + " · ".join(parti) + "]"


DIARIO = ("Sei Alfred, il maggiordomo. Ti do la conversazione di una giornata con {appellativo}. "
          "Scrivi il tuo diario: da tre a sei righe in italiano, in prima persona, solo ciò che "
          "varrà la pena ricordare nei giorni seguenti (impegni presi, preferenze emerse, cose da "
          "seguire). Niente saluti, titoli o formule.")


async def _a_telegram(testo: str, conferma_id: str | None = None, vocale: bool = False,
                      silenzioso: bool = False) -> None:
    try:
        if vocale and parola.disponibile():
            config.CARTELLA_RUNTIME.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=config.CARTELLA_RUNTIME) as cartella:
                percorso = await parola.in_vocale(testo, Path(cartella) / "risposta.ogg")
                await telegram.invia_vocale(percorso, testo)
        else:
            await telegram.invia(testo, conferma_id, silenzioso)
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
        # Da dove arriva l'ultimo messaggio di Pietro ("hud", "telegram" o "voce"):
        # risposte ed esiti tornano lì.
        self._origine = "hud"
        self._ascolto: ascolto.Ascolto | None = None
        self._discorso: parola.Discorso | None = None
        self._vocale_telegram = False  # l'ultimo messaggio Telegram era un vocale
        # Sentendo il suo nome mentre parla, Alfred si zittisce subito: aspettare la
        # fine della frase vorrebbe dire aspettare il silenzio, che con la sua
        # voce in sottofondo non arriverebbe.
        self.sveglia = sveglia.Sveglia(self._chiamato, quando_forse=self.zittisci)
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

    async def ricevi(self, testo: str, origine: str = "hud", vocale: bool = False) -> None:
        """Messaggio di Pietro: lo mostra subito a tutti gli HUD e fa rispondere Alfred."""
        testo = testo.strip()
        if not testo:
            return
        self._origine = origine
        if origine == "telegram":
            self._vocale_telegram = vocale
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
            if nome == "zittisci":
                self.zittisci()  # nessuna risposta: il silenzio è la risposta
                return
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
            # Solo gli ultimi: dopo una diretta piena di clic non si mandano centinaia di righe a Claude.
            self._da_riferire = [*self._da_riferire, descrizione_per_riferire(esito)][-10:]
        await self._invia({"tipo": "messaggio", "messaggio": messaggio})
        if a_telegram and self._origine == "telegram":
            await _a_telegram(testo, vocale=self._vocale_telegram)
        elif self._origine == "voce" and (discorso := self._parla()):
            discorso.aggiungi(testo)
            discorso.fine()

    # --- Voce -------------------------------------------------------------------

    def _parla(self) -> "parola.Discorso | None":
        """Nuovo discorso ad alta voce (zittendo quello in corso), se la voce è attiva."""
        if not (parola.disponibile() and config.carica().get("voce", {}).get("attiva", True)):
            return None
        self.zittisci()
        discorso = parola.Discorso()
        self._discorso = discorso

        async def segui():
            await self._invia({"tipo": "parola", "stato": "parla"})
            await discorso.compito
            if self._discorso is discorso:
                self._discorso = None
                await self._invia({"tipo": "parola", "stato": "fine"})
        asyncio.create_task(segui())
        return discorso

    def zittisci(self) -> bool:
        if self._discorso:
            self._discorso.zittisci()
            self._discorso = None
            return True
        return False

    async def ascolta(self) -> None:
        """Apre il microfono per una frase; se è già aperto, lo chiude.
        Se Alfred sta parlando, prima lo zittisce."""
        if self.zittisci():
            await self._invia({"tipo": "parola", "stato": "fine"})
        if self._ascolto:
            self._ascolto.interrompi()
            return
        self._ascolto = ascolto.Ascolto()
        asyncio.create_task(self._ascolta_frase(self._ascolto))

    async def _chiamato(self, esito: str, comando: str) -> None:
        """Pietro ha detto "Alfred" (verificato)."""
        self.zittisci()
        if esito == "chiamata":
            await self.ricevi(comando, origine="voce")
            return
        # Solo il nome: Alfred si volta, e ascolta.
        if discorso := self._parla():
            discorso.aggiungi("Sì, signore?")
            discorso.fine()
            await discorso.compito
        await self.ascolta()

    async def _ascolta_frase(self, sessione: "ascolto.Ascolto") -> None:
        async def avvisa(stato: str) -> None:
            await self._invia({"tipo": "ascolto", "stato": stato})

        self.sveglia.sospendi()  # il microfono è già aperto per la frase
        try:
            audio = await sessione.frase(avvisa)
            if audio is None:
                await avvisa("niente")
                return
            await avvisa("trascrivo")
            testo = await ascolto.trascrivi(audio)
        except Exception as errore:
            log.exception("ascolto non riuscito")
            await self._invia({"tipo": "ascolto", "stato": "errore", "errore": str(errore)})
            return
        finally:
            self._ascolto = None
            self.sveglia.riprendi()
        await avvisa("fine")
        if testo:
            await self.ricevi(testo, origine="voce")
        else:
            await avvisa("niente")

    async def vocale_telegram(self, percorso: str) -> None:
        """Vocale ricevuto su Telegram: si trascrive e si tratta come un messaggio."""
        testo = await ascolto.trascrivi(await ascolto.da_file(percorso))
        if testo:
            self._vocale_telegram = True  # si risponde con un vocale
            await self.ricevi(testo, origine="telegram", vocale=True)
        else:
            await _a_telegram("Perdoni, signore: nel vocale non sono riuscito a distinguere parole.")

    # --- Di sua iniziativa -------------------------------------------------------

    async def di_sua_iniziativa(self, testo: str, bloccato: bool) -> None:
        """Alfred parla per primo: a voce se Pietro è al computer, con una notifica muta
        nelle ore di silenzio, su Telegram se lo schermo è bloccato (di notte senza suono)."""
        messaggio = {"chi": "alfred", "testo": testo, "quando": time.time(), "modello": None}
        self.messaggi.append(messaggio)
        self._salva()
        self._da_riferire = [*self._da_riferire, f"hai detto di tua iniziativa: «{testo}»"][-10:]
        await self._invia({"tipo": "messaggio", "messaggio": messaggio})
        silenzio = iniziativa.ora_di_silenzio()
        if bloccato:
            await _a_telegram(testo, silenzioso=silenzio)
        elif silenzio:
            avvisa_desktop("Alfred", testo)
        elif discorso := self._parla():
            discorso.aggiungi(testo)
            discorso.fine()

    async def nuovo_giorno(self, adesso: datetime) -> None:
        """Prima apertura della giornata: diario di ieri, conversazione nuova, briefing."""
        if self.messaggi:
            giorno = datetime.fromtimestamp(self.messaggi[-1]["quando"]).date()
            # In austerità niente riassunto: la memoria non vale le ultime riserve.
            if self.economo.regime(limiti.stato())["nome"] != "austerità":
                trascrizione = "\n".join(
                    f"{'Lui' if m['chi'] == 'utente' else 'Alfred'}: {m['testo']}" for m in self.messaggi
                )
                try:
                    riassunto, info = await chiedi_una_volta(
                        trascrizione, DIARIO.replace("{appellativo}", self.cervello.appellativo))
                    if limiti.aggiorna(info):
                        await self._invia(limiti.stato())
                    if riassunto:
                        brain.scrivi_diario(giorno, riassunto)
                except Exception as errore:
                    log.warning("diario non scritto: %s", errore)
            await self.nuova()
        oggi = datetime.combine(adesso.date(), datetime.min.time()).astimezone()
        try:
            eventi = await agenda.eventi(oggi, oggi.replace(hour=23, minute=59)) if agenda.pronta() else None
        except Exception as errore:
            log.warning("agenda per il briefing non letta: %s", errore)
            eventi = None
        try:
            tempo = await meteo.leggi(config.carica()["meteo"])  # appena avviato non c'è ancora in memoria
        except Exception:
            tempo = None
        await self.di_sua_iniziativa(
            iniziativa.testo_briefing(adesso, eventi, tempo, limiti.stato()), bloccato=False)

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
                await _a_telegram(messaggio["testo"], vocale=self._vocale_telegram)
            elif origine == "voce" and (discorso := self._parla()):
                discorso.aggiungi(messaggio["testo"])
                discorso.fine()
            return

        scrivendo = asyncio.create_task(self._sta_scrivendo()) if origine == "telegram" else None
        discorso = self._parla() if origine == "voce" else None
        self.occupato = True
        await self._invia({"tipo": "risposta_inizio", "modello": modello})
        risposta, errore = "", None
        try:
            riferimenti = ""
            if self._da_riferire:
                riferimenti = ("[Nel frattempo, senza passare da te (comandi che " + self.cervello.appellativo
                               + " ti ha dato ed eseguiti direttamente, o cose dette di tua iniziativa): "
                               + "; ".join(self._da_riferire) + "]\n")
                self._da_riferire = []
            async for evento in self.cervello.chiedi(f"{_contesto(origine)}\n{riferimenti}{testo}", modello):
                match evento["tipo"]:
                    case "parziale":
                        await self._invia({"tipo": "risposta_parziale", "testo": evento["testo"]})
                        if discorso:
                            discorso.aggiungi(evento["testo"] or " ")
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
        if discorso:
            if not risposta.strip():
                discorso.aggiungi(messaggio["testo"])
            discorso.fine()
        if scrivendo:
            scrivendo.cancel()
            await _a_telegram(messaggio["testo"], vocale=self._vocale_telegram)

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

"""La sveglia: Alfred risponde quando sente il suo nome.

Due stadi, tutto in locale:
1. un riconoscitore di parole chiave minuscolo (sherpa-onnx, 3,3 milioni di
   parametri) ascolta sempre ed è volutamente permissivo, per non perdere
   nessun "Alfred";
2. quando scatta, si registra la frase intera (compreso il secondo e mezzo
   precedente, così "Alfred, che ore sono?" si può dire d'un fiato) e la si
   trascrive con Whisper: se dice davvero "Alfred" (e non "al freddo" o
   "Alfredo") la frase va ad Alfred, altrimenti si scarta in silenzio.

Se la frase è solo il nome, Alfred risponde "Sì, signore?" e ascolta il
comando. Funziona anche mentre Alfred parla: chiamarlo lo interrompe.
"""

import asyncio
import collections
import logging
import os
import re
from pathlib import Path

import numpy as np

from alfred import config
from alfred.voce import ascolto

log = logging.getLogger("alfred.sveglia")

CARTELLA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "alfred" / "voce" / "kws"
NOME_MODELLO = "epoch-12-avg-2-chunk-16-left-64.int8.onnx"
# "ALFRED" scomposto nei token del modello (inglese, GigaSpeech).
PAROLA_CHIAVE = "▁A L F RE D @ALFRED"
PRIMA_S = 1.5  # audio tenuto prima della parola chiave

CHIAMATA = re.compile(r"\balfred\b(?!o)", re.IGNORECASE)
SOLO_NOME = re.compile(r"^\W*(?:ehi\s+|hey\s+)?al\s?fred\w{0,2}\W*$", re.IGNORECASE)
PREFISSO = re.compile(r"^\W*(?:ehi|hey|scusa|senti|ok)?\W*al\s?fred\w{0,2}\b\W*", re.IGNORECASE)


def _impostazioni() -> dict:
    # Tarate sulla voce di Pietro (2 nov 2026): 6 chiamate su 9 contro 3, stessi falsi allarmi.
    return {"attiva": True, "soglia": 0.15, "punteggio": 1.5} | config.carica().get("sveglia", {})


def disponibile() -> bool:
    return all((CARTELLA / f"{parte}-{NOME_MODELLO}").exists() for parte in ("encoder", "decoder", "joiner"))


def verifica(testo: str) -> tuple[str, str]:
    """("chiamata", comando) | ("solo_nome", "") | ("no", "") dal testo trascritto."""
    if SOLO_NOME.match(testo):
        return "solo_nome", ""
    if CHIAMATA.search(testo):
        comando = PREFISSO.sub("", testo, count=1).strip()
        return ("chiamata", comando) if comando else ("solo_nome", "")
    return "no", ""


istanza: "Sveglia | None" = None


class Sveglia:
    def __init__(self, quando_chiamato, quando_forse=None):
        """quando_chiamato(esito, comando) viene atteso a ogni chiamata verificata;
        quando_forse() appena il primo stadio scatta (es. per zittire Alfred subito)."""
        self._quando_chiamato = quando_chiamato
        self._quando_forse = quando_forse
        self._sospesa = asyncio.Event()  # impostata = non ascoltare (es. microfono occupato)
        self.attiva = _impostazioni()["attiva"]
        global istanza
        istanza = self

    def sospendi(self) -> None:
        self._sospesa.set()

    def riprendi(self) -> None:
        self._sospesa.clear()

    def _riconoscitore(self):
        import sherpa_onnx

        imp = _impostazioni()
        parole = CARTELLA / "parole.txt"
        parole.write_text(PAROLA_CHIAVE + "\n")
        return sherpa_onnx.KeywordSpotter(
            tokens=str(CARTELLA / "tokens.txt"),
            encoder=str(CARTELLA / f"encoder-{NOME_MODELLO}"),
            decoder=str(CARTELLA / f"decoder-{NOME_MODELLO}"),
            joiner=str(CARTELLA / f"joiner-{NOME_MODELLO}"),
            num_threads=1, keywords_file=str(parole), max_active_paths=4,
            keywords_score=imp["punteggio"], keywords_threshold=imp["soglia"],
        )

    async def ascolta_sempre(self) -> None:
        if not disponibile():
            log.info("sveglia non disponibile: manca il modello in %s", CARTELLA)
            return
        riconoscitore = await asyncio.to_thread(self._riconoscitore)
        log.info("sveglia attiva: Alfred risponde al suo nome")
        while True:
            if not self.attiva:
                await asyncio.sleep(2)
                continue
            try:
                await self._ciclo(riconoscitore)
            except Exception:
                log.exception("la sveglia si è inceppata, riparto")
                await asyncio.sleep(3)

    async def _ciclo(self, riconoscitore) -> None:
        processo = await ascolto.microfono("Alfred (sveglia)")
        flusso = riconoscitore.create_stream()
        precedente = collections.deque(maxlen=int(PRIMA_S * ascolto.FREQUENZA / ascolto.BLOCCO))
        try:
            while self.attiva:
                dati = await processo.stdout.readexactly(ascolto.BLOCCO * 2)
                if self._sospesa.is_set():
                    precedente.clear()
                    continue
                blocco = ascolto.blocco(dati)
                precedente.append(blocco)
                flusso.accept_waveform(ascolto.FREQUENZA, blocco)
                scattata = False
                while riconoscitore.is_ready(flusso):
                    riconoscitore.decode_stream(flusso)
                    if riconoscitore.get_result(flusso):
                        scattata = True
                        riconoscitore.reset_stream(flusso)
                if scattata:
                    log.info("forse ho sentito il mio nome: verifico")
                    if self._quando_forse:
                        self._quando_forse()
                    gia_sentito = np.concatenate(precedente)
                    precedente.clear()
                    await self._frase_dopo_il_nome(processo, gia_sentito)
        except asyncio.IncompleteReadError:
            log.warning("il microfono si è chiuso, riparto tra poco")
            await asyncio.sleep(3)
        finally:
            if processo.returncode is None:
                processo.terminate()
                await processo.wait()

    async def _frase_dopo_il_nome(self, processo, gia_sentito: np.ndarray) -> None:
        """Continua a registrare dallo stesso microfono fino al silenzio, poi verifica."""
        audio = await ascolto.fino_al_silenzio(processo, gia_sentito)
        if audio is None:
            return
        testo = await ascolto.trascrivi(audio)
        esito, comando = verifica(testo)
        if esito == "no":
            log.info("falso allarme scartato: «%s»", testo)
            return
        log.info("chiamato (%s): «%s»", esito, testo)
        await self._quando_chiamato(esito, comando)

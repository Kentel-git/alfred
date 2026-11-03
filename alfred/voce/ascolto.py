"""L'ascolto: microfono, fine della frase, trascrizione. Tutto in locale.

- Il microfono si legge con pw-record (PipeWire), audio grezzo a 16 kHz.
- Il rilevatore di voce Silero (incluso in faster-whisper) capisce quando si
  comincia a parlare e quando si è finito.
- faster-whisper trascrive sulla CPU: la GPU resta libera per giochi e dirette.

Nessun audio esce dal computer e non si consumano riserve.
"""

import asyncio
import ctypes
import gc
import logging
import shutil
import time

import numpy as np

from alfred import config

log = logging.getLogger("alfred.ascolto")

FREQUENZA = 16000
BLOCCO = 512  # campioni (32 ms)
CONTROLLO_OGNI_S = 0.25

# Vocabolario che aiuta Whisper con nomi propri e termini di casa.
VOCABOLARIO_BASE = "Alfred, OBS, diretta, registrazione, scena, agenda, Telegram, Notion, Battle.net, CurseForge, standby."

_modello = None
_blocco_modello = asyncio.Lock()
_ultimo_uso = time.monotonic()
# Dopo questa inattività il modello si scarica: libera ~1,6 GB (medium) e alla
# prossima frase si ricarica in ~1,5 s.
RIPOSO_S = 600


def _impostazioni() -> dict:
    return {
        "modello": "small",
        "fine_frase_s": 0.9,  # silenzio che chiude la frase
        "attesa_inizio_s": 6,  # se non si parla entro questo tempo, si rinuncia
        "durata_massima_s": 30,
        "vocabolario": "",
    } | config.carica().get("ascolto", {})


async def _carica_modello():
    global _modello
    async with _blocco_modello:
        if _modello is None:
            from faster_whisper import WhisperModel

            nome = _impostazioni()["modello"]
            inizio = time.monotonic()
            _modello = await asyncio.to_thread(
                WhisperModel, nome, device="cpu", compute_type="int8", cpu_threads=8
            )
            log.info("trascrizione (%s) pronta in %.1f s", nome, time.monotonic() - inizio)
    return _modello


async def prepara() -> None:
    """Carica il modello in anticipo, così la prima frase non aspetta."""
    await _carica_modello()


async def riposa() -> None:
    """Scarica il modello quando non serve da un po'."""
    global _modello
    while True:
        await asyncio.sleep(60)
        if _modello is None or time.monotonic() - _ultimo_uso < RIPOSO_S or _blocco_modello.locked():
            continue
        _modello = None  # una trascrizione in corso tiene ancora il suo riferimento
        gc.collect()
        try:  # senza, al sistema torna solo metà della memoria
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):  # non glibc
            pass
        log.info("trascrizione a riposo: modello scaricato")


async def trascrivi(audio: np.ndarray) -> str:
    modello = await _carica_modello()
    imp = _impostazioni()
    prompt = f"{VOCABOLARIO_BASE} {imp['vocabolario']}".strip()

    def lavora() -> str:
        segmenti, _ = modello.transcribe(
            audio, language="it", beam_size=1, initial_prompt=prompt,
            condition_on_previous_text=False, vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segmenti).strip()

    global _ultimo_uso
    inizio = time.monotonic()
    testo = await asyncio.to_thread(lavora)
    _ultimo_uso = time.monotonic()
    log.info("trascritto in %.1f s: %s", time.monotonic() - inizio, testo)
    return testo


def _parla_ora(audio: np.ndarray, durata_frase_s: float) -> tuple[bool, float]:
    """(si è parlato, secondi di silenzio in coda) secondo Silero."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    tratti = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=200, speech_pad_ms=0))
    if not tratti:
        return False, durata_frase_s
    return True, (len(audio) - tratti[-1]["end"]) / FREQUENZA


async def microfono(nome: str) -> asyncio.subprocess.Process:
    """Il microfono come audio grezzo a 16 kHz; nome è quello che mostra PipeWire."""
    if not shutil.which("pw-record"):
        raise RuntimeError("manca pw-record (PipeWire)")
    return await asyncio.create_subprocess_exec(
        "pw-record", "--raw", "--rate", str(FREQUENZA), "--channels", "1", "--format", "s16",
        "-P", f'{{ media.name = "{nome}" }}', "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )


def blocco(dati: bytes) -> np.ndarray:
    return np.frombuffer(dati, np.int16).astype(np.float32) / 32768


async def fino_al_silenzio(processo, gia_sentito: np.ndarray | None = None,
                           interrompi: asyncio.Event | None = None, **limiti) -> np.ndarray | None:
    """Legge il microfono finché non si smette di parlare. None se non si è parlato.
    gia_sentito: l'audio precedente (la sveglia ci passa il nome appena detto).
    limiti: fine_frase_s, durata_massima_s… al posto di quelli configurati."""
    imp = _impostazioni() | limiti
    blocchi = [] if gia_sentito is None else [gia_sentito]
    ultimo_controllo, inizio = 0.0, time.monotonic()
    while not (interrompi and interrompi.is_set()):
        try:
            dati = await asyncio.wait_for(processo.stdout.readexactly(BLOCCO * 2), 2)
        except (asyncio.IncompleteReadError, TimeoutError):
            break
        blocchi.append(blocco(dati))
        trascorso = time.monotonic() - inizio
        if trascorso - ultimo_controllo < CONTROLLO_OGNI_S:
            continue
        ultimo_controllo = trascorso
        parlato, silenzio = await asyncio.to_thread(_parla_ora, np.concatenate(blocchi), trascorso)
        if parlato and silenzio >= imp["fine_frase_s"]:
            break
        if not parlato and trascorso >= imp["attesa_inizio_s"]:
            return None
        if trascorso >= imp["durata_massima_s"]:
            break
    if not blocchi:
        return None
    audio = np.concatenate(blocchi)
    parlato, _ = await asyncio.to_thread(_parla_ora, audio, 0)
    return audio if parlato else None


class Ascolto:
    """Una frase: dal momento in cui si apre il microfono al silenzio finale."""

    def __init__(self):
        self._interrompi = asyncio.Event()

    def interrompi(self) -> None:
        self._interrompi.set()

    async def frase(self, avvisa, **limiti) -> np.ndarray | None:
        """Registra finché non si smette di parlare. None se non si è parlato."""
        processo = await microfono("Alfred (ascolto)")
        await avvisa("in_ascolto")
        try:
            return await fino_al_silenzio(processo, interrompi=self._interrompi, **limiti)
        finally:
            processo.terminate()
            await processo.wait()


async def da_file(percorso: str) -> np.ndarray:
    """Audio da un file qualunque (es. vocale di Telegram), via ffmpeg."""
    processo = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error", "-i", percorso, "-ar", str(FREQUENZA), "-ac", "1",
        "-f", "s16le", "-", stdout=asyncio.subprocess.PIPE,
    )
    dati, _ = await processo.communicate()
    return np.frombuffer(dati, np.int16).astype(np.float32) / 32768

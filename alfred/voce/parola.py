"""La parola: la voce di Alfred, sintetizzata in locale con Kokoro.

La voce scelta da Pietro (31 ottobre 2026) è una miscela di Nicola (italiano)
e Fable (britannico), un po' più lenta del normale. Kokoro in italiano chiude
le domande con un tono discendente: alle frasi che finiscono con "?" la curva
d'intonazione viene ridisegnata con il vocoder WORLD (pyworld), facendo salire
le ultime sillabe. Senza pyworld le domande restano com'escono da Kokoro.

Si parla frase per frase: la prima frase suona mentre si prepara la seconda,
così Alfred comincia a parlare quasi subito, anche mentre il cervello scrive.
"""

import asyncio
import logging
import os
import re
import time
from pathlib import Path

import numpy as np

from alfred import config

log = logging.getLogger("alfred.parola")

CARTELLA_MODELLI = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "alfred" / "voce"
MODELLO = CARTELLA_MODELLI / "kokoro-v1.0.onnx"
VOCI = CARTELLA_MODELLI / "voices-v1.0.bin"
PAUSA_S = 0.28
# Parole inglesi lette con la pronuncia inglese (britannica, come Fable) invece
# che all'italiana; altre si aggiungono in config.toml, [voce] inglese = [...].
INGLESE_BASE = ["Notion", "YouTube", "Discord", "Twitch", "streaming", "streamer", "live", "just chatting",
                "Battle.net", "CurseForge", "Steam", "gaming", "email", "link", "desk", "addon", "raid",
                "World of Warcraft", "Warcraft", "standby", "podcast", "reel", "post", "feedback"]

_kokoro = None
_blocco = asyncio.Lock()


FILE_PRONUNCE = "pronuncia.json"  # parole imparate parlando con Pietro


def parole_note() -> tuple[list[str], list[str]]:
    """(parole lette all'inglese, parole che Pietro ha voluto all'italiana)."""
    imparate = config.leggi_stato(FILE_PRONUNCE)
    return INGLESE_BASE + _impostazioni()["inglese"] + imparate.get("inglese", []), imparate.get("italiano", [])


def impara(parole: list[str], inglese: bool) -> list[str]:
    """Aggiunge parole all'elenco inglese (o a quelle da lasciare all'italiana,
    così Alfred non lo chiede di nuovo). Restituisce quelle davvero nuove."""
    inglesi, italiane = parole_note()
    note = {p.lower() for p in inglesi + italiane}
    nuove = list(dict.fromkeys(p.strip() for p in parole if p.strip() and p.strip().lower() not in note))
    if nuove:
        chiave = "inglese" if inglese else "italiano"
        config.salva_stato(FILE_PRONUNCE, **{chiave: config.leggi_stato(FILE_PRONUNCE).get(chiave, []) + nuove})
    return nuove


def _impostazioni() -> dict:
    return {
        "attiva": True,
        "voce": {"im_nicola": 0.7, "bm_fable": 0.3},
        "velocita": 0.92,
        "domande": True,  # intonazione interrogativa corretta
        "salita_domande": 0.35,
        "inglese": [],
    } | config.carica().get("voce", {})


def disponibile() -> bool:
    return MODELLO.exists() and VOCI.exists()


async def _modello():
    global _kokoro
    async with _blocco:
        if _kokoro is None:
            from kokoro_onnx import Kokoro

            inizio = time.monotonic()
            _kokoro = await asyncio.to_thread(Kokoro, str(MODELLO), str(VOCI))
            log.info("voce pronta in %.1f s", time.monotonic() - inizio)
    return _kokoro


async def prepara() -> None:
    if disponibile() and _impostazioni()["attiva"]:
        await _modello()


# --- Testo adatto a essere detto ---------------------------------------------

def per_la_voce(testo: str) -> str:
    testo = re.sub(r"[«»\"*_#`]", "", testo)
    testo = re.sub(r"\b(\d{1,2}):00\b", r"\1", testo)
    testo = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1 e \2", testo)
    testo = testo.replace("°C", " gradi").replace("°", " gradi").replace("%", " per cento")
    testo = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", testo)  # emoji
    return re.sub(r"\s+", " ", testo).strip()


def frasi(testo: str) -> list[str]:
    return [f.strip() for f in re.findall(r"[^.?!…]+[.?!…]*", testo) if f.strip(" .")]


# --- Sintesi -------------------------------------------------------------------

SEGNAPOSTO = "zubbalo"  # parola finta: espeak la legge sempre uguale, qualunque cosa abbia intorno


def fonemi(frase: str, inglesi: list[str], vocabolario: dict) -> str:
    """Fonemi per Kokoro: la frase letta in italiano, ma con le parole inglesi
    pronunciate all'inglese. Si leggono al posto di un segnaposto, così il resto
    della frase conserva accenti e ritmo. I segnaposto di cambio lingua di espeak,
    "(en)" e "(it)", si tolgono: Kokoro li leggerebbe come suoni."""
    import phonemizer

    def leggi(testo: str, lingua: str) -> str:
        f = phonemizer.phonemize(testo, lingua, preserve_punctuation=True, with_stress=True,
                                 language_switch="remove-flags")
        return "".join(c for c in f if c in vocabolario).strip()

    trovate = []
    if inglesi:
        schema = r"(?<!\w)(" + "|".join(re.escape(p) for p in sorted(inglesi, key=len, reverse=True)) + r")(?!\w)"
        con_segnaposto = re.sub(schema, lambda m: trovate.append(m[1]) or SEGNAPOSTO, frase, flags=re.IGNORECASE)
    if not trovate:
        return leggi(frase, "it")
    italiano, segnaposto = leggi(con_segnaposto, "it"), leggi(SEGNAPOSTO, "it")
    pezzi = italiano.split(segnaposto)
    if len(pezzi) != len(trovate) + 1:  # imprevisto: meglio tutta in italiano
        return leggi(frase, "it")
    return "".join(p + (leggi(t, "en-gb") if k < len(trovate) else "")
                   for k, (p, t) in enumerate(zip(pezzi, trovate + [""])))


def _domanda(audio: np.ndarray, sr: int, salita: float, coda_s: float = 0.7) -> np.ndarray:
    """Ridisegna la fine della curva d'intonazione: le ultime sillabe salgono."""
    try:
        import pyworld as pw
    except ImportError:
        return audio
    x = audio.astype(np.float64)
    f0, t = pw.dio(x, sr, frame_period=5.0)
    f0 = pw.stonemask(x, f0, t, sr)
    sp, ap = pw.cheaptrick(x, f0, t, sr), pw.d4c(x, f0, t, sr)
    voce = np.nonzero(f0)[0]
    if len(voce) > 10:
        inizio = t[voce[-1]] - coda_s
        prima = f0[(f0 > 0) & (t < inizio)]
        base = np.median(prima) if len(prima) else np.median(f0[f0 > 0])
        liscio = np.convolve(np.where(f0 > 0, f0, base), np.ones(15) / 15, "same")
        m = (t >= inizio) & (f0 > 0)
        rampa = np.clip((t[m] - inizio) / coda_s, 0, 1) ** 1.3
        f0[m] = base * (1 + salita * rampa) * (f0[m] / liscio[m])
    return pw.synthesize(f0, sp, ap, sr).astype(np.float32)


def _taglia(audio: np.ndarray, soglia: float = 0.01) -> np.ndarray:
    voce = np.nonzero(np.abs(audio) > soglia)[0]
    return audio[max(voce[0] - 400, 0): voce[-1] + 800] if len(voce) else audio


async def sintetizza(frase: str) -> tuple[np.ndarray, int]:
    kokoro = await _modello()
    imp = _impostazioni()

    def lavora():
        voce = sum(p * kokoro.get_voice_style(v) for v, p in imp["voce"].items())
        f = fonemi(frase, parole_note()[0], kokoro.tokenizer.vocab)
        audio, sr = kokoro.create(f, voice=voce, speed=imp["velocita"], is_phonemes=True)
        audio = _taglia(audio)
        if imp["domande"] and frase.rstrip().endswith("?"):
            audio = _domanda(audio, sr, imp["salita_domande"])
        return audio, sr

    return await asyncio.to_thread(lavora)


# --- Riproduzione ---------------------------------------------------------------

class Discorso:
    """Una risposta detta ad alta voce, frase per frase.

    Si aggiunge testo man mano che arriva (aggiungi), si chiude con fine();
    zittisci() interrompe subito.
    """

    def __init__(self):
        self._frasi: asyncio.Queue[str | None] = asyncio.Queue()
        self._resto = ""
        self._riproduttore: asyncio.subprocess.Process | None = None
        self._zitto = False
        self.compito = asyncio.create_task(self._parla())

    def aggiungi(self, testo: str) -> None:
        """Testo in arrivo (anche a pezzi): ogni frase completa va in coda."""
        self._resto += testo
        complete = re.findall(r".*?[.?!…](?=\s|$)", self._resto, flags=re.S)
        for frase in complete:
            self._frasi.put_nowait(frase)
        if complete:
            self._resto = self._resto[sum(len(f) for f in complete):]

    def fine(self) -> None:
        if self._resto.strip():
            self._frasi.put_nowait(self._resto)
        self._resto = ""
        self._frasi.put_nowait(None)

    def zittisci(self) -> None:
        self._zitto = True
        if self._riproduttore and self._riproduttore.returncode is None:
            self._riproduttore.kill()
        self._frasi.put_nowait(None)

    async def _parla(self) -> None:
        prossima: asyncio.Task | None = None
        try:
            while not self._zitto:
                if prossima is None:
                    frase = await self._frasi.get()
                    if frase is None:
                        break
                    testo = per_la_voce(frase)
                    if not testo:
                        continue
                    prossima = asyncio.create_task(sintetizza(testo))
                audio, sr = await prossima
                prossima = None
                # Mentre questa frase suona, si prepara la successiva (se è già arrivata).
                if not self._frasi.empty():
                    successiva = self._frasi.get_nowait()
                    if successiva is None:
                        self._frasi.put_nowait(None)
                    elif testo_successivo := per_la_voce(successiva):
                        prossima = asyncio.create_task(sintetizza(testo_successivo))
                await self._riproduci(audio, sr)
        except Exception:
            log.exception("la voce si è inceppata")
        finally:
            if prossima:
                prossima.cancel()

    async def _riproduci(self, audio: np.ndarray, sr: int) -> None:
        if self._zitto:
            return
        pausa = np.zeros(int(sr * PAUSA_S), np.float32)
        dati = np.concatenate([audio, pausa]).astype(np.float32).tobytes()
        self._riproduttore = await asyncio.create_subprocess_exec(
            "pw-play", "--raw", "--rate", str(sr), "--channels", "1", "--format", "f32", "-",
            stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            self._riproduttore.stdin.write(dati)
            await self._riproduttore.stdin.drain()
            self._riproduttore.stdin.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        await self._riproduttore.wait()


def _note(frequenze: list[float], sr: int = 24000, durata_s: float = 0.09) -> np.ndarray:
    """Note brevi e morbide, una dopo l'altra (suoni originali, generati qui)."""
    t = np.arange(int(sr * durata_s)) / sr
    inviluppo = np.sin(np.pi * t / durata_s) ** 2  # attacco e coda dolci, niente clic
    return np.concatenate([0.25 * np.sin(2 * np.pi * f * t) * inviluppo for f in frequenze]).astype(np.float32)


SEGNALI = {"inizio": [660, 880], "fine": [880, 660]}  # sale: ascolto; scende: fatto


async def segnale(nome: str) -> None:
    """Suona un segnale e aspetta che finisca (così il microfono non lo sente)."""
    processo = await asyncio.create_subprocess_exec(
        "pw-play", "--raw", "--rate", "24000", "--channels", "1", "--format", "f32", "-",
        stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    await processo.communicate(_note(SEGNALI[nome]).tobytes())


async def in_vocale(testo: str, destinazione: Path) -> Path:
    """Un vocale Ogg/Opus (per Telegram) con tutto il testo."""
    pezzi, sr = [], 24000
    for frase in frasi(per_la_voce(testo)):
        audio, sr = await sintetizza(frase)
        pezzi += [audio, np.zeros(int(sr * PAUSA_S), np.float32)]
    dati = np.concatenate(pezzi).astype(np.float32).tobytes() if pezzi else b""
    processo = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
        "-c:a", "libopus", "-b:a", "32k", str(destinazione), stdin=asyncio.subprocess.PIPE,
    )
    await processo.communicate(dati)
    return destinazione

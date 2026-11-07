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
import functools
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
# Con Pocket TTS (che legge testo, non fonemi) le parole straniere si dicono
# scrivendole come si pronunciano. Il cervello le segna ‹così› mentre scrive; la
# pronuncia si ricava da sola (espeak, inglese americano) e Pietro la può correggere.
MARCA = re.compile(r"‹([^‹›]+)›")
# Già sentite e approvate da Pietro (7 nov 2026): la loro pronuncia automatica va bene.
PAROLE_NOTE_BASE = ["OBS", "Notion", "YouTube", "Discord", "Twitch", "streaming", "streamer", "live",
                    "just chatting", "Battle.net", "CurseForge", "Steam", "gaming", "email", "desk", "addon",
                    "raid", "World of Warcraft", "Warcraft", "standby", "reel", "feedback", "Claude", "link"]
LETTERE = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [
    "a", "bi", "ci", "di", "e", "effe", "gi", "acca", "i", "i lunga", "cappa", "elle", "emme", "enne", "o",
    "pi", "cu", "erre", "esse", "ti", "u", "vu", "doppia vu", "ics", "ipsilon", "zeta"]))
# Fonemi inglesi (espeak en-us) → lettere italiane. Si prova prima il simbolo più lungo.
VOCALI = {"ɚ": "er", "ɝ": "er", "ɜː": "er", "ɜ": "e", "oʊ": "o", "iː": "i", "ɪə": "ia", "eə": "ea", "ʊə": "ua",
          "eɪ": "ei", "aɪ": "ai", "ɔɪ": "oi", "aʊ": "au", "əʊ": "o", "ɑː": "a", "ɔː": "o", "uː": "u", "i": "i",
          "ɪ": "i", "e": "e", "ɛ": "e", "a": "a", "æ": "a", "ʌ": "a", "ɒ": "o", "ʊ": "u", "ə": "e", "ɐ": "a",
          "o": "o", "u": "u", "ɔ": "o"}
CONSONANTI = {"tʃ": "C", "dʒ": "G", "ʃ": "S", "ʒ": "G", "θ": "t", "ð": "d", "ŋ": "ng", "ɹ": "r", "r": "r",
              "j": "i", "w": "u", "k": "k", "ɡ": "g", "g": "g", "p": "p", "b": "b", "t": "t", "d": "d", "f": "f",
              "v": "v", "s": "s", "z": "s", "h": "h", "m": "m", "n": "n", "l": "l", "ɾ": "t", "x": "k"}
ACCENTATE = dict(zip("aeiou", "àèìòù"))
SIMBOLI = sorted([*VOCALI, *CONSONANTI], key=len, reverse=True)


def visibile(testo: str) -> str:
    """Il testo da mostrare: senza i segni delle parole straniere."""
    return testo.replace("‹", "").replace("›", "")


def _lettere(fonemi: str) -> str:
    """Una parola in fonemi inglesi → come la leggerebbe un italiano."""
    pezzi, accento, i = [], False, 0
    while i < len(fonemi):
        if fonemi[i] == "ˈ":
            accento, i = True, i + 1
            continue
        s = next((s for s in SIMBOLI if fonemi.startswith(s, i)), None)
        i += len(s) if s else 1
        if not s:
            continue
        if s in VOCALI:
            v = VOCALI[s]
            if accento:
                v, accento = ACCENTATE[v[0]] + v[1:], False
            pezzi.append(("v", v))
        else:
            pezzi.append(("c", CONSONANTI[s]))
    uscita = ""
    for j, (_, t) in enumerate(pezzi):
        dopo = pezzi[j + 1] if j + 1 < len(pezzi) else None
        dolce = bool(dopo) and dopo[1][0] in "eièì"
        if t == "k":
            t = "ch" if dolce else "c" if dopo and dopo[1][0] in "aouàòùlr" else "k"
        elif t == "g":
            t = "gh" if dolce else "g"
        elif t in "CGS":
            base = {"C": "c", "G": "g", "S": "sc"}[t]
            if not dopo:  # in fondo: Twitch → tuìcc
                t = {"C": "cc", "G": "g", "S": "sc"}[t]
            else:
                t = base if dolce or dopo[0] == "c" else base + "i"
        uscita += t
    return uscita


@functools.lru_cache(maxsize=512)
def pronuncia_automatica(parola: str) -> str:
    if re.fullmatch(r"[A-Z]{2,5}", parola):  # sigla: si compita all'italiana (OBS → obiesse)
        return "".join(LETTERE[c] for c in parola)
    import phonemizer
    from kokoro_onnx.tokenizer import Tokenizer

    Tokenizer()  # indica a phonemizer dove trovare espeak
    fonemi = phonemizer.phonemize(parola, "en-us", with_stress=True, preserve_punctuation=False)
    return " ".join(_lettere(p) for p in fonemi.split()) or parola


FILE_PRONUNCE = "pronuncia.json"  # ciò che Pietro ha confermato o corretto


def _stato() -> dict:
    return config.leggi_stato(FILE_PRONUNCE)


def correzioni() -> dict[str, str]:
    """Parola → grafia scelta da Pietro (config.toml e quelle insegnate a voce)."""
    return {k.lower(): v for k, v in (_impostazioni()["grafie"] | _stato().get("grafie", {})).items()}


def confermate() -> set[str]:
    stato = _stato()
    return {p.lower() for p in [*PAROLE_NOTE_BASE, *stato.get("confermate", []), *_impostazioni()["inglese"]]} \
        | set(correzioni())


def all_italiana() -> set[str]:
    return {p.lower() for p in _stato().get("italiano", [])}


def pronuncia(parola: str) -> str:
    if parola.lower() in all_italiana():
        return parola
    return correzioni().get(parola.lower()) or pronuncia_automatica(parola)


def per_pocket(frase: str) -> str:
    """Il testo da far leggere: parole segnate e parole già note scritte come si pronunciano."""
    frase = MARCA.sub(lambda m: pronuncia(m[1]), frase)
    note = sorted(confermate() - all_italiana(), key=len, reverse=True)
    if not note:
        return frase
    schema = r"(?<![\w‹])(" + "|".join(re.escape(p) for p in note) + r")(?![\w›])"
    # Le sigle (OBS) solo scritte in maiuscolo: "obs" minuscolo potrebbe essere altro.
    sigle = {p.lower() for p in [*PAROLE_NOTE_BASE, *_stato().get("confermate", [])] if p.isupper()}
    return re.sub(schema, lambda m: pronuncia(m[1]) if m[1].lower() not in sigle or m[1].isupper() else m[1],
                  frase, flags=re.IGNORECASE)


def parole_nuove(testo: str) -> list[str]:
    """Le parole segnate dal cervello che Pietro non ha ancora confermato."""
    note = confermate() | all_italiana()
    return list(dict.fromkeys(p for p in MARCA.findall(testo) if p.lower() not in note))


def impara(parole: list[str], inglese: bool, grafia: str | None = None) -> list[str]:
    """Pietro conferma una pronuncia (inglese, senza grafia), la corregge (con grafia)
    o vuole la parola all'italiana (inglese=False). Restituisce le parole toccate."""
    stato, parole = _stato(), [p.strip() for p in parole if p.strip()]
    if not parole:
        return []
    if grafia:
        config.salva_stato(FILE_PRONUNCE, grafie=stato.get("grafie", {}) | {parole[0]: grafia.strip()})
        return parole[:1]
    chiave = "confermate" if inglese else "italiano"
    gia = {p.lower() for p in stato.get(chiave, [])} | (confermate() if inglese else set())
    nuove = list(dict.fromkeys(p for p in parole if p.lower() not in gia))
    if nuove:
        config.salva_stato(FILE_PRONUNCE, **{chiave: stato.get(chiave, []) + nuove})
    return nuove


_kokoro = None
_pocket = None  # (modello, stato della voce)
_blocco = asyncio.Lock()


def _impostazioni() -> dict:
    return {
        "attiva": True,
        "voce": {"im_nicola": 0.7, "bm_fable": 0.3},
        "velocita": 0.92,
        "domande": True,  # intonazione interrogativa corretta
        "salita_domande": 0.35,
        "inglese": [],
        "motore": "pocket",  # pocket (Pocket TTS, più naturale) o kokoro (più leggero, senza PyTorch)
        "voce_pocket": "giovanni",
        "grafie": {},
    } | config.carica().get("voce", {})


def _pocket_installato() -> bool:
    import importlib.util

    return importlib.util.find_spec("pocket_tts") is not None


def disponibile() -> bool:
    if _impostazioni()["motore"] == "pocket":
        return _pocket_installato()
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


async def _modello_pocket():
    global _pocket
    async with _blocco:
        if _pocket is None:
            def carica():
                from pocket_tts import TTSModel

                modello = TTSModel.load_model(language="italian")
                return modello, modello.get_state_for_audio_prompt(_impostazioni()["voce_pocket"])

            inizio = time.monotonic()
            _pocket = await asyncio.to_thread(carica)
            log.info("voce (Pocket TTS) pronta in %.1f s", time.monotonic() - inizio)
    return _pocket


# --- Conferme istantanee ------------------------------------------------------------
# Mentre il cervello pensa: già sintetizzate all'avvio, così partono senza attesa.
CONFERME_ORDINI = ["Subito, signore.", "Me ne occupo, signore.", "Certamente, signore."]
CONFERME_DOMANDE = ["Un istante, signore.", "Vediamo, signore.", "Mi lasci controllare, signore."]
ORDINE = re.compile(r"^\W*(?:alfred\W+)?(?:per favore\s+|puoi\s+|potresti\s+)?(?:aggiung|segn|mand|mett|apr|cre|spost|"
                    r"cancell|elimin|scriv|annot|avvi|ferm|chiud|prepar|organizz|ricord|imposta|cambia|cerca|trova)",
                    re.IGNORECASE)
_pronte: dict[str, tuple[np.ndarray, int]] = {}


def conferma_per(richiesta: str) -> str:
    """Un ordine riceve "Subito, signore."; una domanda o un discorso "Un istante, signore."."""
    import random

    ordine = ORDINE.match(richiesta) and not richiesta.rstrip().endswith("?")
    return random.choice(CONFERME_ORDINI if ordine else CONFERME_DOMANDE)


async def prepara() -> None:
    if disponibile() and _impostazioni()["attiva"]:
        await (_modello_pocket() if _impostazioni()["motore"] == "pocket" else _modello())
        for frase in CONFERME_ORDINI + CONFERME_DOMANDE:
            _pronte[frase] = await sintetizza(frase)


# --- Testo adatto a essere detto ---------------------------------------------

UNITA = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici",
         "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette", "diciotto", "diciannove"]
DECINE = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]
MESI_RE = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"


def in_lettere(n: int) -> str:
    """Un intero in lettere, all'italiana: 21 → ventuno, 1988 → millenovecentottantotto."""
    if n < 0:
        return "meno " + in_lettere(-n)
    if n < 20:
        return UNITA[n]
    if n < 100:
        decina, unita = divmod(n, 10)
        base = DECINE[decina]
        return base[:-1] + UNITA[unita] if unita in (1, 8) else base + (UNITA[unita] if unita else "")
    if n < 1000:
        centinaia, resto = divmod(n, 100)
        cento = "cento" if centinaia == 1 else UNITA[centinaia] + "cento"
        if resto == 8 or 80 <= resto < 90:  # centotto, centottanta
            cento = cento[:-1]
        return cento + (in_lettere(resto) if resto else "")
    if n < 1_000_000:
        migliaia, resto = divmod(n, 1000)
        mille = "mille" if migliaia == 1 else in_lettere(migliaia) + "mila"
        return mille + (in_lettere(resto) if resto else "")
    milioni, resto = divmod(n, 1_000_000)
    testa = "un milione" if milioni == 1 else in_lettere(milioni) + " milioni"
    return testa + (" " + in_lettere(resto) if resto else "")


def numeri_in_lettere(testo: str) -> str:
    """Cifre → parole: alcune voci (Pocket TTS) si inceppano sulle cifre."""
    testo = re.sub(rf"\b1(?=\s+(?:{MESI_RE})\b)", "primo", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\b(\d+),(\d+)\b", lambda m: f"{in_lettere(int(m[1]))} virgola {in_lettere(int(m[2]))}", testo)
    testo = re.sub(r"\b(\d{1,3}(?:\.\d{3})+)\b", lambda m: m[1].replace(".", ""), testo)  # 1.500 → 1500
    return re.sub(r"\b\d{1,9}\b", lambda m: in_lettere(int(m[0])), testo)


def per_la_voce(testo: str) -> str:
    testo = re.sub(r"[«»\"*_#`]", "", testo)
    testo = re.sub(r"\b(\d{1,2}):00\b", r"\1", testo)
    testo = re.sub(r"\b(\d{1,2}):(\d{2})\b", r"\1 e \2", testo)
    testo = testo.replace("°C", " gradi").replace("°", " gradi").replace("%", " per cento")
    testo = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", testo)  # emoji
    testo = numeri_in_lettere(testo)
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
    if frase in _pronte:
        return _pronte[frase]
    imp = _impostazioni()
    if imp["motore"] == "pocket":
        modello, voce = await _modello_pocket()
        testo = per_pocket(frase)
        # Pocket intona da sé le domande: niente ritocco con pyworld.
        audio = await asyncio.to_thread(lambda: modello.generate_audio(voce, testo).numpy())
        return _taglia(audio.astype(np.float32)), modello.sample_rate
    kokoro = await _modello()

    def lavora():
        voce = sum(p * kokoro.get_voice_style(v) for v, p in imp["voce"].items())
        inglesi = sorted(confermate() | {p.lower() for p in MARCA.findall(frase)})
        f = fonemi(visibile(frase), inglesi, kokoro.tokenizer.vocab)
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

    @property
    def zitto(self) -> bool:
        return self._zitto

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

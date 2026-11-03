"""Il computer di casa: scrivere dove c'è il cursore, aprire app e cartelle,
volume, musica e video. Tutto in locale, senza modello.

Servono wtype (scrive in qualunque finestra su Wayland), playerctl (musica e
video, via MPRIS) e wpctl (volume, PipeWire).
"""

import configparser
import difflib
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

CASA = Path.home()


def _lancia(comando: list[str]) -> None:
    subprocess.Popen(comando, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def _esegui(comando: list[str]) -> str:
    return subprocess.run(comando, capture_output=True, text=True, timeout=5).stdout.strip()


def notifica(titolo: str, testo: str, durata_ms: int = 2500) -> None:
    if shutil.which("notify-send"):
        _lancia(["notify-send", "-a", "Alfred", "-t", str(durata_ms), titolo, testo])


# --- Dettatura ----------------------------------------------------------------------

def scrivi(testo: str) -> bool:
    """Scrive il testo nella finestra attiva, come da tastiera. False se manca wtype."""
    if not shutil.which("wtype"):
        return False
    subprocess.run(["wtype", "--", testo], timeout=60, check=False)
    return True


# --- App e cartelle -----------------------------------------------------------------

def _cartelle_app() -> list[Path]:
    dati = [os.environ.get("XDG_DATA_HOME", str(CASA / ".local/share"))]
    dati += os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
    dati += [str(CASA / ".local/share/flatpak/exports/share"), "/var/lib/flatpak/exports/share"]
    return [Path(d) / "applications" for d in dict.fromkeys(dati)]


@lru_cache(maxsize=1)
def app_installate() -> dict[str, str]:
    """{nome mostrato, in minuscolo: voce di menu (.desktop)} delle app visibili nel menu."""
    trovate = {}
    for cartella in _cartelle_app():
        for file in sorted(cartella.glob("*.desktop")) if cartella.is_dir() else []:
            voce = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                voce.read(file, encoding="utf-8")
                e = voce["Desktop Entry"]
            except (configparser.Error, KeyError, UnicodeDecodeError):
                continue
            if e.get("NoDisplay") == "true" or e.get("Hidden") == "true" or e.get("Type") != "Application":
                continue
            for chiave in ("Name[it]", "Name"):
                if nome := e.get(chiave):
                    trovate.setdefault(nome.lower(), file.name)
            # Anche il nome tecnico: org.gnome.Nautilus.desktop → "nautilus".
            trovate.setdefault(file.name.removesuffix(".desktop").split(".")[-1].lower(), file.name)
    return trovate


NOMI_CARTELLE = {  # come si chiamano a voce → nome XDG
    "documenti": "DOCUMENTS", "scaricati": "DOWNLOAD", "download": "DOWNLOAD", "immagini": "PICTURES",
    "foto": "PICTURES", "video": "VIDEOS", "musica": "MUSIC", "scrivania": "DESKTOP",
}


def _cartella(nome: str) -> Path | None:
    nome = re.sub(r"^(?:la\s+)?(?:cartella\s+)?(?:dei\s+|delle\s+|di\s+|del\s+|della\s+)?", "", nome.strip().lower())
    if nome in ("home", "casa", "personale", "cartella personale"):
        return CASA
    if nome in NOMI_CARTELLE and shutil.which("xdg-user-dir"):
        return Path(_esegui(["xdg-user-dir", NOMI_CARTELLE[nome]]))
    sotto = {p.name.lower(): p for p in CASA.iterdir() if p.is_dir() and not p.name.startswith(".")}
    if nome in sotto:
        return sotto[nome]
    percorso = Path(nome).expanduser()
    return percorso if percorso.is_absolute() and percorso.is_dir() else None


def trova(cosa: str) -> tuple[str, str, str] | None:
    """("link"|"cartella"|"app", obiettivo, nome da dire) o None se non si trova."""
    cosa = cosa.strip().strip(".")
    if re.match(r"^https?://\S+$", cosa):
        return "link", cosa, cosa
    pulito = re.sub(r"^(?:l[ao]?\s+|il\s+|i\s+|gli\s+|le\s+|l')", "", cosa.lower()).strip()
    if pulito.startswith("cartella") or pulito in NOMI_CARTELLE or pulito in ("home", "cartella personale"):
        if c := _cartella(pulito):
            return "cartella", str(c), c.name or "home"
    app = app_installate()
    nome = pulito if pulito in app else next((n for n in app if n.startswith(pulito + " ")), None)
    nome = nome or next(iter(difflib.get_close_matches(pulito, app, n=1, cutoff=0.8)), None)
    if nome:
        return "app", app[nome], nome
    if c := _cartella(pulito):
        return "cartella", str(c), c.name
    return None


def apri(tipo: str, obiettivo: str) -> None:
    if tipo == "app":
        _lancia([shutil.which("gtk-launch") or "gtk-launch", obiettivo.removesuffix(".desktop")])
    else:
        _lancia(["xdg-open", obiettivo])


# --- Volume e riproduzione ------------------------------------------------------------

USCITA = "@DEFAULT_AUDIO_SINK@"


def livello_volume() -> tuple[int, bool]:
    """(volume in percento, muto)."""
    stato = _esegui(["wpctl", "get-volume", USCITA])  # "Volume: 0.45 [MUTED]"
    m = re.search(r"([\d.]+)", stato)
    return (round(float(m[1]) * 100) if m else 0), "MUTED" in stato


def volume(azione: str, livello: int | None = None) -> tuple[int, bool]:
    """azione: alza | abbassa | imposta | muto | audio. Restituisce lo stato finale."""
    passo = f"{livello or 10}%"
    comandi = {
        "alza": ["set-volume", "-l", "1.0", USCITA, passo + "+"],
        "abbassa": ["set-volume", USCITA, passo + "-"],
        "imposta": ["set-volume", "-l", "1.0", USCITA, f"{max(0, min(livello or 0, 100))}%"],
        "muto": ["set-mute", USCITA, "1"],
        "audio": ["set-mute", USCITA, "0"],
    }
    _esegui(["wpctl", *comandi[azione]])
    if azione in ("alza", "abbassa", "imposta"):
        _esegui(["wpctl", "set-mute", USCITA, "0"])
    return livello_volume()


def riproduzione(azione: str) -> str | None:
    """azione: pausa | play | avanti | indietro. Il nome del lettore, o None se
    non c'è niente che suona (o manca playerctl)."""
    if not shutil.which("playerctl"):
        return None
    lettore = _esegui(["playerctl", "-l"]).splitlines()
    if not lettore:
        return None
    comando = {"pausa": "pause", "play": "play", "avanti": "next", "indietro": "previous"}[azione]
    _esegui(["playerctl", comando])
    return _esegui(["playerctl", "metadata", "--format", "{{playerName}}"]) or lettore[0]

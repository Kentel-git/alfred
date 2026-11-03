"""Attività: timer e sorveglianze ("avvisami quando finisce l'esportazione").

Tutto in locale e a costo zero: ogni pochi secondi si controlla ciò che
Pietro ha chiesto di tenere d'occhio, e quando succede Alfred lo avvisa di
sua iniziativa (a voce, o su Telegram se lo schermo è bloccato). L'elenco si
salva su disco, così sopravvive ai riavvii; l'HUD lo mostra nel riquadro
"Attività", con il conto alla rovescia dei timer.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import psutil

from alfred import config
from alfred.core import parole
from alfred.tools import obs

log = logging.getLogger("alfred.attivita")

FILE = "attivita.json"
OGNI_S = 5
CPU_A_RIPOSO = 15  # percento
CPU_PER_S = 60  # tanto a lungo sotto la soglia per dire "ha finito"
PARZIALI = ("*.part", "*.crdownload", "*.download", "*.partial")
OBS_EVENTI = {
    "diretta_inizia": ("diretta", True, "è partita la diretta"),
    "diretta_finisce": ("diretta", False, "la diretta è finita"),
    "registrazione_inizia": ("registrazione", True, "è partita la registrazione"),
    "registrazione_finisce": ("registrazione", False, "la registrazione è finita"),
}


class AttivitaNonValida(Exception):
    pass


def _processi(nome: str) -> list[psutil.Process]:
    nome = nome.lower()
    trovati = []
    for p in psutil.process_iter(["name", "cmdline"]):
        riga = " ".join(p.info["cmdline"] or []).lower()
        if nome in (p.info["name"] or "").lower() or nome in riga.split(" ", 1)[0]:
            trovati.append(p)
    return trovati


def processi_pesanti(quanti: int = 8) -> list[dict]:
    """I processi che lavorano di più adesso: servono per scegliere cosa sorvegliare."""
    processi = list(psutil.process_iter(["name"]))
    for p in processi:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(1)
    misure = []
    for p in processi:
        try:
            misure.append({"nome": p.info["name"], "cpu": round(p.cpu_percent(None))})
        except psutil.Error:
            pass
    return sorted(misure, key=lambda m: -m["cpu"])[:quanti]


def _cartella_scaricati() -> Path:
    from alfred.tools import pc

    return pc._cartella("scaricati") or Path.home() / "Downloads"


def _parziali() -> list[Path]:
    cartella = _cartella_scaricati()
    return [f for schema in PARZIALI for f in cartella.glob(schema)]


def descrizione(a: dict) -> str:
    """Riga per l'HUD e per la voce."""
    etichetta = a.get("etichetta")
    match a["tipo"]:
        case "timer":
            return etichetta or f"timer di {parole.durata(a['secondi'])}"
        case "processo":
            return etichetta or f"fine di {a['valore']}"
        case "cpu":
            return etichetta or "computer a riposo"
        case "file":
            return etichetta or f"file {Path(a['valore']).name}"
        case "download":
            return etichetta or "fine dei download"
        case "batteria":
            return etichetta or f"batteria al {a['soglia']}%"
        case "obs":
            return etichetta or OBS_EVENTI[a["valore"]][2]
    return etichetta or a["tipo"]


class Attivita:
    def __init__(self):
        self.voci: list[dict] = config.leggi_stato(FILE).get("voci", [])
        # Impostati all'avvio: chi avvisa Pietro e chi aggiorna l'HUD.
        self.avvisa: Callable[[str], Awaitable[None]] | None = None
        self.diffondi: Callable[[dict], Awaitable[None]] | None = None

    def _salva(self) -> None:
        config.salva_stato(FILE, voci=self.voci)

    def per_hud(self) -> dict:
        return {"tipo": "attivita", "voci": [
            {"id": a["id"], "tipo": a["tipo"], "testo": descrizione(a), "scadenza": a.get("scadenza")}
            for a in self.voci]}

    async def _cambiate(self) -> None:
        self._salva()
        if self.diffondi:
            await self.diffondi(self.per_hud())

    async def aggiungi(self, tipo: str, valore: str | None = None, soglia: float | None = None,
                       etichetta: str = "") -> dict:
        """Nuova attività. Controlla subito che abbia senso: meglio dirlo ora che aspettare invano."""
        a = {"id": uuid.uuid4().hex[:6], "tipo": tipo, "etichetta": (etichetta or "").strip(), "creata": time.time()}
        match tipo:
            case "timer":
                secondi = round(float(soglia or 0) * 60)
                if secondi <= 0:
                    raise AttivitaNonValida("per quanto tempo?")
                a |= {"secondi": secondi, "scadenza": time.time() + secondi}
            case "processo":
                if not valore or not _processi(valore):
                    raise AttivitaNonValida(f"non vedo nessun programma «{valore}» in esecuzione")
                a["valore"] = valore
            case "cpu":
                a["sotto_da"] = None
            case "file":
                if not valore:
                    raise AttivitaNonValida("quale file?")
                a |= {"valore": str(Path(valore).expanduser()), "dimensioni": None, "uguale_da": 0}
            case "download":
                if not _parziali():
                    raise AttivitaNonValida("in Scaricati non vedo download in corso")
            case "batteria":
                if psutil.sensors_battery() is None:
                    raise AttivitaNonValida("questo computer non ha una batteria")
                a["soglia"] = round(soglia if soglia is not None else 100)
            case "obs":
                if valore not in OBS_EVENTI:
                    raise AttivitaNonValida(f"posso sorvegliare: {', '.join(OBS_EVENTI)}")
                a["valore"] = valore
            case _:
                raise AttivitaNonValida(f"non so sorvegliare «{tipo}»")
        self.voci.append(a)
        await self._cambiate()
        return a

    async def annulla(self, id: str | None = None, tipo: str | None = None) -> int:
        """Toglie un'attività per id, tutte quelle di un tipo, o tutte."""
        prima = len(self.voci)
        self.voci = [a for a in self.voci if not ((id is None or a["id"] == id) and (tipo is None or a["tipo"] == tipo))]
        if len(self.voci) != prima:
            await self._cambiate()
        return prima - len(self.voci)

    async def _avvenuta(self, a: dict, obs_stato: dict | None) -> str | None:
        """Il testo dell'avviso se è successo ciò che si aspettava, altrimenti None."""
        adesso = time.time()
        match a["tipo"]:
            case "timer":
                if adesso >= a["scadenza"]:
                    ritardo = " (mentre ero spento)" if adesso - a["scadenza"] > 60 else ""
                    return (f"Signore, è scaduto il timer di {parole.durata(a['secondi'])}{ritardo}"
                            + (f": {a['etichetta']}." if a["etichetta"] else "."))
            case "processo":
                if not _processi(a["valore"]):
                    return f"Signore, {a['etichetta'] or a['valore']}: ha finito."
            case "cpu":
                if psutil.cpu_percent(None) < CPU_A_RIPOSO:
                    a["sotto_da"] = a["sotto_da"] or adesso
                    if adesso - a["sotto_da"] >= CPU_PER_S:
                        return f"Signore, il computer ha finito di lavorare{': ' + a['etichetta'] if a['etichetta'] else ''}."
                else:
                    a["sotto_da"] = None
            case "file":
                f = Path(a["valore"])
                dimensioni = f.stat().st_size if f.is_file() else None
                a["uguale_da"] = a["uguale_da"] + 1 if dimensioni and dimensioni == a["dimensioni"] else 0
                a["dimensioni"] = dimensioni
                if a["uguale_da"] >= 3:  # ~15 s senza crescere
                    return f"Signore, il file «{f.name}» è pronto."
            case "download":
                if not _parziali():
                    return "Signore, i download sono finiti."
            case "batteria":
                b = psutil.sensors_battery()
                if b and b.power_plugged and b.percent >= a["soglia"]:
                    return f"Signore, la batteria è al {round(b.percent)} per cento: può staccare l'alimentatore."
                if b and not b.power_plugged and b.percent <= a["soglia"] < 100:
                    return f"Signore, la batteria è scesa al {round(b.percent)} per cento."
            case "obs":
                uscita, attesa, testo = OBS_EVENTI[a["valore"]]
                if obs_stato and obs_stato.get("aperto") and obs_stato[uscita]["attiva"] == attesa:
                    return f"Signore, {testo}."
                if obs_stato and not obs_stato.get("aperto") and not attesa:
                    return f"Signore, {testo}: OBS è chiuso."
        return None

    async def ciclo(self) -> None:
        psutil.cpu_percent(None)  # la prima misura fa da riferimento
        while True:
            await asyncio.sleep(OGNI_S)
            if not self.voci:
                continue
            obs_stato = (await obs.stato(config.carica().get("obs", {}))
                         if any(a["tipo"] == "obs" for a in self.voci) else None)
            avvenute = []
            for a in list(self.voci):
                try:
                    testo = await self._avvenuta(a, obs_stato)
                except Exception:
                    log.exception("sorveglianza %s non controllabile", a["tipo"])
                    continue
                if testo:
                    avvenute.append((a, testo))
            if not avvenute:
                continue
            ids = {a["id"] for a, _ in avvenute}
            self.voci = [a for a in self.voci if a["id"] not in ids]
            await self._cambiate()
            for _, testo in avvenute:
                log.info("attività: %s", testo)
                if self.avvisa:
                    await self.avvisa(testo)


_istanza: Attivita | None = None


def istanza() -> Attivita:
    global _istanza
    if _istanza is None:
        _istanza = Attivita()
    return _istanza

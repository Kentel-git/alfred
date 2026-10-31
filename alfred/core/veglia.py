"""La veglia: con l'alimentatore collegato il computer non va in standby da solo.

Schermo bloccato e spento vanno benissimo; sotto però tutto resta attivo
(servizio, Telegram, dirette). Lo standby resta possibile a mano, o
chiedendolo ad Alfred. A batteria non cambia nulla.

Due modi, a seconda del desktop:
- DMS (DankMaterialShell): distingue già alimentatore e batteria; Alfred
  imposta a "mai" lo standby automatico con alimentatore e ricorda il valore
  originale per rimetterlo. Lo standby manuale continua a funzionare.
- altrove: un inibitore di logind ("sleep", modalità block) attivo solo con
  l'alimentatore collegato. Nota: blocca anche lo standby manuale, che va
  chiesto ad Alfred.
"""

import asyncio
import json
import logging
import shutil
import subprocess
from pathlib import Path

from alfred.config import CARTELLA_STATO

FILE_STATO = CARTELLA_STATO / "veglia.json"
CHIAVE_DMS = "acSuspendTimeout"
log = logging.getLogger("alfred.veglia")


def con_alimentatore() -> bool:
    for alimentazione in Path("/sys/class/power_supply").glob("*"):
        try:
            if (alimentazione / "type").read_text().strip() == "Mains":
                return (alimentazione / "online").read_text().strip() == "1"
        except OSError:
            continue
    return True  # fisso senza batteria: sempre "con alimentatore"


def _stato() -> dict:
    try:
        return json.loads(FILE_STATO.read_text())
    except (OSError, ValueError):
        return {}


def _salva(**valori) -> None:
    CARTELLA_STATO.mkdir(parents=True, exist_ok=True)
    FILE_STATO.write_text(json.dumps(_stato() | valori))


def _dms(*argomenti: str) -> str | None:
    if not shutil.which("dms"):
        return None
    try:
        uscita = subprocess.run(["dms", "ipc", "call", "settings", *argomenti],
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return uscita.stdout.strip() if uscita.returncode == 0 else None


class Veglia:
    def __init__(self):
        # Scelta di Pietro: la veglia è attiva salvo che chieda altrimenti.
        self.voluta = _stato().get("voluta", True)
        self._inibitore: subprocess.Popen | None = None
        self._usa_dms = _dms("get", CHIAVE_DMS) is not None

    def stato(self) -> dict:
        return {
            "tipo": "veglia",
            "voluta": self.voluta,
            "alimentatore": con_alimentatore(),
            "attiva": self.voluta and con_alimentatore(),
            "modo": "DMS" if self._usa_dms else "logind",
        }

    # --- DMS -----------------------------------------------------------------
    def _applica_dms(self, attiva: bool) -> None:
        attuale = _dms("get", CHIAVE_DMS)
        if attuale is None:
            return
        if attiva and attuale != "0":
            _salva(originale_dms=attuale)
            _dms("set", CHIAVE_DMS, "0")
            log.info("standby automatico con alimentatore disattivato (era %s s)", attuale)
        elif not attiva and attuale == "0":
            originale = _stato().get("originale_dms")
            if originale:
                _dms("set", CHIAVE_DMS, originale)
                log.info("standby automatico con alimentatore ripristinato a %s s", originale)

    # --- logind ----------------------------------------------------------------
    def _applica_logind(self, attiva: bool) -> None:
        attiva = attiva and con_alimentatore()
        vivo = self._inibitore is not None and self._inibitore.poll() is None
        if attiva and not vivo:
            self._inibitore = subprocess.Popen([
                "systemd-inhibit", "--what=sleep", "--mode=block", "--who=Alfred",
                "--why=Alfred resta sveglio con l'alimentatore collegato", "sleep", "infinity",
            ])
        elif not attiva and vivo:
            self._inibitore.terminate()
            self._inibitore = None

    def applica(self) -> None:
        if self._usa_dms:
            self._applica_dms(self.voluta)
        else:
            self._applica_logind(self.voluta)

    def imposta(self, voluta: bool) -> None:
        self.voluta = voluta
        _salva(voluta=voluta)
        self.applica()

    def chiudi(self) -> None:
        """Alfred si ferma: tutto torna come prima."""
        if self._usa_dms:
            self._applica_dms(False)
        else:
            self._applica_logind(False)

    async def sorveglia(self, invia) -> None:
        """Segue i cambi di alimentazione (serve al modo logind e all'HUD)."""
        ultimo = None
        while True:
            self.applica()
            stato = self.stato()
            if stato != ultimo:
                await invia(stato)
                ultimo = stato
            await asyncio.sleep(10)

    async def sospendi_ora(self) -> None:
        """Standby chiesto da Pietro: niente inibitori di mezzo. Al risveglio
        la sorveglianza rimette la veglia da sola."""
        await asyncio.sleep(2)  # il tempo di far arrivare la risposta (HUD, Telegram)
        if not self._usa_dms:
            self._applica_logind(False)
        subprocess.Popen(["systemctl", "suspend"])


_istanza: Veglia | None = None


def istanza() -> Veglia:
    global _istanza
    if _istanza is None:
        _istanza = Veglia()
    return _istanza

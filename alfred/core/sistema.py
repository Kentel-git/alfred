"""Dati di sistema per l'HUD: CPU, GPU, memoria, disco, batteria, rete."""

import time
from pathlib import Path

import psutil

# La prima lettura di cpu_percent restituisce sempre 0: la facciamo subito.
psutil.cpu_percent(interval=None)
_rete_precedente = (time.monotonic(), psutil.net_io_counters())


def _temperatura_cpu() -> float | None:
    sensori = psutil.sensors_temperatures()
    for nome in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
        letture = sensori.get(nome)
        if letture:
            # "Package id 0" (Intel) o "Tctl" (AMD) se ci sono, altrimenti la prima.
            for lettura in letture:
                if lettura.label.startswith(("Package", "Tctl", "Tdie")):
                    return round(lettura.current, 1)
            return round(letture[0].current, 1)
    return None


def _frequenza_gpu() -> int | None:
    """Frequenza attuale della GPU Intel in MHz (driver i915 o xe)."""
    for scheda in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        for percorso in (
            scheda / "gt_act_freq_mhz",
            scheda / "device/tile0/gt0/freq0/act_freq",
        ):
            try:
                return int(percorso.read_text().strip())
            except (OSError, ValueError):
                continue
    return None


def leggi() -> dict:
    global _rete_precedente

    adesso, rete = time.monotonic(), psutil.net_io_counters()
    prima, rete_prima = _rete_precedente
    _rete_precedente = (adesso, rete)
    secondi = max(adesso - prima, 0.001)

    memoria = psutil.virtual_memory()
    disco = psutil.disk_usage("/")
    batteria = psutil.sensors_battery()
    frequenza = psutil.cpu_freq()

    return {
        "cpu": {
            "uso": psutil.cpu_percent(interval=None),
            "frequenza_mhz": round(frequenza.current) if frequenza else None,
            "temperatura": _temperatura_cpu(),
        },
        "gpu": {"frequenza_mhz": _frequenza_gpu()},
        "memoria": {
            "uso": memoria.percent,
            "usata_gb": round(memoria.used / 1024**3, 1),
            "totale_gb": round(memoria.total / 1024**3, 1),
        },
        "disco": {
            "uso": disco.percent,
            "libero_gb": round(disco.free / 1024**3),
        },
        "batteria": (
            {"livello": round(batteria.percent), "in_carica": batteria.power_plugged}
            if batteria
            else None
        ),
        "rete": {
            "giu_kbs": round((rete.bytes_recv - rete_prima.bytes_recv) / 1024 / secondi),
            "su_kbs": round((rete.bytes_sent - rete_prima.bytes_sent) / 1024 / secondi),
        },
        "acceso_da_s": round(time.time() - psutil.boot_time()),
    }

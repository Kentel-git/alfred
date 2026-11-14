"""Compiti in sottofondo che nessuno aspetta.

Il ciclo degli eventi tiene solo riferimenti deboli ai compiti: uno lanciato
e dimenticato può essere raccolto prima di finire, senza errori. Qui restano
in un set finché girano, e un'eccezione finisce nel log invece di sparire.
"""

import asyncio
import logging
from collections.abc import Coroutine

log = logging.getLogger("alfred.compiti")

_vivi: set[asyncio.Task] = set()


def lancia(coro: Coroutine) -> asyncio.Task:
    compito = asyncio.create_task(coro)
    _vivi.add(compito)
    compito.add_done_callback(_finito)
    return compito


def _finito(compito: asyncio.Task) -> None:
    _vivi.discard(compito)
    if not compito.cancelled() and (errore := compito.exception()):
        log.error("compito %s fallito", compito.get_coro().__qualname__, exc_info=errore)

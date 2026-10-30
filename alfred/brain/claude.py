"""Adattatore per Claude Code (`claude -p`).

Tiene acceso un solo processo `claude -p` in modalità stream-json: riceve i
messaggi uno dopo l'altro senza ripartire ogni volta, quindi risponde in fretta
e ricorda la conversazione. L'id di sessione viene salvato, così dopo un
riavvio la conversazione riprende con --resume.

Claude non ha strumenti propri (--tools ""): può usare solo quelli di Alfred,
esposti dal server MCP `alfred mcp`.
"""

import asyncio
import json
import logging
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from alfred.brain import personalita

log = logging.getLogger("alfred.cervello")

CARTELLA_DATI = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "alfred"
CARTELLA_LAVORO = CARTELLA_DATI / "cervello"
COMANDO_ALFRED = Path(__file__).resolve().parents[2] / "bin" / "alfred"


class CervelloClaude:
    def __init__(self, modello: str, appellativo: str, sessione: str | None = None):
        self.modello = modello
        self.appellativo = appellativo
        self.sessione = sessione
        self._processo: asyncio.subprocess.Process | None = None
        self._turno = asyncio.Lock()

    def _comando(self) -> list[str]:
        server_mcp = {"mcpServers": {"alfred": {"command": str(COMANDO_ALFRED), "args": ["mcp"]}}}
        comando = [
            shutil.which("claude") or "claude", "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--model", self.modello,
            "--system-prompt", personalita(self.appellativo),
            # La personalità si può ritoccare dal vivo: non va congelata nella sessione.
            "--system-prompt-snapshot", "off",
            "--tools", "",
            "--mcp-config", json.dumps(server_mcp),
            "--strict-mcp-config",
            "--allowedTools", "mcp__alfred",
            # Niente hook, plugin o impostazioni personali di Claude Code.
            "--setting-sources", "project",
        ]
        if self.sessione:
            comando += ["--resume", self.sessione]
        return comando

    async def _avvia(self) -> None:
        CARTELLA_LAVORO.mkdir(parents=True, exist_ok=True)
        self._processo = await asyncio.create_subprocess_exec(
            *self._comando(),
            cwd=CARTELLA_LAVORO,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024,
        )
        asyncio.create_task(self._leggi_errori(self._processo))
        log.info("cervello avviato (%s, sessione %s)", self.modello, self.sessione or "nuova")

    @staticmethod
    async def _leggi_errori(processo: asyncio.subprocess.Process) -> None:
        async for riga in processo.stderr:
            log.warning("claude: %s", riga.decode(errors="replace").rstrip())

    def _vivo(self) -> bool:
        return self._processo is not None and self._processo.returncode is None

    async def ferma(self) -> None:
        if self._vivo():
            self._processo.stdin.close()
            try:
                await asyncio.wait_for(self._processo.wait(), 5)
            except TimeoutError:
                self._processo.kill()
        self._processo = None

    async def riavvia(self) -> None:
        """Riparte con la stessa conversazione (es. personalità modificata)."""
        async with self._turno:
            await self.ferma()

    async def nuova_conversazione(self) -> None:
        async with self._turno:
            await self.ferma()
            self.sessione = None

    async def chiedi(self, testo: str) -> AsyncIterator[dict]:
        """Manda un messaggio e restituisce gli eventi della risposta:
        {"tipo": "sessione", "id"}, {"tipo": "parziale", "testo"},
        {"tipo": "strumento", "nome"}, {"tipo": "fine", "testo", "errore"}.
        """
        async with self._turno:
            for tentativo in range(2):
                if not self._vivo():
                    await self._avvia()
                messaggio = {"type": "user", "message": {"role": "user", "content": testo}}
                try:
                    self._processo.stdin.write((json.dumps(messaggio) + "\n").encode())
                    await self._processo.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    self._processo = None
                    continue

                finito = False
                async for evento in self._eventi():
                    yield evento
                    if evento["tipo"] == "fine":
                        finito = True
                if finito:
                    return

                # Il processo è morto senza rispondere. Se stava riprendendo una
                # sessione che non esiste più, si riparte da una conversazione nuova.
                await self.ferma()
                if tentativo == 0 and self.sessione:
                    log.warning("ripresa della sessione %s fallita: ne apro una nuova", self.sessione)
                    self.sessione = None
                    yield {"tipo": "sessione", "id": None}
                    continue
                break
            yield {"tipo": "fine", "testo": "", "errore": "Il cervello non risponde."}

    async def _eventi(self) -> AsyncIterator[dict]:
        async for riga in self._processo.stdout:
            try:
                e = json.loads(riga)
            except json.JSONDecodeError:
                continue
            tipo = e.get("type")
            if tipo == "system" and e.get("subtype") == "init":
                if e.get("session_id") != self.sessione:
                    self.sessione = e.get("session_id")
                    yield {"tipo": "sessione", "id": self.sessione}
            elif tipo == "stream_event":
                ev = e.get("event", {})
                if ev.get("type") == "content_block_delta" and ev["delta"].get("type") == "text_delta":
                    yield {"tipo": "parziale", "testo": ev["delta"]["text"]}
                elif ev.get("type") == "content_block_start" and ev["content_block"].get("type") == "tool_use":
                    nome = ev["content_block"].get("name", "").removeprefix("mcp__alfred__")
                    yield {"tipo": "strumento", "nome": nome}
                elif ev.get("type") == "message_start":
                    # Nuovo messaggio dopo l'uso di uno strumento: separa i testi.
                    yield {"tipo": "parziale", "testo": ""}
            elif tipo == "result":
                errore = e.get("result") if e.get("is_error") else None
                yield {"tipo": "fine", "testo": e.get("result") or "", "errore": errore}
                return

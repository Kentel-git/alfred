"""Il cervello di Alfred: adattatori verso i modelli linguistici."""

import re
from pathlib import Path

from alfred import config

FILE_PERSONALITA = Path(__file__).with_name("personalita.md")
FILE_SCHEDA = config.CARTELLA_CONFIG / "su-di-me.md"


def personalita(appellativo: str) -> str:
    """Prompt di sistema: personalità più la scheda personale, se c'è."""
    testo = FILE_PERSONALITA.read_text().replace("{appellativo}", appellativo)
    if FILE_SCHEDA.exists():
        scheda = re.sub(r"<!--.*?-->", "", FILE_SCHEDA.read_text(), flags=re.S).strip()
        if scheda:
            testo += (
                f"\n\n## Ciò che sai di {appellativo}\n"
                f"Questa è la scheda che {appellativo} ha scritto per te.\n\n{scheda}\n"
            )
    return testo

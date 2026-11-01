"""Il cervello di Alfred: adattatori verso i modelli linguistici."""

import re
from datetime import date
from pathlib import Path

from alfred import config

FILE_PERSONALITA = Path(__file__).with_name("personalita.md")
FILE_SCHEDA = config.CARTELLA_CONFIG / "su-di-me.md"
# Ciò che Alfred impara da sé: fatti ("ricordati che…") e diario dei giorni.
# Stanno accanto alla scheda: Pietro può leggerli e correggerli.
FILE_MEMORIA = config.CARTELLA_CONFIG / "memoria.md"
FILE_DIARIO = config.CARTELLA_CONFIG / "diario.md"
GIORNI_DI_DIARIO = 7  # quanti giorni del diario entrano nel prompt


def ricorda(fatto: str) -> None:
    nuovo = not FILE_MEMORIA.exists()
    with FILE_MEMORIA.open("a") as f:
        if nuovo:
            f.write("# Ciò che Alfred ha imparato\n\n")
        f.write(f"- {date.today().isoformat()}: {fatto.strip()}\n")


def scrivi_diario(giorno: date, riassunto: str) -> None:
    with FILE_DIARIO.open("a") as f:
        f.write(f"\n## {giorno.isoformat()}\n{riassunto.strip()}\n")


def _ultimi_giorni(diario: str, n: int) -> str:
    giorni = re.split(r"\n(?=## )", diario.strip())
    return "\n".join(g for g in giorni[-n:] if g.startswith("## "))


def personalita(appellativo: str) -> str:
    """Prompt di sistema: personalità, scheda personale, memoria e diario recente."""
    testo = FILE_PERSONALITA.read_text().replace("{appellativo}", appellativo)
    if FILE_SCHEDA.exists():
        scheda = re.sub(r"<!--.*?-->", "", FILE_SCHEDA.read_text(), flags=re.S).strip()
        if scheda:
            testo += (
                f"\n\n## Ciò che sai di {appellativo}\n"
                f"Questa è la scheda che {appellativo} ha scritto per te.\n\n{scheda}\n"
            )
    if FILE_MEMORIA.exists():
        testo += f"\n\n## Ciò che hai imparato da solo\n{FILE_MEMORIA.read_text().strip()}\n"
    if FILE_DIARIO.exists() and (diario := _ultimi_giorni(FILE_DIARIO.read_text(), GIORNI_DI_DIARIO)):
        testo += f"\n\n## Il tuo diario dei giorni scorsi\n{diario}\n"
    return testo

"""Date, orari ed eventi detti come li direbbe Alfred."""

from datetime import date, datetime

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def giorno(d: date) -> str:
    differenza = (d - date.today()).days
    if differenza == 0:
        return "oggi"
    if differenza == 1:
        return "domani"
    if differenza == 2:
        return "dopodomani"
    if differenza == -1:
        return "ieri"
    testo = f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"
    return testo if d.year == date.today().year else f"{testo} {d.year}"


def giorno_esteso(d: date) -> str:
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def orario(istante: datetime) -> str:
    return f"{istante.hour}:{istante.minute:02d}" if istante.minute else str(istante.hour)


def ora(istante: datetime) -> str:
    articolo = "all'" if istante.hour in (1, 8, 11) else "alle "
    return articolo + orario(istante)


def tra(minuti: int) -> str:
    nomi = {15: "un quarto d'ora", 30: "mezz'ora", 45: "tre quarti d'ora", 60: "un'ora"}
    return "tra un momento" if minuti <= 1 else f"tra {nomi.get(minuti, f'{minuti} minuti')}"


def quando(evento: dict, con_giorno: bool = True) -> str:
    if evento["tutto_il_giorno"]:
        d = date.fromisoformat(evento["inizio"][:10])
        return f"{giorno(d)}, tutto il giorno" if con_giorno else "tutto il giorno"
    inizio = datetime.fromisoformat(evento["inizio"]).astimezone()
    return f"{giorno(inizio.date())} {ora(inizio)}" if con_giorno else ora(inizio)


def elenco_eventi(eventi: list[dict], etichetta_giorno: str) -> str:
    if not eventi:
        return f"{etichetta_giorno.capitalize()} non ha impegni, signore. Una rarità da custodire."
    voci = [f"{quando(e, con_giorno=False)} «{e['titolo']}»" for e in eventi]
    corpo = voci[0] if len(voci) == 1 else ", ".join(voci[:-1]) + " e " + voci[-1]
    return f"{etichetta_giorno.capitalize()}, signore: {corpo}."

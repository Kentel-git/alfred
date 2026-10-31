"""Comandi diretti: frasi brevi e comuni riconosciute in locale, senza modello.

Costano zero token e sono istantanei. Si riconoscono solo frasi corte e
inequivocabili: tutto ciò che è più lungo o sfumato ("avvia la diretta tra
dieci minuti") passa al cervello, che può comunque usare le stesse azioni.
"""

import re
import unicodedata

MAX_PAROLE = 9

# Cortesie da togliere prima di riconoscere il comando.
CORTESIE_INIZIO = re.compile(
    r"^(?:(?:alfred|ehi|ok|allora|per favore|per piacere|puoi|potresti|mi|ti prego|dai)\s+)+"
)
CORTESIE_FINE = re.compile(r"(?:\s+(?:alfred|per favore|per piacere|grazie|subito|ora|adesso))+$")

CONFERMA = re.compile(r"^(?:si|confermo|conferma|procedi|vai pure|vai|certo|certamente|esatto|si procedi|si grazie|si vai)$")
ANNULLA = re.compile(r"^(?:no|annulla|lascia stare|lascia perdere|non ora|meglio di no|aspetta)(?:\s.*)?$")

AVVIA = r"(?:avvia|inizia|comincia|fai partire|parti con|lancia|apri|attiva|accendi)"
FERMA = r"(?:ferma|termina|chiudi|concludi|interrompi|stoppa|stop|spegni|fine)"
DIRETTA = r"(?:la\s+)?(?:diretta|live|trasmissione|stream)"
REGISTRAZIONE = r"(?:la\s+)?registrazione"

COMANDI: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"^(?:{AVVIA}\s+)?(?:la\s+)?modalita\s+gioco$|^voglio giocare$|^si gioca$"
                rf"|^{AVVIA}\s+(?:il\s+)?(?:gioco|battle\s*net|wow|world of warcraft)$"), "modalita_gioco"),
    (re.compile(rf"^{AVVIA}\s+obs$"), "apri_obs"),
    (re.compile(r"^(?:metti|manda)\s+(?:il\s+)?(?:computer|pc|portatile)?\s*in\s+standby$|^sospendi(?:\s+il\s+(?:computer|pc|portatile))?$"
                r"|^(?:vai|andiamo)\s+in\s+standby$"), "sospendi_computer"),
    (re.compile(r"^(?:puoi\s+)?(?:consenti|permetti|lascia(?:\s+andare)?)\s+(?:lo\s+|in\s+)?standby$|^(?:il computer )?puo andare in standby$"), "consenti_standby"),
    (re.compile(r"^(?:resta|rimani|stai)\s+sveglio$|^tieni\s+sveglio\s+(?:il\s+)?(?:computer|pc|portatile)$|^niente\s+standby$"), "impedisci_standby"),
    (re.compile(rf"^{AVVIA}\s+{DIRETTA}$|^(?:andiamo|vai|mandami|mettimi)\s+in\s+(?:onda|diretta|live)$|^in onda$"), "avvia_diretta"),
    (re.compile(rf"^{FERMA}\s+{DIRETTA}$|^(?:chiudiamo|fuori onda)$"), "ferma_diretta"),
    (re.compile(rf"^{AVVIA}\s+{REGISTRAZIONE}$|^registra$|^(?:inizia|comincia)\s+a\s+registrare$"), "avvia_registrazione"),
    (re.compile(rf"^{FERMA}\s+{REGISTRAZIONE}$|^smetti\s+di\s+registrare$"), "ferma_registrazione"),
    (re.compile(rf"^(?:metti\s+in\s+pausa|pausa)\s+{REGISTRAZIONE}$"), "pausa_registrazione"),
    (re.compile(rf"^riprendi\s+{REGISTRAZIONE}$|^riprendi\s+a\s+registrare$"), "riprendi_registrazione"),
]
GIORNO = r"(?P<giorno>oggi|domani|dopodomani|lunedi|martedi|mercoledi|giovedi|venerdi|sabato|domenica)"
AGENDA = [re.compile(schema) for schema in (
    rf"^(?:cosa|che cosa|che impegni|quali impegni)\s+ho\s+(?:in\s+agenda\s+)?(?:per\s+)?{GIORNO}$",
    rf"^(?:l\s+)?(?:agenda|impegni)\s+(?:di|per)\s+{GIORNO}$",
    rf"^{GIORNO}\s+(?:cosa|che)\s+(?:ho|impegni ho)$",
    r"^(?:cosa ho in agenda|che impegni ho|agenda|impegni)$",
)]
GIORNI_ACCENTATI = {"lunedi": "lunedì", "martedi": "martedì", "mercoledi": "mercoledì",
                    "giovedi": "giovedì", "venerdi": "venerdì"}
SCENA = re.compile(
    r"^(?:passa\s+(?:alla|a)|vai\s+(?:alla|a)|metti\s+(?:la|il)?|cambia\s+scena\s+(?:in|a)?|scena)\s*(?:scena\s+)?(?P<scena>.+)$"
)


# Il testo del messaggio va preso così com'è (non normalizzato).
TELEGRAM = re.compile(
    r"^\s*(?:alfred[\s,]+)?(?:mandami|inviami|scrivimi|mandami un messaggio|scrivimi un messaggio)"
    r"\s+su\s+telegram\s*[:,]?\s*(?P<testo>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def normalizza(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.lower())
    testo = "".join(c for c in testo if not unicodedata.combining(c))  # sì → si, modalità → modalita
    testo = re.sub(r"[^\w\s]", " ", testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    testo = CORTESIE_INIZIO.sub("", testo)
    return CORTESIE_FINE.sub("", testo).strip()


def riconosci(testo: str) -> tuple[str, dict] | None:
    """("conferma"|"annulla"|nome_azione, parametri) oppure None (→ cervello)."""
    if m := TELEGRAM.match(testo):
        return "invia_telegram", {"testo": m["testo"].strip()}
    t = normalizza(testo)
    if not t or len(t.split()) > MAX_PAROLE:
        return None
    if CONFERMA.match(t):
        return "conferma", {}
    if ANNULLA.match(t):
        return "annulla", {}
    for schema, azione in COMANDI:
        if schema.match(t):
            return azione, {}
    for schema in AGENDA:
        if m := schema.match(t):
            giorno = m.groupdict().get("giorno") or "oggi"
            return "leggi_agenda", {"giorno": GIORNI_ACCENTATI.get(giorno, giorno)}
    if m := SCENA.match(t):
        return "cambia_scena", {"scena": m["scena"]}
    return None

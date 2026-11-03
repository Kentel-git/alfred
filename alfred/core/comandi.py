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
    (re.compile(r"^(?:basta|basta cosi|silenzio|zitto|taci|stop|fermati|ok basta)$"), "zittisci"),
    (re.compile(r"^(?:smetti|smettila)\s+di\s+ascoltar(?:e|mi)$|^non\s+ascoltar(?:e|mi)(?:\s+piu)?$|^spegni\s+(?:la\s+)?sveglia$"), "sveglia_spenta"),
    (re.compile(r"^(?:torna\s+ad|ricomincia\s+ad?)\s+ascoltar(?:e|mi)$|^ascoltami\s+(?:di\s+nuovo|ancora)$|^(?:accendi|riaccendi)\s+(?:la\s+)?sveglia$"), "sveglia_accesa"),
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


# Link della chat della diretta, incollato: "chat: https://youtube.com/live/…"
CHAT = re.compile(r"^\s*(?:alfred[\s,]+)?(?:aggiorna\s+(?:il\s+link\s+della\s+)?)?chat\s*[:,]?\s*(?P<link>https?://\S+)\s*$",
                  re.IGNORECASE)

# Il testo del messaggio va preso così com'è (non normalizzato).
TELEGRAM = re.compile(
    r"^\s*(?:alfred[\s,]+)?(?:mandami|inviami|scrivimi|mandami un messaggio|scrivimi un messaggio)"
    r"\s+su\s+telegram\s*[:,]?\s*(?P<testo>.+)$",
    re.IGNORECASE | re.DOTALL,
)


# --- Il computer ----------------------------------------------------------------------
NUMERI = {"un": 1, "uno": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6, "sette": 7,
          "otto": 8, "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "quindici": 15, "venti": 20,
          "venticinque": 25, "trenta": 30, "quaranta": 40, "quarantacinque": 45, "cinquanta": 50, "sessanta": 60}
NUMERO = r"(?:\d+|" + "|".join(NUMERI) + ")"
UNITA = {"second": 1 / 60, "minut": 1, "or": 60}
# normalizza unisce "mezz'ora", "quarto d'ora", "un'ora" (se no "ora" cadrebbe con le cortesie).
FRAZIONE = r"(?P<frazione>un\s+quarto\s+dora|mezzora|unora)"
TIMER = re.compile(
    r"^(?:(?:(?:metti|imposta|fai\s+partire|avvia)\s+)?(?:un\s+)?timer\s+(?:di\s+|da\s+|per\s+)?"
    r"|(?:avvisami|chiamami|svegliami)\s+tra\s+)"
    rf"(?:{FRAZIONE}|(?P<quanto>{NUMERO})\s*(?P<unita>secondi?|minuti?|ore|ora)?)$"
)
ANNULLA_TIMER = re.compile(r"^(?:annulla|togli|cancella|ferma|spegni|stop)\s+(?:il\s+|i\s+|tutti\s+i\s+)?timer$")
VOLUME = [
    (re.compile(r"^(?:alza|aumenta)\s+(?:il\s+)?volume$|^(?:piu|più)\s+forte$|^volume\s+su$"), "alza"),
    (re.compile(r"^(?:abbassa|diminuisci)\s+(?:il\s+)?volume$|^(?:piu|più)\s+piano$|^volume\s+giu$"), "abbassa"),
    (re.compile(r"^(?:togli\s+l\s+audio|muto|silenzia(?:\s+(?:l\s+audio|il\s+computer))?|metti\s+(?:in\s+)?muto)$"), "muto"),
    (re.compile(r"^(?:riattiva\s+l\s+audio|togli\s+il\s+muto|rimetti\s+l\s+audio)$"), "audio"),
]
VOLUME_A = re.compile(rf"^(?:(?:metti|imposta|porta)\s+(?:il\s+)?)?volume\s+(?:al?\s+|a\s+)?(?P<livello>{NUMERO})(?:\s+per\s*cento)?$")
MUSICA = r"(?:\s+(?:la\s+)?(?:musica|canzone|video|riproduzione|brano|podcast))?"
RIPRODUZIONE = [
    (re.compile(rf"^(?:pausa|metti\s+in\s+pausa|ferma|stoppa){MUSICA}$|^metti\s+in\s+pausa{MUSICA}$"), "pausa"),
    (re.compile(rf"^(?:play|riprendi|fai\s+ripartire|riparti|continua){MUSICA}$"), "play"),
    (re.compile(r"^(?:prossima|successiva|avanti|salta)(?:\s+(?:canzone|traccia|brano|video))?$|^(?:canzone|traccia|brano)\s+successiv[ao]$"), "avanti"),
    (re.compile(r"^(?:precedente|indietro|torna\s+indietro)(?:\s+(?:canzone|traccia|brano))?$|^(?:canzone|traccia|brano)\s+precedente$"), "indietro"),
]
APRI = re.compile(r"^(?:apri|avvia|lancia|aprimi|fammi\s+vedere)\s+(?P<cosa>.+)$")


def _numero(t: str) -> int:
    return int(t) if t.isdigit() else NUMERI[t]


def _comando_pc(t: str) -> tuple[str, dict] | None:
    if ANNULLA_TIMER.match(t):
        return "annulla_timer", {}
    if m := TIMER.match(t):
        if m["frazione"]:
            return "timer", {"minuti": {"mezzora": 30, "unora": 60}.get(m["frazione"], 15)}
        fattore = next((v for k, v in UNITA.items() if (m["unita"] or "minut").startswith(k)), 1)
        return "timer", {"minuti": _numero(m["quanto"]) * fattore}
    for schema, azione in VOLUME:
        if schema.match(t):
            return "volume", {"azione": azione}
    if m := VOLUME_A.match(t):
        return "volume", {"azione": "imposta", "livello": _numero(m["livello"])}
    for schema, azione in RIPRODUZIONE:
        if schema.match(t):
            return "riproduzione", {"azione": azione}
    if (m := APRI.match(t)) and len(m["cosa"].split()) <= 4:
        from alfred.tools import pc

        if pc.trova(m["cosa"]):  # solo app e cartelle che esistono; il resto al cervello
            return "apri", {"cosa": m["cosa"]}
    return None


def normalizza(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.lower())
    testo = "".join(c for c in testo if not unicodedata.combining(c))  # sì → si, modalità → modalita
    testo = re.sub(r"[^\w\s]", " ", testo)
    testo = re.sub(r"\s+", " ", testo).strip()
    testo = re.sub(r"\b(un|mezz|d) ora\b", r"\1ora", testo)
    testo = CORTESIE_INIZIO.sub("", testo)
    return CORTESIE_FINE.sub("", testo).strip()


def riconosci(testo: str) -> tuple[str, dict] | None:
    """("conferma"|"annulla"|nome_azione, parametri) oppure None (→ cervello)."""
    if m := CHAT.match(testo):
        return "aggiorna_chat", {"link": m["link"]}
    if m := TELEGRAM.match(testo):
        return "invia_telegram", {"testo": m["testo"].strip()}
    t = normalizza(testo)
    if not t or len(t.split()) > MAX_PAROLE:
        return None
    if CONFERMA.match(t):
        return "conferma", {}
    if ANNULLA_TIMER.match(t):  # prima di ANNULLA, che prenderebbe "annulla il timer"
        return "annulla_timer", {}
    if ANNULLA.match(t):
        return "annulla", {}
    for schema, azione in COMANDI:
        if schema.match(t):
            return azione, {}
    if comando := _comando_pc(t):  # prima della scena: "metti in pausa" non è una scena
        return comando
    for schema in AGENDA:
        if m := schema.match(t):
            giorno = m.groupdict().get("giorno") or "oggi"
            return "leggi_agenda", {"giorno": GIORNI_ACCENTATI.get(giorno, giorno)}
    if m := SCENA.match(t):
        return "cambia_scena", {"scena": m["scena"]}
    return None

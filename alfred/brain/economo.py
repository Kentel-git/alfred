"""L'economo: sceglie il modello per ogni messaggio e protegge le riserve.

Le riserve (limiti di utilizzo dell'abbonamento Claude) sono condivise con
tutto il resto del lavoro di Pietro: Alfred deve consumarne il meno possibile.

- Il compito decide il modello: conversazione quotidiana → modello leggero;
  riflessioni, consigli, decisioni, lato cinico → modello profondo.
  Il riconoscimento è locale (parole chiave e lunghezza): non costa token.
- Il regime decide quanto ci si può permettere:
  normale     → come sopra;
  parsimonia  → sempre il modello leggero (metà settimana consumata, o
                consumo più rapido del passare della settimana);
  austerità   → niente modello: Alfred risponde da solo, salvo "è importante".
"""

import re
import time

SETTIMANA_S = 7 * 24 * 3600

PROFONDO = re.compile(
    r"perch[eé]|cosa ne pensi|che ne pensi|secondo te|senza filtri|cinic|realist|brutal"
    r"|come stanno davvero|consigli|aiutami a|dovrei|conviene|meglio se|decider|scelt"
    r"|pianific|organizz|strategi|riflett|anima|senso della|filosof|spiegami",
    re.IGNORECASE,
)
FORZA = re.compile(r"è importante|e' importante|é importante", re.IGNORECASE)

# Dopo una risposta profonda il modello profondo resta per qualche messaggio:
# cambiare modello a ogni frase costerebbe di più (la cache va ricostruita).
MESSAGGI_DI_TRASCINAMENTO = 2

RISPOSTE_AUSTERITA = [
    "Signore, le riserve della settimana sono quasi esaurite e le sto custodendo per il "
    "suo lavoro. Per ora mi limito ai comandi essenziali. Se è davvero necessario, me lo "
    "dica: «è importante».",
]


class Economo:
    def __init__(self, config: dict):
        self.aggiorna_config(config)
        self._trascinamento = 0

    def aggiorna_config(self, config: dict) -> None:
        cervello, economia = config["cervello"], config["economia"]
        self.leggero = cervello["quotidiano"]
        self.profondo = cervello["profondo"]
        self.soglia_parsimonia = economia["parsimonia_settimana"]
        self.soglia_austerita = economia["austerita_settimana"]
        self.soglia_austerita_sessione = economia["austerita_sessione"]
        self.anticipo_massimo = economia["anticipo_sul_ritmo"]

    def regime(self, limiti: dict) -> dict:
        """Regime attuale con il motivo, dai limiti di utilizzo."""
        settimana, sessione = limiti.get("settimana") or {}, limiti.get("sessione") or {}
        uso_settimana = settimana.get("uso") or 0
        uso_sessione = sessione.get("uso") or 0

        # Ritmo: quota di settimana consumata rispetto alla quota di settimana trascorsa.
        trascorsa = None
        if settimana.get("rinnovo"):
            mancano = settimana["rinnovo"] - time.time()
            trascorsa = min(max(1 - mancano / SETTIMANA_S, 0), 1)

        if uso_settimana >= self.soglia_austerita:
            return {"nome": "austerità", "motivo": f"settimana al {uso_settimana:.0%}"}
        if uso_sessione >= self.soglia_austerita_sessione:
            return {"nome": "austerità", "motivo": f"sessione al {uso_sessione:.0%}"}
        if uso_settimana >= self.soglia_parsimonia:
            return {"nome": "parsimonia", "motivo": f"settimana al {uso_settimana:.0%}"}
        if trascorsa is not None and uso_settimana > trascorsa + self.anticipo_massimo:
            return {
                "nome": "parsimonia",
                "motivo": f"consumo in anticipo: {uso_settimana:.0%} usato, {trascorsa:.0%} di settimana passata",
            }
        return {"nome": "normale", "motivo": ""}

    def scegli(self, testo: str, limiti: dict) -> str | None:
        """Modello per questo messaggio, o None se Alfred deve fare da sé."""
        regime = self.regime(limiti)["nome"]
        if regime == "austerità":
            return self.leggero if FORZA.search(testo) else None
        if regime == "parsimonia":
            return self.leggero

        if PROFONDO.search(testo) or len(testo) > 280:
            self._trascinamento = MESSAGGI_DI_TRASCINAMENTO
            return self.profondo
        if self._trascinamento > 0:
            self._trascinamento -= 1
            return self.profondo
        return self.leggero

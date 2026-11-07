"""Server MCP che espone gli strumenti di Alfred al cervello (claude -p).

È un ponte sottile: ogni strumento interroga alfred-core, che ha già i dati.
"""

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from alfred import config

server = MCPServer("alfred", instructions="Gli strumenti del maggiordomo Alfred.")
SOLA_LETTURA = ToolAnnotations(readOnlyHint=True)
AZIONE = ToolAnnotations(readOnlyHint=False, destructiveHint=False)


async def _chiedi_al_core(percorso: str) -> dict:
    async with httpx.AsyncClient(base_url=config.url_core(), timeout=30) as client:
        risposta = await client.get(percorso)
        return risposta.json()


@server.tool(annotations=SOLA_LETTURA)
async def stato_computer() -> dict:
    """Stato del computer di casa: uso e temperatura del processore, frequenza
    della grafica, memoria, disco libero, batteria, velocità di rete e da quanti
    secondi è acceso."""
    return await _chiedi_al_core("/api/sistema")


@server.tool(annotations=SOLA_LETTURA)
async def meteo() -> dict:
    """Meteo attuale e dei prossimi tre giorni nel luogo in cui si trova il
    computer."""
    return await _chiedi_al_core("/api/meteo")


@server.tool(annotations=SOLA_LETTURA)
async def stato_obs() -> dict:
    """Stato di OBS Studio: se è aperto, se la diretta o la registrazione sono
    attive e da quanto, la scena attuale e l'elenco delle scene."""
    return await _chiedi_al_core("/api/obs")


async def _azione(nome: str, parametri: dict | None = None) -> dict:
    async with httpx.AsyncClient(base_url=config.url_core(), timeout=60) as client:
        risposta = await client.post(f"/api/azioni/{nome}", json=parametri or {})
        return risposta.json()


# Ogni azione restituisce "messaggio": una frase già pronta che descrive
# l'esito. Se c'è "in_attesa_di_conferma", l'azione NON è ancora avvenuta.

@server.tool(annotations=AZIONE)
async def modalita_gioco() -> dict:
    """Avvia la modalità gioco: apre Battle.net e CurseForge (per controllare
    gli addon); la macchina prepara da sola schermi e prestazioni. Il gioco
    lo lancia Pietro da Battle.net."""
    return await _azione("modalita_gioco")


@server.tool(annotations=AZIONE)
async def apri_obs() -> dict:
    """Apre OBS Studio. Dopo l'apertura servono alcuni secondi prima che
    risponda ai comandi."""
    return await _azione("apri_obs")


@server.tool(annotations=AZIONE)
async def avvia_diretta() -> dict:
    """Chiede di avviare la diretta in OBS. Richiede sempre la conferma di
    Pietro: l'HUD gliela chiede, e a lui basta rispondere "sì"."""
    return await _azione("avvia_diretta")


@server.tool(annotations=AZIONE)
async def ferma_diretta() -> dict:
    """Chiede di terminare la diretta in OBS. Richiede sempre la conferma di
    Pietro."""
    return await _azione("ferma_diretta")


@server.tool(annotations=AZIONE)
async def registrazione(azione: str) -> dict:
    """Controlla la registrazione di OBS. azione: "avvia", "ferma", "pausa"
    oppure "riprendi"."""
    nomi = {"avvia": "avvia_registrazione", "ferma": "ferma_registrazione",
            "pausa": "pausa_registrazione", "riprendi": "riprendi_registrazione"}
    if azione not in nomi:
        return {"ok": False, "messaggio": f"Azione sconosciuta: {azione}. Usa avvia, ferma, pausa o riprendi."}
    return await _azione(nomi[azione])


@server.tool(annotations=AZIONE)
async def invia_telegram(testo: str) -> dict:
    """Invia un messaggio Telegram a Pietro (solo a lui, tramite il bot di
    Alfred). Utile per promemoria, appunti o cose da ritrovare sul telefono."""
    return await _azione("invia_telegram", {"testo": testo})


@server.tool(annotations=SOLA_LETTURA)
async def agenda_eventi(da: str, a: str, calendari: list[str] | None = None) -> dict:
    """Eventi dell'agenda di Pietro tra due date (AAAA-MM-GG, "a" esclusa),
    con id e calendario: servono per spostare o eliminare un evento.
    Senza "calendari" legge solo i suoi calendari personali; gli altri sono
    elencati in "altri_calendari" e vanno consultati solo se lui li nomina o
    la domanda li riguarda: passa i loro nomi, oppure ["tutti"]."""
    parametri = {"da": da, "a": a, "calendari": ",".join(calendari or [])}
    async with httpx.AsyncClient(base_url=config.url_core(), timeout=30) as client:
        return (await client.get("/api/agenda", params=parametri)).json()


@server.tool(annotations=AZIONE)
async def crea_evento(titolo: str, inizio: str, fine: str | None = None, tutto_il_giorno: bool = False,
                      luogo: str | None = None, descrizione: str | None = None) -> dict:
    """Crea un evento nel calendario principale. inizio e fine in ISO 8601
    nell'ora locale (es. 2026-11-07T21:00); per eventi di un giorno intero
    solo la data e tutto_il_giorno=true. Senza fine dura un'ora."""
    return await _azione("crea_evento", {"titolo": titolo, "inizio": inizio, "fine": fine,
                                         "tutto_il_giorno": tutto_il_giorno, "luogo": luogo,
                                         "descrizione": descrizione})


@server.tool(annotations=AZIONE)
async def sposta_evento(id: str, inizio: str, fine: str | None = None, calendario: str = "primary") -> dict:
    """Sposta un evento (id e calendario da agenda_eventi) al nuovo inizio in
    ISO 8601, ora locale. Senza fine mantiene la durata."""
    return await _azione("sposta_evento", {"id": id, "inizio": inizio, "fine": fine, "calendario": calendario})


@server.tool(annotations=AZIONE)
async def elimina_evento(id: str, calendario: str = "primary") -> dict:
    """Chiede di eliminare un evento (id e calendario da agenda_eventi).
    Richiede sempre la conferma di Pietro."""
    return await _azione("elimina_evento", {"id": id, "calendario": calendario})


# --- Second brain: il vault Obsidian di Pietro (metodo PARA). Si aggiunge, non si cancella.

@server.tool(annotations=AZIONE)
async def cattura(testo: str) -> dict:
    """Annota al volo un'idea, una cosa da fare o da ricordare: una riga in fondo
    all'Inbox del second brain, da smistare poi con calma."""
    return await _azione("cattura", {"testo": testo})


@server.tool(annotations=SOLA_LETTURA)
async def cerca_nota(testo: str) -> dict:
    """Cerca nel second brain (progetti, aree, risorse, diario): restituisce le
    note più pertinenti con i paragrafi che contengono le parole cercate."""
    return await _azione("cerca_nota", {"testo": testo})


@server.tool(annotations=SOLA_LETTURA)
async def leggi_nota(nota: str) -> dict:
    """Legge per intero una nota del second brain (nome come lo dà cerca_nota,
    es. "Progetti/Alfred")."""
    return await _azione("leggi_nota", {"nota": nota})


@server.tool(annotations=AZIONE)
async def aggiungi_attivita(nota: str, testo: str, scadenza: str | None = None) -> dict:
    """Aggiunge un'attività ("- [ ] testo @data") nella sezione Attività della
    nota di un progetto o di un'area (es. "Alfred", "Lore is Magic").
    scadenza: "oggi", "domani", un giorno della settimana o AAAA-MM-GG."""
    return await _azione("aggiungi_attivita", {"nota": nota, "testo": testo, "scadenza": scadenza})


@server.tool(annotations=SOLA_LETTURA)
async def attivita_di_oggi(giorno: str = "oggi") -> dict:
    """Attività del second brain in scadenza entro quel giorno ("oggi",
    "domani", AAAA-MM-GG), comprese quelle già scadute."""
    return await _azione("attivita_di_oggi", {"giorno": giorno})


# --- Notion: Alfred vede solo le pagine che Pietro ha condiviso con l'integrazione.
# Il testo delle pagine è semplice, una riga per blocco: "# titolo", "## sottotitolo",
# "- punto", "[ ] da fare", "[x] fatto", "> citazione".

@server.tool(annotations=SOLA_LETTURA)
async def notion_cerca(testo: str) -> dict:
    """Cerca pagine e database nel Notion di Pietro per titolo (testo vuoto:
    i più recenti). Restituisce id, tipo, titolo e data di modifica."""
    return await _azione("notion_cerca", {"testo": testo})


@server.tool(annotations=SOLA_LETTURA)
async def notion_leggi(id: str) -> dict:
    """Legge una pagina (proprietà e contenuto, ogni riga con l'id del suo
    blocco) o un database (proprietà con le opzioni ammesse e voci)."""
    return await _azione("notion_leggi", {"id": id})


@server.tool(annotations=AZIONE)
async def notion_crea(genitore: str, titolo: str, testo: str = "", proprieta: dict | None = None) -> dict:
    """Crea una pagina dentro la pagina "genitore", oppure una voce se
    "genitore" è un database: in quel caso "proprieta" ne imposta i campi con
    valori semplici, es. {"Stato": "Da fare", "Scadenza": "2026-11-07"}."""
    return await _azione("notion_crea", {"genitore": genitore, "titolo": titolo, "testo": testo, "proprieta": proprieta})


@server.tool(annotations=AZIONE)
async def notion_aggiungi(id: str, testo: str) -> dict:
    """Aggiunge testo in fondo a una pagina (per appunti e annotazioni)."""
    return await _azione("notion_aggiungi", {"id": id, "testo": testo})


@server.tool(annotations=AZIONE)
async def notion_aggiorna(id: str, proprieta: dict) -> dict:
    """Cambia i campi di una voce di database con valori semplici, es.
    {"Stato": "Fatto"}; le opzioni ammesse sono in notion_leggi del database."""
    return await _azione("notion_aggiorna", {"id": id, "proprieta": proprieta})


@server.tool(annotations=AZIONE)
async def notion_riscrivi(id: str, testo: str) -> dict:
    """Sostituisce il testo di un blocco (id da notion_leggi). Chiede sempre
    conferma a Pietro."""
    return await _azione("notion_riscrivi", {"id": id, "testo": testo})


@server.tool(annotations=AZIONE)
async def notion_elimina(id: str) -> dict:
    """Mette nel cestino di Notion una pagina o un blocco. Chiede sempre
    conferma a Pietro."""
    return await _azione("notion_elimina", {"id": id})


@server.tool(annotations=AZIONE)
async def standby(azione: str) -> dict:
    """Standby del computer. azione: "sospendi" (subito, chiede conferma a
    Pietro), "consenti" (permette lo standby automatico) o "impedisci"
    (predefinito: con l'alimentatore collegato non va in standby da solo,
    lo schermo può comunque bloccarsi e spegnersi)."""
    nomi = {"sospendi": "sospendi_computer", "consenti": "consenti_standby", "impedisci": "impedisci_standby"}
    if azione not in nomi:
        return {"ok": False, "messaggio": f"Azione sconosciuta: {azione}. Usa sospendi, consenti o impedisci."}
    return await _azione(nomi[azione])


@server.tool(annotations=SOLA_LETTURA)
async def fonti_obs() -> dict:
    """Rassegna della regia prima di una diretta: scena in onda e cosa vi è
    visibile, ingressi audio silenziati o attivi, link delle fonti della chat."""
    return await _chiedi_al_core("/api/obs/fonti")


@server.tool(annotations=AZIONE)
async def aggiorna_chat(link: str) -> dict:
    """Mette nelle fonti della chat di OBS la chat della nuova diretta. link: il
    link della diretta su YouTube (anche solo l'ID del video)."""
    return await _azione("aggiorna_chat", {"link": link})


# --- Il computer --------------------------------------------------------------------

@server.tool(annotations=AZIONE)
async def apri(cosa: str) -> dict:
    """Apre un'app (per nome: "firefox", "kdenlive", "calcolatrice"), una
    cartella ("documenti", "scaricati", "cartella progetti") o un link."""
    return await _azione("apri", {"cosa": cosa})


@server.tool(annotations=AZIONE)
async def volume(azione: str, livello: int | None = None) -> dict:
    """Volume del computer. azione: "alza" o "abbassa" (di livello punti, 10
    se non indicato), "imposta" (livello 0-100), "muto", "audio" (toglie il muto)."""
    return await _azione("volume", {"azione": azione, "livello": livello})


@server.tool(annotations=AZIONE)
async def riproduzione(azione: str) -> dict:
    """Musica e video in riproduzione sul computer (Spotify, browser…).
    azione: "pausa", "play", "avanti", "indietro"."""
    return await _azione("riproduzione", {"azione": azione})


@server.tool(annotations=AZIONE)
async def timer(minuti: float, etichetta: str = "") -> dict:
    """Avvia un timer: allo scadere Alfred avvisa Pietro (a voce, o su Telegram
    se non è al computer). minuti può avere decimali (0.5 = 30 secondi);
    etichetta: a cosa serve ("la pasta")."""
    return await _azione("timer", {"minuti": minuti, "etichetta": etichetta})


@server.tool(annotations=AZIONE)
async def sorveglia(tipo: str, valore: str | None = None, soglia: float | None = None, etichetta: str = "") -> dict:
    """Tiene d'occhio qualcosa e avvisa Pietro quando succede (a costo zero).
    tipo:
    - "processo": quando il programma "valore" termina (es. "melt" per i render
      di Kdenlive, "ffmpeg"); se non sai il nome usa processi_attivi
    - "cpu": quando il computer torna a riposo per un minuto (render generico)
    - "file": quando il file "valore" (percorso) esiste e smette di crescere
    - "download": quando finiscono i download in corso in Scaricati
    - "batteria": in carica, quando arriva a "soglia" (100 se manca); a
      batteria, quando scende a "soglia"
    - "obs": "valore" tra diretta_inizia, diretta_finisce,
      registrazione_inizia, registrazione_finisce
    etichetta: come chiamarla nell'avviso ("l'esportazione del reel")."""
    return await _azione("sorveglia", {"tipo": tipo, "valore": valore, "soglia": soglia, "etichetta": etichetta})


@server.tool(annotations=SOLA_LETTURA)
async def processi_attivi() -> dict:
    """I programmi che stanno usando più processore adesso (nome e percento):
    per scegliere quale sorvegliare."""
    return await _chiedi_al_core("/api/processi")


@server.tool(annotations=SOLA_LETTURA)
async def attivita_in_corso() -> dict:
    """Timer e sorveglianze in corso, con il loro id."""
    return await _chiedi_al_core("/api/attivita")


@server.tool(annotations=AZIONE)
async def annulla_attivita(id: str | None = None, tipo: str | None = None) -> dict:
    """Annulla un timer o una sorveglianza (id da attivita_in_corso), tutte
    quelle di un tipo ("timer"), o tutte se non indichi nulla."""
    return await _azione("annulla_attivita", {"id": id, "tipo": tipo})


@server.tool(annotations=AZIONE)
async def impara_pronuncia(parole: list[str], inglese: bool = True) -> dict:
    """Dopo il sì di Pietro, aggiunge parole o nomi (anche di più termini,
    es. "Lore is Magic") a quelli che la tua voce pronuncia all'inglese.
    Con inglese=false li segna da lasciare all'italiana."""
    return await _azione("impara_pronuncia", {"parole": parole, "inglese": inglese})


@server.tool(annotations=AZIONE)
async def ricorda(fatto: str) -> dict:
    """Annota nella memoria a lungo termine un fatto stabile su Pietro (gusti,
    abitudini, persone, decisioni). Non per gli impegni con data e ora: quelli
    vanno in agenda."""
    return await _azione("ricorda", {"fatto": fatto})


@server.tool(annotations=AZIONE)
async def cambia_scena(scena: str) -> dict:
    """Cambia la scena di OBS. Il nome può essere approssimativo: viene
    confrontato con le scene esistenti (vedi stato_obs)."""
    return await _azione("cambia_scena", {"scena": scena})


def avvia() -> None:
    server.run("stdio")

# Roadmap

Ogni fase produce qualcosa di usabile da sola.

## Fase 0 — Finestra e HUD di base
- [x] alfred-core: servizio FastAPI su 127.0.0.1, unità systemd utente
- [x] alfred-window: finestra GTK/WebKit, `alfred toggle`
- [x] regola niri + scorciatoia (Mod+A) tramite `installa.sh`
- [x] HUD: ora/data, sistema (CPU, RAM, temperature, batteria), meteo (Open-Meteo)
- [x] aggiornamento dal vivo: dati spinti via WebSocket, HUD che si aggiorna da solo quando cambiano grafica, config o codice
- [x] meteo dalla posizione del computer (GeoClue + Nominatim); città o coordinate in config come alternativa
- [x] config.toml + secrets.env, `installa.sh` per altre macchine

## Fase 1 — Alfred pensa (chat testuale)
- [x] adattatore brain `claude -p` in streaming (processo persistente, Sonnet)
- [x] personalità a strati (docs/ISPIRAZIONI.md) e scheda personale `su-di-me.md`
- [x] server MCP con i primi strumenti in sola lettura (computer, meteo, OBS)
- [x] memoria della conversazione (sopravvive ai riavvii, "nuova conversazione")
- [x] riquadro di conversazione nell'HUD, risposte parola per parola
- [x] "Le riserve": limiti di utilizzo di Claude (sessione e settimana) e consumo di Alfred nell'HUD
- [x] economo: modello per compito (Haiku quotidiano, Sonnet profondo) e regimi di risparmio

## Fase 2 — Alfred agisce
- [x] comandi diretti a costo zero: frasi comuni riconosciute in locale, senza modello
- [x] Telegram: bot dedicato, conversazione completa da Telegram (stessa dell'HUD), conferme con pulsanti, "mandami su telegram …" a costo zero; chat collegata al primo /start (da provare col bot vero)
- [x] agenda: Google Calendar API diretta (docs/AGENDA.md), lettura a costo zero, creazione, spostamento, eliminazione con conferma, riquadro nell'HUD (da autorizzare)
- [x] modalità gioco → Battle.net (comando in config; da provare dal vivo)
- [x] OBS: apertura, scene, diretta, registrazione; riquadro "La regia" nell'HUD
- [x] conferme per le azioni sensibili (pulsanti o "sì"/"no")
- [x] veglia: con l'alimentatore il computer non va in standby da solo mentre Alfred è attivo (DMS o logind); standby su richiesta con conferma

## Fase 3 — Alfred parla
- [x] ascolto a pulsante: Mod+Shift+A o microfono nell'HUD, fine frase con Silero, trascrizione faster-whisper small su CPU (~1,2 s)
- [x] vocali di Telegram trascritti e trattati come messaggi
- [x] parola di attivazione "Alfred" in due stadi: sherpa-onnx (sempre in ascolto, ~2-3% di un core) + verifica con Whisper ("al freddo" e "Alfredo" scartati); "Alfred" da solo → "Sì, signore?"
- [x] voce: Kokoro, miscela Nicola 70% + Fable 30% a velocità 0,92, domande con intonazione corretta (pyworld), frase per frase mentre il cervello scrive
- [x] risposta a voce quando si parla a voce; vocale in risposta ai vocali di Telegram
- [x] interruzione con Mod+Shift+A o il microfono (zittisce e ascolta)
- [x] interruzione a voce: "Alfred" mentre parla lo zittisce subito; "basta", "silenzio" a costo zero
- [ ] cancellazione dell'eco (PipeWire) per interromperlo anche senza dire il suo nome, se servirà

## Fase 4 — Alfred di sua iniziativa
- [x] presenza: schermo bloccato (logind) → Telegram; ore di silenzio (23-8) → notifica muta o Telegram senza suono
- [x] promemoria dell'agenda a costo zero (15 minuti prima, 60 per i turni)
- [x] dirette: con il calendario "Lore is Magic" Alfred apre OBS mezz'ora prima e propone la rassegna; strumenti fonti_obs e aggiorna_chat ("chat: <link>" a costo zero)
- [x] briefing alla prima apertura della giornata (dopo le 8), detto a voce, senza modello
- [x] memoria: "ricordati che…" in memoria.md; diario quotidiano (un riassunto di Haiku) e conversazione nuova ogni mattina

## Più avanti
- [x] Whisper a riposo: dopo 10 minuti senza trascrizioni il modello si scarica (−1,6 GB), si ricarica in ~1,5 s
- [x] dettatura: Mod+Shift+D, si parla e il testo compare dove c'è il cursore (wtype)
- [x] controllo del PC a costo zero: apri app/cartelle/link, volume, pausa/play/avanti (playerctl), timer
- [x] second brain: vault Obsidian ([vault] in config.toml); contesto sempre caricato, ricerca nelle note, cattura nell'Inbox, attività "- [ ] … @data" nelle note, diario di Alfred nella nota del giorno ("Chiusura serale"), tutto a costo zero
- [x] routine del second brain: briefing con le attività in scadenza (scritto nella nota del giorno), chiusura serale ("buonanotte", o proposta alle 22: attività completate, domani, "Fatto oggi"), revisione dell'Inbox la domenica riga per riga (attività, risorsa o via, mai cancellata)
- [x] sorveglianze a costo zero ("avvisami quando…"): fine di un programma, computer a riposo, file pronto, download, batteria, diretta/registrazione; timer e sorveglianze salvati (sopravvivono ai riavvii) e mostrati nel riquadro "Attività" dell'HUD
- [x] Notion: cerca, legge, crea pagine e voci di database, aggiunge appunti, aggiorna campi; riscrivere ed eliminare con conferma ([NOTION.md](NOTION.md))
- [x] tema "ologramma da laboratorio": nucleo ad anelli che segue gli stati di Alfred (riposo, ascolto, pensa, parla, lato cinico) con transizioni morbide; ciano per i dati, ambra per le parole di Alfred
- [ ] suoni originali (avvio, conferme)
- [ ] cervello locale alternativo (Ollama)

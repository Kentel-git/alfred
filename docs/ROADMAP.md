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
- [ ] parola di attivazione "Alfred"
- [ ] voce TTS
- [ ] interruzione (si parla sopra ad Alfred e lui tace)

## Fase 4 — Alfred di sua iniziativa
- [ ] memoria a lungo termine: cose che Alfred impara su Pietro oltre la scheda
- [ ] briefing del mattino
- [ ] promemoria (agenda, live in arrivo)
- [ ] avvisi su Telegram quando si è lontani dal PC

## Più avanti
- [ ] tema "maniero" (grafica e suoni originali, nessun materiale DC)
- [ ] cervello locale alternativo (Ollama)

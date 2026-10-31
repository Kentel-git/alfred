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
- [ ] memoria a lungo termine: cose che Alfred impara su Pietro oltre la scheda

## Fase 2 — Alfred agisce
- [ ] comandi diretti a costo zero: frasi comuni riconosciute in locale, senza modello
- [ ] Telegram (bot)
- [ ] agenda: lettura, creazione e modifica di eventi
- [ ] modalità gioco → Battle.net
- [ ] OBS: scene, live, registrazione
- [ ] conferme per le azioni sensibili

## Fase 3 — Alfred parla
- [ ] parola di attivazione
- [ ] trascrizione whisper.cpp
- [ ] voce TTS
- [ ] interruzione (si parla sopra ad Alfred e lui tace)

## Fase 4 — Alfred di sua iniziativa
- [ ] briefing del mattino
- [ ] promemoria (agenda, live in arrivo)
- [ ] avvisi su Telegram quando si è lontani dal PC

## Più avanti
- [ ] tema "maniero" (grafica e suoni originali, nessun materiale DC)
- [ ] cervello locale alternativo (Ollama)

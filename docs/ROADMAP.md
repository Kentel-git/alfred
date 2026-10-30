# Roadmap

Ogni fase produce qualcosa di usabile da sola.

## Fase 0 — Finestra e HUD di base
- [x] alfred-core: servizio FastAPI su 127.0.0.1, unità systemd utente
- [x] alfred-window: finestra GTK/WebKit, `alfred toggle`
- [x] regola niri + scorciatoia (Mod+A) tramite `installa.sh`
- [x] HUD: ora/data, sistema (CPU, RAM, temperature, batteria), meteo (Open-Meteo)
- [x] aggiornamento dal vivo: dati spinti via WebSocket, HUD che si aggiorna da solo quando cambiano grafica, config o codice
- [ ] meteo: impostare la città sulla macchina di Pietro
- [x] config.toml + secrets.env, `installa.sh` per altre macchine

## Fase 1 — Alfred pensa (chat testuale)
- [ ] adattatore brain `claude -p` in streaming
- [ ] personalità: prompt di sistema del maggiordomo
- [ ] server MCP con i primi strumenti in sola lettura (stato OBS, ora, sistema)
- [ ] memoria della conversazione

## Fase 2 — Alfred agisce
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

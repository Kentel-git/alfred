# Architettura di Alfred

Alfred è un maggiordomo digitale per desktop Linux: una finestra richiamabile con
una scorciatoia, che si apre a schermo intero sullo schermo attivo, con cui si
parla a voce. Ha la personalità del maggiordomo britannico: brillante, ironico,
impeccabile.

## Principi

1. **Free and open source.** Solo dipendenze libere. Niente servizi a pagamento
   obbligatori.
2. **Clonabile.** `git clone` + `./installa.sh` su un'altra macchina. Niente
   percorsi personali nel codice: tutto ciò che è specifico della macchina sta
   in `~/.config/alfred/config.toml`, i segreti in `~/.config/alfred/secrets.env`.
3. **Cervello intercambiabile.** Il default è `claude -p` (Claude Code in modalità
   non interattiva). Il cervello è un adattatore: chi non ha Claude Code potrà
   usare un modello locale (es. Ollama) senza toccare il resto.
4. **Locale.** Il servizio ascolta solo su `127.0.0.1`.
5. **Azioni sensibili confermate.** Inviare messaggi, avviare/fermare live:
   Alfred chiede conferma (configurabile per azione).

## Componenti

```
 scorciatoia niri (Mod+A)
          │
          ▼
 ┌─────────────────┐   HTTP/WebSocket   ┌──────────────────────────────┐
 │ alfred-window   │ ◄────────────────► │ alfred-core (servizio utente │
 │ GTK + WebKitGTK │   127.0.0.1:7878   │ systemd, Python/FastAPI)     │
 │ mostra ui/      │                    │                              │
 └─────────────────┘                    │  ├─ brain/   adattatori LLM  │
                                        │  │   └─ claude -p (default)  │
                                        │  ├─ tools/   azioni          │
                                        │  │   ├─ agenda               │
                                        │  │   ├─ telegram             │
                                        │  │   ├─ modalità gioco       │
                                        │  │   └─ obs (WebSocket 4455) │
                                        │  ├─ voice/  STT + TTS        │
                                        │  └─ widget  dati HUD         │
                                        └──────────────────────────────┘
                                                     ▲
                                                     │ MCP (stdio)
                                         claude -p ──┘ usa i tools di Alfred
```

- **alfred-core**: servizio sempre attivo (`systemctl --user`). Raccoglie i dati
  dei widget, gestisce la conversazione e la voce, esegue le azioni. Così la
  finestra si apre all'istante e Alfred può parlare o mandare un Telegram anche
  a finestra chiusa.
- **alfred-window**: client leggero (PyGObject + WebKitGTK, già nei repo di
  ogni distro). `alfred toggle` la apre se è chiusa e la chiude se è aperta.
  Una regola di niri (`app-id="^alfred$"` → `open-fullscreen true`) la mette a
  schermo intero; niri apre le finestre nuove sullo schermo che ha il focus.
- **ui/**: HUD in HTML/CSS/JS, servito da alfred-core. Il tema "maniero"
  arriverà più avanti.
- **brain/**: interfaccia comune `rispondi(messaggi) → flusso di testo +
  chiamate a strumenti`. L'adattatore `claude` lancia `claude -p` con la
  personalità in `--append-system-prompt`, `--output-format stream-json` e
  `--resume` per mantenere il filo della conversazione.
- **tools/**: ogni azione è una funzione Python documentata, esposta a
  `claude -p` come **server MCP**. Gli stessi strumenti saranno usabili da un
  cervello locale.
- **voice/**: parola di attivazione (openWakeWord), trascrizione (whisper.cpp),
  sintesi vocale (Piper o Kokoro: si decide in fase 3, conta la qualità delle
  voci italiane).

## Strumenti previsti

| Strumento | Come | Note |
|---|---|---|
| Agenda | Da decidere in fase 2: CalDAV/Google Calendar API (libero, portabile) | |
| Telegram | Bot API ufficiale (bot personale di Alfred), long polling | Conversazione completa da Telegram; risponde solo alla chat collegata al primo /start |
| Modalità gioco | Lancia un comando configurabile | Qui: `steam://rungameid/…` di Battle.net, che passa già da `modalita-gioco` |
| OBS | obs-websocket v5 (porta 4455) | Scene, avvio/stop live e registrazione, stato |

## Economia delle risorse

Le riserve (limiti di utilizzo dell'abbonamento Claude, finestra di 5 ore e
settimanale) sono condivise con tutto il resto del lavoro dell'utente. Alfred
le legge dagli eventi di `claude -p` e le mostra nell'HUD ("Le riserve").
L'**economo** (`alfred/brain/economo.py`) sceglie il modello per ogni compito:

| Compito | Modello |
|---|---|
| Comandi diretti (fase 2: OBS, gioco, Telegram…) | nessuno: riconosciuti ed eseguiti in locale |
| Conversazione quotidiana | `quotidiano` (Haiku) |
| Riflessioni, consigli, decisioni, lato cinico | `profondo` (Sonnet), riconosciuti in locale |
| Sonda delle riserve, riassunti, briefing | Haiku |

E un regime in base alle riserve: **normale**; **parsimonia** (solo modello
quotidiano) oltre metà settimana o se il consumo corre più del calendario;
**austerità** (nessun modello, salvo "è importante") oltre l'80% della
settimana o il 90% della sessione. Soglie in `[economia]` di `config.toml`.
Regola di progetto: ogni nuova funzione deve dichiarare quale modello usa, e
preferire sempre la soluzione senza modello quando basta.

## Veglia

Mentre Alfred è attivo e l'alimentatore è collegato, il computer non va in
standby da solo: schermo bloccato e spento sì, sistema no (servizio, Telegram,
dirette restano vivi). Con DMS Alfred imposta a "mai" `acSuspendTimeout` e
rimette il valore originale quando si ferma o quando glielo si chiede; lo
standby manuale resta possibile. Altrove usa un inibitore di logind attivo
solo con l'alimentatore (che però blocca anche lo standby manuale: va chiesto
ad Alfred). Modulo: `alfred/core/veglia.py`.

## Posizione

Il meteo usa la posizione del computer tramite **GeoClue** (servizio libero di
freedesktop: reti WiFi via BeaconDB, altrimenti indirizzo IP) e il nome del
luogo da **Nominatim** (OpenStreetMap). Alfred si presenta a GeoClue con l'id
`alfred`: serve un agente GeoClue attivo che lo autorizzi (GNOME ne ha uno; su
altri desktop c'è quello demo, `/usr/lib/geoclue-2.0/demos/agent`). Una città o
delle coordinate in `config.toml` hanno la precedenza.

## Stack

- Python ≥ 3.12, FastAPI + uvicorn, ambiente virtuale in `.venv`
- PyGObject + WebKitGTK 4.1 per la finestra
- HTML/CSS/JS senza build step per l'HUD (niente npm obbligatorio)

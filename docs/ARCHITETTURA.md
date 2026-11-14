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
4. **Locale.** Il servizio ascolta solo su `127.0.0.1` e accetta solo l'host
   `127.0.0.1`/`localhost` e, dai browser, solo l'Origin del proprio HUD: una
   pagina web qualunque non può leggerlo né comandarlo.
5. **Azioni sensibili confermate.** Inviare messaggi, avviare/fermare live:
   Alfred chiede conferma (`sensibile=True` in `alfred/core/azioni.py`).

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
                                        │  │   ├─ notion               │
                                        │  │   ├─ vault (Obsidian)     │
                                        │  │   ├─ modalità gioco       │
                                        │  │   └─ obs (WebSocket 4455) │
                                        │  ├─ voce/   STT + TTS        │
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
- **ui/**: HUD in HTML/CSS/JS senza dipendenze, servito da alfred-core (sempre
  con `Cache-Control: no-cache`). Stile "ologramma da laboratorio": il nucleo ad
  anelli segue lo stato di Alfred, con colori sfumati (`@property`) e velocità
  con inerzia. Font liberi in `ui/fonts` (Rajdhani, JetBrains Mono: SIL OFL).
- **brain/**: interfaccia comune `chiedi(testo, modello) → flusso di eventi`
  (testo parola per parola, chiamate a strumenti, fine). L'adattatore `claude`
  tiene acceso un solo processo `claude -p` in stream-json, con la personalità
  in `--system-prompt`, nessuno strumento proprio (`--tools ""`) oltre a quelli
  MCP di Alfred, e `--resume` per mantenere il filo della conversazione.
- **tools/**: ogni azione è una funzione Python documentata, esposta a
  `claude -p` come **server MCP**. Gli stessi strumenti saranno usabili da un
  cervello locale.
- **voce/**: ascolto (pw-record, fine frase con Silero VAD, trascrizione
  faster-whisper "small" sulla CPU: la GPU resta libera per giochi e dirette)
  e sintesi vocale (predefinita Pocket TTS con la voce italiana "giovanni";
  in alternativa Kokoro, più leggero, con le domande intonate da WORLD).
  Sveglia sul nome "Alfred" in due stadi: riconoscitore di parole chiave
  sherpa-onnx sempre attivo e permissivo, poi verifica della frase con
  Whisper. Tutto in locale, zero riserve.

## Canale HUD ↔ core

L'HUD parla con alfred-core su un solo WebSocket, `/ws`; le rotte `/api/...`
servono ad altri client, non all'HUD. Il core spedisce messaggi con un campo
`tipo` tramite `Diffusore.invia` (`alfred/core/server.py`), `ui/app.js` li
smista per tipo. `Conversazione`, `Gestore` e `Attivita` ricevono
`diffusore.invia` in `ciclo_di_vita()` e scrivono all'HUD da soli.

| Riquadro | `tipo` | Origine |
|---|---|---|
| Sistema | `sistema` | `sistema.leggi()`, a ciclo in `_ciclo_sistema` |
| Meteo | `meteo` | `_meteo()` → `meteo.leggi()`, a ciclo in `_ciclo_meteo` |
| Regia OBS | `regia` | `obs.stato()`, a ciclo in `_ciclo_regia` |
| Agenda | `agenda` | `agenda_per_hud()` (`core/azioni.py`), a ciclo in `_ciclo_agenda` |
| Riserve e regime | `limiti` | `limiti.stato()`, con il regime dell'`Economo` |
| Veglia | `veglia` | `core/veglia.py`, ai cambi di alimentazione |
| Attività | `attivita` | `Attivita.per_hud()` (`core/attivita.py`) |
| Conferma Sì/No | `conferma`, `conferma_chiusa` | `Gestore` (`core/azioni.py`) |
| Dialogo | `messaggio`, `cronologia`, `risposta_*` | `Conversazione` |
| Nucleo e microfono | `ascolto`, `parola` | `Conversazione` |

In senso inverso l'HUD manda `chat`, `azione` (pulsanti dei riquadri, stessa
strada dei comandi diretti), `conferma_azione`, `ascolta`,
`nuova_conversazione` e `aggiornami` (finestra appena richiamata: dati freschi
subito).

## Strumenti

| Strumento | Come | Note |
|---|---|---|
| Agenda | Google Calendar API diretta (`alfred/tools/agenda.py`), vedi [AGENDA.md](AGENDA.md) | Lettura a costo zero; eliminare chiede conferma |
| Second brain | Vault Obsidian in locale (`alfred/tools/vault.py`), letto e scritto come file Markdown | Contesto sempre caricato; ricerca per parole senza indice; si aggiunge, non si cancella |
| Notion | API ufficiale con integrazione interna (token in secrets.env), vedi [NOTION.md](NOTION.md) | Vede solo le pagine condivise; riscrivere ed eliminare chiedono conferma |
| Telegram | Bot API ufficiale (bot personale di Alfred), long polling | Conversazione completa da Telegram; risponde solo alla chat collegata al primo /start |
| Modalità gioco | Lancia un comando configurabile | Qui: `steam://rungameid/…` di Battle.net, che passa già da `modalita-gioco` |
| OBS | obs-websocket v5 (porta 4455) | Scene, avvio/stop live e registrazione, stato |
| Controllo del PC | `alfred/tools/pc.py`: app, cartelle e link, volume, playerctl, dettatura (wtype) | A costo zero; standby su richiesta con conferma |

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
| Sonda delle riserve, briefing | Haiku |
| Diario di fine giornata | cervello gratuito se configurato, altrimenti Haiku |

E un regime in base alle riserve: **normale**; **parsimonia** (solo modello
quotidiano) oltre metà settimana o se il consumo corre più del calendario;
**austerità** (nessun modello, salvo "è importante") oltre l'80% della
settimana o il 90% della sessione. Soglie in `[economia]` di `config.toml`.
In austerità, se in `[cervello_gratuito]` c'è un endpoint compatibile OpenAI
(es. FreeLLMAPI, Ollama), risponde quello con gli ultimi messaggi
(`alfred/brain/gratuito.py`); se non risponde, la frase fissa di sempre. Ha
pochi strumenti (`STRUMENTI_IN_AUSTERITA`: meteo, agenda, apri, volume, timer,
cattura, attività di oggi), presi dal server MCP ed eseguiti dentro il
processo: passano da `/api/azioni` come quelli di Claude e chiedono le stesse
conferme. Al più 5 giri di strumenti, poi risponde. Serve un modello che sappia
chiamare strumenti; `strumenti = false` li spegne. Con un endpoint non locale
anche gli esiti degli strumenti escono dalla macchina.
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

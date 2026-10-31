# Alfred — istruzioni per Claude Code

Maggiordomo digitale FOSS per desktop Linux (sviluppato su CachyOS + niri).
Architettura in `docs/ARCHITETTURA.md`, avanzamento in `docs/ROADMAP.md`:
leggili prima di lavorare e aggiorna la roadmap quando chiudi un punto.

## Regole
- Si parla in italiano con Pietro. Il progetto è su base italiana: codice,
  commenti, commit e documentazione tecnica in italiano. Il README è bilingue
  (italiano + sezione inglese): aggiorna entrambe le parti.
- Licenza GPL-3.0-or-later.
- Il progetto deve restare clonabile: nessun percorso o dato personale nel
  codice. Ciò che è specifico della macchina va in `~/.config/alfred/config.toml`
  (con un esempio commentato in `config.example.toml`), i segreti in
  `~/.config/alfred/secrets.env`, mai nel repo.
- Solo dipendenze libere. Il cervello `claude -p` è il default ma resta un
  adattatore sostituibile.
- Il servizio ascolta solo su 127.0.0.1.
- Niente materiale protetto da copyright (loghi, immagini, musiche DC/Batman):
  il tema è "maggiordomo britannico", con risorse originali.
- Riserve: ogni funzione che usa un modello deve passare dall'economo
  (`alfred/brain/economo.py`) e usare il modello più leggero che basta; se si
  può fare senza modello, si fa senza. Opus mai di default.
- Le azioni sensibili (inviare messaggi, avviare/fermare live o registrazioni)
  passano da una conferma.

## Sulla macchina di Pietro
- OBS Flatpak, WebSocket su 4455, collezione "LiM LIVE".
- Modalità gioco: lanciare Battle.net da Steam basta, il wrapper
  `~/.local/bin/modalita-gioco` fa il resto. Non modificarlo senza chiedere.
- `~/.config/niri/config.kdl` è di Pietro: `installa.sh` deve aggiungere un
  `include` a un file di Alfred, non riscrivere la config.

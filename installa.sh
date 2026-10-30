#!/usr/bin/env bash
# Installa Alfred per l'utente corrente. Si può rilanciare: non duplica nulla.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"
TASTO="${ALFRED_TASTO:-Mod+A}"

dire() { printf '\033[33m»\033[0m %s\n' "$*"; }
errore() { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# --- Requisiti ---------------------------------------------------------------
command -v python3 >/dev/null || errore "Serve python3."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' || errore "Serve Python 3.11 o più recente."
python3 - <<'EOF' 2>/dev/null || errore "Mancano PyGObject e WebKitGTK 4.1.
  Arch/CachyOS:   sudo pacman -S python-gobject webkit2gtk-4.1
  Debian/Ubuntu:  sudo apt install python3-gi gir1.2-webkit2-4.1
  Fedora:         sudo dnf install python3-gobject webkit2gtk4.1"
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2
EOF

# --- Ambiente Python ---------------------------------------------------------
if [ ! -x "$DIR/.venv/bin/python" ]; then
    dire "Creo l'ambiente Python…"
    python3 -m venv --system-site-packages "$DIR/.venv"
fi
dire "Installo le dipendenze…"
"$DIR/.venv/bin/pip" install -q --disable-pip-version-check -r "$DIR/requirements.txt"

# --- Comando alfred ----------------------------------------------------------
chmod +x "$DIR/bin/alfred"
mkdir -p "$BIN"
ln -sf "$DIR/bin/alfred" "$BIN/alfred"
dire "Comando: $BIN/alfred"

# --- Configurazione ----------------------------------------------------------
mkdir -p "$CONFIG/alfred"
if [ ! -f "$CONFIG/alfred/config.toml" ]; then
    cp "$DIR/config.example.toml" "$CONFIG/alfred/config.toml"
    dire "Configurazione creata: $CONFIG/alfred/config.toml"
fi
if [ ! -f "$CONFIG/alfred/secrets.env" ]; then
    install -m 600 /dev/null "$CONFIG/alfred/secrets.env"
fi

# --- Servizio systemd utente -------------------------------------------------
mkdir -p "$CONFIG/systemd/user"
cat > "$CONFIG/systemd/user/alfred-core.service" <<EOF
[Unit]
Description=Alfred, il servizio del maggiordomo

[Service]
ExecStart=$DIR/bin/alfred core
EnvironmentFile=-$CONFIG/alfred/secrets.env
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now alfred-core.service >/dev/null 2>&1
systemctl --user restart alfred-core.service
dire "Servizio alfred-core attivo."

# --- niri --------------------------------------------------------------------
NIRI="$CONFIG/niri/config.kdl"
if [ -f "$NIRI" ]; then
    cat > "$CONFIG/niri/alfred.kdl" <<EOF
// Generato da installa.sh di Alfred: verrà sovrascritto. Non modificare.
binds {
    $TASTO hotkey-overlay-title="Alfred" { spawn "$BIN/alfred" "toggle"; }
}

window-rule {
    match app-id="^alfred$"
    open-fullscreen true
}
EOF
    if ! grep -q '^include "alfred.kdl"' "$NIRI"; then
        cp "$NIRI" "$NIRI.prima-di-alfred"
        printf '\n// Alfred\ninclude "alfred.kdl"\n' >> "$NIRI"
        dire "Aggiunto include a $NIRI (copia: config.kdl.prima-di-alfred)."
    fi
    if command -v niri >/dev/null && ! niri validate >/dev/null 2>&1; then
        errore "niri rifiuta la configurazione: controlla con 'niri validate'."
    fi
    dire "Scorciatoia niri: $TASTO"
else
    dire "niri non trovato: associa a una scorciatoia il comando '$BIN/alfred toggle'."
fi

dire "Fatto. Alfred è a sua disposizione."

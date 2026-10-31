#!/usr/bin/env bash
# Installa Alfred per l'utente corrente. Si può rilanciare: non duplica nulla.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN="$HOME/.local/bin"
TASTO="${ALFRED_TASTO:-Mod+A}"
TASTO_VOCE="${ALFRED_TASTO_VOCE:-Mod+Shift+A}"

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

# --- Voce --------------------------------------------------------------------
for programma in pw-record pw-play ffmpeg; do
    command -v "$programma" >/dev/null || dire "Attenzione: manca $programma (serve per ascolto e voce)."
done
VOCE="${XDG_DATA_HOME:-$HOME/.local/share}/alfred/voce"
mkdir -p "$VOCE"
for file in kokoro-v1.0.onnx voices-v1.0.bin; do
    if [ ! -f "$VOCE/$file" ]; then
        dire "Scarico la voce ($file)…"
        curl -L --fail --progress-bar -o "$VOCE/$file.parziale" \
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$file"
        mv "$VOCE/$file.parziale" "$VOCE/$file"
    fi
done
# Sveglia sul nome "Alfred": riconoscitore di parole chiave (sherpa-onnx, 5 MB).
KWS="$VOCE/kws"
if [ ! -f "$KWS/encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx" ]; then
    dire "Scarico il riconoscitore del nome…"
    TEMP=$(mktemp -d)
    curl -L --fail --progress-bar -o "$TEMP/kws.tar.bz2" \
        "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2"
    tar xjf "$TEMP/kws.tar.bz2" -C "$TEMP"
    mkdir -p "$KWS"
    cp "$TEMP"/sherpa-onnx-kws-*/tokens.txt "$TEMP"/sherpa-onnx-kws-*/*-epoch-12-avg-2-chunk-16-left-64.int8.onnx "$KWS/"
    rm -rf "$TEMP"
fi
# Facoltativo: intonazione corretta delle domande (pyworld va compilato).
if ! "$DIR/.venv/bin/python" -c "import pyworld" 2>/dev/null; then
    "$DIR/.venv/bin/pip" install -q --disable-pip-version-check "setuptools<81" cython \
        && "$DIR/.venv/bin/pip" install -q --disable-pip-version-check --no-build-isolation pyworld \
        || dire "pyworld non installato: le domande avranno l'intonazione standard di Kokoro."
fi

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
if [ ! -f "$CONFIG/alfred/su-di-me.md" ]; then
    cp "$DIR/su-di-me.example.md" "$CONFIG/alfred/su-di-me.md"
    dire "Scheda personale da completare: $CONFIG/alfred/su-di-me.md"
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
    $TASTO_VOCE hotkey-overlay-title="Parla ad Alfred" { spawn "$BIN/alfred" "ascolta"; }
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
    dire "Scorciatoie niri: $TASTO (finestra), $TASTO_VOCE (parla ad Alfred)"
else
    dire "niri non trovato: associa a una scorciatoia il comando '$BIN/alfred toggle'."
fi

dire "Fatto. Alfred è a sua disposizione."

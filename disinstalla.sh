#!/usr/bin/env bash
# Rimuove l'installazione di Alfred. Lascia la configurazione in ~/.config/alfred.
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"

systemctl --user disable --now alfred-core.service 2>/dev/null || true
rm -f "$CONFIG/systemd/user/alfred-core.service"
systemctl --user daemon-reload

pkill -f "python.* -m alfred finestra" 2>/dev/null || true
rm -f "$HOME/.local/bin/alfred"

if [ -f "$CONFIG/niri/config.kdl" ]; then
    sed -i '/^\/\/ Alfred$/d; /^include "alfred.kdl"$/d' "$CONFIG/niri/config.kdl"
    rm -f "$CONFIG/niri/alfred.kdl"
fi

echo "Alfred si è congedato. La configurazione è rimasta in $CONFIG/alfred."

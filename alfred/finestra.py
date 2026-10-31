"""alfred-window: la finestra a schermo intero che mostra l'HUD.

Il processo resta vivo anche quando la finestra è nascosta, così si riapre
all'istante. `alfred toggle` gli manda SIGUSR1 per mostrarla o nasconderla.
"""

import os
import shutil
import signal
import subprocess
import sys

from alfred import config

FILE_PID = config.CARTELLA_RUNTIME / "finestra.pid"

PAGINA_ATTESA = """<!doctype html><html><body style="background:#0d1117;color:#c9b37e;
font-family:Georgia,serif;display:flex;align-items:center;justify-content:center;
height:100vh;margin:0;font-size:1.6rem">
<p>Un momento, signore: sto ancora indossando i guanti bianchi…</p></body></html>"""


def _pid_vivo() -> int | None:
    try:
        pid = int(FILE_PID.read_text())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"alfred" in f.read():
                return pid
    except (OSError, ValueError):
        pass
    return None


def toggle() -> None:
    """Mostra o nasconde la finestra; se non è mai stata aperta la avvia."""
    pid = _pid_vivo()
    if pid:
        os.kill(pid, signal.SIGUSR1)
        return
    config.CARTELLA_RUNTIME.mkdir(parents=True, exist_ok=True)
    with open(config.CARTELLA_RUNTIME / "finestra.log", "ab") as log:
        subprocess.Popen(
            [sys.executable, "-m", "alfred", "finestra"],
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def _avvisa(titolo: str, testo: str) -> None:
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "Alfred", titolo, testo], check=False)


def gestisci_servizio(comando: str) -> None:
    """spegni: ferma servizio e finestra (ripartono al prossimo accesso).
    riavvia: riavvia il servizio (lo avvia se era fermo)."""
    pid = _pid_vivo()
    if pid:
        os.kill(pid, signal.SIGTERM)  # la finestra ripartirà con Mod+A
    if comando == "spegni":
        subprocess.run(["systemctl", "--user", "stop", "alfred-core"], check=False)
        _avvisa("Alfred si è congedato", "Il servizio è fermo. Per richiamarlo: Alfred: riavvia.")
    else:
        esito = subprocess.run(["systemctl", "--user", "restart", "alfred-core"], check=False)
        if esito.returncode == 0:
            _avvisa("Alfred è di nuovo in servizio", "A sua disposizione, signore.")
        else:
            _avvisa("Alfred non riparte", "Controllare con: systemctl --user status alfred-core")


def avvia() -> None:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GLib, Gtk, WebKit2

    # Su Wayland diventa l'app-id della finestra (usato dalla regola di niri).
    GLib.set_prgname("alfred")
    GLib.set_application_name("Alfred")

    url = config.url_core()

    finestra = Gtk.Window(title="Alfred")
    finestra.set_default_size(1280, 800)

    impostazioni = WebKit2.Settings(
        enable_developer_extras=bool(os.environ.get("ALFRED_DEBUG")),
        hardware_acceleration_policy=WebKit2.HardwareAccelerationPolicy.ALWAYS,
    )
    vista = WebKit2.WebView(settings=impostazioni)
    vista.set_background_color(Gdk.RGBA(0.05, 0.07, 0.09, 1))
    finestra.add(vista)

    def riprova():
        vista.load_uri(url)
        return GLib.SOURCE_REMOVE

    def caricamento_fallito(_vista, _evento, uri, _errore):
        # Il servizio non risponde ancora: pagina d'attesa e nuovo tentativo.
        vista.load_alternate_html(PAGINA_ATTESA, uri, None)
        GLib.timeout_add_seconds(2, riprova)
        return True

    vista.connect("load-failed", caricamento_fallito)

    def mostra():
        finestra.fullscreen()
        finestra.show_all()
        finestra.present()
        vista.grab_focus()
        vista.run_javascript("window.alfredMostrato && window.alfredMostrato()", None, None, None)

    def alterna():
        if finestra.get_visible():
            finestra.hide()
        else:
            mostra()
        return GLib.SOURCE_CONTINUE

    def tasto(_finestra, evento):
        if evento.keyval == Gdk.KEY_Escape:
            finestra.hide()
            return True
        if evento.keyval == Gdk.KEY_F5:
            vista.reload()
            return True
        return False

    def chiusura(_finestra, _evento):
        # Chiudere la finestra (es. Mod+Q) la nasconde soltanto.
        finestra.hide()
        return True

    finestra.connect("key-press-event", tasto)
    finestra.connect("delete-event", chiusura)

    config.CARTELLA_RUNTIME.mkdir(parents=True, exist_ok=True)
    FILE_PID.write_text(str(os.getpid()))
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, alterna)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit())

    vista.load_uri(url)
    mostra()
    try:
        Gtk.main()
    finally:
        FILE_PID.unlink(missing_ok=True)

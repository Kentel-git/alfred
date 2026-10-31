"""Riga di comando: alfred core | finestra | toggle."""

import sys

USO = """Uso: alfred <comando>

  core      avvia il servizio (di solito lo fa systemd)
  finestra  apre la finestra di Alfred
  toggle    mostra o nasconde la finestra (per la scorciatoia)
  ascolta   apre il microfono per una frase (per la scorciatoia)
  spegni    ferma Alfred (servizio e finestra) fino al prossimo accesso
  riavvia   riavvia Alfred
  mcp       server MCP con gli strumenti (lo avvia il cervello)
  google    collega l'agenda di Google Calendar (apre il browser)
"""


def main() -> None:
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "core":
        from alfred.core.server import avvia

        avvia()
    elif comando == "finestra":
        from alfred.finestra import avvia

        avvia()
    elif comando == "ascolta":
        import httpx

        from alfred import config

        httpx.post(f"{config.url_core()}/api/ascolta", timeout=5)
    elif comando in ("spegni", "riavvia"):
        from alfred.finestra import gestisci_servizio

        gestisci_servizio(comando)
    elif comando == "toggle":
        from alfred.finestra import toggle

        toggle()
    elif comando == "google":
        from alfred.tools.agenda import autorizza

        autorizza()
    elif comando == "mcp":
        from alfred.mcp_server import avvia

        avvia()
    else:
        print(USO, end="")
        sys.exit(0 if comando in ("-h", "--help", "aiuto") else 2)


if __name__ == "__main__":
    main()

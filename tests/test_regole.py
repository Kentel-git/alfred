"""Le regole che nessuno deve rompere senza accorgersene.

Si lancia con `pytest` oppure, senza dipendenze, con:
    .venv/bin/python -m tests.test_regole
"""

import time
from datetime import date, timedelta
from unittest import mock

from alfred.brain.economo import Economo
from alfred.core import azioni
from alfred.core.comandi import riconosci
from alfred.core.server import origine_fidata
from alfred.voce.parola import per_la_voce
from alfred.voce.sveglia import verifica


def test_comandi_diretti():
    casi = {
        "Avvia la diretta!": "avvia_diretta",
        "Alfred, modalità gioco": "modalita_gioco",
        "passa alla scena just chatting": "cambia_scena",
        "Cosa ho domani?": "leggi_agenda",
        "Mandami su Telegram: comprare il latte": "invia_telegram",
        "Sì": "conferma",
        "No, lascia stare": "annulla",
        "basta così": "zittisci",
        "smetti di ascoltare": "sveglia_spenta",
        "metti in standby": "sospendi_computer",
        # Al cervello: troppo lunghe o sfumate per un comando diretto.
        "avvia la diretta tra dieci minuti": None,
        "Che ne pensi della diretta di ieri?": None,
        "puoi andare in standby": None,
    }
    for frase, atteso in casi.items():
        trovato = riconosci(frase)
        assert (trovato and trovato[0]) == atteso, (frase, trovato)
    assert riconosci("Mandami su Telegram: comprare il latte")[1] == {"testo": "comprare il latte"}


def test_sveglia_distingue_il_nome():
    assert verifica("Alfred, che ore sono?") == ("chiamata", "che ore sono?")
    assert verifica("Alfredi")[0] == "solo_nome"
    assert verifica("Ehi Alfred.")[0] == "solo_nome"
    assert verifica("Mettilo al freddo, nel frigorifero.")[0] == "no"
    assert verifica("Alfredo mi senti?") == ("chiamata", "mi senti?")
    assert verifica("È arrivato Alfredo in ritardo.")[0] == "no"


def test_economo():
    cfg = {"cervello": {"quotidiano": "haiku", "profondo": "sonnet"},
           "economia": {"parsimonia_settimana": 0.5, "austerita_settimana": 0.8,
                        "austerita_sessione": 0.9, "anticipo_sul_ritmo": 0.15}}
    e = Economo(cfg)

    def limiti(settimana, sessione=0.1, giorni_al_rinnovo=3.5):
        return {"settimana": {"uso": settimana, "rinnovo": time.time() + giorni_al_rinnovo * 86400},
                "sessione": {"uso": sessione}}

    assert e.regime(limiti(0.30))["nome"] == "normale"
    assert e.regime(limiti(0.55))["nome"] == "parsimonia"
    assert e.regime(limiti(0.35, giorni_al_rinnovo=6))["nome"] == "parsimonia"  # troppo in fretta
    assert e.regime(limiti(0.82))["nome"] == "austerità"
    assert e.regime(limiti(0.2, sessione=0.92))["nome"] == "austerità"
    assert e.scegli("Che ore sono?", limiti(0.1)) == "haiku"
    assert e.scegli("Secondo te dovrei spostare la diretta?", limiti(0.1)) == "sonnet"
    assert e.scegli("Avvia OBS", limiti(0.85)) is None
    assert e.scegli("Alfred, è importante", limiti(0.85)) == "haiku"


def test_domani_di_notte():
    oggi = date.today()
    with mock.patch.object(azioni, "notte_fonda", return_value=True):
        assert azioni.giorno_richiesto("domani") == oggi
        assert azioni.giorno_richiesto("oggi") == oggi
    with mock.patch.object(azioni, "notte_fonda", return_value=False):
        assert azioni.giorno_richiesto("domani") == oggi + timedelta(days=1)


def test_testo_per_la_voce():
    assert per_la_voce("Domani all'8:30 «Dentista», alle 21:00 la diretta. Fuori 8°C, umidità 89% 🎙") == \
        "Domani all'8 e 30 Dentista, alle 21 la diretta. Fuori 8 gradi, umidità 89 per cento"


def test_solo_l_hud_di_alfred():
    assert origine_fidata(None)  # programmi locali (server MCP, script)
    assert origine_fidata("http://127.0.0.1:7878")
    assert not origine_fidata("https://sito-malevolo.example")
    assert not origine_fidata("http://127.0.0.1:7878.sito-malevolo.example")


def test_ore_di_silenzio():
    from datetime import datetime

    from alfred.core.iniziativa import ora_di_silenzio

    with mock.patch("alfred.core.iniziativa._impostazioni", return_value={"silenzio": [23, 8]}):
        assert ora_di_silenzio(datetime(2026, 11, 1, 23, 30))
        assert ora_di_silenzio(datetime(2026, 11, 1, 7, 59))
        assert not ora_di_silenzio(datetime(2026, 11, 1, 8, 0))
        assert not ora_di_silenzio(datetime(2026, 11, 1, 22, 59))


def test_promemoria():
    from datetime import datetime

    from alfred.core.iniziativa import da_avvisare, testo_promemoria

    adesso = datetime(2026, 11, 1, 18, 0).astimezone()
    imp = {"anticipo_minuti": 15, "anticipi": {"TURNI REDAZIONE": 60},
           "calendario_dirette": "Lore is Magic", "anticipo_dirette": 30}

    def evento(id, minuti, calendario="Settimana Pietro", tutto_il_giorno=False):
        return {"id": id, "titolo": id, "nome_calendario": calendario, "tutto_il_giorno": tutto_il_giorno,
                "inizio": (adesso + timedelta(minutes=minuti)).isoformat()}

    eventi = [evento("dentista", 15), evento("cena", 40), evento("desk", 60, "TURNI REDAZIONE"),
              evento("live", 30, "Lore is Magic"), evento("fiera", 0, tutto_il_giorno=True),
              evento("già detto", 10), evento("passato", -5)]
    scelti = {e["id"]: diretta for e, diretta in da_avvisare(eventi, adesso, {"già detto"}, imp)}
    assert scelti == {"dentista": False, "desk": False, "live": True}
    assert testo_promemoria(eventi[0], adesso, False) == "Signore, tra un quarto d'ora: «dentista»."
    assert testo_promemoria(eventi[2], adesso, False).startswith("Signore, tra un'ora")


def test_link_della_chat():
    from alfred.core.azioni import ID_VIDEO

    for link in ("https://www.youtube.com/live/AbCdEfGhIj1?si=x", "https://youtu.be/AbCdEfGhIj1",
                 "https://www.youtube.com/watch?v=AbCdEfGhIj1&t=3", "AbCdEfGhIj1"):
        m = ID_VIDEO.search(link)
        assert m and (m[1] or m[2]) == "AbCdEfGhIj1", link
    assert riconosci("chat: https://youtube.com/live/AbCdEfGhIj1") == \
        ("aggiorna_chat", {"link": "https://youtube.com/live/AbCdEfGhIj1"})


def test_diario_solo_ultimi_giorni():
    from alfred.brain import _ultimi_giorni

    diario = "\n".join(f"\n## 2026-10-{g:02d}\nGiorno {g}." for g in range(1, 11))
    ultimi = _ultimi_giorni(diario, 7)
    assert ultimi.count("## ") == 7 and "Giorno 10." in ultimi and "Giorno 3." not in ultimi


def test_cervello_gratuito_spento_o_assente():
    # None = si torna al comportamento senza cervello gratuito (risposta fissa, diario con Claude).
    import asyncio

    from alfred import config
    from alfred.brain import gratuito

    for url in ("", "http://127.0.0.1:9/v1"):  # spento; acceso ma irraggiungibile
        cfg = config.PREDEFINITI | {"cervello_gratuito": {"url": url, "modello": "auto", "attesa_massima": 2}}
        with mock.patch.object(config, "carica", return_value=cfg):
            assert asyncio.run(gratuito.chiedi([{"role": "user", "content": "ciao"}], "sistema")) is None, url


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)

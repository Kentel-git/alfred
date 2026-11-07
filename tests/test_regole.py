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
        "Metti un timer di 10 minuti": "timer",
        "avvisami tra mezz'ora": "timer",
        "annulla il timer": "annulla_attivita",
        "alza il volume": "volume",
        "volume al 40%": "volume",
        "metti in pausa la musica": "riproduzione",
        "prossima canzone": "riproduzione",
        "riprendi la registrazione": "riprendi_registrazione",
        "apri un file che non esiste da nessuna parte": None,
        "Annota: comprare le corde": "cattura",
        "segna in agenda la riunione di venerdì": None,  # l'agenda non è l'Inbox
        "quali attività ho domani": "attivita_di_oggi",
        "Cosa devo fare oggi?": None,  # agenda o attività: decide il cervello
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
    durate = {"timer di 30 secondi": 0.5, "timer 5": 5, "avvisami tra un'ora": 60,
              "timer di un quarto d'ora": 15, "avvisami tra 2 ore": 120, "timer di mezz'ora, grazie": 30}
    for frase, minuti in durate.items():
        assert riconosci(frase) == ("timer", {"minuti": minuti}), frase
    assert riconosci("avvia la diretta ora") == ("avvia_diretta", {})  # "ora" resta una cortesia
    assert riconosci("volume 30") == ("volume", {"azione": "imposta", "livello": 30})


def test_sveglia_distingue_il_nome():
    assert verifica("Alfred, che ore sono?") == ("chiamata", "che ore sono?")
    assert verifica("Alfredi")[0] == "solo_nome"
    assert verifica("Ehi Alfred.")[0] == "solo_nome"
    assert verifica("Mettilo al freddo, nel frigorifero.")[0] == "no"
    assert verifica("Alfredo mi senti?") == ("chiamata", "mi senti?")
    assert verifica("È arrivato Alfredo in ritardo.")[0] == "no"


def test_durata_a_parole():
    from alfred.core.parole import durata

    assert [durata(s) for s in (30, 60, 90, 900, 3600, 5400, 3725)] == [
        "30 secondi", "un minuto", "un minuto e 30 secondi", "un quarto d'ora", "un'ora",
        "un'ora e 30 minuti", "un'ora, 2 minuti e 5 secondi"]


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


def test_notion_testo_e_proprieta():
    from alfred.tools.notion import _riga, blocchi, valori_per_notion

    righe = ["# Spesa", "- latte", "[ ] uova", "[x] pane", "Nota libera"]
    b = blocchi("\n".join(righe) + "\n\n")
    assert [x["type"] for x in b] == ["heading_1", "bulleted_list_item", "to_do", "to_do", "paragraph"]
    for x in b:  # i blocchi creati si rileggono uguali
        x[x["type"]]["rich_text"] = [{"plain_text": t["text"]["content"]} for t in x[x["type"]]["rich_text"]]
    assert [_riga(x) for x in b] == righe
    assert len(blocchi("a" * 4500)[0]["paragraph"]["rich_text"]) == 3  # pezzi da 2000
    schema = {"Nome": {"type": "title"}, "Stato": {"type": "status"}, "Scadenza": {"type": "date"},
              "Tag": {"type": "multi_select"}}
    assert valori_per_notion(schema, {"Stato": "Fatto", "Scadenza": "2026-11-07", "Tag": "lavoro"}) == {
        "Stato": {"status": {"name": "Fatto"}}, "Scadenza": {"date": {"start": "2026-11-07", "end": None}},
        "Tag": {"multi_select": [{"name": "lavoro"}]}}
    try:
        valori_per_notion(schema, {"Priorità": "alta"})
        raise AssertionError("proprietà inesistente accettata")
    except Exception as errore:
        assert "Priorità" in str(errore)


def test_pronuncia_inglese():
    from kokoro_onnx.tokenizer import Tokenizer

    from alfred.voce.parola import INGLESE_BASE, fonemi

    vocabolario = Tokenizer().vocab
    misto = fonemi("Lo streaming su YouTube parte alle 21.", INGLESE_BASE, vocabolario)
    assert "juː" in misto and "ventˈuno" in misto and "(en)" not in misto and "en" not in misto.split()[1]
    assert fonemi("Il link è nel linkage.", ["link"], vocabolario).count("lˈɪŋk") == 1  # solo la parola intera
    italiano = fonemi("Nessuna parola inglese qui.", INGLESE_BASE, vocabolario)
    assert italiano == fonemi("Nessuna parola inglese qui.", [], vocabolario)


def test_impara_pronuncia():
    import tempfile
    from pathlib import Path

    from alfred import config
    from alfred.voce import parola

    with tempfile.TemporaryDirectory() as cartella, mock.patch.object(config, "CARTELLA_STATO", Path(cartella)):
        assert parola.impara(["Skyborne", "notion", " ", "Skyborne"], True) == ["Skyborne"]  # Notion c'è già
        assert parola.impara(["post"], False) == []  # già nell'elenco base
        assert parola.impara(["Andarun"], False) == ["Andarun"]
        inglesi, italiane = parola.parole_note()
        assert "Skyborne" in inglesi and italiane == ["Andarun"]
        assert parola.impara(["andarun", "SKYBORNE"], True) == []  # già decise, in qualunque maiuscola


def test_attivita():
    import asyncio
    import tempfile
    from pathlib import Path

    from alfred import config
    from alfred.core import attivita

    async def prova(cartella: Path):
        a = attivita.Attivita()
        t = await a.aggiungi("timer", soglia=10, etichetta="la pasta")
        f = cartella / "reel.mp4"
        await a.aggiungi("file", valore=str(f))
        try:
            await a.aggiungi("processo", valore="programma-che-non-esiste")
            raise AssertionError("processo inesistente accettato")
        except attivita.AttivitaNonValida:
            pass
        assert len(attivita.Attivita().voci) == 2  # salvate: sopravvivono a un riavvio
        assert await a._avvenuta(t, None) is None
        t["scadenza"] = 0  # scaduto mentre Alfred era spento
        assert "mentre ero spento" in await a._avvenuta(t, None) and "la pasta" in await a._avvenuta(t, None)
        sorveglia_file = a.voci[1]
        f.write_bytes(b"x" * 10)
        risposte = [await a._avvenuta(sorveglia_file, None) for _ in range(4)]
        assert risposte[:3] == [None, None, None] and "reel.mp4" in risposte[3]  # pronto quando smette di crescere
        assert await a.annulla(tipo="timer") == 1 and await a.annulla() == 1 and not a.voci

    with tempfile.TemporaryDirectory() as cartella, mock.patch.object(config, "CARTELLA_STATO", Path(cartella)):
        asyncio.run(prova(Path(cartella)))


def test_script_dell_hud():
    """Un errore di sintassi in app.js spegne tutto l'HUD senza dire nulla."""
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("node"):
        return  # senza Node.js il controllo si salta
    app = Path(__file__).parent.parent / "ui" / "app.js"
    esito = subprocess.run(["node", "--check", str(app)], capture_output=True, text=True)
    assert esito.returncode == 0, esito.stderr


def test_second_brain():
    import tempfile
    from datetime import date
    from pathlib import Path

    from alfred import config
    from alfred.tools import vault

    with tempfile.TemporaryDirectory() as cartella:
        wiki = Path(cartella) / "wiki"
        for d in ("Progetti", "Aree", "Diario", "Modelli", "Alfred"):
            (wiki / d).mkdir(parents=True)
        (wiki / "Inbox.md").write_text("---\ntitle: Inbox\n---\n# Inbox\n\n- prima idea\n")
        (wiki / "Alfred" / "contesto.md").write_text("---\ntitle: x\n---\n# Contesto\n- Vive a Isernia.\n")
        (wiki / "Modelli" / "Giorno.md").write_text(
            "---\ntitle: \"{{date}}\"\n---\n# {{date:dddd D MMMM YYYY}}\n\n## Briefing\n- \n\n## Chiusura serale\n- \n")
        (wiki / "Progetti" / "Alfred.md").write_text(
            "# Alfred\n\n## Attività\n- [x] fatto\n- [ ] collegare il vault @2026-11-01\n\n## Note\nIl maggiordomo usa Kokoro.\n")
        (wiki / "Aree" / "Salute.md").write_text("# Salute\n\nCamminare ogni giorno.\n")
        with mock.patch.object(config, "carica", return_value={"vault": {"percorso": cartella}}):
            assert vault.contesto() == "# Contesto\n- Vive a Isernia."
            vault.cattura("comprare  le\ncorde")
            assert (wiki / "Inbox.md").read_text().endswith("- prima idea\n- comprare le corde\n")
            vault.aggiungi_attivita("alfred", "provare la dettatura", date(2026, 11, 9))
            testo = (wiki / "Progetti" / "Alfred.md").read_text()
            assert "- [ ] collegare il vault @2026-11-01\n- [ ] provare la dettatura @2026-11-09\n\n## Note" in testo
            vault.aggiungi_attivita("Salute", "visita")  # sezione che non c'è: si crea in fondo
            assert (wiki / "Aree" / "Salute.md").read_text().endswith("## Attività\n- [ ] visita\n")
            entro = vault.attivita(fino_a=date(2026, 11, 5))
            assert [a["testo"] for a in entro] == ["collegare il vault"]  # le altre scadono dopo o senza data
            assert len(vault.attivita()) == 3
            assert vault.cerca("kokoro maggiordomo")[0]["nota"] == "Progetti/Alfred"
            vault.scrivi_diario(date(2026, 11, 7), "Ha collegato il vault.")
            giorno = (wiki / "Diario" / "2026-11-07.md").read_text()
            assert "# Sabato 7 novembre 2026" in giorno and "## Chiusura serale\n- Ha collegato il vault.\n" in giorno
            assert "- \n\n## Chiusura" in giorno  # il segnaposto del Briefing resta a Pietro
            assert vault.diario_recente(7) == "## 2026-11-07\n- Ha collegato il vault."


if __name__ == "__main__":
    for nome, prova in list(globals().items()):
        if nome.startswith("test_"):
            prova()
            print("ok", nome)

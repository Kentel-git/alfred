"""Il second brain: un vault Obsidian (metodo PARA) letto e scritto da Alfred.

Il percorso sta in config.toml ([vault] percorso = "~/…"); senza, Alfred fa a
meno del vault. Le note stanno sotto wiki/:

- wiki/Alfred/contesto.md  l'unico file che Alfred carica sempre (breve)
- wiki/Inbox.md            cattura veloce: una riga in fondo per cosa
- wiki/Diario/AAAA-MM-GG.md nota del giorno (modello wiki/Modelli/Giorno.md);
                            il diario di Alfred va nella sezione "Chiusura serale"
- attività: righe "- [ ] testo @AAAA-MM-GG" (data facoltativa = scadenza)
  dentro le note dei progetti e delle aree

Tutto a costo zero: si cerca e si scrive senza modello. Nel vault si aggiunge,
non si cancella.
"""

import re
import unicodedata
from datetime import date
from pathlib import Path

from alfred import config
from alfred.core import parole

ESCLUSE = ("Modelli", "Allegati", "meta")  # cartelle di wiki/ dove non si cerca
ATTIVITA = re.compile(r"^\s*- \[ \]\s+(?P<testo>.+?)(?:\s+@(?P<data>\d{4}-\d{2}-\d{2}))?\s*$")
MAX_NOTA = 6000  # caratteri di una nota letta per intero


class VaultNonPronto(Exception):
    pass


def radice() -> Path | None:
    percorso = config.carica().get("vault", {}).get("percorso")
    if not percorso:
        return None
    cartella = Path(percorso).expanduser()
    return cartella if (cartella / "wiki").is_dir() else None


def _wiki() -> Path:
    if not (r := radice()):
        raise VaultNonPronto("il second brain non è collegato: manca [vault] percorso in config.toml")
    return r / "wiki"


def _semplice(testo: str) -> str:
    testo = unicodedata.normalize("NFKD", testo.lower())
    return "".join(c for c in testo if not unicodedata.combining(c))


def _senza_frontmatter(testo: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", testo, flags=re.S).strip()


def _note() -> list[Path]:
    wiki = _wiki()
    return [p for p in wiki.rglob("*.md")
            if not any(parte in ESCLUSE for parte in p.relative_to(wiki).parts[:-1])]


def _nome(p: Path) -> str:
    return str(p.relative_to(_wiki()).with_suffix(""))


# --- Lettura --------------------------------------------------------------------------

def contesto() -> str:
    """wiki/Alfred/contesto.md senza frontmatter ("" se manca)."""
    try:
        f = _wiki() / "Alfred" / "contesto.md"
    except VaultNonPronto:
        return ""
    return _senza_frontmatter(f.read_text()) if f.exists() else ""


def cerca(testo: str, quante: int = 6) -> list[dict]:
    """Le note più pertinenti, ciascuna con i paragrafi che contengono le parole cercate.

    shortcut: punteggio per parole contate, senza indice; con qualche migliaio
    di note conviene un indice BM25 (wiki-retrieve del plugin claude-obsidian).
    """
    parole_cercate = [p for p in re.findall(r"\w+", _semplice(testo)) if len(p) >= 3]
    if not parole_cercate:
        return []
    risultati = []
    for nota in _note():
        nome, corpo = _semplice(nota.stem), _senza_frontmatter(nota.read_text(errors="replace"))
        semplice = _semplice(corpo)
        punti = sum(3 * nome.count(p) + semplice.count(p) for p in parole_cercate)
        presenti = sum(1 for p in parole_cercate if p in nome or p in semplice)
        if not presenti:
            continue
        paragrafi = [par.strip() for par in re.split(r"\n\s*\n", corpo) if par.strip()]
        utili = sorted(paragrafi, key=lambda par: -sum(_semplice(par).count(p) for p in parole_cercate))
        estratti = [par[:400] for par in utili[:2] if any(p in _semplice(par) for p in parole_cercate)]
        # Prima le note che contengono tutte le parole, poi le più fitte.
        risultati.append((presenti, punti, {"nota": _nome(nota), "estratti": estratti}))
    risultati.sort(key=lambda r: (-r[0], -r[1]))
    return [r[2] for r in risultati[:quante]]


def trova_nota(nome: str) -> Path:
    """Una nota per nome ("Alfred", "Progetti/Alfred"); errore se manca o è ambigua."""
    cercato = _semplice(nome.strip().removesuffix(".md"))
    note = _note()
    esatte = [n for n in note if _semplice(_nome(n)) == cercato or _semplice(n.stem) == cercato]
    if not esatte:
        esatte = [n for n in note if cercato in _semplice(n.stem)]
    if len(esatte) == 1:
        return esatte[0]
    if not esatte:
        raise VaultNonPronto(f"non trovo la nota «{nome}»")
    raise VaultNonPronto(f"«{nome}» può essere: {', '.join(_nome(n) for n in esatte[:6])}")


def leggi(nome: str) -> dict:
    nota = trova_nota(nome)
    corpo = _senza_frontmatter(nota.read_text(errors="replace"))
    return {"nota": _nome(nota), "testo": corpo[:MAX_NOTA], "troncata": len(corpo) > MAX_NOTA}


def attivita(fino_a: date | None = None, senza_data: bool = False) -> list[dict]:
    """Attività aperte. fino_a: solo quelle che scadono entro quel giorno (anche
    già scadute); senza_data: includi anche quelle senza scadenza."""
    trovate = []
    for nota in _note():
        if nota.name == "Attività.md":
            continue
        for riga in nota.read_text(errors="replace").splitlines():
            if not (m := ATTIVITA.match(riga)):
                continue
            scadenza = date.fromisoformat(m["data"]) if m["data"] else None
            if fino_a and not (scadenza and scadenza <= fino_a) and not (senza_data and not scadenza):
                continue
            trovate.append({"testo": m["testo"].strip(), "scadenza": m["data"], "nota": _nome(nota)})
    return sorted(trovate, key=lambda a: (a["scadenza"] or "9999", a["nota"]))


# --- Scrittura ------------------------------------------------------------------------

def cattura(testo: str) -> None:
    """Una riga in fondo a wiki/Inbox.md."""
    inbox = _wiki() / "Inbox.md"
    contenuto = inbox.read_text() if inbox.exists() else "# Inbox\n"
    riga = " ".join(testo.split())
    inbox.write_text(contenuto.rstrip("\n") + f"\n- {riga}\n")


def _aggiungi_in_sezione(testo: str, titolo: str, righe: list[str]) -> str:
    """Aggiunge righe in fondo alla sezione "## titolo" (creandola se manca).
    Un segnaposto vuoto ("- ") del modello viene sostituito."""
    linee = testo.rstrip("\n").split("\n")
    try:
        inizio = next(i for i, l in enumerate(linee) if l.strip() == f"## {titolo}")
    except StopIteration:
        return "\n".join(linee) + f"\n\n## {titolo}\n" + "\n".join(righe) + "\n"
    fine = next((i for i in range(inizio + 1, len(linee)) if linee[i].startswith("#")), len(linee))
    sezione = [l for l in linee[inizio + 1:fine] if l.strip() not in ("-", "- [ ]")]
    while sezione and not sezione[-1].strip():
        sezione.pop()
    nuova = sezione + righe + ([""] if fine < len(linee) else [])
    return "\n".join(linee[:inizio + 1] + nuova + linee[fine:]) + "\n"


def aggiungi_attivita(nome: str, testo: str, scadenza: date | None = None) -> str:
    """Aggiunge "- [ ] testo @data" nella sezione Attività della nota. Restituisce la nota."""
    nota = trova_nota(nome)
    riga = "- [ ] " + " ".join(testo.split()) + (f" @{scadenza.isoformat()}" if scadenza else "")
    nota.write_text(_aggiungi_in_sezione(nota.read_text(), "Attività", [riga]))
    return _nome(nota)


def nota_del_giorno(giorno: date) -> Path:
    """wiki/Diario/AAAA-MM-GG.md, creata dal modello se non c'è ancora."""
    wiki = _wiki()
    nota = wiki / "Diario" / f"{giorno.isoformat()}.md"
    if not nota.exists():
        modello = wiki / "Modelli" / "Giorno.md"
        testo = modello.read_text() if modello.exists() else "# {{date}}\n"
        esteso = f"{parole.GIORNI[giorno.weekday()]} {giorno.day} {parole.MESI[giorno.month - 1]} {giorno.year}"
        testo = re.sub(r"\{\{date:[^}]*\}\}", esteso.capitalize(), testo).replace("{{date}}", giorno.isoformat())
        nota.parent.mkdir(parents=True, exist_ok=True)
        nota.write_text(testo)
    return nota


def scrivi_diario(giorno: date, riassunto: str) -> None:
    nota = nota_del_giorno(giorno)
    righe = [f"- {r.strip().removeprefix('- ')}" for r in riassunto.strip().splitlines() if r.strip()]
    nota.write_text(_aggiungi_in_sezione(nota.read_text(), "Chiusura serale", righe))


def diario_recente(giorni: int) -> str:
    """Le chiusure serali degli ultimi giorni che ne hanno una, dal più vecchio."""
    try:
        cartella = _wiki() / "Diario"
    except VaultNonPronto:
        return ""
    voci = []
    for nota in sorted(cartella.glob("????-??-??.md"))[::-1]:
        m = re.search(r"^## Chiusura serale\n(.*?)(?=^#|\Z)", nota.read_text(), flags=re.S | re.M)
        corpo = m and "\n".join(l for l in m[1].strip().splitlines() if l.strip() not in ("-", ""))
        if corpo:
            voci.append(f"## {nota.stem}\n{corpo}")
        if len(voci) == giorni:
            break
    return "\n".join(voci[::-1])

"""Notion: le pagine e i database di Pietro tramite le API ufficiali.

Configurazione una tantum (vedi docs/NOTION.md): un'integrazione interna creata
su notion.so/profile/integrations, con il token in secrets.env (NOTION_TOKEN).
Alfred vede solo le pagine condivise con l'integrazione ("Connessioni" nel menu
di ogni pagina): è Pietro a decidere cosa gli mostra.

Le pagine si leggono e si scrivono come testo semplice, una riga per blocco:
"# titolo", "## sottotitolo", "- punto", "[ ] da fare", "[x] fatto", "> citazione".
"""

import httpx

from alfred import config

API = "https://api.notion.com/v1"
# shortcut: versione 2022-06-28 (database senza "data source"), finché Notion la
# mantiene; passare alla 2025-09-03 se servono database con più origini.
VERSIONE = "2022-06-28"
MAX_BLOCCHI = 300  # una pagina più lunga si legge solo in parte
TESTO_MAX = 2000  # limite di Notion per un singolo pezzo di testo


class NotionNonPronto(Exception):
    pass


def pronto() -> bool:
    return bool(config.segreto("NOTION_TOKEN"))


async def _chiama(metodo: str, percorso: str, dati: dict | None = None) -> dict:
    token = config.segreto("NOTION_TOKEN")
    if not token:
        raise NotionNonPronto("manca NOTION_TOKEN in secrets.env")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.request(metodo, API + percorso, json=dati, headers={
            "Authorization": f"Bearer {token}", "Notion-Version": VERSIONE})
    if r.status_code >= 400:
        raise NotionNonPronto(r.json().get("message", r.text))
    return r.json()


# --- Da Notion a testo ------------------------------------------------------------

def _testo(ricco: list) -> str:
    return "".join(t.get("plain_text", "") for t in ricco)


def _titolo(oggetto: dict) -> str:
    if oggetto["object"] == "database":
        return _testo(oggetto.get("title", [])) or "(senza titolo)"
    for p in oggetto.get("properties", {}).values():
        if p["type"] == "title":
            return _testo(p["title"]) or "(senza titolo)"
    return "(senza titolo)"


def _valore(p: dict):
    """Una proprietà di Notion come valore semplice."""
    tipo, v = p["type"], p.get(p["type"])
    if tipo in ("title", "rich_text"):
        return _testo(v)
    if tipo in ("select", "status"):
        return v and v["name"]
    if tipo == "multi_select":
        return [o["name"] for o in v]
    if tipo == "date":
        return v and (v["start"] + (f" → {v['end']}" if v.get("end") else ""))
    if tipo in ("checkbox", "number", "url", "email", "phone_number", "created_time", "last_edited_time"):
        return v
    if tipo == "formula":
        return v.get(v["type"])
    return None  # relazioni, persone, file: non servono a voce


def _proprieta(pagina: dict) -> dict:
    return {nome: _valore(p) for nome, p in pagina["properties"].items() if _valore(p) not in (None, "", [])}


PREFISSI = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ", "bulleted_list_item": "- ",
            "numbered_list_item": "1. ", "quote": "> ", "callout": "> "}


def _riga(blocco: dict) -> str:
    tipo = blocco["type"]
    corpo = blocco.get(tipo, {})
    if tipo == "to_do":
        return ("[x] " if corpo.get("checked") else "[ ] ") + _testo(corpo["rich_text"])
    if tipo == "child_page":
        return f"[pagina] {corpo['title']}"
    if tipo == "child_database":
        return f"[database] {corpo['title']}"
    if "rich_text" in corpo:
        return PREFISSI.get(tipo, "") + _testo(corpo["rich_text"])
    return ""


# --- Da testo a Notion ------------------------------------------------------------

def _ricco(testo: str) -> list:
    return [{"type": "text", "text": {"content": testo[i:i + TESTO_MAX]}}
            for i in range(0, len(testo), TESTO_MAX)] or [{"type": "text", "text": {"content": ""}}]


def blocchi(testo: str) -> list[dict]:
    """Testo semplice → blocchi di Notion, una riga per blocco."""
    risultato = []
    for riga in testo.splitlines():
        if not riga.strip():
            continue
        tipo = "paragraph"
        for prefisso, t in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"),
                            ("- ", "bulleted_list_item"), ("> ", "quote"), ("[ ] ", "to_do"), ("[x] ", "to_do")):
            if riga.startswith(prefisso):
                tipo, riga = t, riga[len(prefisso):]
                break
        corpo = {"rich_text": _ricco(riga)}
        if tipo == "to_do":
            corpo["checked"] = prefisso == "[x] "
        risultato.append({"object": "block", "type": tipo, tipo: corpo})
    return risultato


def valori_per_notion(schema: dict, valori: dict) -> dict:
    """Valori semplici ({"Stato": "Fatto", "Scadenza": "2026-11-07"}) → proprietà
    di Notion, secondo lo schema del database."""
    risultato = {}
    for nome, v in valori.items():
        if nome not in schema:
            raise NotionNonPronto(f"il database non ha la proprietà «{nome}» (ci sono: {', '.join(schema)})")
        tipo = schema[nome]["type"]
        if tipo in ("title", "rich_text"):
            risultato[nome] = {tipo: _ricco(str(v))}
        elif tipo in ("select", "status"):
            risultato[nome] = {tipo: {"name": str(v)} if v else None}
        elif tipo == "multi_select":
            risultato[nome] = {tipo: [{"name": str(x)} for x in (v if isinstance(v, list) else [v])]}
        elif tipo == "date":
            inizio, _, fine = str(v).partition("→")
            risultato[nome] = {tipo: {"start": inizio.strip(), "end": fine.strip() or None} if v else None}
        elif tipo in ("checkbox", "number", "url", "email", "phone_number"):
            risultato[nome] = {tipo: v}
        else:
            raise NotionNonPronto(f"non so ancora scrivere proprietà di tipo {tipo} («{nome}»)")
    return risultato


# --- Operazioni ---------------------------------------------------------------------

def _voce(o: dict) -> dict:
    return {"id": o["id"], "tipo": "database" if o["object"] == "database" else "pagina",
            "titolo": _titolo(o), "modificata": o.get("last_edited_time", "")[:10], "url": o.get("url")}


async def cerca(testo: str) -> list[dict]:
    r = await _chiama("POST", "/search", {"query": testo, "page_size": 15,
                                           "sort": {"direction": "descending", "timestamp": "last_edited_time"}})
    return [_voce(o) for o in r["results"] if not o.get("archived")]


async def _figli(id: str) -> list[dict]:
    figli, cursore = [], None
    while len(figli) < MAX_BLOCCHI:
        r = await _chiama("GET", f"/blocks/{id}/children?page_size=100" + (f"&start_cursor={cursore}" if cursore else ""))
        figli += r["results"]
        if not r.get("has_more"):
            break
        cursore = r["next_cursor"]
    return figli


async def leggi(id: str) -> dict:
    """Una pagina (proprietà e contenuto) o un database (schema e voci)."""
    try:
        pagina = await _chiama("GET", f"/pages/{id}")
    except NotionNonPronto:
        database = await _chiama("GET", f"/databases/{id}")
        voci = await _chiama("POST", f"/databases/{id}/query", {"page_size": 50})
        return {**_voce(database), "proprieta": {
                    n: p["type"] + (f" ({', '.join(o['name'] for o in p[p['type']]['options'])})"
                                    if p["type"] in ("select", "multi_select", "status") else "")
                    for n, p in database["properties"].items()},
                "voci": [{"id": v["id"], **_proprieta(v)} for v in voci["results"]],
                "altre_voci": voci.get("has_more", False)}
    figli = await _figli(id)
    righe = [{"id": b["id"], "testo": t} for b in figli if (t := _riga(b))]
    return {**_voce(pagina), "proprieta": _proprieta(pagina), "contenuto": righe,
            "troncata": len(figli) >= MAX_BLOCCHI}


async def crea(genitore: str, titolo: str, testo: str = "", proprieta: dict | None = None) -> dict:
    """Pagina nuova dentro una pagina, o voce nuova di un database."""
    try:
        database = await _chiama("GET", f"/databases/{genitore}")
    except NotionNonPronto:
        database = None
    if database:
        schema = database["properties"]
        nome_titolo = next(n for n, p in schema.items() if p["type"] == "title")
        dati = {"parent": {"database_id": genitore},
                "properties": valori_per_notion(schema, {nome_titolo: titolo, **(proprieta or {})})}
    else:
        dati = {"parent": {"page_id": genitore}, "properties": {"title": {"title": _ricco(titolo)}}}
    if testo:
        dati["children"] = blocchi(testo)[:100]
    return _voce(await _chiama("POST", "/pages", dati))


async def aggiungi(id: str, testo: str) -> int:
    nuovi = blocchi(testo)
    for i in range(0, len(nuovi), 100):
        await _chiama("PATCH", f"/blocks/{id}/children", {"children": nuovi[i:i + 100]})
    return len(nuovi)


async def aggiorna(id: str, proprieta: dict) -> dict:
    pagina = await _chiama("GET", f"/pages/{id}")
    database = pagina["parent"].get("database_id")
    if not database:
        raise NotionNonPronto("è una pagina semplice, non una voce di database: per il testo usi riscrivi o aggiungi")
    schema = (await _chiama("GET", f"/databases/{database}"))["properties"]
    return _voce(await _chiama("PATCH", f"/pages/{id}", {"properties": valori_per_notion(schema, proprieta)}))


async def blocco(id: str) -> str:
    return _riga(await _chiama("GET", f"/blocks/{id}"))


async def riscrivi(id: str, testo: str) -> None:
    """Riscrive un blocco di testo mantenendone il tipo."""
    vecchio = await _chiama("GET", f"/blocks/{id}")
    tipo = vecchio["type"]
    if "rich_text" not in vecchio.get(tipo, {}):
        raise NotionNonPronto(f"questo blocco ({tipo}) non contiene testo")
    await _chiama("PATCH", f"/blocks/{id}", {tipo: {"rich_text": _ricco(testo)}})


async def descrivi(id: str) -> str:
    """Cosa sarebbe eliminato: il titolo della pagina o il testo del blocco."""
    try:
        return f"la pagina «{_titolo(await _chiama('GET', f'/pages/{id}'))}»"
    except NotionNonPronto:
        return f"il blocco «{(await blocco(id))[:80]}»"


async def elimina(id: str) -> None:
    """Pagine e blocchi finiscono nel cestino di Notion (recuperabili per 30 giorni)."""
    try:
        await _chiama("PATCH", f"/pages/{id}", {"archived": True})
    except NotionNonPronto:
        await _chiama("DELETE", f"/blocks/{id}")

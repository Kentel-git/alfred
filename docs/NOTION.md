# Notion

Alfred legge e scrive il Notion di chi lo usa tramite le API ufficiali, con
un'**integrazione interna**: vede solo le pagine che gli vengono condivise.

## Collegamento (una volta sola)

1. Apri <https://www.notion.so/profile/integrations> e crea una nuova
   integrazione **interna** (nome: "Alfred", area di lavoro: la tua).
2. In *Funzionalità* lascia attive lettura, aggiornamento e inserimento dei
   contenuti; le informazioni sugli utenti non servono.
3. Copia il **token interno** (`ntn_…`) e aggiungilo a
   `~/.config/alfred/secrets.env`:

   ```
   NOTION_TOKEN=ntn_...
   ```

   Il file si rilegge a ogni richiesta: non serve riavviare Alfred.
4. In Notion, su ogni pagina o database che Alfred deve vedere:
   menu `•••` → *Connessioni* → *Alfred*. Le sottopagine ereditano l'accesso,
   quindi basta condividere le pagine principali.

## Cosa sa fare

| Strumento | Conferma | |
|---|---|---|
| `notion_cerca` | no | pagine e database per titolo |
| `notion_leggi` | no | contenuto di una pagina, o schema e voci di un database |
| `notion_crea` | no | pagina nuova, o voce nuova di un database |
| `notion_aggiungi` | no | testo in fondo a una pagina |
| `notion_aggiorna` | no | campi di una voce di database (stato, date, etichette…) |
| `notion_riscrivi` | **sì** | sostituisce il testo di un blocco |
| `notion_elimina` | **sì** | pagina o blocco nel cestino (recuperabile per 30 giorni) |

Il testo passa come testo semplice, una riga per blocco: `# titolo`,
`## sottotitolo`, `- punto`, `[ ] da fare`, `[x] fatto`, `> citazione`.
Tabelle, immagini, relazioni e persone non si scrivono (si leggono solo i titoli
delle sottopagine e dei database).

Leggere e scrivere non costa riserve: il modello serve solo a capire le
richieste a parole libere.

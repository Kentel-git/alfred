# Revisione del 13 novembre 2026

Appunti per riprendere il lavoro sullo Zenbook. Li ha scritti Claude Code dopo
aver letto il repo al commit `c787809`, da un'altra macchina (macOS): **i test
non sono stati eseguiti** e nulla è stato modificato.

Per riprendere: apri Claude Code nella cartella del repo e incolla uno dei
prompt della sezione «Prompt pronti», uno per sessione. Quando un punto è
chiuso, spuntalo qui; a lavoro finito questo file si può eliminare.

## Cosa è stato letto e cosa no

- Letti per intero: `README.md`, `CLAUDE.md`, `docs/`, `config.example.toml`,
  `alfred/config.py`, `alfred/brain/` (tranne `personalita.md`),
  `alfred/core/conversazione.py`, `azioni.py`, `server.py`,
  `telegram_ponte.py`, `alfred/mcp_server.py`.
- Letti in parte: `alfred/tools/pc.py`, `vault.py`, `obs.py`, `agenda.py`,
  `tests/test_regole.py` (solo l'elenco dei test).
- Non letti: `alfred/voce/`, `ui/`, `alfred/tools/notion.py`,
  `alfred/core/attivita.py`, `iniziativa.py`, `routine.py`, `veglia.py`,
  `comandi.py`, `limiti.py`, `installa.sh` (solo le righe di pip).

Prima di toccare un punto, rileggi il codice: le righe indicate valgono per
`c787809`.

## Correzioni al codice

Ognuna va con il suo test in `tests/test_regole.py` (regola di `CLAUDE.md`).

- [ ] **1. La conferma in attesa si sovrascrive.**
  `Gestore.richiedi` (`alfred/core/azioni.py`, riga 591) assegna
  `self.in_attesa` senza guardare se ce n'è già una valida. Le proposte che
  partono da Alfred (`conferma_pronuncia` da `Conversazione._chiedi_pronuncia`,
  `proponi_chiusura`, `proponi_revisione`) possono rimpiazzare una richiesta
  del cervello come `elimina_evento`, o esserne rimpiazzate: il «sì» detto a
  voce conferma l'ultima arrivata, non quella a cui Pietro crede di rispondere.
  Correzione minima: le proposte di iniziativa non partono se
  `_attesa_valida()` restituisce qualcosa (si riproveranno dopo); una richiesta
  sensibile nuova che ne trova un'altra chiude la vecchia con
  `conferma_chiusa` e lo dice nel messaggio.
  Test: richiesta sensibile A, poi proposta di iniziativa B → resta A.

- [ ] **2. Il cervello può aprire link e cambiare l'agenda senza conferma.**
  Da verificare prima di correggere: cosa restituiscono al cervello
  `agenda.eventi_di` (descrizioni degli eventi? calendari condivisi da altri?),
  `notion.leggi` e `vault.leggi`. Se vi entra testo scritto da terzi, quel
  testo può indurre il cervello a chiamare `apri` con un link (`pc.trova`
  accetta qualunque `https?://`, `pc.apri` lo passa a `xdg-open`),
  `sposta_evento`, `crea_evento`, `notion_crea`: nessuna è `sensibile`.
  Correzione minima: `/api/azioni/{nome}` (la strada del cervello, in
  `alfred/core/server.py`) tratta come sensibile `apri` quando l'obiettivo è un
  link; i comandi diretti e i pulsanti dell'HUD restano immediati. Valutare lo
  stesso per `sposta_evento`.
  Non indebolire `origine_fidata`.

- [ ] **3. Origine della richiesta come stato condiviso.**
  In `alfred/core/conversazione.py` `self._origine`, `self._vocale_telegram` e
  `self.occupato` appartengono all'istanza. `_rispondi` copia l'origine
  all'inizio, ma `annuncia`, `_invia_da_azioni` e le conferme leggono il valore
  corrente: un messaggio Telegram arrivato mentre Alfred risponde a voce sposta
  lì esiti e conferme. `occupato` torna `False` alla prima risposta finita
  anche se ce n'è un'altra in coda dietro `CervelloClaude._turno`.
  Correzione minima: passare `origine` (e `vocale`) come parametro ad
  `annuncia` e a chi la chiama; `occupato` come contatore.

- [ ] **4. `asyncio.create_task` senza riferimento (32 punti).**
  Il ciclo degli eventi tiene solo riferimenti deboli ai compiti: uno non
  referenziato può essere raccolto prima di finire, senza errori. Correzione
  minima: una funzione in un solo posto (per esempio `alfred/core/compiti.py`)
  che crea il compito, lo mette in un `set` globale e lo toglie con
  `add_done_callback`, registrando l'eccezione se c'è; poi sostituire le
  chiamate. I compiti di `ciclo_di_vita` in `server.py` sono già tenuti in
  lista: lì non serve.

- [ ] **5. La memoria cresce e ogni «ricordati che…» riavvia il cervello.**
  `brain.personalita` mette tutto `memoria.md` nel prompt di sistema;
  `_osserva_file` (`server.py`, riga 155) riavvia il cervello a ogni modifica
  di `memoria.md`, `diario.md`, pronunce e contesto del vault, e la cache del
  prompt va ricostruita. Va contro la regola dell'economo. Da decidere con
  Pietro: tetto alle righe di `memoria.md` nel prompt (le più recenti, il
  resto cercabile), oppure consolidazione periodica nel vault; e se il riavvio
  per la memoria può aspettare la conversazione nuova del mattino.

- [ ] **6. Scritture di stato non atomiche.**
  `config.salva_stato` scrive direttamente sul file; `Conversazione._salva`
  usa già file temporaneo e `replace`. Usare lo stesso schema in `salva_stato`.

## Documentazione e flusso di lavoro

- [ ] `README.md`: «Stato: fase 0» in entrambe le lingue, con le fasi 0–4
  chiuse in `docs/ROADMAP.md`.
- [ ] `docs/ARCHITETTURA.md`: nello schema `voice/` (è `voce/`); in «Strumenti
  previsti» l'agenda è «da decidere in fase 2» (è Google Calendar, fatta);
  la voce descritta è Kokoro (la predefinita è Pocket TTS).
- [ ] `requirements.txt`: dichiarare `websockets`, `watchfiles` e `numpy`,
  importati direttamente ma installati solo per via indiretta; aggiungere un
  file di blocco (`pip freeze`) per installazioni riproducibili.
- [ ] CI: una GitHub Action che esegue `python -m tests.test_regole` a ogni
  push. I test importano `alfred.voce` e `alfred.core.server`, quindi oggi
  serve l'installazione completa: verificare quanto pesa, altrimenti separare
  i test delle regole pure da quelli che vogliono i modelli.
- [ ] Per ogni strumento nuovo si toccano tre file (`azioni.py`,
  `mcp_server.py`, `comandi.py`). Non intervenire ora: si risolve con il punto
  1 degli ampliamenti.

## Ampliamenti proposti

In ordine di resa; nessuno è deciso. Ognuno deve dichiarare quale modello usa
(regola dell'economo).

1. **Cervello locale con strumenti.** `brain/gratuito.py` oggi risponde senza
   strumenti. Ricavando gli schemi dal registro `AZIONI` (nome, descrizione,
   parametri in un solo posto) si possono passare a un endpoint compatibile
   OpenAI (Ollama) e generare da lì anche gli strumenti MCP. Chiude «cervello
   locale alternativo» in roadmap e toglie la duplicazione dei tre file.
2. **Missioni Claude Code.** «Alfred, lavora su X»: una sessione `claude` nella
   cartella del progetto, con aggiornamenti a voce e l'esito nel riquadro
   Attività. Azione sensibile; consuma riserve, quindi passa dall'economo.
3. **Ricerca sul web** come strumento in sola lettura.
4. **Fine del turno e cancellazione dell'eco** (già in roadmap): interrompere
   Alfred senza dire il suo nome, non tagliare chi fa pause.
5. **Posta in sola lettura** nel briefing del mattino, a costo zero se basta
   contare e citare i mittenti.

## Prompt pronti

Uno per sessione, nell'ordine indicato. Ogni prompt rimanda al punto
corrispondente di questo file, che contiene i dettagli. Le regole comuni
valgono per tutti e stanno nel prompt 0: gli altri le richiamano.

### 0. Regole comuni (da incollare in testa a ogni prompt)

```text
Lavori sul repo Alfred. Prima leggi CLAUDE.md e docs/REVISIONE.md.
Regole per questa sessione:
- Fai solo il punto indicato sotto. Se noti altro, scrivilo in fondo a
  docs/REVISIONE.md sotto «Trovato strada facendo» e non toccarlo.
- Prima di modificare, rileggi il codice attuale: le righe di REVISIONE.md
  valgono per il commit c787809 e l'analisi non è stata verificata eseguendo
  nulla. Se il problema descritto non c'è o è diverso, fermati e dimmelo.
- La modifica più piccola che risolve: niente astrazioni, opzioni o
  rifattorizzazioni non richieste. Mantieni stile, nomi e commenti in italiano.
- Aggiungi o aggiorna il test in tests/test_regole.py, poi esegui
  .venv/bin/python -m tests.test_regole e riporta l'esito vero, con l'output
  se fallisce.
- Non indebolire origine_fidata né le conferme delle azioni sensibili.
- Non fare commit né push: mostrami il diff e aspetta il mio sì.
- A lavoro approvato, spunta il punto in docs/REVISIONE.md.
```

### 1. Verifica preliminare (prima di tutto, sola lettura)

```text
[regole comuni]
Compito: sola lettura, nessuna modifica al codice.
1. Esegui i test e dimmi se passano tutti.
2. Per ognuno dei punti 1-6 di «Correzioni al codice» in docs/REVISIONE.md,
   leggi il codice citato e dimmi: confermato, non confermato o diverso da
   come descritto, con file e riga attuali.
3. Per il punto 2 rispondi con precisione: quali campi degli eventi
   restituisce agenda.eventi_di al cervello (descrizione? luogo? calendari
   di altri?), e cosa restituiscono notion.leggi e vault.leggi.
Scrivi l'esito in docs/REVISIONE.md sotto ogni punto, in una riga che
comincia con «Verifica:». Non correggere nulla.
```

### 2. Conferma in attesa (punto 1)

```text
[regole comuni]
Compito: punto 1 di «Correzioni al codice».
Comportamento voluto:
- una proposta di iniziativa (conferma_pronuncia, proponi_chiusura,
  proponi_revisione) non parte se c'è già un'attesa valida;
- una richiesta sensibile nuova che ne trova un'altra in attesa chiude la
  vecchia con conferma_chiusa e lo dice nel messaggio di ritorno.
Prima di scrivere, elenca tutti i punti che chiamano Gestore.richiedi e
dimmi per ognuno in quale dei due casi ricade. Controlla che la proposta
di chiusura delle 22 venga riprovata più tardi e non persa.
Test: richiesta sensibile A, poi proposta di iniziativa B → resta A;
richiesta sensibile A, poi sensibile C → resta C e A risulta chiusa.
```

### 3. Origine della richiesta (punto 3)

```text
[regole comuni]
Compito: punto 3 di «Correzioni al codice», in alfred/core/conversazione.py.
Comportamento voluto: esiti, conferme e risposte tornano al canale da cui è
partita la richiesta, anche se nel frattempo arriva un messaggio da un altro
canale; l'HUD risulta occupato finché c'è almeno una risposta in corso.
Prima di scrivere, elenca ogni lettura di self._origine,
self._vocale_telegram e self.occupato e dimmi quali possono vedere un valore
cambiato da un altro messaggio. Passa l'origine come parametro lungo la
catena; non introdurre classi nuove.
Test: richiesta da "voce" in corso, arriva un messaggio "telegram" → l'esito
della prima non va a Telegram.
```

### 4. Compiti senza riferimento (punto 4)

```text
[regole comuni]
Compito: punto 4 di «Correzioni al codice».
Una sola funzione che crea il compito, lo tiene in un set globale, lo toglie
a fine corsa e registra l'eccezione se c'è. Sostituisci le chiamate ad
asyncio.create_task il cui risultato non viene conservato; lascia stare
quelle già tenute in una variabile o in una lista (ciclo_di_vita, scrivendo,
discorso.compito). Dammi l'elenco delle chiamate sostituite e di quelle
lasciate, con il motivo.
Test: un compito che solleva un'eccezione la registra e non resta nel set.
```

### 5. Stato atomico, dipendenze, documentazione (punto 6 e «Documentazione»)

```text
[regole comuni]
Compito: tre modifiche piccole, un diff solo.
1. config.salva_stato scrive con file temporaneo e replace, come
   Conversazione._salva.
2. requirements.txt dichiara le dipendenze importate direttamente ma oggi
   installate solo per via indiretta: trovale confrontando gli import in
   alfred/ con il file, non fidarti dell'elenco di REVISIONE.md.
3. README.md (entrambe le lingue) e docs/ARCHITETTURA.md allineati allo
   stato reale: confronta con docs/ROADMAP.md e con il codice, non con
   REVISIONE.md.
Non aggiungere CI né file di blocco: ne parliamo dopo.
```

### 6. Link e agenda dal cervello (punto 2) — dopo la verifica e la mia risposta

```text
[regole comuni]
Compito: punto 2 di «Correzioni al codice». Leggi la riga «Verifica:» sotto
quel punto e la mia decisione in «Domande aperte».
Comportamento voluto: quando la richiesta arriva dal cervello
(/api/azioni/{nome}), apri con un link chiede conferma; da comando diretto e
dai pulsanti dell'HUD resta immediato. [Aggiungi qui sposta_evento e
crea_evento se ho deciso di sì.]
Prima di scrivere, dimmi come distingui le tre strade nel codice attuale e
proponi la modifica più piccola. La conferma deve mostrare il link per
intero.
Test: apri con link dalla strada del cervello → in attesa di conferma;
dalla strada dei comandi diretti → eseguito; apri con un'app → eseguito
da entrambe.
```

### 7. Memoria (punto 5) — dopo la mia risposta

```text
[regole comuni]
Compito: punto 5 di «Correzioni al codice». Non scrivere codice subito.
1. Misura: quante righe ha memoria.md, quanti caratteri pesa oggi il prompt
   di sistema (brain.personalita) e quale parte viene da memoria e diario.
2. Dimmi quali file fanno riavviare il cervello in _osserva_file e quanto
   spesso cambiano in un giorno normale.
3. Proponi la modifica più piccola coerente con la mia decisione in
   «Domande aperte», con quanto si risparmia. Aspetta il mio sì.
```

### 8. Ampliamenti — uno alla volta, prima il progetto

```text
[regole comuni, tranne «fai solo il punto indicato»]
Compito: progettare l'ampliamento n. [N] di docs/REVISIONE.md. Non scrivere
codice.
Leggi docs/ARCHITETTURA.md, docs/ROADMAP.md e i moduli coinvolti, poi dammi:
quale modello usa e quanto costa in riserve (regola dell'economo); i file da
toccare; cosa chiede conferma; cosa succede se manca la dipendenza o la
rete; il passo più piccolo che sia già usabile da solo; come si prova.
Fammi le domande che ti servono prima di proporre. Quando approvo, aggiungi
il punto a docs/ROADMAP.md e fermati: il codice in una sessione nuova.
```

## Domande aperte per Pietro

- Punto 2: `sposta_evento` e `crea_evento` chiesti dal cervello devono
  chiedere conferma, o basta `apri` con i link?
- Punto 5: tetto alla memoria o consolidazione nel vault?
- Quale ampliamento per primo?

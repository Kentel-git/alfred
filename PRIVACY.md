# Privacy

🇮🇹 Italiano · [🇬🇧 English](#english)

Alfred è un programma che ogni persona installa e usa sul proprio computer.
Gli autori di Alfred non gestiscono server e non ricevono alcun dato.

**Dove restano i dati.** Configurazione, conversazioni, token di accesso e
stato restano sul computer dell'utente (`~/.config/alfred`,
`~/.local/state/alfred`).

**Google Calendar.** Se l'utente collega la propria agenda, Alfred usa le API
di Google Calendar con i soli permessi per gli eventi e l'elenco dei
calendari. I dati dell'agenda vengono letti e modificati dal computer
dell'utente, su sua richiesta, e non vengono inviati agli autori di Alfred né
ad altri, salvo quanto indicato sotto per il modello linguistico. L'uso dei
dati ricevuti dalle API di Google rispetta le
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
inclusi i requisiti di uso limitato.

**Servizi esterni usati da Alfred**, sempre dal computer dell'utente:

- il modello linguistico configurato (per esempio Claude, tramite Claude
  Code): riceve i messaggi rivolti ad Alfred e i dati necessari a
  rispondere, compresi eventi dell'agenda quando la richiesta li riguarda;
- Telegram, se l'utente collega un proprio bot;
- Open-Meteo, BeaconDB (tramite GeoClue) e OpenStreetMap per meteo e
  posizione approssimativa.

L'utente può revocare l'accesso a Google in qualsiasi momento da
[myaccount.google.com/permissions](https://myaccount.google.com/permissions)
ed eliminare i dati locali cancellando le cartelle sopra.

---

## English

Alfred is software that each person installs and runs on their own computer.
Alfred's authors run no servers and receive no data.

All configuration, conversations, access tokens and state stay on the user's
computer. If the user connects Google Calendar, Alfred uses the Google
Calendar API with access limited to events and the calendar list; calendar
data is read and changed from the user's computer, at the user's request,
and is not sent to Alfred's authors or anyone else, except to the language
model configured by the user when a request involves it. Use of information
received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

Other services Alfred may contact from the user's computer: the configured
language model, Telegram (if the user connects a bot), Open-Meteo, BeaconDB
(via GeoClue) and OpenStreetMap. Google access can be revoked at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

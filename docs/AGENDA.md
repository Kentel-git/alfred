# Collegare l'agenda (Google Calendar)

Alfred usa direttamente le API di Google Calendar: leggere e scrivere
l'agenda non consuma riserve del modello. Serve un client OAuth personale,
gratuito, da creare una volta sola.

1. **Progetto**: [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate),
   nome "Alfred", **Crea**, e assicurarsi che sia selezionato in alto.
2. **API**: [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com) → **Abilita**.
3. **Schermata di consenso**: [Google Auth Platform](https://console.cloud.google.com/auth/overview) → **Inizia**.
   Nome app "Alfred", email di assistenza; pubblico **Esterno**; email di contatto; **Crea**.
4. **In produzione**: sezione **Pubblico** → **Pubblica app**. In stato "test"
   Google fa scadere l'accesso ogni 7 giorni.
5. **Client**: sezione **Client** → **Crea client** → tipo **App desktop** →
   **Crea** → **Scarica JSON**.
6. Salvare il file come `~/.config/alfred/google-client.json`.
7. Eseguire `alfred google`: si apre il browser. Google avvisa che "non ha
   verificato questa app" (è normale: l'app è vostra) → **Avanzate** →
   **Vai ad Alfred** → consentire.

Alfred chiede solo due permessi: gli **eventi** dei calendari e l'**elenco
dei calendari**. Il token resta in `~/.local/state/alfred/google-token.json`.

Per default Alfred legge tutti i calendari visibili in Google Calendar. Per
indicare i propri calendari **personali** (HUD, "cosa ho domani", domande sui
propri impegni), in `config.toml`:

```toml
[agenda]
calendari = ["Lavoro", "Famiglia"]   # nomi come in Google Calendar, oppure id
```

Gli altri calendari visibili restano consultabili: Alfred li legge solo
quando vengono nominati ("cosa esce oggi sul calendario editoriale?").

"use strict";

const $ = (id) => document.getElementById(id);
let appellativo = "signore";

const BATTUTE = {
  notte: [
    "Le ricordo, con il dovuto rispetto, che esiste un'invenzione chiamata letto.",
    "Anche i pipistrelli, a quest'ora, cominciano a sbadigliare.",
    "Preparo un tè o preferisce fingere che sia ancora ieri?",
  ],
  mattina: [
    "Il tè è servito. Metaforicamente, s'intende: sono pur sempre un programma.",
    "Ho stirato il giornale. Anche questo, metaforicamente.",
    "Una splendida giornata per essere straordinariamente produttivi. O almeno presentabili.",
  ],
  pomeriggio: [
    "Confido che il pranzo sia stato all'altezza delle sue aspettative.",
    "L'ora del tè si avvicina, e con essa ogni speranza di civiltà.",
    "Tutto in ordine, signore. Per quanto la casa lo consenta.",
  ],
  sera: [
    "Una serata tranquilla, oppure ha in mente di salvare qualcosa?",
    "Le luci della città sono accese. Le sue, spero, presto spente.",
    "Ho fatto preparare la poltrona. E il caricatore.",
  ],
};

function fascia(ora) {
  if (ora < 5) return "notte";
  if (ora < 13) return "mattina";
  if (ora < 18) return "pomeriggio";
  return "sera";
}

function aggiornaSaluto() {
  const f = fascia(new Date().getHours());
  const saluti = { notte: "Ancora in piedi", mattina: "Buongiorno", pomeriggio: "Buon pomeriggio", sera: "Buonasera" };
  $("saluto").textContent = `${saluti[f]}, ${appellativo}${f === "notte" ? "?" : "."}`;
  const battute = BATTUTE[f];
  $("battuta").textContent = battute[Math.floor(Math.random() * battute.length)];
}

function aggiornaOrologio() {
  const adesso = new Date();
  $("ora").textContent = adesso.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  $("data").textContent = adesso.toLocaleDateString("it-IT", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
}

const formatoVelocita = (kbs) => (kbs >= 1024 ? `${(kbs / 1024).toFixed(1)} MB/s` : `${kbs} KB/s`);

function mostraSistema(s) {
  $("cpu-uso").textContent = `${Math.round(s.cpu.uso)}%` + (s.cpu.frequenza_mhz ? ` · ${(s.cpu.frequenza_mhz / 1000).toFixed(1)} GHz` : "");
  $("cpu-barra").style.width = `${s.cpu.uso}%`;
  $("cpu-temp").textContent = s.cpu.temperatura != null ? `${Math.round(s.cpu.temperatura)} °C` : "—";
  $("gpu-freq").textContent = s.gpu.frequenza_mhz == null ? "—" : s.gpu.frequenza_mhz === 0 ? "a riposo" : `${s.gpu.frequenza_mhz} MHz`;
  $("ram-uso").textContent = `${s.memoria.usata_gb} / ${s.memoria.totale_gb} GB`;
  $("ram-barra").style.width = `${s.memoria.uso}%`;
  $("disco").textContent = `${s.disco.libero_gb} GB liberi`;
  $("batteria").textContent = s.batteria
    ? `${s.batteria.livello}%${s.batteria.in_carica ? " · in carica" : ""}`
    : "a rete";
  $("rete").textContent = `↓ ${formatoVelocita(s.rete.giu_kbs)} · ↑ ${formatoVelocita(s.rete.su_kbs)}`;
}

function mostraMeteo(messaggio) {
  const m = messaggio.dati;
  if (messaggio.errore) {
    $("riquadro-meteo").hidden = false;
    $("meteo-temp").textContent = "";
    $("meteo-desc").textContent = "non riesco a guardare fuori dalla finestra";
    $("meteo-dettagli").textContent = messaggio.errore;
    $("meteo-giorni").replaceChildren();
    return;
  }
  $("riquadro-meteo").hidden = !m;
  if (!m) return;
  $("meteo-temp").textContent = `${m.temperatura}°`;
  $("meteo-desc").textContent = m.descrizione;
  $("meteo-dettagli").textContent = `${m.luogo} · percepiti ${m.percepita}° · umidità ${m.umidita}% · vento ${m.vento_kmh} km/h`;
  $("meteo-giorni").replaceChildren(
    ...m.prossimi_giorni.map((g, i) => {
      const li = document.createElement("li");
      const nome = i === 0 ? "oggi" : new Date(g.data).toLocaleDateString("it-IT", { weekday: "long" });
      li.innerHTML = `<span></span><span class="tenue"></span><span></span>`;
      li.children[0].textContent = nome;
      li.children[1].textContent = g.descrizione + (g.pioggia ? ` · ${g.pioggia}%` : "");
      li.children[2].textContent = `${g.min}° / ${g.max}°`;
      return li;
    }),
  );
}

// Ricarica i fogli di stile senza ricaricare la pagina.
function aggiornaStile() {
  for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
    const url = new URL(link.href);
    url.searchParams.set("v", Date.now());
    link.href = url.toString();
  }
}

// --- Le riserve (limiti di utilizzo di Claude) -------------------------------

function quandoSiRinnova(secondi) {
  const d = new Date(secondi * 1000);
  const ora = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  const oggi = new Date();
  const domani = new Date(oggi.getFullYear(), oggi.getMonth(), oggi.getDate() + 1);
  if (d.toDateString() === oggi.toDateString()) return `alle ${ora}`;
  if (d.toDateString() === domani.toDateString()) return `domani alle ${ora}`;
  return `${d.toLocaleDateString("it-IT", { weekday: "long" })} alle ${ora}`;
}

function mostraRiserva(nome, finestra) {
  if (!finestra || finestra.uso == null) {
    $(`riserva-${nome}`).textContent = "—";
    return;
  }
  const percento = Math.round(finestra.uso * 100);
  const rinnovo = finestra.rinnovo ? ` · si rinnova ${quandoSiRinnova(finestra.rinnovo)}` : "";
  $(`riserva-${nome}`).textContent = `${percento}%${rinnovo}`;
  const barra = $(`barra-${nome}`);
  barra.style.width = `${Math.min(percento, 100)}%`;
  barra.classList.toggle("attenzione", percento >= 75 && percento < 90);
  barra.classList.toggle("allarme", percento >= 90 || finestra.stato === "rejected");
}

function mostraLimiti(m) {
  if (!m.sessione && !m.settimana) return;
  if ($("riquadro-riserve").hidden) {
    // La striscia compare ora e accorcia la conversazione: si torna in fondo.
    $("riquadro-riserve").hidden = false;
    inFondo(true);
  }
  mostraRiserva("sessione", m.sessione);
  mostraRiserva("settimana", m.settimana);
  const minuti = Math.round((Date.now() / 1000 - m.aggiornato) / 60);
  const eta = minuti < 1 ? "aggiornate ora" : `aggiornate ${minuti} min fa`;
  const token = m.oggi.token >= 1000 ? `${Math.round(m.oggi.token / 1000)} mila token` : `${m.oggi.token} token`;
  const consumo = m.oggi.messaggi
    ? `Alfred oggi: ${m.oggi.messaggi} risposte, ${token}`
    : "Alfred oggi non ha ancora parlato";
  const r = m.regime || { nome: "normale" };
  const regime = r.nome === "normale" ? "regime normale" : `regime di ${r.nome} (${r.motivo})`;
  $("riserve-note").textContent = `${consumo} · ${regime} · ${eta}`;
  $("riserve-note").classList.toggle("avviso", r.nome !== "normale");
}

// --- L'agenda --------------------------------------------------------------------

function etichettaGiorno(d) {
  const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  const giorni = Math.round((d - oggi) / 86400000);
  if (giorni === 0) return "Oggi";
  if (giorni === 1) return "Domani";
  return d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
}

function mostraAgenda(m) {
  $("riquadro-agenda").hidden = false;
  const contenitore = $("agenda-giorni");
  if (!m.pronta || m.errore) {
    const p = document.createElement("p");
    p.className = "tenue";
    p.textContent = !m.pronta ? "L'agenda non è ancora collegata." : "Google non risponde, riproverò a breve.";
    contenitore.replaceChildren(p);
    return;
  }
  const perGiorno = new Map();
  const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  for (const e of m.eventi) {
    const inizio = new Date(e.tutto_il_giorno ? `${e.inizio}T00:00` : e.inizio);
    // Gli eventi cominciati nei giorni scorsi e ancora in corso stanno sotto "Oggi".
    const chiave = new Date(Math.max(inizio, oggi)); chiave.setHours(0, 0, 0, 0);
    if (!perGiorno.has(+chiave)) perGiorno.set(+chiave, []);
    perGiorno.get(+chiave).push({ ...e, inizioData: inizio });
  }
  if (!perGiorno.size) {
    const p = document.createElement("p");
    p.className = "tenue";
    p.textContent = "Nessun impegno nei prossimi giorni.";
    contenitore.replaceChildren(p);
    return;
  }
  const adesso = new Date();
  contenitore.replaceChildren(...[...perGiorno].map(([chiave, eventi]) => {
    const sezione = document.createElement("section");
    const titolo = document.createElement("h3");
    titolo.textContent = etichettaGiorno(new Date(chiave));
    const lista = document.createElement("ul");
    for (const e of eventi) {
      const li = document.createElement("li");
      const fine = new Date(e.tutto_il_giorno ? `${e.fine}T00:00` : e.fine);
      if (fine < adesso) li.className = "passato";
      const orario = document.createElement("span");
      orario.className = "orario";
      orario.textContent = e.tutto_il_giorno
        ? "giorno"
        : e.inizioData.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
      const nome = document.createElement("span");
      nome.textContent = e.titolo;
      li.append(orario, nome);
      lista.append(li);
    }
    sezione.append(titolo, lista);
    return sezione;
  }));
}

// --- La regia (OBS) ------------------------------------------------------------

function azione(nome, parametri = {}) {
  invia({ tipo: "azione", nome, parametri });
}

function mostraRegia(r) {
  $("riquadro-regia").hidden = false;
  $("regia-chiusa").hidden = r.aperto;
  $("regia-aperta").hidden = !r.aperto;
  if (!r.aperto) return;

  const durata = (t) => (t || "").split(".")[0];
  $("regia-diretta").textContent = r.diretta.attiva ? `in onda · ${durata(r.diretta.durata)}` : "spenta";
  $("regia-diretta").classList.toggle("in-onda", r.diretta.attiva);
  const reg = r.registrazione;
  $("regia-registrazione").textContent = reg.attiva
    ? (reg.in_pausa ? `in pausa · ${durata(reg.durata)}` : `in corso · ${durata(reg.durata)}`)
    : "spenta";
  $("regia-registrazione").classList.toggle("in-onda", reg.attiva && !reg.in_pausa);

  $("pulsante-diretta").textContent = r.diretta.attiva ? "Chiudi la diretta" : "Vai in diretta";
  $("pulsante-diretta").dataset.azione = r.diretta.attiva ? "ferma_diretta" : "avvia_diretta";
  $("pulsante-registrazione").textContent = reg.attiva ? "Ferma la registrazione" : "Registra";
  $("pulsante-registrazione").dataset.azione = reg.attiva ? "ferma_registrazione" : "avvia_registrazione";

  // Le scene si ridisegnano solo se cambiano, per non disturbare i clic.
  const firma = JSON.stringify([r.scene, r.scena_attuale]);
  if ($("regia-scene").dataset.firma !== firma) {
    $("regia-scene").dataset.firma = firma;
    $("regia-scene").replaceChildren(...r.scene.map((nome) => {
      const b = document.createElement("button");
      b.className = `pulsante${nome === r.scena_attuale ? " attivo" : ""}`;
      b.textContent = nome;
      b.addEventListener("click", () => azione("cambia_scena", { scena: nome }));
      return b;
    }));
  }
}

for (const b of document.querySelectorAll("[data-azione], #pulsante-diretta, #pulsante-registrazione")) {
  b.addEventListener("click", () => azione(b.dataset.azione));
}

function mostraConferma(m) {
  $("conferma").dataset.id = m.id;
  $("conferma-domanda").textContent = m.domanda;
  $("conferma").hidden = false;
  inFondo(true);
}

$("conferma-si").addEventListener("click", () => {
  invia({ tipo: "conferma_azione", id: $("conferma").dataset.id, si: true });
});
$("conferma-no").addEventListener("click", () => {
  invia({ tipo: "conferma_azione", id: $("conferma").dataset.id, si: false });
});

// --- Conversazione -----------------------------------------------------------

const ETICHETTE_STRUMENTI = {
  stato_computer: "dà un'occhiata al computer",
  meteo: "guarda fuori dalla finestra",
  stato_obs: "controlla OBS",
};

let bollaInCorso = null; // la risposta che Alfred sta scrivendo
let inizioAttesa = 0;
let timerAttesa = null;

function inFondo(forza = false) {
  const m = $("messaggi");
  const vicino = m.scrollHeight - m.scrollTop - m.clientHeight < 120;
  if (forza || vicino) m.scrollTop = m.scrollHeight;
}

function etichettaModello(bolla, modello) {
  if (modello === undefined) return;
  bolla.dataset.modello = modello ? modello : "senza consumare riserve";
}

function creaBolla(chi, testo = "", errore = false, modello, origine) {
  const div = document.createElement("div");
  div.className = `messaggio ${chi}${errore ? " errore" : ""}`;
  etichettaModello(div, modello);
  if (origine === "telegram") div.dataset.origine = "da Telegram";
  div.textContent = testo;
  $("messaggi").querySelector(".vuoto")?.remove();
  $("messaggi").append(div);
  inFondo(chi === "utente");
  return div;
}

function mostraCronologia(m) {
  $("messaggi").replaceChildren();
  bollaInCorso = null;
  if (!m.messaggi.length) {
    const p = document.createElement("p");
    p.className = "vuoto";
    p.textContent = "Sono a sua disposizione.";
    $("messaggi").append(p);
  }
  for (const msg of m.messaggi) creaBolla(msg.chi, msg.testo, !!msg.errore, msg.modello, msg.origine);
  if (m.occupato) iniziaAttesa();
  else fineAttesa();
  inFondo(true);
}

function iniziaAttesa() {
  inizioAttesa = Date.now();
  $("attesa").hidden = false;
  $("attesa").textContent = "Alfred riflette";
  clearInterval(timerAttesa);
  timerAttesa = setInterval(() => {
    const s = (Date.now() - inizioAttesa) / 1000;
    if (s > 45) $("attesa").textContent = "Alfred ci sta mettendo decisamente più del solito";
    else if (s > 15) $("attesa").textContent = "Alfred ci sta mettendo un po' più del solito";
  }, 1000);
}

function fineAttesa() {
  clearInterval(timerAttesa);
  $("attesa").hidden = true;
}

function rispostaParziale(testo) {
  if (!bollaInCorso) {
    bollaInCorso = creaBolla("alfred");
    $("attesa").hidden = true;
  }
  if (testo === "" && bollaInCorso.lastChild?.nodeType === Node.TEXT_NODE) {
    // Nuovo blocco di testo dopo uno strumento: va a capo.
    bollaInCorso.append(document.createTextNode("\n"));
  }
  bollaInCorso.append(document.createTextNode(testo));
  inFondo();
}

function rispostaStrumento(nome) {
  if (!bollaInCorso) bollaInCorso = creaBolla("alfred");
  const nota = document.createElement("span");
  nota.className = "strumento";
  nota.textContent = `Alfred ${ETICHETTE_STRUMENTI[nome] || `usa ${nome}`}`;
  bollaInCorso.append(nota);
  inFondo();
}

function rispostaFine(msg) {
  fineAttesa();
  // Il testo definitivo sostituisce quello arrivato a pezzi (note degli strumenti escluse).
  const bolla = bollaInCorso || creaBolla("alfred");
  const note = [...bolla.querySelectorAll(".strumento")];
  bolla.replaceChildren(...note, document.createTextNode(msg.testo));
  bolla.classList.toggle("errore", !!msg.errore);
  etichettaModello(bolla, msg.modello);
  bollaInCorso = null;
  inFondo();
}

function invia(oggetto) {
  if (canale && canale.readyState === WebSocket.OPEN) {
    canale.send(JSON.stringify(oggetto));
    return true;
  }
  return false;
}

$("modulo").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const testo = $("domanda").value.trim();
  if (testo && invia({ tipo: "chat", testo })) $("domanda").value = "";
});

$("nuova").addEventListener("click", () => {
  invia({ tipo: "nuova_conversazione" });
  $("domanda").focus();
});

// Basta iniziare a scrivere, ovunque: il cursore va da solo nella casella.
document.addEventListener("keydown", (evento) => {
  if (evento.target === $("domanda") || evento.ctrlKey || evento.altKey || evento.metaKey) return;
  if (evento.key.length === 1) $("domanda").focus();
});

// --- Collegamento col servizio ----------------------------------------------
// Un solo WebSocket: il servizio spinge i dati e avvisa quando qualcosa cambia.
// Se cade, si ricollega da solo; se il servizio è stato riavviato con codice
// nuovo, la pagina si ricarica.

let canale = null;
let avvioVisto = null;
let attesa = 500;

function collega() {
  canale = new WebSocket(`ws://${location.host}/ws`);

  canale.onopen = () => {
    attesa = 500;
    document.body.classList.remove("scollegato");
  };

  canale.onmessage = (evento) => {
    const m = JSON.parse(evento.data);
    switch (m.tipo) {
      case "benvenuto":
        if (avvioVisto && avvioVisto !== m.avvio) location.reload();
        avvioVisto = m.avvio;
        appellativo = m.dati.appellativo || appellativo;
        aggiornaSaluto();
        break;
      case "stato":
        appellativo = m.dati.appellativo || appellativo;
        aggiornaSaluto();
        break;
      case "sistema":
        mostraSistema(m.dati);
        break;
      case "meteo":
        mostraMeteo(m);
        break;
      case "limiti":
        mostraLimiti(m);
        break;
      case "cronologia":
        mostraCronologia(m);
        break;
      case "messaggio":
        creaBolla(m.messaggio.chi, m.messaggio.testo, !!m.messaggio.errore, m.messaggio.modello, m.messaggio.origine);
        break;
      case "conferma":
        mostraConferma(m);
        break;
      case "conferma_chiusa":
        if ($("conferma").dataset.id === m.id) $("conferma").hidden = true;
        break;
      case "agenda":
        mostraAgenda(m);
        break;
      case "regia":
        mostraRegia(m.dati);
        break;
      case "risposta_inizio":
        bollaInCorso = null;
        iniziaAttesa();
        break;
      case "risposta_parziale":
        rispostaParziale(m.testo);
        break;
      case "risposta_strumento":
        rispostaStrumento(m.nome);
        break;
      case "risposta_fine":
        rispostaFine(m.messaggio);
        break;
      case "aggiorna":
        if (m.solo_stile) aggiornaStile();
        else location.reload();
        break;
    }
  };

  canale.onclose = () => {
    document.body.classList.add("scollegato");
    setTimeout(collega, attesa);
    attesa = Math.min(attesa * 2, 5000);
  };
}

// Chiamata dalla finestra ogni volta che Alfred viene richiamato.
window.alfredMostrato = () => {
  aggiornaSaluto();
  aggiornaOrologio();
  invia({ tipo: "aggiornami" });
  $("domanda").focus();
};

let fasciaAttuale = fascia(new Date().getHours());
setInterval(() => {
  aggiornaOrologio();
  const f = fascia(new Date().getHours());
  if (f !== fasciaAttuale) {
    fasciaAttuale = f;
    aggiornaSaluto();
  }
}, 1000);

aggiornaOrologio();
aggiornaSaluto();
collega();

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
  $("riserve-note").textContent = m.oggi.messaggi
    ? `Alfred oggi: ${m.oggi.messaggi} risposte, ${token} · ${eta}`
    : `Alfred oggi non ha ancora parlato · ${eta}`;
}

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

function creaBolla(chi, testo = "", errore = false) {
  const div = document.createElement("div");
  div.className = `messaggio ${chi}${errore ? " errore" : ""}`;
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
  for (const msg of m.messaggi) creaBolla(msg.chi, msg.testo, !!msg.errore);
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
        creaBolla(m.messaggio.chi, m.messaggio.testo);
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

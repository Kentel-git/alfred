"use strict";

const $ = (id) => document.getElementById(id);
let appellativo = "signore";

// --- Fondo: piste di circuito (sempre le stesse: seme fisso) ------------------
{
  let seme = 7;
  const caso = () => (seme = (seme * 9301 + 49297) % 233280) / 233280;
  for (let i = 0; i < 46; i++) {
    let x = Math.round(caso() * 40) * 48, y = Math.round(caso() * 22) * 48, d = `M${x} ${y}`;
    for (let s = 0; s < 5; s++) {
      const lungo = 48 * (2 + Math.floor(caso() * 6)) * (caso() < 0.5 ? 1 : -1);
      if (s % 2) y += lungo; else x += lungo;
      d += ` L${x} ${y}`;
    }
    const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
    p.setAttribute("d", d);
    p.setAttribute("class", i % 4 === 0 ? "pista viva" : "pista");
    $("piste").append(p);
  }
}

// --- Il nucleo ----------------------------------------------------------------
// Velocità degli anelli (gradi al secondo), battito (giri al secondo), ampiezza
// dell'onda. Si passa da uno stato all'altro con inerzia, mai di colpo.
const PROFILI = {
  riposo:  { tacche: 4,  segmenti: -15,  tratteggio: 9,  battito: 0.25, onda: 0.04 },
  ascolto: { tacche: 6,  segmenti: -24,  tratteggio: 45, battito: 0.9,  onda: 0.45 },
  pensa:   { tacche: 10, segmenti: -120, tratteggio: 72, battito: 0.5,  onda: 0.25 },
  parla:   { tacche: 6,  segmenti: -30,  tratteggio: 20, battito: 1.1,  onda: 1 },
  cinico:  { tacche: 2,  segmenti: -6,   tratteggio: 5,  battito: 0.35, onda: 0.85 },
};
const NOMI_STATO = {
  riposo: ["RIPOSO", "◆ IN ATTESA"], ascolto: ["ASCOLTA", "◆ MICROFONO APERTO"], pensa: ["PENSA", "◆ ELABORAZIONE"],
  parla: ["PARLA", "◆ RISPOSTA"], cinico: ["SENZA FILTRI", "◆ LATO CINICO"],
};
const INERZIA_S = 0.9;
const animato = !matchMedia("(prefers-reduced-motion: reduce)").matches;
const anelli = { tacche: $("giro-tacche"), segmenti: $("giro-segmenti"), tratteggio: $("giro-tratteggio") };
const cuore = document.querySelector(".cuore"), increspatura = document.querySelector(".increspatura"), onda = $("onda");
for (let i = 0; i < 56; i++) onda.append(document.createElement("i"));
let obiettivo = PROFILI.riposo, attuale = { ...PROFILI.riposo }, angoli = { tacche: 0, segmenti: 0, tratteggio: 0 }, fase = 0, prima = performance.now();

// Cosa sta facendo Alfred: lo stato del nucleo si ricava da qui.
const attivita = { ascolto: false, trascrive: false, pensa: false, scrive: false, parla: false, cinico: false };
let avvisoFinoA = 0;

function aggiornaNucleo() {
  let s = "riposo";
  if (attivita.ascolto) s = "ascolto";
  else if (attivita.trascrive || attivita.pensa) s = "pensa";
  else if (attivita.scrive || attivita.parla) s = attivita.cinico ? "cinico" : "parla";
  if (document.body.dataset.stato !== s) {
    document.body.dataset.stato = s;
    obiettivo = PROFILI[s];
    increspatura.classList.remove("via"); void increspatura.getBBox(); increspatura.classList.add("via");
    const scritta = $("stato-testo");
    scritta.style.opacity = 0;
    setTimeout(() => { scritta.textContent = NOMI_STATO[s][0]; scritta.style.opacity = 1; }, 300);
  }
  if (Date.now() > avvisoFinoA) {
    let d = NOMI_STATO[s][1];
    if (s === "pensa" && attivita.trascrive) d = "◆ TRASCRIZIONE";
    if (s === "parla" && attivita.parla) d = "◆ VOCE IN USCITA";
    $("didascalia").textContent = d;
  }
}

function avvisa(testo, ms = 3000) {
  avvisoFinoA = Date.now() + ms;
  $("didascalia").textContent = testo;
  setTimeout(aggiornaNucleo, ms + 50);
}

function anima(adesso) {
  const dt = Math.min((adesso - prima) / 1000, 0.1); prima = adesso;
  const k = 1 - Math.exp(-dt / INERZIA_S);
  for (const chiave in attuale) attuale[chiave] += (obiettivo[chiave] - attuale[chiave]) * k;
  for (const chiave in angoli) {
    angoli[chiave] += attuale[chiave] * dt;
    anelli[chiave].style.transform = `rotate(${angoli[chiave]}deg)`;
  }
  fase += attuale.battito * dt * 2 * Math.PI;
  cuore.style.transform = `scale(${0.94 + 0.06 * Math.cos(fase)})`;
  cuore.style.opacity = 0.8 + 0.2 * Math.cos(fase);
  const t = adesso / 300;
  [...onda.children].forEach((b, i) => {
    const centro = 1 - Math.abs(i - 27.5) / 28;
    b.style.transform = `scaleY(${0.06 + 0.88 * attuale.onda * centro * Math.abs(Math.sin(t + i * 0.7) * Math.cos(t * 1.7 + i * 0.3))})`;
  });
  if (animato) requestAnimationFrame(anima);
}
anima(prima);

// --- Accensione -----------------------------------------------------------------
// Gli anelli partono veloci e rallentano fino al riposo con la solita inerzia.
if (animato) {
  document.body.classList.add("accensione");
  document.querySelectorAll(".pannello").forEach((p, i) => p.style.setProperty("--i", i));
  attuale = { tacche: 90, segmenti: -420, tratteggio: 260, battito: 1.6, onda: 0.9 };
  ["◆ ACCENSIONE", "◆ ALLINEAMENTO ANELLI", "◆ SISTEMI IN LINEA"].forEach((t, i) => setTimeout(() => avvisa(t, 750), i * 750));
  setTimeout(() => increspatura.classList.add("via"), 2000);
  // Tolta a sequenza finita, così i pannelli che compaiono dopo non si rianimano.
  setTimeout(() => document.body.classList.remove("accensione"), 3200);
}

// --- Barra di stato e orologio -------------------------------------------------
function aggiornaOrologio() {
  const adesso = new Date();
  $("ora").textContent = adesso.toLocaleTimeString("it-IT");
  $("data").textContent = adesso.toLocaleDateString("it-IT", { weekday: "short", day: "2-digit", month: "short", year: "numeric" }).replaceAll(".", "");
}
setInterval(aggiornaOrologio, 1000);
aggiornaOrologio();

// --- Sistema --------------------------------------------------------------------
const formatoVelocita = (kbs) => (kbs >= 1024 ? `${(kbs / 1024).toFixed(1)} MB/S` : `${kbs} KB/S`);
const GPU_MAX_MHZ = 2250;  // shortcut: frequenza massima della Arc del portatile; su altre GPU la barra è solo indicativa
const rete = [];

function misura(nome, percento, testo) {
  $(`b-${nome}`).style.width = `${Math.max(0, Math.min(100, percento))}%`;
  $(`v-${nome}`).textContent = testo;
}

function mostraSistema(s) {
  misura("cpu", s.cpu.uso, `${Math.round(s.cpu.uso)}%` + (s.cpu.frequenza_mhz ? ` · ${(s.cpu.frequenza_mhz / 1000).toFixed(1)} GHZ` : ""));
  misura("temp", s.cpu.temperatura ?? 0, s.cpu.temperatura != null ? `${Math.round(s.cpu.temperatura)} °C` : "—");
  misura("gpu", (s.gpu.frequenza_mhz ?? 0) / GPU_MAX_MHZ * 100, s.gpu.frequenza_mhz == null ? "—" : s.gpu.frequenza_mhz === 0 ? "RIPOSO" : `${s.gpu.frequenza_mhz} MHZ`);
  misura("ram", s.memoria.uso, `${s.memoria.usata_gb} / ${s.memoria.totale_gb} GB`);
  misura("disco", s.disco.uso, `${s.disco.libero_gb} GB LIBERI`);
  misura("batt", s.batteria ? s.batteria.livello : 100, s.batteria ? `${s.batteria.livello}% · ${s.batteria.in_carica ? "RETE" : "BATTERIA"}` : "RETE");
  $("v-rete").textContent = `↓ ${formatoVelocita(s.rete.giu_kbs)} · ↑ ${formatoVelocita(s.rete.su_kbs)}`;
  const ore = Math.floor(s.acceso_da_s / 3600);
  $("sistema-acceso").textContent = ore >= 24 ? `ACCESO DA ${Math.floor(ore / 24)} G` : `ACCESO DA ${ore} H`;

  rete.push(s.rete.giu_kbs + s.rete.su_kbs);
  if (rete.length > 60) rete.shift();
  const c = $("traccia"), g = c.getContext("2d");
  c.width = c.clientWidth * devicePixelRatio; c.height = c.clientHeight * devicePixelRatio;
  const massimo = Math.max(...rete, 50);
  g.strokeStyle = "#4fd8ff"; g.lineWidth = 1.5 * devicePixelRatio; g.shadowColor = "#4fd8ff"; g.shadowBlur = 6;
  g.beginPath();
  // Da destra verso sinistra, come un oscilloscopio: l'ultimo valore è sempre sul bordo.
  rete.forEach((v, i) => g[i ? "lineTo" : "moveTo"]((60 - rete.length + i) / 59 * c.width, c.height * (1 - 0.9 * v / massimo)));
  g.stroke();
}

// --- Meteo -----------------------------------------------------------------------
function mostraMeteo(messaggio) {
  const m = messaggio.dati;
  $("riquadro-meteo").hidden = !m && !messaggio.errore;
  if (messaggio.errore || !m) {
    $("meteo-temp").textContent = "";
    $("meteo-desc").textContent = messaggio.errore ? "NON DISPONIBILE" : "";
    $("meteo-dettagli").textContent = "";
    $("meteo-giorni").replaceChildren();
    return;
  }
  $("barra-luogo").textContent = m.luogo;
  $("meteo-luogo").textContent = m.luogo;
  $("meteo-temp").textContent = `${m.temperatura}°`;
  $("meteo-desc").textContent = m.descrizione;
  $("meteo-dettagli").textContent = `PERC ${m.percepita}° · UMID ${m.umidita}% · VENTO ${m.vento_kmh} KM/H`;
  $("meteo-giorni").replaceChildren(...m.prossimi_giorni.map((g, i) => {
    const d = document.createElement("div"), b = document.createElement("b"), e = document.createElement("span");
    b.textContent = i === 0 ? "OGGI" : new Date(g.data).toLocaleDateString("it-IT", { weekday: "short" }).replace(".", "");
    e.className = "etichetta";
    e.textContent = g.pioggia ? `PIOGGIA ${g.pioggia}%` : g.descrizione;
    d.append(b, `${g.min}° / ${g.max}°`, document.createElement("br"), e);
    return d;
  }));
}

// --- Agenda ----------------------------------------------------------------------
function etichettaGiorno(d) {
  const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  const giorni = Math.round((d - oggi) / 86400000);
  const nome = d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric" });
  return giorni === 0 ? `OGGI · ${nome}` : giorni === 1 ? `DOMANI · ${nome}` : nome;
}

function voceAgenda(classe, testo) {
  const li = document.createElement("li");
  li.className = classe;
  li.textContent = testo;
  return li;
}

function mostraAgenda(m) {
  $("riquadro-agenda").hidden = false;
  const lista = $("agenda");
  if (!m.pronta || m.errore) {
    lista.replaceChildren(voceAgenda("vuota", !m.pronta ? "AGENDA NON COLLEGATA" : "GOOGLE NON RISPONDE"));
    return;
  }
  const adesso = new Date(), oggi = new Date(); oggi.setHours(0, 0, 0, 0);
  $("agenda-calendari").textContent = `${new Set(m.eventi.map((e) => e.nome_calendario)).size} CALENDARI`;
  if (!m.eventi.length) {
    lista.replaceChildren(voceAgenda("vuota", "NESSUN IMPEGNO NEI PROSSIMI GIORNI"));
    return;
  }
  const voci = [];
  let giornoPrecedente = null, prossimoTrovato = false;
  for (const e of m.eventi) {
    const inizio = new Date(e.tutto_il_giorno ? `${e.inizio}T00:00` : e.inizio);
    const fine = new Date(e.tutto_il_giorno ? `${e.fine}T00:00` : e.fine);
    // Gli eventi cominciati nei giorni scorsi e ancora in corso stanno sotto oggi.
    const giorno = new Date(Math.max(inizio, oggi)); giorno.setHours(0, 0, 0, 0);
    if (+giorno !== giornoPrecedente) { voci.push(voceAgenda("giorno", etichettaGiorno(giorno))); giornoPrecedente = +giorno; }
    const li = document.createElement("li"), t = document.createElement("span"), nome = document.createElement("span"), nota = document.createElement("span");
    t.className = "t";
    t.textContent = e.tutto_il_giorno ? "GIORNO" : inizio.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    nota.className = "etichetta";
    if (fine < adesso) li.className = "passato";
    else if (!prossimoTrovato && !e.tutto_il_giorno && inizio > adesso) {
      prossimoTrovato = true;
      li.className = "prossimo";
      const minuti = Math.round((inizio - adesso) / 60000);
      if (minuti < 180) nota.textContent = minuti < 60 ? ` · TRA ${minuti} MIN` : ` · TRA ${Math.round(minuti / 60)} H`;
    }
    nome.append(e.titolo, nota);
    li.append(t, nome);
    voci.push(li);
  }
  lista.replaceChildren(...voci);
}

// --- Regia (OBS) -----------------------------------------------------------------
function azione(nome, parametri = {}) {
  invia({ tipo: "azione", nome, parametri });
}

function mostraRegia(r) {
  $("riquadro-regia").hidden = false;
  $("regia-chiusa").hidden = r.aperto;
  $("regia-aperta").hidden = !r.aperto;
  if (!r.aperto) return;
  const durata = (t) => (t || "").split(".")[0];
  const reg = r.registrazione;
  $("regia-diretta").textContent = r.diretta.attiva ? `IN ONDA ${durata(r.diretta.durata)}` : "DIRETTA —";
  $("regia-diretta").classList.toggle("in-onda", r.diretta.attiva);
  $("regia-registrazione").textContent = reg.attiva ? `${reg.in_pausa ? "REC ‖" : "REC"} ${durata(reg.durata)}` : "REC —";
  $("regia-registrazione").classList.toggle("in-onda", reg.attiva && !reg.in_pausa);
  $("pulsante-diretta").textContent = r.diretta.attiva ? "CHIUDI DIRETTA" : "VAI IN DIRETTA";
  $("pulsante-diretta").dataset.azione = r.diretta.attiva ? "ferma_diretta" : "avvia_diretta";
  $("pulsante-registrazione").textContent = reg.attiva ? "FERMA REC" : "REGISTRA";
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

// --- Riserve e veglia -------------------------------------------------------------
function quandoSiRinnova(secondi) {
  const d = new Date(secondi * 1000), oggi = new Date();
  const ora = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === oggi.toDateString() ? `RINNOVO ${ora}` : `RINNOVO ${d.toLocaleDateString("it-IT", { weekday: "short" }).replace(".", "")} ${ora}`;
}

function mostraRiserva(nome, finestra) {
  if (!finestra || finestra.uso == null) return;
  const percento = Math.round(finestra.uso * 100), arco = $(`arco-${nome}`);
  $(`r-${nome}`).textContent = `${percento}%`;
  $(`rinnovo-${nome}`).textContent = finestra.rinnovo ? quandoSiRinnova(finestra.rinnovo) : "";
  arco.style.strokeDashoffset = 132 * (1 - Math.min(percento, 100) / 100);
  arco.classList.toggle("attenzione", percento >= 75 && percento < 90);
  arco.classList.toggle("allarme", percento >= 90 || finestra.stato === "rejected");
}

function mostraLimiti(m) {
  if (!m.sessione && !m.settimana) return;
  $("riquadro-riserve").hidden = false;
  mostraRiserva("sessione", m.sessione);
  mostraRiserva("settimana", m.settimana);
  const r = m.regime || { nome: "normale" };
  $("barra-regime").textContent = `REGIME ${r.nome}`;
  $("barra-regime").classList.toggle("avviso", r.nome !== "normale");
  const token = m.oggi.token >= 1000 ? `${Math.round(m.oggi.token / 1000)}K TOKEN` : `${m.oggi.token} TOKEN`;
  $("riserve-note").textContent = r.nome !== "normale" ? `${r.nome}: ${r.motivo}` : m.oggi.messaggi ? `OGGI ${m.oggi.messaggi} RISPOSTE · ${token}` : "OGGI NESSUNA RISPOSTA";
  $("riserve-note").classList.toggle("avviso", r.nome !== "normale");
}

function mostraVeglia(v) {
  $("barra-veglia").textContent = !v.alimentatore ? "A BATTERIA" : v.voluta ? "VEGLIA ATTIVA" : "STANDBY CONSENTITO";
}

// --- Conversazione ----------------------------------------------------------------
const ETICHETTE_STRUMENTI = {
  stato_computer: "controlla il computer", meteo: "guarda fuori", stato_obs: "controlla OBS",
  agenda_eventi: "consulta l'agenda", fonti_obs: "passa in rassegna la regia", ricorda: "prende nota",
};
const CINICO = /senza filtri|cinic|brutal|realist|come stanno davvero/i;  // come l'economo: lato cinico evocato
let rigaInCorso = null;
let timerAttesa = null;

function inFondo(forza = false) {
  const m = $("messaggi");
  if (forza || m.scrollHeight - m.scrollTop - m.clientHeight < 120) m.scrollTop = m.scrollHeight;
}

function nota(modello, origine) {
  if (origine === "voce") return "A VOCE";
  if (origine === "telegram") return "DA TELEGRAM";
  if (modello === null) return "COMANDO DIRETTO · 0 TOKEN";
  if (modello === "gratuito") return "CERVELLO DI SCORTA · 0 RISERVE";
  return modello || "";
}

function creaRiga(chi, testo = "", errore = false, modello, origine) {
  const riga = document.createElement("div"), etichetta = document.createElement("span"), p = document.createElement("p");
  riga.className = `riga ${chi}${errore ? " errore" : ""}`;
  etichetta.className = "chi";
  etichetta.textContent = chi === "utente" ? "TU ›" : "ALFRED ›";
  p.textContent = testo;
  riga.append(etichetta, p);
  scriviNota(riga, nota(modello, origine));
  $("messaggi").querySelector(".vuoto")?.remove();
  $("messaggi").append(riga);
  inFondo(chi === "utente");
  return riga;
}

function scriviNota(riga, testo) {
  riga.querySelector(".nota")?.remove();
  if (!testo) return;
  const n = document.createElement("span");
  n.className = "nota";
  n.textContent = testo;
  riga.querySelector("p").append(n);
}

function mostraCronologia(m) {
  $("messaggi").replaceChildren();
  rigaInCorso = null;
  if (!m.messaggi.length) {
    const p = document.createElement("p");
    p.className = "vuoto";
    p.textContent = "Sono a sua disposizione";
    $("messaggi").append(p);
  }
  for (const msg of m.messaggi) creaRiga(msg.chi, msg.testo, !!msg.errore, msg.modello, msg.origine);
  attivita.pensa = !!m.occupato;
  aggiornaNucleo();
  inFondo(true);
}

function iniziaAttesa() {
  attivita.pensa = true; attivita.scrive = false;
  aggiornaNucleo();
  const inizio = Date.now();
  clearInterval(timerAttesa);
  timerAttesa = setInterval(() => {
    const s = (Date.now() - inizio) / 1000;
    if (s > 15 && attivita.pensa) avvisa(s > 45 ? "◆ CI METTE MOLTO PIÙ DEL SOLITO" : "◆ CI METTE PIÙ DEL SOLITO", 1100);
  }, 1000);
}

function rispostaParziale(testo) {
  if (!rigaInCorso) rigaInCorso = creaRiga("alfred");
  if (testo) { attivita.pensa = false; attivita.scrive = true; aggiornaNucleo(); }
  const p = rigaInCorso.querySelector("p");
  if (testo === "" && p.lastChild?.nodeType === Node.TEXT_NODE) p.append("\n");  // nuovo blocco dopo uno strumento
  p.append(testo);
  inFondo();
}

function rispostaStrumento(nome) {
  if (!rigaInCorso) rigaInCorso = creaRiga("alfred");
  const s = document.createElement("span");
  s.className = "strumento";
  s.textContent = `◆ ${ETICHETTE_STRUMENTI[nome] || nome}`;
  rigaInCorso.querySelector("p").append(s);
  inFondo();
}

function rispostaFine(msg) {
  clearInterval(timerAttesa);
  attivita.pensa = false; attivita.scrive = false;
  aggiornaNucleo();
  // Il testo definitivo sostituisce quello arrivato a pezzi (note degli strumenti escluse).
  const riga = rigaInCorso || creaRiga("alfred"), p = riga.querySelector("p");
  p.replaceChildren(...p.querySelectorAll(".strumento"), msg.testo);
  riga.classList.toggle("errore", !!msg.errore);
  scriviNota(riga, nota(msg.modello));
  rigaInCorso = null;
  inFondo();
}

function mostraConferma(m) {
  $("conferma").dataset.id = m.id;
  $("conferma-domanda").textContent = m.domanda;
  $("conferma").hidden = false;
  inFondo(true);
}
$("conferma-si").addEventListener("click", () => invia({ tipo: "conferma_azione", id: $("conferma").dataset.id, si: true }));
$("conferma-no").addEventListener("click", () => invia({ tipo: "conferma_azione", id: $("conferma").dataset.id, si: false }));

$("modulo").addEventListener("submit", (evento) => {
  evento.preventDefault();
  const testo = $("domanda").value.trim();
  if (testo && invia({ tipo: "chat", testo })) $("domanda").value = "";
});
$("nuova").addEventListener("click", () => { invia({ tipo: "nuova_conversazione" }); $("domanda").focus(); });
$("microfono").addEventListener("click", () => invia({ tipo: "ascolta" }));

// Basta iniziare a scrivere, ovunque: il cursore va da solo nella casella.
document.addEventListener("keydown", (evento) => {
  if (evento.target === $("domanda") || evento.ctrlKey || evento.altKey || evento.metaKey) return;
  if (evento.key.length === 1) $("domanda").focus();
});

function mostraAscolto(m) {
  attivita.ascolto = m.stato === "in_ascolto";
  attivita.trascrive = m.stato === "trascrivo";
  aggiornaNucleo();
  if (m.stato === "niente") avvisa("◆ NON HO SENTITO NULLA");
  if (m.stato === "errore") avvisa(`◆ MICROFONO: ${m.errore}`, 6000);
}

// --- Collegamento col servizio ----------------------------------------------------
// Un solo WebSocket: il servizio spinge i dati e avvisa quando qualcosa cambia.
// Se cade, si ricollega da solo; se il servizio è ripartito con codice nuovo,
// la pagina si ricarica.
let canale = null, avvioVisto = null, ritardo = 500;

function invia(oggetto) {
  if (canale?.readyState !== WebSocket.OPEN) return false;
  canale.send(JSON.stringify(oggetto));
  return true;
}

function aggiornaStile() {
  for (const link of document.querySelectorAll('link[rel="stylesheet"]')) {
    const url = new URL(link.href);
    url.searchParams.set("v", Date.now());
    link.href = url.toString();
  }
}

function collega() {
  canale = new WebSocket(`ws://${location.host}/ws`);
  canale.onopen = () => { ritardo = 500; document.body.classList.remove("scollegato"); };
  canale.onclose = () => {
    document.body.classList.add("scollegato");
    avvisa("◆ COLLEGAMENTO PERSO", ritardo + 500);
    setTimeout(collega, ritardo);
    ritardo = Math.min(ritardo * 2, 5000);
  };
  canale.onmessage = (evento) => {
    const m = JSON.parse(evento.data);
    switch (m.tipo) {
      case "benvenuto":
        if (avvioVisto && avvioVisto !== m.avvio) location.reload();
        avvioVisto = m.avvio;
      // fallthrough: il benvenuto porta anche lo stato
      case "stato":
        appellativo = m.dati.appellativo || appellativo;
        $("domanda").placeholder = `Mi dica, ${appellativo}…`;
        $("versione").textContent = `MAGGIORDOMO · v${m.dati.versione}`;
        break;
      case "sistema": mostraSistema(m.dati); break;
      case "meteo": mostraMeteo(m); break;
      case "limiti": mostraLimiti(m); break;
      case "veglia": mostraVeglia(m); break;
      case "agenda": mostraAgenda(m); break;
      case "regia": mostraRegia(m.dati); break;
      case "cronologia": mostraCronologia(m); break;
      case "messaggio":
        if (m.messaggio.chi === "utente") attivita.cinico = CINICO.test(m.messaggio.testo);
        creaRiga(m.messaggio.chi, m.messaggio.testo, !!m.messaggio.errore, m.messaggio.modello, m.messaggio.origine);
        break;
      case "conferma": mostraConferma(m); break;
      case "conferma_chiusa": if ($("conferma").dataset.id === m.id) $("conferma").hidden = true; break;
      case "ascolto": mostraAscolto(m); break;
      case "parola":
        attivita.parla = m.stato === "parla";
        $("microfono").classList.toggle("parla", attivita.parla);
        $("microfono").title = attivita.parla ? "Interrompi Alfred e parla (Mod+Shift+A)" : "Parla ad Alfred (Mod+Shift+A)";
        aggiornaNucleo();
        break;
      case "risposta_inizio": rigaInCorso = null; iniziaAttesa(); break;
      case "risposta_parziale": rispostaParziale(m.testo); break;
      case "risposta_strumento": rispostaStrumento(m.nome); break;
      case "risposta_fine": rispostaFine(m.messaggio); break;
      case "aggiorna": if (m.solo_stile) aggiornaStile(); else location.reload(); break;
    }
  };
}

// Chiamata dalla finestra ogni volta che Alfred viene richiamato.
window.alfredMostrato = () => {
  aggiornaOrologio();
  invia({ tipo: "aggiornami" });
  $("domanda").focus();
};

collega();

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

async function aggiornaSistema() {
  try {
    const s = await (await fetch("/api/sistema")).json();
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
  } catch {
    $("cpu-uso").textContent = "il servizio non risponde";
  }
}

async function aggiornaMeteo() {
  try {
    const risposta = await fetch("/api/meteo");
    const m = await risposta.json();
    if (!risposta.ok || !m) {
      $("riquadro-meteo").hidden = !m;
      if (m && m.errore) $("meteo-desc").textContent = "non riesco a guardare fuori dalla finestra";
      return;
    }
    $("riquadro-meteo").hidden = false;
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
  } catch {
    /* riproveremo al prossimo giro */
  }
}

// Chiamata dalla finestra ogni volta che Alfred viene richiamato.
window.alfredMostrato = () => {
  aggiornaSaluto();
  aggiornaOrologio();
  aggiornaSistema();
  aggiornaMeteo();
};

async function avvio() {
  try {
    appellativo = (await (await fetch("/api/stato")).json()).appellativo || appellativo;
  } catch { /* resta il predefinito */ }
  window.alfredMostrato();
  setInterval(aggiornaOrologio, 1000);
  setInterval(aggiornaSistema, 2000);
  setInterval(aggiornaMeteo, 10 * 60 * 1000);
}

avvio();

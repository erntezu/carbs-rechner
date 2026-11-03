"use strict";
/* Carbs Rechner – Browser-Oberfläche.
 * Rechnung: carbs_logik.py über Pyodide (bruecke.py). Speicher: localStorage (nur dieses Gerät/dieser Browser). */

const VERSION = 1;
const K_PLAN = "carbsRechner.plan";
const K_VORLAGEN = "carbsRechner.vorlagen";
const RASTER_MIN = 5;          // Raster beim Ziehen in der Timeline
const ZUSATZ_TYPEN = ["Riegel", "Gel", "Sonstiges"];

const $ = (sel) => document.querySelector(sel);
const S = { plan: null, erg: null, py: null, auswahl: null, herkunft: null, autosaveAus: null, zuletzt: null };

// ---------------------------------------------------------------------------
// Hilfen
// ---------------------------------------------------------------------------
const zahl = (v, d = 1) => (v == null || !Number.isFinite(v)) ? "–"
  : v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
const zahlKurz = (v) => v.toLocaleString("de-DE", { maximumFractionDigits: 2 });
const hm = (m) => { m = Math.round(m); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`; };
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const klemmen = (v, a, b) => Math.min(Math.max(v, a), b);
const verhText = (r) => r == null ? "–" : `1 : ${zahlKurz(r)}` + (r > 0 ? ` (${zahlKurz(1 / r)} : 1)` : " (nur Glukose)");
const jetzt = () => { const d = new Date(), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
const neueId = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), (b) => b.toString(16).padStart(2, "0")).join("");

// Standardwerte wie carbs_logik.neue_flasche / neuer_zusatz / standard_plan
const neueFlasche = (name, s, e) => ({ id: neueId(), art: "flasche", name, start_min: s, ende_min: e, volumen_ml: 500,
  pulver_modus: "selbst", malto_kh_prozent: 96, fructose_kh_prozent: 100, fertig_verhaeltnis: 0.8, fertig_kh_prozent: 90 });
const neuerZusatz = (name, s, e) => ({ id: neueId(), art: "zusatz", typ: "Riegel", name, start_min: s, ende_min: e,
  anzahl: 1, kh_pro_stueck: 40, verhaeltnis: 0.5 });
const standardPlan = () => ({ dauer_h: 2, carbs_pro_stunde: 90, verhaeltnis_modus: "automatisch", eigenes_verhaeltnis: 0.5,
  eintraege: [neueFlasche("Flasche 1", 0, 60), neueFlasche("Flasche 2", 60, 120)] });

const eintrag = (id) => S.plan.eintraege.find((e) => e.id === id);
const fahrtMin = () => Number.isFinite(S.plan.dauer_h) && S.plan.dauer_h > 0 ? Math.round(S.plan.dauer_h * 60) : 0;
const achsenMin = () => fahrtMin() || Math.max(60, ...S.plan.eintraege.map((e) => e.ende_min || 0));

function meldung(text, fehler = false) {
  const el = $("#menu").open ? $("#v-meldung") : $("#meldung");
  el.textContent = text;
  el.className = "meldung" + (fehler ? " fehler" : "");
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, fehler ? 8000 : 4000);
}

// ---------------------------------------------------------------------------
// Speicher (localStorage, nur dieses Gerät)
// ---------------------------------------------------------------------------
class SpeicherFehler extends Error {}

function lesen(schluessel) {
  let roh;
  try { roh = localStorage.getItem(schluessel); } catch (err) { throw new SpeicherFehler("Browserspeicher nicht verfügbar."); }
  if (!roh) return [null, null];
  let daten;
  try {
    daten = JSON.parse(roh);
    if (!daten || typeof daten !== "object" || Array.isArray(daten)) throw new Error("kein JSON-Objekt");
  } catch (err) {
    try { localStorage.setItem(`${schluessel}.defekt-${jetzt()}`, roh); localStorage.removeItem(schluessel); } catch (_) { /* egal */ }
    return [null, "Gespeicherte Daten waren nicht lesbar und wurden beiseitegelegt."];
  }
  formatPruefen(daten);
  return [daten, null];
}

function formatPruefen(daten) {
  const v = daten.format_version;
  if (!Number.isInteger(v) || v > VERSION)
    throw new SpeicherFehler(`Formatversion ${v} ist unbekannt (diese App kennt bis ${VERSION}). Daten werden nicht verändert.`);
}

function schreiben(schluessel, daten) {
  try { localStorage.setItem(schluessel, JSON.stringify(daten)); }
  catch (err) { throw new SpeicherFehler("Speichern im Browser fehlgeschlagen (Speicher voll oder gesperrt)."); }
}

function vorlagenLesen() {
  const [d, hinweis] = lesen(K_VORLAGEN);
  if (hinweis) meldung(hinweis, true);
  const v = (d && d.vorlagen && typeof d.vorlagen === "object") ? d.vorlagen : {};
  return Object.fromEntries(Object.entries(v).filter(([, x]) => x && typeof x === "object"));
}
const vorlagenSchreiben = (v) => schreiben(K_VORLAGEN, { format_version: VERSION, vorlagen: v });

function normalisieren(plan) {
  return S.py ? JSON.parse(S.py.normalisieren(JSON.stringify(plan ?? null))) : plan;
}

let autosaveTimer;
function autosave() {
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    if (S.autosaveAus || !S.erg || !S.erg.gueltig) return;
    const stand = JSON.stringify(S.plan);
    if (stand === S.zuletzt) return;
    try {
      schreiben(K_PLAN, { format_version: VERSION, gespeichert_am: jetzt(), plan: S.plan });
      S.zuletzt = stand;
    } catch (err) { meldung(err.message, true); }
  }, 300);
}

// ---------------------------------------------------------------------------
// Rechnen
// ---------------------------------------------------------------------------
function berechnen() {
  if (!S.py) { S.erg = null; return; }
  // Leere Felder (NaN) als ungültigen Wert übergeben, damit die Prüfung sie meldet
  const roh = JSON.stringify(S.plan, (k, v) => (typeof v === "number" && !Number.isFinite(v)) ? -1 : v);
  try { S.erg = JSON.parse(S.py.berechnen(roh)); }
  catch (err) { S.erg = { gueltig: false, fehler: [[null, "Rechenfehler: " + err.message]] }; }
}

let geplant = false;
function neuRechnen() {
  if (geplant) return;
  geplant = true;
  requestAnimationFrame(() => {
    geplant = false;
    berechnen();
    renderErgebnis();
    renderAbschnitte();
    balkenMarkieren();
    autosave();
  });
}

// ---------------------------------------------------------------------------
// Fahrt
// ---------------------------------------------------------------------------
function renderGlobal() {
  const p = S.plan;
  $("#g-dauer").value = Number.isFinite(p.dauer_h) ? p.dauer_h : "";
  $("#g-cph").value = Number.isFinite(p.carbs_pro_stunde) ? p.carbs_pro_stunde : "";
  $("#g-modus").value = p.verhaeltnis_modus;
  $("#g-r").value = Number.isFinite(p.eigenes_verhaeltnis) ? p.eigenes_verhaeltnis : "";
  $("#g-r").hidden = p.verhaeltnis_modus !== "eigen";
}

function globalBinden() {
  $("#g-dauer").addEventListener("input", (ev) => { S.plan.dauer_h = ev.target.valueAsNumber; renderTimeline(); neuRechnen(); });
  $("#g-cph").addEventListener("input", (ev) => { S.plan.carbs_pro_stunde = Math.round(ev.target.valueAsNumber); neuRechnen(); });
  $("#g-modus").addEventListener("change", (ev) => { S.plan.verhaeltnis_modus = ev.target.value; renderGlobal(); neuRechnen(); });
  $("#g-r").addEventListener("input", (ev) => { S.plan.eigenes_verhaeltnis = ev.target.valueAsNumber; neuRechnen(); });
}

// ---------------------------------------------------------------------------
// Timeline
// ---------------------------------------------------------------------------
const prozent = (m, D) => `${(klemmen(m, 0, D) / D) * 100}%`;

function balkenStil(el, e, D) {
  const s = klemmen(e.start_min || 0, 0, D), t = klemmen(e.ende_min || 0, 0, D);
  el.style.left = prozent(Math.min(s, t), D);
  el.style.width = `calc(${prozent(Math.abs(t - s), D)})`;
  el.querySelector(".name").textContent = e.name || "(ohne Namen)";
  el.querySelector(".zeit").textContent = `${hm(e.start_min || 0)}–${hm(e.ende_min || 0)}`;
}

function renderTimeline() {
  const D = achsenMin();
  const schritt = [5, 10, 15, 30, 60, 120, 240].find((s) => D / s <= 6) || 480;
  let achse = "", gitter = "";
  for (let m = 0; m < D - schritt * 0.4; m += schritt) {
    achse += `<span style="left:${prozent(m, D)}">${hm(m)}</span>`;
    if (m > 0) gitter += `<div class="gitter" style="left:${prozent(m, D)}"></div>`;
  }
  achse += `<span style="left:${prozent(D, D)}">${hm(D)}</span>`;
  const spuren = S.plan.eintraege.map((e) => `
    <div class="spur"><div class="balken ${e.art}${e.id === S.auswahl ? " gewaehlt" : ""}" data-id="${e.id}">
      <div class="griff links" data-griff="start"></div>
      <span class="name"></span><span class="zeit"></span>
      <div class="griff rechts" data-griff="ende"></div>
    </div></div>`).join("");
  $("#timeline").innerHTML = `<div class="achse">${achse}</div>
    <div class="spuren">${gitter}${spuren}</div><div class="abschnitte"></div>`;
  for (const el of document.querySelectorAll(".balken")) balkenStil(el, eintrag(el.dataset.id), D);
  renderAbschnitte();
  balkenMarkieren();
}

function renderAbschnitte() {
  const box = document.querySelector(".abschnitte");
  if (!box) return;
  const erg = S.erg;
  if (!erg || !erg.gueltig) { box.innerHTML = ""; return; }
  const D = achsenMin(), c = S.plan.carbs_pro_stunde;
  box.innerHTML = erg.abschnitte.map((a) => {
    const art = a.luecke ? "luecke" : (Math.abs(a.abweichung_rate) > 0.1 || a.fruktose_fehlt > 0.05) ? "warn" : "ok";
    const titel = `${hm(a.start_min)}–${hm(a.ende_min)}: ${zahl(a.rate)} g/h (Ziel ${c}) · Fruktose ${zahl(a.ist_fruktose)} g (mind. ${zahl(a.min_fruktose)} g)`;
    return `<div class="abschnitt ${art}" style="left:${prozent(a.start_min, D)};width:${prozent(a.ende_min - a.start_min, D)}"
      title="${esc(titel)}">${Math.round(a.rate)} g/h</div>`;
  }).join("");
}

function balkenMarkieren() {
  const fehlerIds = new Set((S.erg && !S.erg.gueltig ? S.erg.fehler : []).map(([id]) => id));
  for (const el of document.querySelectorAll(".balken")) {
    el.classList.toggle("fehlerhaft", fehlerIds.has(el.dataset.id));
    el.classList.toggle("gewaehlt", el.dataset.id === S.auswahl);
  }
}

function timelineBinden() {
  const tl = $("#timeline");
  let zug = null;
  tl.addEventListener("pointerdown", (ev) => {
    const el = ev.target.closest(".balken");
    if (!el || (ev.pointerType === "mouse" && ev.button !== 0)) return;
    const e = eintrag(el.dataset.id);
    const griff = ev.target.closest(".griff");
    zug = { el, e, art: griff ? griff.dataset.griff : "schieben", x0: ev.clientX, s0: e.start_min, e0: e.ende_min,
      breite: tl.querySelector(".spuren").clientWidth, D: achsenMin(), bewegt: false, id: ev.pointerId };
    el.setPointerCapture(ev.pointerId);
  });
  tl.addEventListener("pointermove", (ev) => {
    if (!zug || ev.pointerId !== zug.id) return;
    const dx = ev.clientX - zug.x0;
    if (!zug.bewegt && Math.abs(dx) < 4) return;
    zug.bewegt = true;
    const { e, s0, e0, D } = zug;
    const dm = (dx / zug.breite) * D;
    const rund = (m) => Math.round(m / RASTER_MIN) * RASTER_MIN;
    if (zug.art === "schieben") {
      const laenge = Math.min(e0 - s0, D);
      e.start_min = klemmen(rund(s0 + dm), 0, D - laenge);
      e.ende_min = e.start_min + laenge;
    } else if (zug.art === "start") {
      e.start_min = klemmen(rund(s0 + dm), 0, Math.max(0, Math.min(e0, D) - RASTER_MIN));
      e.ende_min = Math.min(e0, D);
      if (e.start_min >= e.ende_min) e.start_min = Math.max(0, e.ende_min - 1);
    } else {
      e.ende_min = klemmen(rund(e0 + dm), Math.min(D, s0 + RASTER_MIN), D);
      e.start_min = Math.max(0, s0);
    }
    balkenStil(zug.el, e, D);
    editorZeitSetzen(e);
    neuRechnen();
  });
  const ende = (ev) => {
    if (!zug || ev.pointerId !== zug.id) return;
    const { e, bewegt } = zug;
    zug = null;
    if (!bewegt && ev.type === "pointerup") {
      S.auswahl = S.auswahl === e.id ? null : e.id;
      balkenMarkieren();
      renderEditor();
    }
  };
  tl.addEventListener("pointerup", ende);
  tl.addEventListener("pointercancel", ende);
}

// ---------------------------------------------------------------------------
// Eintrag-Editor
// ---------------------------------------------------------------------------
const nf = (feld, label, attr = "") =>
  `<label>${label}<input type="number" data-feld="${feld}" inputmode="decimal" ${attr}></label>`;

function renderEditor() {
  const box = $("#editor");
  const e = S.auswahl && eintrag(S.auswahl);
  if (!e) { box.innerHTML = ""; return; }
  let felder;
  if (e.art === "flasche") {
    const selbst = e.pulver_modus === "selbst";
    felder = `
      <div class="raster3">${nf("start_min", "Start (min)", 'min="0" step="1" inputmode="numeric"')}
        ${nf("ende_min", "Ende (min)", 'min="0" step="1" inputmode="numeric"')}
        ${nf("volumen_ml", "Wasser (ml)", 'min="0" step="50"')}</div>
      <div class="segment">
        <button data-modus="selbst" class="${selbst ? "aktiv" : ""}">Selbst mischen</button>
        <button data-modus="fertig" class="${selbst ? "" : "aktiv"}">Fertiges Pulver</button></div>
      <div class="raster2">${selbst
        ? nf("malto_kh_prozent", "Maltodextrin g KH/100 g", 'min="0" max="100" step="1"') + nf("fructose_kh_prozent", "Fruktose g KH/100 g", 'min="0" max="100" step="1"')
        : nf("fertig_verhaeltnis", "Pulver Glukose : Fruktose = 1 :", 'min="0" step="0.05"') + nf("fertig_kh_prozent", "Pulver g KH/100 g", 'min="0" max="100" step="1"')}</div>`;
  } else {
    felder = `
      <div class="raster2">${nf("start_min", "Start (min)", 'min="0" step="1" inputmode="numeric"')}
        ${nf("ende_min", "Ende (min)", 'min="0" step="1" inputmode="numeric"')}</div>
      <div class="raster3">${nf("anzahl", "Stück", 'min="0" step="0.5"')}
        ${nf("kh_pro_stueck", "KH je Stück (g)", 'min="0" step="1"')}
        ${nf("verhaeltnis", "Glukose : Fruktose = 1 :", 'min="0" step="0.05"')}</div>`;
  }
  const typ = e.art === "zusatz"
    ? `<label>Typ<select data-feld="typ">${ZUSATZ_TYPEN.map((t) => `<option${t === e.typ ? " selected" : ""}>${t}</option>`).join("")}</select></label>`
    : "";
  box.innerHTML = `<div class="editor">
    <div class="kopfzeile"><label>Name<input type="text" data-feld="name" maxlength="40"></label>${typ}</div>
    ${felder}
    <div class="fehlerliste"></div>
    <div class="knoepfe breit">
      <button data-aktion="duplizieren">Duplizieren</button>
      <button data-aktion="loeschen" class="gefahr">Löschen</button>
      <button data-aktion="fertig">Fertig</button></div></div>`;
  for (const inp of box.querySelectorAll("input[data-feld]")) {
    const v = e[inp.dataset.feld];
    inp.value = (typeof v === "number" && !Number.isFinite(v)) ? "" : v;
  }
  editorFehler();
}

function editorZeitSetzen(e) {
  if (e.id !== S.auswahl) return;
  for (const f of ["start_min", "ende_min"]) {
    const inp = document.querySelector(`#editor input[data-feld="${f}"]`);
    if (inp && document.activeElement !== inp) inp.value = e[f];
  }
}

function editorFehler() {
  const box = document.querySelector("#editor .fehlerliste");
  if (!box) return;
  const liste = (S.erg && !S.erg.gueltig ? S.erg.fehler : []).filter(([id]) => id === S.auswahl);
  box.innerHTML = liste.map(([, t]) => `<p class="fehlertext">${esc(t)}</p>`).join("");
}

function editorBinden() {
  const box = $("#editor");
  const aendern = (ev) => {
    const inp = ev.target.closest("[data-feld]");
    const e = S.auswahl && eintrag(S.auswahl);
    if (!inp || !e) return;
    const feld = inp.dataset.feld;
    if (inp.type === "number") {
      const v = inp.valueAsNumber;
      e[feld] = (feld === "start_min" || feld === "ende_min") && Number.isFinite(v) ? Math.round(v) : v;
    } else {
      e[feld] = inp.value;
    }
    if (["name", "start_min", "ende_min"].includes(feld)) {
      const el = document.querySelector(`.balken[data-id="${e.id}"]`);
      if (el) balkenStil(el, e, achsenMin());
    }
    neuRechnen();
  };
  box.addEventListener("input", aendern);
  box.addEventListener("change", aendern);
  box.addEventListener("click", (ev) => {
    const e = S.auswahl && eintrag(S.auswahl);
    if (!e) return;
    const modus = ev.target.closest("[data-modus]");
    const aktion = ev.target.closest("[data-aktion]")?.dataset.aktion;
    if (modus) { e.pulver_modus = modus.dataset.modus; renderEditor(); neuRechnen(); return; }
    if (aktion === "duplizieren") {
      const kopie = { ...structuredClone(e), id: neueId(), name: `${e.name} (Kopie)` };
      S.plan.eintraege.splice(S.plan.eintraege.indexOf(e) + 1, 0, kopie);
      S.auswahl = kopie.id;
    } else if (aktion === "loeschen") {
      S.plan.eintraege = S.plan.eintraege.filter((x) => x.id !== e.id);
      S.auswahl = null;
    } else if (aktion === "fertig") {
      S.auswahl = null;
    } else return;
    renderTimeline(); renderEditor(); neuRechnen();
  });
}

function neu(art) {
  const D = fahrtMin() || 60;
  const gleiche = S.plan.eintraege.filter((e) => e.art === art);
  const letzte = gleiche[gleiche.length - 1];
  const start = letzte && letzte.ende_min >= 0 && letzte.ende_min < D ? letzte.ende_min : 0;
  const ende = Math.min(start + 60, D);
  const e = art === "flasche" ? neueFlasche(`Flasche ${gleiche.length + 1}`, start, ende)
    : neuerZusatz(`Riegel/Gel ${gleiche.length + 1}`, start, ende);
  S.plan.eintraege.push(e);
  S.auswahl = e.id;
  renderTimeline(); renderEditor(); neuRechnen();
}

// ---------------------------------------------------------------------------
// Ergebnis: Pack-/Mischliste mit zeitlicher Bilanz
// ---------------------------------------------------------------------------
function renderErgebnis() {
  const erg = S.erg;
  const hinweise = $("#hinweise"), liste = $("#liste"), summe = $("#summe"), zus = $("#zusammenfassung");
  editorFehler();
  $("#global-fehler").innerHTML = "";
  if (!erg) { zus.textContent = ""; hinweise.innerHTML = ""; liste.innerHTML = '<p class="klein">Rechner lädt …</p>'; summe.innerHTML = ""; return; }
  if (!erg.gueltig) {
    zus.textContent = "";
    $("#global-fehler").innerHTML = erg.fehler.filter(([id]) => id == null).map(([, t]) => `<p class="fehlertext">${esc(t)}</p>`).join("");
    hinweise.innerHTML = erg.fehler.filter(([id]) => id != null).map(([, t]) => `<div class="hinweis fehler">${esc(t)}</div>`).join("")
      || '<div class="hinweis fehler">Bitte die Eingaben oben korrigieren.</div>';
    liste.innerHTML = ""; summe.innerHTML = "";
    return;
  }
  zus.innerHTML = `${fahrtMin()} min · Ziel <b>${zahl(erg.ziel_kh, 0)} g</b> KH · ${verhText(erg.ziel_verhaeltnis)}`
    + (erg.min_fruktose > 0 ? ` · mind. <b>${zahl(erg.min_fruktose)} g</b> Fruktose` : "");

  // Über-/Unterversorgung je Abschnitt steht farbig in der Timeline -> nur ein Sammelhinweis
  const abweichend = erg.hinweise.filter(([, t]) => /^(Über|Unter)versorgung/.test(t)).length;
  const texte = erg.hinweise.filter(([art, t]) => art !== "info" && !/^(Über|Unter)versorgung/.test(t));
  if (abweichend) texte.unshift(["warnung", `Ziel ${S.plan.carbs_pro_stunde} g/h wird in ${abweichend} Abschnitt(en) nicht erreicht `
    + "(gelb in der Timeline). Zeiträume anpassen."]);
  hinweise.innerHTML = texte
    .map(([art, t]) => `<div class="hinweis ${art === "fehler" ? "fehler" : ""}">${esc(t)}</div>`).join("");

  const sortiert = [...S.plan.eintraege].sort((a, b) => a.start_min - b.start_min || a.ende_min - b.ende_min);
  liste.innerHTML = sortiert.map((e) => {
    const wann = `${hm(e.start_min)}–${hm(e.ende_min)}`;
    if (e.art === "flasche") {
      const r = erg.flaschen[e.id];
      let mischen;
      if (r.kh <= 0) mischen = "nur Wasser";
      else if (e.pulver_modus === "selbst")
        mischen = `<b>${zahl(r.malto_pulver)} g</b> Maltodextrin` + (r.fructose_pulver > 0 ? ` + <b>${zahl(r.fructose_pulver)} g</b> Fruktose` : "");
      else mischen = `<b>${zahl(r.fertig_pulver)} g</b> Fertigpulver`;
      const details = [`${zahl(r.kh)} g KH`, `${zahl(r.rate, 0)} g/h`, `${zahl(r.konzentration)} g/100 ml`];
      if (e.pulver_modus === "fertig" && r.fruktose > 0) details.splice(1, 0, `davon ${zahl(r.fruktose)} g Fruktose`);
      return `<div class="posten flasche"><span class="wann">${wann}</span>
        <span class="titel">${esc(e.name || "Flasche")} · ${zahl(e.volumen_ml, 0)} ml</span>
        <span class="mischen">${mischen}</span><span class="details">${details.join(" · ")}</span></div>`;
    }
    const r = erg.zusaetze[e.id];
    return `<div class="posten zusatz"><span class="wann">${wann}</span>
      <span class="titel">${zahlKurz(e.anzahl)} × ${esc(e.name || e.typ)}</span>
      <span class="mischen"><b>${zahl(r.kh)} g</b> KH${r.fruktose > 0 ? ` · davon ${zahl(r.fruktose)} g Fruktose` : ""}</span>
      <span class="details">${zahl(r.rate, 0)} g/h · ${esc(e.typ)}</span></div>`;
  }).join("") || '<p class="klein">Noch keine Einträge.</p>';

  const frOk = erg.fruktose_gesamt >= erg.min_fruktose - 0.05;
  summe.innerHTML = `Gesamt <b>${zahl(erg.kh_gesamt)} g</b> KH von ${zahl(erg.ziel_kh, 0)} g`
    + ` · Fruktose <span class="${frOk ? "ok-text" : "warn-text"}">${zahl(erg.fruktose_gesamt)} g</span>`
    + (erg.min_fruktose > 0 ? ` (mind. ${zahl(erg.min_fruktose)} g)` : "");
}

// ---------------------------------------------------------------------------
// Menü: Vorlagen, Export/Import, Schnellrechner
// ---------------------------------------------------------------------------
function planUebernehmen(plan, herkunft = null) {
  S.plan = normalisieren(plan);
  S.auswahl = null;
  S.herkunft = herkunft;
  const h = $("#herkunft");
  h.hidden = !herkunft;
  h.textContent = herkunft ? `Aus Vorlage „${herkunft}“ – Änderungen ändern die Vorlage nicht.` : "";
  renderGlobal(); renderTimeline(); renderEditor(); neuRechnen();
}

function renderVorlagen() {
  let v;
  try { v = vorlagenLesen(); } catch (err) { $("#v-liste").innerHTML = `<li>${esc(err.message)}</li>`; return; }
  const namen = Object.keys(v).sort((a, b) => a.localeCompare(b, "de", { sensitivity: "base" }));
  $("#v-liste").innerHTML = namen.map((n) => `<li data-name="${esc(n)}"><span class="vname">${esc(n)}</span>
      <button data-v="laden">Laden</button><button data-v="ueberschreiben">Überschreiben</button>
      <button data-v="umbenennen">Umbenennen</button><button data-v="loeschen" class="gefahr">Löschen</button></li>`).join("")
    || '<li class="klein">Noch keine Vorlagen.</li>';
}

function planGueltig() {
  if (!S.erg || !S.erg.gueltig) { meldung("Der Plan enthält Fehler oder der Rechner lädt noch.", true); return false; }
  return true;
}

function vorlageAktion(art, name) {
  try {
    const v = vorlagenLesen();
    if (art === "laden") {
      if (!v[name]) throw new SpeicherFehler(`Vorlage „${name}“ existiert nicht.`);
      planUebernehmen(structuredClone(v[name].plan), name);
      $("#menu").close();
      meldung(`Vorlage „${name}“ geladen.`);
      return;
    }
    if (art === "ueberschreiben") {
      if (!planGueltig() || !confirm(`Vorlage „${name}“ mit dem aktuellen Plan überschreiben?`)) return;
      v[name] = { gespeichert_am: jetzt(), plan: structuredClone(S.plan) };
      vorlagenSchreiben(v);
      meldung(`Vorlage „${name}“ überschrieben.`);
    } else if (art === "umbenennen") {
      const neuName = (prompt("Neuer Name", name) || "").trim();
      if (!neuName || neuName === name) return;
      if (v[neuName]) throw new SpeicherFehler(`Vorlage „${neuName}“ existiert bereits.`);
      v[neuName] = v[name]; delete v[name];
      vorlagenSchreiben(v);
      if (S.herkunft === name) { S.herkunft = neuName; $("#herkunft").textContent = `Aus Vorlage „${neuName}“ – Änderungen ändern die Vorlage nicht.`; }
      meldung(`Umbenannt in „${neuName}“.`);
    } else if (art === "loeschen") {
      if (!confirm(`Vorlage „${name}“ löschen?`)) return;
      delete v[name];
      vorlagenSchreiben(v);
      meldung(`Vorlage „${name}“ gelöscht.`);
    }
  } catch (err) { meldung(err.message, true); }
  renderVorlagen();
}

function vorlageSpeichern() {
  const name = $("#v-name").value.trim();
  if (!name) { meldung("Bitte einen Namen eingeben.", true); return; }
  if (!planGueltig()) return;
  try {
    const v = vorlagenLesen();
    if (v[name] && !confirm(`Vorlage „${name}“ existiert bereits. Überschreiben?`)) return;
    v[name] = { gespeichert_am: jetzt(), plan: structuredClone(S.plan) };
    vorlagenSchreiben(v);
    $("#v-name").value = "";
    meldung(`Vorlage „${name}“ gespeichert.`);
  } catch (err) { meldung(err.message, true); }
  renderVorlagen();
}

function exportieren() {
  let vorlagen = {};
  try { vorlagen = vorlagenLesen(); } catch (_) { /* nur Plan exportieren */ }
  const daten = { format_version: VERSION, gespeichert_am: jetzt(), plan: S.plan, vorlagen };
  const url = URL.createObjectURL(new Blob([JSON.stringify(daten, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `carbs-rechner-${jetzt().slice(0, 10)}.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function importieren(datei) {
  try {
    let daten;
    try { daten = JSON.parse(await datei.text()); } catch (_) { throw new SpeicherFehler("Datei ist kein gültiges JSON."); }
    if (!daten || typeof daten !== "object") throw new SpeicherFehler("Datei enthält keinen Plan.");
    if (daten.format_version !== undefined) formatPruefen(daten);
    let anzahl = 0;
    if (daten.vorlagen && typeof daten.vorlagen === "object") {
      const v = vorlagenLesen();
      for (const [name, inhalt] of Object.entries(daten.vorlagen)) {
        if (!inhalt || typeof inhalt !== "object") continue;
        let ziel = name, i = 2;
        while (v[ziel]) ziel = `${name} (Import${i > 2 ? " " + (i - 1) : ""})`, i++;
        v[ziel] = { gespeichert_am: inhalt.gespeichert_am || jetzt(), plan: normalisieren(inhalt.plan) };
        anzahl++;
      }
      vorlagenSchreiben(v);
    }
    const plan = daten.plan || (Array.isArray(daten.eintraege) ? daten : null);
    let planGeladen = false;
    if (plan && confirm("Aktuellen Plan durch den importierten Plan ersetzen?")) { planUebernehmen(plan); planGeladen = true; }
    meldung(`Import: ${anzahl} Vorlage(n)${planGeladen ? ", aktueller Plan ersetzt" : ""}.`, !anzahl && !planGeladen);
  } catch (err) { meldung(err.message, true); }
  renderVorlagen();
}

function schnellrechner() {
  const g = $("#s-gesamt").valueAsNumber, r = $("#s-r").valueAsNumber;
  if (!(g > 0) || !(r >= 0)) { $("#s-ergebnis").textContent = "Bitte gültige Werte eingeben."; return; }
  const malto = g / (1 + r);
  $("#s-ergebnis").innerHTML = `Maltodextrin <b>${zahl(malto)} g</b> · Fruktose <b>${zahl(g - malto)} g</b> <span class="klein">(KH, nicht Pulvergewicht)</span>`;
}

function menuBinden() {
  $("#menu-auf").addEventListener("click", () => { renderVorlagen(); schnellrechner(); $("#menu").showModal(); });
  $("#menu").addEventListener("click", (ev) => {
    if (ev.target === $("#menu") || ev.target.closest("[data-schliessen]")) { $("#menu").close(); return; }
    const knopf = ev.target.closest("[data-v]");
    if (knopf) vorlageAktion(knopf.dataset.v, knopf.closest("li").dataset.name);
  });
  $("#v-speichern").addEventListener("click", vorlageSpeichern);
  $("#v-name").addEventListener("keydown", (ev) => { if (ev.key === "Enter") vorlageSpeichern(); });
  $("#export").addEventListener("click", exportieren);
  $("#import").addEventListener("change", (ev) => { const f = ev.target.files[0]; ev.target.value = ""; if (f) importieren(f); });
  $("#s-gesamt").addEventListener("input", schnellrechner);
  $("#s-r").addEventListener("input", schnellrechner);
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
async function pythonLaden() {
  const pyodide = await loadPyodide();
  await pyodide.loadPackage("numpy");
  for (const datei of ["carbs_logik.py", "bruecke.py"]) {
    const antwort = await fetch(datei, { cache: "no-cache" });
    if (!antwort.ok) throw new Error(`${datei} nicht gefunden`);
    pyodide.FS.writeFile(datei, await antwort.text());
  }
  pyodide.runPython("import bruecke");
  return pyodide.pyimport("bruecke");
}

async function start() {
  try {
    const [d, hinweis] = lesen(K_PLAN);
    if (hinweis) meldung(hinweis, true);
    if (d && d.plan) { S.plan = d.plan; S.zuletzt = JSON.stringify(d.plan); }
  } catch (err) {
    S.autosaveAus = err.message;
    meldung(`${err.message} Automatisches Speichern ist aus.`, true);
  }
  if (!S.plan || !Array.isArray(S.plan.eintraege)) S.plan = standardPlan();
  globalBinden(); timelineBinden(); editorBinden(); menuBinden();
  for (const k of document.querySelectorAll("[data-neu]")) k.addEventListener("click", () => neu(k.dataset.neu));
  renderGlobal(); renderTimeline(); renderErgebnis();

  try {
    S.py = await pythonLaden();
    S.plan = normalisieren(S.plan);
    renderGlobal(); renderTimeline(); renderEditor();
    neuRechnen();
    $("#laden").hidden = true;
  } catch (err) {
    $("#laden").textContent = "Rechner konnte nicht geladen werden (Internetverbindung?). Seite neu laden.";
    console.error(err);
  }
}

start();

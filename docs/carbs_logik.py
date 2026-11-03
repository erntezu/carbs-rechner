"""Rechenlogik des Carbs-Rechners (ohne Streamlit).

Verhältnisse sind immer Glukosequellen : Fruktose = 1 : r, bezogen auf die
enthaltenen Kohlenhydrate (nicht auf das Pulvergewicht). 2:1 entspricht 1:0.5.

Zeiten im Plan sind Minuten ab Fahrtbeginn, intern wird in Stunden gerechnet.
Jeder Timeline-Eintrag wird gleichmäßig über seinen Zeitraum aufgenommen.
"""

import copy
import uuid

import numpy as np

PLAN_FORMAT_VERSION = 1
TOLERANZ_G = 1e-6          # Rechen-Toleranz für Grammwerte
TOLERANZ_RATE = 0.1        # ab dieser Abweichung (g/h) wird ein Abschnitt markiert
TOLERANZ_FRUKTOSE = 0.05   # ab diesem Fehlbetrag (g) wird Fruktose markiert


# ---------------------------------------------------------------------------
# Bestehende Grundfunktionen (aus app.py übernommen)
# ---------------------------------------------------------------------------

def mischung_aufteilen(gesamt, verhaeltnis):
    """Teilt eine KH-Menge nach 1:r in Glukosequellen und Fruktose."""
    malto_gesamt = gesamt / (1 + verhaeltnis)
    fructose = gesamt - malto_gesamt
    return malto_gesamt, fructose


def gesamt_berechnen(carbs_pro_stunde, dauer):
    return carbs_pro_stunde * dauer


def verhaeltnis_berechnen(carbs_pro_stunde):
    """Bestehende automatische Verhältnisregel (Software-Heuristik)."""
    if carbs_pro_stunde <= 60:
        return 0.0
    elif carbs_pro_stunde <= 90:
        return (carbs_pro_stunde - 60) / 30 * 0.5
    elif carbs_pro_stunde < 120:
        return 0.5 + (carbs_pro_stunde - 90) / 30 * 0.3
    else:
        return 0.8


def konzentration_berechnen(carbs_pro_flasche, volumen_pro_flasche):
    return carbs_pro_flasche / volumen_pro_flasche * 100


def fruktose_anteil(verhaeltnis):
    """Fruktoseanteil an den KH bei 1:r."""
    return verhaeltnis / (1 + verhaeltnis)


def mindest_fruktose(kh_ziel, verhaeltnis):
    """Mindestfruktose = T * r / (1 + r)."""
    return kh_ziel * fruktose_anteil(verhaeltnis)


def pulver_menge(kh, kh_pro_100g):
    """Pulvermenge = benötigte KH / (KH pro 100 g / 100)."""
    if not (0 < kh_pro_100g <= 100):
        raise ValueError("KH-Gehalt muss > 0 und <= 100 g pro 100 g sein.")
    return kh / (kh_pro_100g / 100)


def verhaeltnis_text(r):
    """'1 : 0.5 (2 : 1)' – einheitliche Beschriftung Glukosequellen : Fruktose."""
    if r is None:
        return "nicht definiert"
    text = f"1 : {r:.2f}".rstrip("0").rstrip(".").rstrip(",")
    if r > 0:
        umgekehrt = 1 / r
        text += f" (entspricht {umgekehrt:.2f}".rstrip("0").rstrip(".") + " : 1)"
    else:
        text += " (nur Glukosequellen)"
    return text


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

def neue_id():
    return uuid.uuid4().hex[:12]


def neue_flasche(name="Flasche", start_min=0, ende_min=60):
    return {
        "id": neue_id(),
        "art": "flasche",
        "name": name,
        "start_min": int(start_min),
        "ende_min": int(ende_min),
        "volumen_ml": 500.0,
        "pulver_modus": "selbst",
        "malto_kh_prozent": 96.0,
        "fructose_kh_prozent": 100.0,
        "fertig_verhaeltnis": 0.8,
        "fertig_kh_prozent": 90.0,
    }


def neuer_zusatz(name="Riegel", typ="Riegel", start_min=0, ende_min=60):
    return {
        "id": neue_id(),
        "art": "zusatz",
        "typ": typ,
        "name": name,
        "start_min": int(start_min),
        "ende_min": int(ende_min),
        "anzahl": 1.0,
        "kh_pro_stueck": 40.0,
        "verhaeltnis": 0.5,
    }


def standard_plan():
    """Startplan wie bisherige Standardwerte: 2 h, 90 g/h, 2 Flaschen."""
    return {
        "dauer_h": 2.0,
        "carbs_pro_stunde": 90,
        "verhaeltnis_modus": "automatisch",
        "eigenes_verhaeltnis": 0.5,
        "eintraege": [
            neue_flasche("Flasche 1", 0, 60),
            neue_flasche("Flasche 2", 60, 120),
        ],
    }


ZUSATZ_TYPEN = ["Riegel", "Gel", "Sonstiges"]


def _zahl(wert, standard, typ=float):
    try:
        return typ(wert)
    except (TypeError, ValueError):
        return standard


def plan_normalisieren(daten):
    """Füllt fehlende Felder mit Standardwerten und erzwingt Typen.

    Unbekannte oder kaputte Einträge werden übersprungen statt die App
    abstürzen zu lassen. Gibt einen neuen Plan zurück.
    """
    basis = standard_plan()
    if not isinstance(daten, dict):
        return basis
    plan = {
        "dauer_h": _zahl(daten.get("dauer_h"), basis["dauer_h"]),
        "carbs_pro_stunde": _zahl(daten.get("carbs_pro_stunde"), basis["carbs_pro_stunde"], int),
        "verhaeltnis_modus": daten.get("verhaeltnis_modus")
        if daten.get("verhaeltnis_modus") in ("automatisch", "eigen") else "automatisch",
        "eigenes_verhaeltnis": _zahl(daten.get("eigenes_verhaeltnis"), basis["eigenes_verhaeltnis"]),
        "eintraege": [],
    }
    gesehene_ids = set()
    for roh in daten.get("eintraege", []) or []:
        if not isinstance(roh, dict) or roh.get("art") not in ("flasche", "zusatz"):
            continue
        vorlage = neue_flasche() if roh["art"] == "flasche" else neuer_zusatz()
        eintrag = {}
        for feld, std in vorlage.items():
            wert = roh.get(feld, std)
            if isinstance(std, bool) or feld in ("id", "art", "name", "typ", "pulver_modus"):
                eintrag[feld] = str(wert) if wert is not None else std
            elif isinstance(std, int):
                eintrag[feld] = _zahl(wert, std, int)
            else:
                eintrag[feld] = _zahl(wert, std, float)
        if eintrag["id"] in gesehene_ids or not eintrag["id"]:
            eintrag["id"] = neue_id()
        gesehene_ids.add(eintrag["id"])
        if eintrag["art"] == "flasche" and eintrag["pulver_modus"] not in ("selbst", "fertig"):
            eintrag["pulver_modus"] = "selbst"
        if eintrag["art"] == "zusatz" and eintrag["typ"] not in ZUSATZ_TYPEN:
            eintrag["typ"] = "Sonstiges"
        plan["eintraege"].append(eintrag)
    return plan


def eintrag_duplizieren(eintrag):
    kopie = copy.deepcopy(eintrag)
    kopie["id"] = neue_id()
    kopie["name"] = f"{eintrag['name']} (Kopie)"
    return kopie


def fahrt_minuten(plan):
    return int(round(plan["dauer_h"] * 60))


def zusatz_kh_gesamt(zusatz):
    """Gesamte KH eines Riegels/Gels im Zeitraum = Stückzahl x KH pro Stück."""
    return zusatz["anzahl"] * zusatz["kh_pro_stueck"]


def ziel_verhaeltnis(plan):
    if plan["verhaeltnis_modus"] == "eigen":
        return plan["eigenes_verhaeltnis"]
    return verhaeltnis_berechnen(plan["carbs_pro_stunde"])


# ---------------------------------------------------------------------------
# Prüfung
# ---------------------------------------------------------------------------

def plan_pruefen(plan):
    """Liefert Liste von (eintrag_id oder None, Fehlertext). Leer = gültig."""
    fehler = []
    if plan["dauer_h"] <= 0 or fahrt_minuten(plan) < 1:
        fehler.append((None, "Die Fahrtdauer muss größer als 0 sein."))
    if plan["carbs_pro_stunde"] <= 0:
        fehler.append((None, "Das KH-Ziel muss größer als 0 g/h sein."))
    if plan["eigenes_verhaeltnis"] < 0:
        fehler.append((None, "Das eigene Verhältnis darf nicht negativ sein."))
    dauer = fahrt_minuten(plan)
    for e in plan["eintraege"]:
        name = e["name"] or "(ohne Namen)"
        if e["start_min"] < 0 or e["ende_min"] > dauer:
            fehler.append((e["id"], f"{name}: Zeitraum {e['start_min']}–{e['ende_min']} min liegt "
                                    f"nicht innerhalb der Fahrt (0–{dauer} min)."))
        if e["start_min"] >= e["ende_min"]:
            fehler.append((e["id"], f"{name}: Start muss vor dem Ende liegen."))
        if e["art"] == "flasche":
            if e["volumen_ml"] <= 0:
                fehler.append((e["id"], f"{name}: Wasservolumen muss größer als 0 ml sein."))
            if e["pulver_modus"] == "selbst":
                for feld, label in (("malto_kh_prozent", "Maltodextrin"), ("fructose_kh_prozent", "Fruktose")):
                    if not (0 < e[feld] <= 100):
                        fehler.append((e["id"], f"{name}: KH-Gehalt {label}-Pulver muss > 0 und ≤ 100 g/100 g sein."))
            else:
                if not (0 < e["fertig_kh_prozent"] <= 100):
                    fehler.append((e["id"], f"{name}: KH-Gehalt des Fertigpulvers muss > 0 und ≤ 100 g/100 g sein."))
                if e["fertig_verhaeltnis"] < 0:
                    fehler.append((e["id"], f"{name}: Verhältnis des Fertigpulvers darf nicht negativ sein."))
        else:
            if e["anzahl"] < 0 or e["kh_pro_stueck"] < 0:
                fehler.append((e["id"], f"{name}: Stückzahl und KH pro Stück dürfen nicht negativ sein."))
            if e["verhaeltnis"] < 0:
                fehler.append((e["id"], f"{name}: Verhältnis darf nicht negativ sein."))
    return fehler


# ---------------------------------------------------------------------------
# Kleiner QP-Löser (primales Active-Set-Verfahren, nur numpy)
# ---------------------------------------------------------------------------

def _qp_loesen(H, g, A_eq, G, h, z0, max_iter=2000):
    """min 1/2 z'Hz + g'z  u. d. N.  A_eq z = A_eq z0,  G z >= h.

    H muss positiv definit sein, z0 zulässig. Liefert (z, konvergiert).
    """
    z = np.array(z0, dtype=float)
    n = z.size
    if A_eq is not None and len(A_eq):
        _, s, vt = np.linalg.svd(np.atleast_2d(A_eq), full_matrices=False)
        rang = int(np.sum(s > 1e-10 * max(s[0], 1.0)))
        A_eq = vt[:rang]
    else:
        A_eq = np.zeros((0, n))
    G = np.atleast_2d(G) if G is not None and len(G) else np.zeros((0, n))
    h = np.asarray(h, dtype=float) if len(G) else np.zeros(0)
    arbeit = []
    teilproblem_geloest = False  # nach vollem Schritt ist z Optimum auf der Arbeitsmenge
    for _ in range(max_iter):
        grad = H @ z + g
        C = np.vstack([A_eq, G[arbeit]]) if arbeit else A_eq
        m = C.shape[0]
        K = np.zeros((n + m, n + m))
        K[:n, :n] = H
        K[:n, n:] = -C.T
        K[n:, :n] = C
        rhs = np.concatenate([-grad, np.zeros(m)])
        try:
            loesung = np.linalg.solve(K, rhs)
        except np.linalg.LinAlgError:
            loesung = np.linalg.lstsq(K, rhs, rcond=None)[0]
        p, lam = loesung[:n], loesung[n:]
        if teilproblem_geloest or np.linalg.norm(p) <= 1e-10 * (1 + np.linalg.norm(z)):
            teilproblem_geloest = False
            lam_ungl = lam[A_eq.shape[0]:]
            if lam_ungl.size == 0 or lam_ungl.min() >= -1e-9 * (1 + np.abs(grad).max()):
                return z, True
            arbeit.pop(int(np.argmin(lam_ungl)))
            continue
        alpha, blockiert = 1.0, None
        Gp = G @ p
        for i in np.where(Gp < -1e-14)[0]:
            if i in arbeit:
                continue
            schritt = max(0.0, (h[i] - G[i] @ z) / Gp[i])
            if schritt < alpha:
                alpha, blockiert = schritt, int(i)
        z = z + alpha * p
        if blockiert is not None:
            arbeit.append(blockiert)
        else:
            teilproblem_geloest = True
    return z, False


# ---------------------------------------------------------------------------
# Planberechnung
# ---------------------------------------------------------------------------

def _ueberlappung(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def plan_berechnen(plan):
    """Berechnet Flaschenmengen, Abschnittsbilanz und Hinweise.

    Prioritäten der Verteilung (deterministisch):
      1. Gesamtziel: Flaschen liefern genau Ziel - Riegel/Gele (nie negativ).
      2. KH-Ziel je Abschnitt so genau wie möglich (gewichtete kleinste Quadrate).
      3. Gleichzeitige Flaschen bei sonst gleichen Bedingungen nach Volumen.
      4. Fruktose-Mindestmenge je Abschnitt so gut wie möglich.
      5. In Selbstmischungen nur die zusätzlich nötige Fruktose.
    """
    fehler = plan_pruefen(plan)
    if fehler:
        return {"gueltig": False, "fehler": fehler}

    D = fahrt_minuten(plan) / 60
    c = float(plan["carbs_pro_stunde"])
    r_ziel = ziel_verhaeltnis(plan)
    k_ziel = fruktose_anteil(r_ziel)
    T = c * D
    F_min = T * k_ziel

    flaschen = [e for e in plan["eintraege"] if e["art"] == "flasche"]
    zusaetze = [e for e in plan["eintraege"] if e["art"] == "zusatz"]

    # Abschnitte an allen Start-/Endzeiten
    grenzen = {0.0, D}
    for e in plan["eintraege"]:
        grenzen.update((e["start_min"] / 60, e["ende_min"] / 60))
    grenzen = sorted(grenzen)
    abschnitte = [(a, b) for a, b in zip(grenzen[:-1], grenzen[1:]) if b - a > 1e-12]
    L = np.array([b - a for a, b in abschnitte])
    K = len(abschnitte)

    # Riegel/Gele: einmalig, gleichmäßig über ihren Zeitraum
    z_kh = np.zeros(K)
    z_fr = np.zeros(K)
    zusatz_ergebnisse = {}
    for e in zusaetze:
        s, t = e["start_min"] / 60, e["ende_min"] / 60
        menge = zusatz_kh_gesamt(e)
        fr = menge * fruktose_anteil(e["verhaeltnis"])
        for k, (a, b) in enumerate(abschnitte):
            anteil = _ueberlappung(s, t, a, b) / (t - s)
            z_kh[k] += menge * anteil
            z_fr[k] += fr * anteil
        zusatz_ergebnisse[e["id"]] = {
            "kh": menge, "fruktose": fr, "glukose": menge - fr, "rate": menge / (t - s),
        }
    Q = float(z_kh.sum())

    # Flaschen: Anteil je Abschnitt (gleichmäßiges Trinken)
    n = len(flaschen)
    A = np.zeros((K, n))
    for i, e in enumerate(flaschen):
        s, t = e["start_min"] / 60, e["ende_min"] / 60
        for k, (a, b) in enumerate(abschnitte):
            A[k, i] = _ueberlappung(s, t, a, b) / (t - s)
    volumen = np.array([e["volumen_ml"] for e in flaschen], dtype=float)
    selbst = [i for i, e in enumerate(flaschen) if e["pulver_modus"] == "selbst"]
    kappa = np.array([fruktose_anteil(e["fertig_verhaeltnis"]) if e["pulver_modus"] == "fertig" else 0.0
                      for e in flaschen])

    R = max(0.0, T - Q)
    ziel_kh = c * L
    ziel_fr = ziel_kh * k_ziel
    W = np.diag(1 / L)
    hinweise = []
    naeherung = False

    x = np.zeros(n)
    if n and R > 0:
        w_vol = volumen.mean() / volumen / D
        # Phase 1: KH je Abschnitt, Gesamtsumme fest, Volumen als Gleichstand-Regel
        H = 2 * (A.T @ W @ A + 1e-6 * np.diag(w_vol))
        g = 2 * A.T @ W @ (z_kh - ziel_kh)
        x0 = R * volumen / volumen.sum()
        x, ok = _qp_loesen(H, g, np.ones((1, n)), np.eye(n), np.zeros(n), x0)
        naeherung |= not ok
        x = np.maximum(x, 0.0)
        x *= R / x.sum()

    y = np.zeros(n)  # Fruktose-KH je Flasche
    m = len(selbst)
    if n and k_ziel > 0 and x.sum() > 0:
        bedarf = ziel_fr - z_fr  # je Abschnitt noch fehlende Fruktose

        def fruktose_phase(x_fest, y_start):
            """Phase 2: Fruktose-Fehlbetrag je Abschnitt minimieren (x fest)."""
            fest = A @ (kappa * x_fest)
            As = A[:, selbst]
            # Variablen [y_selbst (m), u (K)]
            Hm = np.zeros((m + K, m + K))
            Hm[:m, :m] = 2e-6 * np.diag(volumen[selbst].mean() / volumen[selbst] / D) if m else 0
            Hm[m:, m:] = 2 * W
            gm = np.zeros(m + K)
            G = np.vstack([
                np.hstack([As, np.eye(K)]),                     # Fruktose + u >= Bedarf
                np.hstack([np.zeros((K, m)), np.eye(K)]),       # u >= 0
                np.hstack([np.eye(m), np.zeros((m, K))]),       # y >= 0
                np.hstack([-np.eye(m), np.zeros((m, K))]),      # y <= x
            ])
            hv = np.concatenate([bedarf - fest, np.zeros(K), np.zeros(m), -x_fest[selbst]])
            u0 = np.maximum(0.0, bedarf - fest - As @ y_start)
            z, ok = _qp_loesen(Hm, gm, None, G, hv, np.concatenate([y_start, u0]))
            return z[:m], np.maximum(z[m:], 0.0), ok

        y_s, u, ok = fruktose_phase(x, np.zeros(m))
        naeherung |= not ok

        # Phase 2b: Nur falls Fruktose fehlt, KH zwischen gleichwertigen Flaschen
        # verschieben (KH je Abschnitt bleiben exakt gleich).
        if u.sum() > TOLERANZ_G and n >= 2:
            As = A[:, selbst]
            nv = n + m + K
            Hb = np.zeros((nv, nv))
            Hb[:n, :n] = 2e-6 * np.diag(volumen.mean() / volumen / D)
            if m:
                Hb[n:n + m, n:n + m] = 2e-6 * np.diag(volumen[selbst].mean() / volumen[selbst] / D)
            Hb[n + m:, n + m:] = 2 * W
            A_eq = np.vstack([A, np.ones((1, n))])
            A_eq = np.hstack([A_eq, np.zeros((A_eq.shape[0], m + K))])
            sel = np.zeros((m, n))
            for j, i in enumerate(selbst):
                sel[j, i] = 1.0
            G = np.vstack([
                np.hstack([A * kappa, As, np.eye(K)]),
                np.hstack([np.zeros((K, n + m)), np.eye(K)]),
                np.hstack([np.eye(n), np.zeros((n, m + K))]),
                np.hstack([np.zeros((m, n)), np.eye(m), np.zeros((m, K))]),
                np.hstack([sel, -np.eye(m), np.zeros((m, K))]),
            ])
            hv = np.concatenate([bedarf, np.zeros(K), np.zeros(n), np.zeros(m), np.zeros(m)])
            z, ok = _qp_loesen(Hb, np.zeros(nv), A_eq, G, hv, np.concatenate([x, y_s, u]))
            if ok and np.maximum(z[n + m:], 0).sum() < u.sum() - TOLERANZ_G:
                x = np.maximum(z[:n], 0.0)
                x *= R / x.sum()
                y_s, u, ok = fruktose_phase(x, np.minimum(np.maximum(z[n:n + m], 0), x[selbst]))
            naeherung |= not ok

        # Phase 3: nur notwendige Fruktose in Selbstmischungen (x fest)
        if m:
            fest = A @ (kappa * x)
            As = A[:, selbst]
            Hc = 2e-8 * np.diag(volumen[selbst].mean() / volumen[selbst] / D)
            gc = np.ones(m)
            G = np.vstack([As, np.eye(m), -np.eye(m)])
            hv = np.concatenate([bedarf - fest - u * (1 + 1e-9) - 1e-9, np.zeros(m), -x[selbst]])
            y_c, ok = _qp_loesen(Hc, gc, None, G, hv, y_s)
            naeherung |= not ok
            y_s = np.clip(y_c, 0.0, x[selbst])
        for j, i in enumerate(selbst):
            y[i] = y_s[j]
    x[x < TOLERANZ_G] = 0.0
    if R > 0 and x.sum() > 0:
        x *= R / x.sum()  # Gesamtsumme nach dem Abschneiden kleiner Reste exakt halten
    for i in range(n):
        y[i] = kappa[i] * x[i] if flaschen[i]["pulver_modus"] == "fertig" else min(y[i], x[i])
    y[y < TOLERANZ_G] = 0.0

    # Ergebnisse je Flasche
    flaschen_ergebnisse = {}
    for i, e in enumerate(flaschen):
        dauer_h = (e["ende_min"] - e["start_min"]) / 60
        erg = {
            "kh": x[i], "fruktose": y[i], "glukose": x[i] - y[i], "rate": x[i] / dauer_h,
            "konzentration": konzentration_berechnen(x[i], e["volumen_ml"]),
            "verhaeltnis": (y[i] / (x[i] - y[i])) if x[i] - y[i] > TOLERANZ_G else None,
        }
        if e["pulver_modus"] == "selbst":
            erg["malto_pulver"] = pulver_menge(x[i] - y[i], e["malto_kh_prozent"])
            erg["fructose_pulver"] = pulver_menge(y[i], e["fructose_kh_prozent"])
            erg["pulver_gesamt"] = erg["malto_pulver"] + erg["fructose_pulver"]
        else:
            erg["fertig_pulver"] = pulver_menge(x[i], e["fertig_kh_prozent"])
            erg["pulver_gesamt"] = erg["fertig_pulver"]
        flaschen_ergebnisse[e["id"]] = erg

    # Abschnittsbilanz
    fl_kh = A @ x
    fl_fr = A @ y
    ist_kh = z_kh + fl_kh
    ist_fr = z_fr + fl_fr
    bilanz = []
    for k, (a, b) in enumerate(abschnitte):
        aktiv = [e["name"] for e in plan["eintraege"]
                 if _ueberlappung(e["start_min"] / 60, e["ende_min"] / 60, a, b) > 0]
        rate = ist_kh[k] / L[k]
        bilanz.append({
            "start_min": a * 60, "ende_min": b * 60, "aktiv": aktiv,
            "soll_kh": ziel_kh[k], "ist_kh": ist_kh[k], "riegel_kh": z_kh[k], "flaschen_kh": fl_kh[k],
            "rate": rate, "abweichung_rate": rate - c,
            "min_fruktose": ziel_fr[k], "ist_fruktose": ist_fr[k],
            "fruktose_fehlt": max(0.0, ziel_fr[k] - ist_fr[k]),
            "luecke": not aktiv,
        })

    # Hinweise
    def mm(v):
        return f"{v:g}"

    kh_gesamt = Q + x.sum()
    fr_gesamt = z_fr.sum() + y.sum()
    if n == 0 and Q < T - TOLERANZ_G:
        hinweise.append(("fehler", f"Keine Flasche angelegt: Es fehlen {T - Q:.1f} g KH zum Ziel von {T:.1f} g."))
    if Q > T + TOLERANZ_G:
        hinweise.append(("warnung", f"Riegel/Gele liefern allein {Q:.1f} g KH und liegen {Q - T:.1f} g über dem "
                                    f"Ziel von {T:.1f} g. Die Flaschen enthalten keine KH (nur Wasser)."))
    for ab in bilanz:
        zeit = f"{mm(round(ab['start_min'], 1))}–{mm(round(ab['ende_min'], 1))} min"
        if ab["luecke"]:
            hinweise.append(("warnung", f"Versorgungslücke {zeit}: kein Eintrag aktiv, "
                                        f"es fehlen {ab['soll_kh']:.1f} g KH."))
        elif abs(ab["abweichung_rate"]) > TOLERANZ_RATE:
            art = "Überversorgung" if ab["abweichung_rate"] > 0 else "Unterversorgung"
            hinweise.append(("warnung", f"{art} {zeit}: {ab['rate']:.1f} g/h statt {c:g} g/h "
                                        f"({ab['abweichung_rate']:+.1f} g/h)."))
        if ab["fruktose_fehlt"] > TOLERANZ_FRUKTOSE:
            hinweise.append(("warnung", f"Fruktose {zeit}: {ab['ist_fruktose']:.1f} g statt mindestens "
                                        f"{ab['min_fruktose']:.1f} g (fehlen {ab['fruktose_fehlt']:.1f} g)."))
    if any(ab["luecke"] or abs(ab["abweichung_rate"]) > TOLERANZ_RATE for ab in bilanz):
        hinweise.append(("info", "Bei gleichmäßiger Aufnahme je Eintrag ist das g/h-Ziel nicht in jedem Abschnitt "
                                 "erreichbar. Passe die Zeiträume der Flaschen/Riegel an oder plane die Aufnahme "
                                 "bewusst ungleichmäßig. Jede Flasche behält trotzdem genau eine Rezeptur."))
    if fr_gesamt < F_min - TOLERANZ_FRUKTOSE:
        hinweise.append(("warnung", f"Fruktose gesamt {fr_gesamt:.1f} g liegt unter der Mindestmenge "
                                    f"{F_min:.1f} g (Ziel {verhaeltnis_text(r_ziel)})."))
    for i, e in enumerate(flaschen):
        if e["pulver_modus"] == "fertig" and kappa[i] < k_ziel - 1e-9 and x[i] > 0:
            betroffen = any(A[k, i] > 0 and bilanz[k]["fruktose_fehlt"] > TOLERANZ_FRUKTOSE for k in range(K))
            if betroffen:
                hinweise.append(("warnung", f"{e['name']}: Fertigpulver mit {verhaeltnis_text(e['fertig_verhaeltnis'])} "
                                            f"enthält weniger Fruktose als das Ziel {verhaeltnis_text(r_ziel)}. "
                                            f"Selbstmischung, ein anderes Pulver oder fruktosehaltige Riegel/Gele wählen."))
    for i, e in enumerate(flaschen):
        if R > 0 and x[i] == 0:
            hinweise.append(("info", f"{e['name']}: Keine KH nötig – nur Wasser."))
    if naeherung:
        hinweise.append(("warnung", "Die Verteilung konnte numerisch nur näherungsweise bestimmt werden."))

    return {
        "gueltig": True, "fehler": [],
        "ziel_kh": T, "ziel_verhaeltnis": r_ziel, "min_fruktose": F_min,
        "kh_gesamt": kh_gesamt, "fruktose_gesamt": fr_gesamt, "glukose_gesamt": kh_gesamt - fr_gesamt,
        "zusatz_kh": Q, "flaschen_kh": float(x.sum()), "ueberschuss": max(0.0, Q - T),
        "fehlbetrag": max(0.0, T - kh_gesamt),
        "flaschen": flaschen_ergebnisse, "zusaetze": zusatz_ergebnisse,
        "abschnitte": bilanz, "hinweise": hinweise,
    }

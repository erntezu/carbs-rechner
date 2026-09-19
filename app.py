
import streamlit as st

st.title("Carbs Rechner")

if "schritt" not in st.session_state:
    st.session_state["schritt"] = "fahrt"

if "fahrt" not in st.session_state:
    st.session_state["fahrt"] = None

if "flaschen" not in st.session_state:
    st.session_state["flaschen"] = None

if "zusaetze_fertig" not in st.session_state:
    st.session_state["zusaetze_fertig"] = False

plan_vollstaendig = (
    st.session_state["fahrt"] is not None
    and st.session_state["flaschen"] is not None
    and st.session_state["zusaetze_fertig"]
)

if "zusaetze" not in st.session_state:
    st.session_state["zusaetze"] = []

if "zusatz_bearbeiten" not in st.session_state:
    st.session_state["zusatz_bearbeiten"] = None

# Definitionen der Funktionen
# Gesamt
def mischung_aufteilen(gesamt, verhaeltnis):
    malto_gesamt = gesamt / (1 + verhaeltnis)
    fructose = gesamt - malto_gesamt
    return malto_gesamt, fructose

# Flaschen + Riegel/Gels
def gesamt_berechnen(carbs_pro_stunde, dauer):
    return carbs_pro_stunde * dauer

def verhaeltnis_berechnen(carbs_pro_stunde):
    if carbs_pro_stunde <= 60:
        return 0.0
    elif carbs_pro_stunde <= 90:
        return (carbs_pro_stunde - 60) / 30 * 0.5
    elif carbs_pro_stunde < 120:
        return 0.5 + (carbs_pro_stunde - 90) / 30 * 0.3
    else:
        return 0.8

def carbs_flaschen_berechnen(carbs_flaschen_pro_stunde, malto_flaschen_pro_stunde, fructose_flaschen_pro_stunde, dauer):
    carbs_flaschen_gesamt = carbs_flaschen_pro_stunde * dauer
    malto_flaschen_gesamt = malto_flaschen_pro_stunde * dauer
    fructose_flaschen_gesamt = fructose_flaschen_pro_stunde * dauer
    return carbs_flaschen_gesamt, malto_flaschen_gesamt, fructose_flaschen_gesamt

def mischung_pro_flasche_berechnen(carbs_flaschen_gesamt, malto_flaschen_gesamt, fructose_flaschen_gesamt, flaschen):
    carbs_pro_flasche = carbs_flaschen_gesamt / flaschen
    malto_pro_flasche = malto_flaschen_gesamt / flaschen
    fructose_pro_flasche = fructose_flaschen_gesamt / flaschen
    return carbs_pro_flasche, malto_pro_flasche, fructose_pro_flasche

def konzentration_berechnen(carbs_pro_flasche, volumen_pro_flasche):
    konzentration = carbs_pro_flasche / volumen_pro_flasche * 100
    return konzentration

def zusaetze_berechnen(zusaetze):
    carbs_zusaetze_pro_stunde = 0.0
    malto_zusaetze_pro_stunde = 0.0
    fructose_zusaetze_pro_stunde = 0.0

    for zusatz in zusaetze:
        carbs_zusaetze = zusatz["anzahl"] * zusatz["carbs"]
        carbs_zusaetze_pro_stunde += carbs_zusaetze
        malto_zusatz, fructose_zusatz = mischung_aufteilen(carbs_zusaetze, zusatz["verhaeltnis"])
        malto_zusaetze_pro_stunde += malto_zusatz
        fructose_zusaetze_pro_stunde += fructose_zusatz

    return carbs_zusaetze_pro_stunde, malto_zusaetze_pro_stunde, fructose_zusaetze_pro_stunde

# Modus wählen
modus = st.radio(
    "Was möchtest du berechnen?",
    ["Gesamtmenge berechnen", "Flaschen + Riegel/Gels planen"]
)

# Eingabe der Werte
if modus == "Gesamtmenge berechnen":
    gesamt = st.number_input(
        "Gesamtmenge an Kohlenhydraten in g?",
        min_value=1,
        value=90,
        step=5
    )
    verhaeltnis = st.number_input(
        "Fructose zu 1 Teil Maltodextrin?",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05
        )

if modus == "Flaschen + Riegel/Gels planen":

    #Fahrten Block:
    if st.session_state["schritt"] == "fahrt":
        with st.form("fahrt_formular"):
            carbs_pro_stunde = st.number_input(
                "Kohlenhydrate pro Stunde in g?",
                min_value=1,
                value=st.session_state["fahrt"]["carbs_pro_stunde"] if st.session_state["fahrt"] is not None else 90,
                step=5
            )

            dauer = st.number_input(
                "Dauer in Stunden?",
                min_value=0.5,
                value=st.session_state["fahrt"]["dauer"] if st.session_state["fahrt"] is not None else 2.0,
                step=0.5
                )

            speichern = st.form_submit_button("Fahrt speichern")
            fahrt_abbrechen = st.form_submit_button("Abbrechen")

        if speichern:
            st.session_state["fahrt"] = {
                "carbs_pro_stunde": carbs_pro_stunde,
                "dauer": dauer
            }
            st.session_state["schritt"] = "auswertung" if plan_vollstaendig else "flaschen"
            st.rerun()

        if fahrt_abbrechen and plan_vollstaendig == True:
            st.session_state["schritt"] = "auswertung"
            st.rerun()

    if (
        st.session_state["fahrt"] is not None and st.session_state["schritt"] != "fahrt"):
            with st.container(border=True):
                st.subheader("Fahrt")
                st.write(
                    f"{st.session_state['fahrt']['dauer']:g} Stunden · "
                    f"{st.session_state['fahrt']['carbs_pro_stunde']:g} g KH/h"
                )

                if st.button("Fahrt bearbeiten"):
                    st.session_state["schritt"] = "fahrt"
                    st.rerun()

    #Flaschen Block:
    if st.session_state["schritt"] == "flaschen":
        gespeichertes_volumen = None
        gespeichertes_verhaeltnis = None

        if st.session_state["flaschen"] is not None:
            gespeichertes_volumen = st.session_state["flaschen"].get("volumen")
            gespeichertes_verhaeltnis = st.session_state["flaschen"].get("verhaeltnis")

        with st.form("flaschen_formular"):
            flaschen = st.number_input(
                "Anzahl der Flaschen?",
                min_value=1,
                value=st.session_state["flaschen"]["anzahl"] if st.session_state["flaschen"] is not None else 2,
                step=1
                )

            volumen_verwenden = st.checkbox(
                "Volumen für die Konzentration berücksichtigen",
                value=gespeichertes_volumen is not None
                )
            volumen_pro_flasche = st.number_input(
                "Volumen pro Flasche in ml?",
                min_value=100.0,
                step=50.0,
                value=gespeichertes_volumen if gespeichertes_volumen is not None else 500.0,
                )

            verhaeltnis_flaschen_verwenden = st.checkbox(
                "Eigenes Verhealtnis verwenden?",
                value=gespeichertes_verhaeltnis is not None
                )
            verhaeltnis_flaschen = st.number_input(
                "Eigenes Flaschenverhältnis 1:",
                min_value=0.0,
                max_value=1.0,
                step=0.05,
                value=gespeichertes_verhaeltnis if gespeichertes_verhaeltnis is not None else 0.5,
                )

            flaschen_speichern = st.form_submit_button("Flaschen speichern")
            flaschen_abbrechen = st.form_submit_button("Flaschen abbrechen")

        if flaschen_speichern:
            st.session_state["flaschen"] = {
                "anzahl": flaschen,
                "volumen": volumen_pro_flasche if volumen_verwenden else None,
                "verhaeltnis": verhaeltnis_flaschen if verhaeltnis_flaschen_verwenden else None,
            }
            st.session_state["schritt"] = "auswertung" if plan_vollstaendig else "zusatz"
            st.rerun()

        if flaschen_abbrechen and plan_vollstaendig == True:
            st.session_state["schritt"] = "auswertung"
            st.rerun()

    if st.session_state["flaschen"] is not None and st.session_state["schritt"] != "flaschen":
        with st.container(border=True):
            st.subheader("Flaschen")
            flaschen_daten = st.session_state["flaschen"]

            if flaschen_daten["volumen"] is not None:
                st.write(
                    f"{flaschen_daten['anzahl']} Flaschen "
                    f"a {flaschen_daten['volumen']:g} ml"
                )
            else:
                st.write(f"{flaschen_daten['anzahl']} Flaschen")

            if flaschen_daten["verhaeltnis"] is None:
                st.write("Verhältnis: automatisch")
            else:
                st.write(f"Verhältnis: 1:{flaschen_daten['verhaeltnis']:g}")

            if st.button("Flaschen bearbeiten"):
                st.session_state["schritt"] = "flaschen"
                st.rerun()

    #Zusatz Block:
    if st.session_state["schritt"] == "zusatz":
        bearbeiten_index = st.session_state["zusatz_bearbeiten"]
        gespeicherter_zusatz = None

        if bearbeiten_index is not None:
            gespeicherter_zusatz = st.session_state["zusaetze"][bearbeiten_index]

        zusatz_abbrechen = False

        with st.form(f"neuer_zusatz_formular_{bearbeiten_index}"):
            name = st.text_input(
                "Name des Zusatzes?",
                value=gespeicherter_zusatz["name"] if gespeicherter_zusatz is not None else ""
                )
            anzahl = st.number_input(
                "Stückzahl pro Stunde:",
                min_value=0.0,
                value=gespeicherter_zusatz["anzahl"] if gespeicherter_zusatz is not None else 1.0,
                step=0.5
                )
            carbs = st.number_input(
                "Kohlenhydrate pro Stück in g:",
                min_value=0,
                value=gespeicherter_zusatz["carbs"] if gespeicherter_zusatz is not None else 40,
                step=5
                )
            verhaeltnis = st.number_input(
                "Fructose zu 1 Teil Glucose/Malto:",
                min_value=0.0,
                max_value=1.0,
                value=gespeicherter_zusatz["verhaeltnis"] if gespeicherter_zusatz is not None else 0.5,
                step=0.05
                )
            zusatz_hinzufuegen = st.form_submit_button(
                "Änderung speichern" if bearbeiten_index is not None else "Zusatz hinzufügen"
                )
            if bearbeiten_index is not None:
                zusatz_abbrechen = st.form_submit_button("Abbrechen")            

        if zusatz_abbrechen:
            st.session_state["zusatz_bearbeiten"] = None
            st.rerun()

        if zusatz_hinzufuegen:
            if name.strip() == "":
                st.error("Bitte gib einen Namen für den Zusatz ein.")
            else:
                neuer_zusatz = {
                    "name": name.strip(),
                    "anzahl": anzahl,
                    "carbs": carbs,
                    "verhaeltnis": verhaeltnis
                }
                if bearbeiten_index is None:
                    st.session_state["zusaetze"].append(neuer_zusatz)
                else:
                    st.session_state["zusaetze"][bearbeiten_index] = neuer_zusatz
                st.session_state["zusatz_bearbeiten"] = None
                st.rerun()

        for index, zusatz in enumerate(st.session_state["zusaetze"]):
            with st.container(border=True):
                st.write(f"**{zusatz['name']}**")
                st.write(
                    f"{zusatz['anzahl']} Stück/h · "
                    f"{zusatz['carbs']} g KH pro Stück · "
                    f"Verhältnis 1:{zusatz['verhaeltnis']}"
                )
                st.write(f"Beitrag: {zusatz['anzahl'] * zusatz['carbs']} g KH/h")

                spalte_bearbeiten, spalte_loeschen = st.columns(2)

                with spalte_bearbeiten:
                    if st.button("Bearbeiten", key=f"zusatz_bearbeiten_{index}"):
                        st.session_state["zusatz_bearbeiten"] = index
                        st.rerun()
                with spalte_loeschen:
                    if st.button("Löschen", key=f"zusatz_loeschen_{index}"):
                        st.session_state["zusaetze"].pop(index)
                        st.session_state["zusatz_bearbeiten"] = None
                        st.rerun()

        if st.button("Zur Auswertung"):
            st.session_state["zusaetze_fertig"] = True
            st.session_state["schritt"] = "auswertung"
            st.rerun()

    if (st.session_state["zusaetze_fertig"] and st.session_state["schritt"] != "zusatz"):
        with st.container(border=True):
            st.subheader("Riegel & Gels")
            st.write(f"Zusätze: {len(st.session_state['zusaetze'])}")

            if st.button("Zusätze bearbeiten"):
                st.session_state["schritt"] = "zusatz"
                st.rerun()

# Aufruf der Werte:
if modus == "Gesamtmenge berechnen":
    malto_gesamt, fructose_gesamt = mischung_aufteilen(gesamt, verhaeltnis)

if modus == "Flaschen + Riegel/Gels planen":

    if st.session_state["schritt"] != "auswertung":
        st.stop()

    if st.session_state["fahrt"] is None:
        st.stop()

    carbs_pro_stunde = st.session_state["fahrt"]["carbs_pro_stunde"]
    dauer = st.session_state["fahrt"]["dauer"]

    if st.session_state["flaschen"] is None:
        st.stop()

    flaschen = st.session_state["flaschen"]["anzahl"]
    volumen_pro_flasche = st.session_state["flaschen"].get("volumen")
    verhaeltnis_flaschen = st.session_state["flaschen"].get("verhaeltnis")
    verhaeltnis_flaschen_verwenden = verhaeltnis_flaschen is not None

    carbs_zusatz_pro_stunde, malto_zusatz_pro_stunde, fructose_zusatz_pro_stunde = zusaetze_berechnen(
    st.session_state["zusaetze"])

    gesamt = gesamt_berechnen(carbs_pro_stunde, dauer)
    verhaeltnis = verhaeltnis_berechnen(carbs_pro_stunde)
    malto_pro_stunde, fructose_pro_stunde = mischung_aufteilen(carbs_pro_stunde, verhaeltnis)

    carbs_flaschen_pro_stunde = carbs_pro_stunde - carbs_zusatz_pro_stunde

    if verhaeltnis_flaschen_verwenden:
        malto_flaschen_pro_stunde, fructose_flaschen_pro_stunde = mischung_aufteilen(
            carbs_flaschen_pro_stunde, verhaeltnis_flaschen
        )
    else:
        malto_flaschen_pro_stunde = malto_pro_stunde - malto_zusatz_pro_stunde
        fructose_flaschen_pro_stunde = fructose_pro_stunde - fructose_zusatz_pro_stunde

    if carbs_flaschen_pro_stunde < -0.000001:
        st.error("Die Zusätze überschreiten die Kohlenhydrate pro Stunde. Bitte anpassen!")
        st.stop()
    elif malto_flaschen_pro_stunde < -0.000001 or fructose_flaschen_pro_stunde < -0.000001:
        st.error("Das automatische Gesamtverhältnis ist mit diesen Zusätzen nicht erreichbar. Ändere die Zusätze oder wähle ein eigenes Flaschenverhältnis!")
        st.stop()

    malto_flaschen_pro_stunde = max(0.0, malto_flaschen_pro_stunde)
    fructose_flaschen_pro_stunde = max(0.0, fructose_flaschen_pro_stunde)
    carbs_flaschen_pro_stunde = max(0.0, carbs_flaschen_pro_stunde)
    
    carbs_flaschen_gesamt, malto_flaschen_gesamt, fructose_flaschen_gesamt = carbs_flaschen_berechnen(carbs_flaschen_pro_stunde, malto_flaschen_pro_stunde, fructose_flaschen_pro_stunde, dauer)
    carbs_pro_flasche, malto_pro_flasche, fructose_pro_flasche = mischung_pro_flasche_berechnen(carbs_flaschen_gesamt, malto_flaschen_gesamt, fructose_flaschen_gesamt, flaschen)

    if malto_pro_flasche > 0:
        verhaeltnis_flaschen_ist = fructose_pro_flasche / malto_pro_flasche
    else:
        verhaeltnis_flaschen_ist = None

    malto = malto_flaschen_gesamt + malto_zusatz_pro_stunde * dauer
    fructose = fructose_flaschen_gesamt + fructose_zusatz_pro_stunde * dauer

    if malto > 0:
        verhaeltnis_gesamt = fructose / malto
    else:
        verhaeltnis_gesamt = None
    
    if volumen_pro_flasche is not None:
        konzentration = konzentration_berechnen(carbs_pro_flasche, volumen_pro_flasche)

# Ausgabe der Ergebnisse
if modus == "Gesamtmenge berechnen":
    st.write("Verhältnis Maltodextrin : Fructose:", "1 :", round(verhaeltnis, 2))
    st.write("Maltodextrin:", round(malto_gesamt, 1), "g")
    st.write("Fructose:", round(fructose_gesamt, 1), "g")

if modus == "Flaschen + Riegel/Gels planen":
    st.subheader("Dein Ergebnis")

    spalte_gesamt, spalte_flasche, spalte_zusaetze = st.columns(3)

    with spalte_gesamt:
        st.metric("Gesamt", f"{gesamt:.0f} g")

    with spalte_flasche:
        st.metric("Pro Flasche", f"{carbs_pro_flasche:.1f} g")

    with spalte_zusaetze:
        st.metric("Zusätze", f"{carbs_zusatz_pro_stunde:.1f} g/h")

    with st.container(border=True):
        st.subheader("Mischung pro Flasche")
        st.write(
            f"**{malto_pro_flasche:.1f} g Maltodextrin** + "
            f"**{fructose_pro_flasche:.1f} g Fructose**"
        )    

    with st.expander("Zusammensetzung und Konzentration"):
        if verhaeltnis_gesamt is not None:
            st.write("Verhältnis Maltodextrin : Fructose:", "1 :", round(verhaeltnis_gesamt, 2))
        elif fructose > 0:
            st.write("Gesamtverhältnis: Nur Fructose")
        else:
            st.write("Keine Kohlenhydrate!")

        st.write("Maltodextrin:", round(malto, 1), "g")
        st.write("Fructose:", round(fructose, 1), "g")

        if verhaeltnis_flaschen_ist is not None:
            st.write("Verhältnis Flasche Maltodextrin : Fructose:", "1:", round(verhaeltnis_flaschen_ist, 2))
        elif fructose_pro_flasche > 0:
            st.write("Flaschenverhältnis: Nur Fructose")
        else:
            st.write("Keine Kohlenhydrate in der Flasche!")

        if volumen_pro_flasche is not None:
            st.write("g Kohlenhydrate pro 100 ml:", round(konzentration, 1))
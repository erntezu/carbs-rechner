import streamlit as st

st.title("Carbs Rechner")

# Definitionen der Funktionen
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

def mischung_berechnen(gesamt, verhaeltnis):
    malto = gesamt / (1 + verhaeltnis)
    fructose = gesamt - malto
    return malto, fructose

def pro_flasche_berechnen(gesamt, malto, fructose, flaschen):
    carbs_pro_flasche = gesamt / flaschen
    malto_pro_flasche = malto / flaschen
    fructose_pro_flasche = fructose / flaschen
    return carbs_pro_flasche, malto_pro_flasche, fructose_pro_flasche

# Eingabe der Werte
carbs_pro_stunde = st.number_input(
    "Kohlenhydrate pro Stunde in g?",
    min_value=1,
    value=90,
    step=5
)

dauer_verwenden = st.checkbox("Fahrtdauer?")
if dauer_verwenden:
    dauer = st.number_input(
        "Dauer in Stunden?",
        min_value=0.5,
        value=2.0,
        step=0.5
    )
else:
    dauer = None

eigenes_verhaeltnis = st.checkbox("Eigenes Verhältnis?")
if eigenes_verhaeltnis:
    verhaeltnis = st.number_input(
        "Fructose zu 1 Teil Maltodextrin?",
        min_value=0.0,
        value=0.5,
        step=0.05
    )
else:
    verhaeltnis = verhaeltnis_berechnen(carbs_pro_stunde)

if dauer is not None:
    flaschen_verwenden = st.checkbox("Anzahl der Flaschen?")
    if flaschen_verwenden:
        flaschen = st.number_input(
            "Anzahl der Flaschen?",
            min_value=1.0,
            value=2.0,
            step=0.5
        )

# Berechnung der Werte
if dauer is not None:
    gesamt = gesamt_berechnen(carbs_pro_stunde, dauer)
else:
    gesamt = carbs_pro_stunde

malto, fructose = mischung_berechnen(gesamt, verhaeltnis)

if dauer is None or not flaschen_verwenden:
    flaschen = None

if flaschen is not None:
    carbs_pro_flasche, malto_pro_flasche, fructose_pro_flasche = pro_flasche_berechnen(gesamt, malto, fructose, flaschen)

# Ausgabe der Ergebnisse
st.write("Gesamte Kohlenhydrate:", gesamt, "g")
st.write("Verhältnis Maltodextrin : Fructose:", "1 :", round(verhaeltnis, 2))

if flaschen is not None:
    st.write("Kohlenhydrate pro Flasche:", round(carbs_pro_flasche, 1), "g")
    st.write("Maltodextrin pro Flasche:", round(malto_pro_flasche, 1), "g")
    st.write("Fructose pro Flasche:", round(fructose_pro_flasche, 1), "g")
else:
    st.write("Maltodextrin:", round(malto, 1), "g")
    st.write("Fructose:", round(fructose, 1), "g")
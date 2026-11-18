# Príklad rozšírenia formulára v app.py
col1, col2 = st.columns(2)
with col1:
    st.subheader("🇸🇰 Bazoš.sk")
    bazos_sk = st.checkbox("Hľadať na Bazoš.sk", value=config.get("bazos_sk", True))
    cena_od_sk = st.number_input("Cena od (€)", value=config.get("cena_od_sk", 0))
    cena_do_sk = st.number_input("Cena do (€)", value=config.get("cena_do_sk", 1000))
    psc_sk = st.text_input("PSČ (SK)", value=config.get("psc_sk", ""), placeholder="napr. 02801")
    okolie_sk = st.number_input("Okolie v km (SK)", min_value=0, max_value=200, value=config.get("okolie_sk", 25))

with col2:
    st.subheader("🇨🇿 Bazoš.cz")
    bazos_cz = st.checkbox("Hľadať na Bazoš.cz", value=config.get("bazos_cz", False))
    cena_od_cz = st.number_input("Cena od (Kč)", value=config.get("cena_od_cz", 0))
    cena_do_cz = st.number_input("Cena do (Kč)", value=config.get("cena_do_cz", 25000))
    psc_cz = st.text_input("PSČ (CZ)", value=config.get("psc_cz", ""), placeholder="napr. 11000")
    okolie_cz = st.number_input("Okolie v km (CZ)", min_value=0, max_value=200, value=config.get("okolie_cz", 25))

# Pri ukladaní do Firebase (db.collection("settings").document("user_config").set({...})) pridaj nové kľúče:
data_to_save = {
    "keyword": keyword,
    "bazos_sk": bazos_sk,
    "cena_od_sk": cena_od_sk,
    "cena_do_sk": cena_do_sk,
    "psc_sk": psc_sk.replace(" ", ""),
    "okolie_sk": okolie_sk,
    "bazos_cz": bazos_cz,
    "cena_od_cz": cena_od_cz,
    "cena_do_cz": cena_do_cz,
    "psc_cz": psc_cz.replace(" ", ""),
    "okolie_cz": okolie_cz,
    # ... zvyšok tvojich údajov
}

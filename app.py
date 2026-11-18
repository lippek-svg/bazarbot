import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import requests

# Inicializácia Firebase (bezpečné pre opakované načítanie)
if not firebase_admin._apps:
    firebase_secret = os.environ.get("FIREBASE_CREDENTIALS")
    if firebase_secret:
        cred_dict = json.loads(firebase_secret)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    else:
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None

st.title("🤖 BazarBOT Konfigurácia")

# Načítanie aktuálnych nastavení z Firebase
config = {}
if db:
    doc_ref = db.collection("settings").document("user_config")
    doc = doc_ref.get()
    if doc.exists:
        config = doc.to_dict()

# Formulár v rozhraní
keyword = st.text_input("Kľúčové slovo (napr. tamron 17-28mm)", value=config.get("keyword", ""))

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

# Tlačidlo na uloženie nastavení
if st.button("Uložiť nastavenia", type="primary"):
    if db:
        data_to_save = {
            "keyword": keyword,
            "bazos_sk": bazos_sk,
            "cena_od_sk": cena_od_sk,
            "cena_do_sk": cena_do_sk,
            "psc_sk": psc_sk.replace(" ", "").strip(),
            "okolie_sk": okolie_sk,
            "bazos_cz": bazos_cz,
            "cena_od_cz": cena_od_cz,
            "cena_do_cz": cena_do_cz,
            "psc_cz": psc_cz.replace(" ", "").strip(),
            "okolie_cz": okolie_cz,
        }
        db.collection("settings").document("user_config").set(data_to_save)
        st.success("Nastavenia boli úspešne uložené do Firebase!")
    else:
        st.error("Nepodarilo sa pripojiť k databáze Firebase.")

st.divider()

# --- TESTOVACIE REŽIMY ---
st.subheader("🧪 Testovacie nástroje")

if st.button("Otestovať Telegram správu"):
    token = "9264841857:AAHJR2NNilv2KHX3qQEBVuMiTTCh3HM6M6A"
    # Sem si môžeš docasne doplniť svoje chat_id alebo ho načítať zo Streamlit Secrets
    chat_id = st.secrets.get("CHAT_ID", "") 
    
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": "🧪 Toto je testovacia správa z BazarBOT rozhrania!"}
        try:
            res = requests.post(url, json=payload)
            if res.status_code == 200:
                st.success("Testovacia správa bola úspešne odoslaná na Telegram!")
            else:
                st.error(f"Chyba pri odosielaní: {res.text}")
        except Exception as e:
            st.error(f"Chyba pripojenia: {e}")
    else:
        st.warning("Chýba nastavený CHAT_ID v Streamlit Secrets.")

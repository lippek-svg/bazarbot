import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests

# 1. Inicializácia Firebase (funguje lokálne aj v cloude cez Secrets)
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred)
    except Exception:
        firebase_secrets = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_secrets)
        firebase_admin.initialize_app(cred)

db = firestore.client()

st.title("🛒 BazarBOT - Multi-platformový sledovač")

# Načítanie existujúcich nastavení z Firebase (ak už existujú)
doc_ref = db.collection("settings").document("user_config")
saved_data = doc_ref.get().to_dict() or {}

# 2. Nastavenie vyhľadávania
st.subheader("🔍 Čo a kde hľadať")
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "iPhone 15"))

st.write("**Vyber platformy na sledovanie:**")
col1, col2 = st.columns(2)

with col1:
    bazos_sk = st.checkbox("Bazoš.sk", value=saved_data.get("bazos_sk", True))
    bazos_cz = st.checkbox("Bazoš.cz", value=saved_data.get("bazos_cz", False))
    fb_market = st.checkbox("Facebook Marketplace", value=saved_data.get("fb_market", False))

with col2:
    vinted_sk = st.checkbox("Vinted.sk", value=saved_data.get("vinted_sk", False))
    vinted_cz = st.checkbox("Vinted.cz", value=saved_data.get("vinted_cz", False))
    vinted_pl = st.checkbox("Vinted.pl", value=saved_data.get("vinted_pl", False))

# Podmienené zobrazenie okruhu v km pre Facebook Marketplace
fb_radius = 20
if fb_market:
    fb_radius = st.slider("Okruh hľadania pre Facebook Marketplace (v km)", min_value=5, max_value=200, value=saved_data.get("fb_radius", 20), step=5)

st.divider()

# 3. Telegram nastavenia
st.subheader("📲 Telegram notifikácie")
telegram_token = st.text_input("Telegram Bot Token", value=saved_data.get("telegram_token", ""), type="password")
chat_id = st.text_input("Telegram Chat ID", value=saved_data.get("chat_id", ""))

def send_telegram_alert(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    return requests.post(url, json=payload).json()

# 4. Uloženie do Firebase
if st.button("💾 Uložiť nastavenia", type="primary"):
    config_data = {
        "keyword": keyword,
        "bazos_sk": bazos_sk,
        "bazos_cz": bazos_cz,
        "vinted_sk": vinted_sk,
        "vinted_cz": vinted_cz,
        "vinted_pl": vinted_pl,
        "fb_market": fb_market,
        "fb_radius": fb_radius if fb_market else None,
        "telegram_token": telegram_token,
        "chat_id": chat_id
    }
    doc_ref.set(config_data)
    st.success("Nastavenia boli uložené do Firebase databázy!")

    if telegram_token and chat_id:
        active_platforms = [name for name, active in [
            ("Bazoš.sk", bazos_sk), ("Bazoš.cz", bazos_cz),
            ("Vinted.sk", vinted_sk), ("Vinted.cz", vinted_cz), ("Vinted.pl", vinted_pl),
            (f"FB Marketplace ({fb_radius} km)", fb_market)
        ] if active]
        
        msg = f"✅ <b>Nastavenia aktualizované</b>\n🔍 Hľadám: <code>{keyword}</code>\n🌐 Platformy: {', '.join(active_platforms)}"
        res = send_telegram_alert(telegram_token, chat_id, msg)
        if not res.get("ok"):
            st.error("Chyba pri odosielaní Telegram správy. Skontroluj Token a Chat ID.")

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup

# 1. Bezpečná inicializácia Firebase
if not firebase_admin._apps:
    try:
        firebase_secrets = dict(st.secrets["firebase"])
        if "private_key" in firebase_secrets:
            firebase_secrets["private_key"] = firebase_secrets["private_key"].replace("\\n", "\n")
            
        cred = credentials.Certificate(firebase_secrets)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Chyba pri inicializácii Firebase: {e}")

db = None
if firebase_admin._apps:
    db = firestore.client()

st.title("🛒 BazarBOT - Multi-platformový sledovač")

saved_data = {}
if db:
    try:
        doc_ref = db.collection("settings").document("user_config")
        saved_data = doc_ref.get().to_dict() or {}
    except Exception:
        pass

# 2. Nastavenie vyhľadávania
st.subheader("🔍 Čo a kde hľadať")
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "Herný PC"))

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

fb_radius = 20
if fb_market:
    fb_radius = st.slider("Okruh hľadania pre Facebook Marketplace (v km)", min_value=5, max_value=200, value=saved_data.get("fb_radius", 20), step=5)

frequency = st.slider(
    "Frekvencia hľadania",
    min_value=30,
    max_value=1440,
    value=saved_data.get("frequency", 60),
    step=30,
    format="%d minút"
)

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
    if db:
        config_data = {
            "keyword": keyword,
            "bazos_sk": bazos_sk,
            "bazos_cz": bazos_cz,
            "vinted_sk": vinted_sk,
            "vinted_cz": vinted_cz,
            "vinted_pl": vinted_pl,
            "fb_market": fb_market,
            "fb_radius": fb_radius if fb_market else None,
            "frequency": frequency,
            "telegram_token": telegram_token,
            "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené do Firebase databázy!")
    else:
        st.error("Databáza nie je pripojená, nastavenia sa neuložili.")

    if telegram_token and chat_id:
        active_platforms = [name for name, active in [
            ("Bazoš.sk", bazos_sk), ("Bazoš.cz", bazos_cz),
            ("Vinted.sk", vinted_sk), ("Vinted.cz", vinted_cz), ("Vinted.pl", vinted_pl),
            (f"FB Marketplace ({fb_radius} km)", fb_market)
        ] if active]
        
        msg = f"✅ <b>Nastavenia aktualizované</b>\n🔍 Hľadám: <code>{keyword}</code>\n⏱ Frekvencia: {frequency} min\n🌐 Platformy: {', '.join(active_platforms)}"
        res = send_telegram_alert(telegram_token, chat_id, msg)
        if not res.get("ok"):
            st.error("Chyba pri odosielaní Telegram správy. Skontroluj Token a Chat ID.")

# 5. Vylepšený skener inzerátov pre Bazoš
def search_bazos(keyword):
    url = f"https://bazos.sk/vyhladavanie.php?hledat={keyword}&rubriky=bazos_sk&hlokalita=&cenaod=&cenado=&Submit=Hľadať"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    
    ads = []
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select(".inzeraty") or soup.select(".inzeratzobrazenie")
        
        for item in items[:5]:
            title_elem = item.select_one(".nadpis a") or item.select_one("h2 a")
            price_elem = item.select_one(".cena")
            if title_elem:
                title = title_elem.text.strip()
                link = "https://bazos.sk" + title_elem["href"] if title_elem.has_attr("href") else ""
                price = price_elem.text.strip() if price_elem else "Cena neuvedená"
                ads.append(f"• <a href='{link}'>{title}</a> ({price})")
    return ads

st.divider()
st.subheader("🚀 Manuálne spustenie")
if st.button("🔍 Sledovať inzeráty hneď"):
    if not telegram_token or not chat_id:
        st.warning("Najprv vyplň Telegram Token a Chat ID.")
    else:
        with st.spinner("Prehľadávam bazáre..."):
            results = search_bazos(keyword)
            if results:
                msg = f"🔍 <b>Výsledky pre: {keyword}</b>\n\n" + "\n".join(results)
                send_telegram_alert(telegram_token, chat_id, msg)
                st.success("Hľadanie dokončené, výsledky odoslané na Telegram!")
            else:
                st.info("Žiadne nové inzeráty sa nenašli.")

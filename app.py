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

# 2. Nastavenie vyhľadávania a cien
st.subheader("🔍 Čo a kde hľadať")
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "auto"))

col_p1, col_p2 = st.columns(2)
with col_p1:
    cena_od = st.number_input("Cena od (€)", min_value=0, value=saved_data.get("cena_od", 0), step=10)
with col_p2:
    cena_do = st.number_input("Cena do (€)", min_value=0, value=saved_data.get("cena_do", 10000), step=10)

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
    try:
        res = requests.post(url, json=payload).json()
        return res
    except Exception as e:
        return {"ok": False, "description": str(e)}

# 4. Uloženie do Firebase
if st.button("💾 Uložiť nastavenia", type="primary"):
    if db:
        config_data = {
            "keyword": keyword,
            "cena_od": cena_od,
            "cena_do": cena_do,
            "bazos_sk": bazos_sk,
            "bazos_cz": bazos_cz,
            "vinted_sk": vinted_sk,
            "vinted_cz": vinted_cz,
            "vinted_pl": vinted_pl,
            "fb_market": fb_market,
            "frequency": frequency,
            "telegram_token": telegram_token,
            "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené!")

    if telegram_token and chat_id:
        msg = f"✅ <b>BazarBOT: Nastavenia aktualizované</b>\n🔍 Hľadám: <code>{keyword}</code>"
        res = send_telegram_alert(telegram_token, chat_id, msg)
        if res.get("ok"):
            st.success("Notifikácia odoslaná na Telegram!")

# 5. Skener pre Bazoš
def search_bazos(keyword, domain="sk"):
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        ads = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "/inzerat/" in href:
                    title = a_tag.get_text(strip=True)
                    if not title or len(title) < 4 or "foto" in title.lower():
                        continue
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    
                    item = {
                        "title": title,
                        "link": link,
                        "price": "Neuvedená",
                        "telegram_text": f"• <a href='{link}'>{title}</a>"
                    }
                    if item not in ads:
                        ads.append(item)
                        if len(ads) >= 5:
                            break
        return ads
    except Exception as e:
        return []

st.divider()
st.subheader("🚀 Manuálne spustenie")

if st.button("🔍 Sledovať inzeráty hneď"):
    with st.spinner("Prehľadávam..."):
        all_ads = []
        if bazos_sk:
            all_ads.extend(search_bazos(keyword, "sk"))
        if bazos_cz:
            all_ads.extend(search_bazos(keyword, "cz"))
            
        st.session_state["latest_results"] = all_ads
        
        if all_ads and telegram_token and chat_id:
            formatted_lines = [ad["telegram_text"] for ad in all_ads]
            msg = f"🔍 <b>Nájdené inzeráty ({keyword}):</b>\n\n" + "\n".join(formatted_lines)
            send_telegram_alert(telegram_token, chat_id, msg)

# 6. Zobrazenie výsledkov
if "latest_results" in st.session_state:
    st.markdown("### 📋 Výsledky skenovania:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            st.markdown(f"- [{ad['title']}]({ad['link']})")
    else:
        st.write("Žiadne záznamy.")

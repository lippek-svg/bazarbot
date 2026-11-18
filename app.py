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
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "Herný PC"))

col_p1, col_p2 = st.columns(2)
with col_p1:
    cena_od = st.number_input("Cena od (€)", min_value=0, value=saved_data.get("cena_od", 0), step=10)
with col_p2:
    cena_do = st.number_input("Cena do (€)", min_value=0, value=saved_data.get("cena_do", 1000), step=10)

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
            "cena_od": cena_od,
            "cena_do": cena_do,
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

# 5. Skener s diagnostikou blokovania
def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/vyhladavanie.php?hledat={keyword}&rubriky=bazos_{domain}&cenaod={min_price}&cenado={max_price}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        st.write(f"🛠 **[Debug {domain.upper()}]** HTTP Status: `{response.status_code}` | Dĺžka HTML: `{len(response.text)} znakov`")
        
        # Ak je odpoveď podozrivo krátka alebo blokovaná, ukážeme HTML
        if response.status_code != 200 or len(response.text) < 1000:
            st.warning(Server zrejme blokuje požiadavku alebo vracia anomáliu.")
            st.code(response.text[:500])
            
        ads = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(".inzeraty")
            
            for item in items:
                title_elem = item.select_one(".nadpis a")
                price_elem = item.select_one(".cena")
                
                if title_elem:
                    title = title_elem.text.strip()
                    link = title_elem.get("href", "")
                    if link and not link.startswith("http"):
                        link = f"https://bazos.{domain}" + link
                    
                    price_text = price_elem.text.strip() if price_elem else "Cena neuvedená"
                    
                    ads.append({
                        "title": title,
                        "link": link,
                        "price": price_text,
                        "text": f"• <a href='{link}'>{title}</a> — <b>{price_text}</b>"
                    })
                    if len(ads) >= 5:
                        break
        return ads
    except Exception as e:
        st.error(f"Chyba pripojenia k Bazošovi ({domain}): {e}")
        return []

st.divider()
st.subheader("🚀 Manuálne spustenie a diagnostika")

if st.button("🔍 Sledovať inzeráty hneď"):
    with st.spinner("Prehľadávam bazáre..."):
        all_ads = []
        if bazos_sk:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "sk"))
        if bazos_cz:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "cz"))
            
        st.session_state["latest_results"] = all_ads
        
        if all_ads:
            formatted_lines = [ad["text"] for ad in all_ads]
            msg = f"🔍 <b>Nájdené inzeráty ({cena_od}€ - {cena_do}€):</b>\n\n" + "\n".join(formatted_lines)
            if telegram_token and chat_id:
                send_telegram_alert(telegram_token, chat_id, msg)
                st.success("Odoslané na Telegram aj zobrazené nižšie!")
        else:
            st.info("Žiadne inzeráty sa nenašli (skontroluj debug hlásenia vyššie).")

# 6. Zobrazenie výsledkov
if "latest_results" in st.session_state:
    st.markdown("### 📋 Výsledky skenovania:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}**")
    else:
        st.write("Žiadne záznamy.")

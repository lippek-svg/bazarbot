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

st.title("🛒 BazarBOT - Inteligentný jedinečný strážca")

saved_data = {}
if db:
    try:
        doc_ref = db.collection("settings").document("user_config")
        saved_data = doc_ref.get().to_dict() or {}
    except Exception:
        pass

# 2. Nastavenie vyhľadávania a cien
st.subheader("🔍 Čo a kde hľadať")
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "iphone"))

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

with col2:
    vinted_sk = st.checkbox("Vinted.sk", value=saved_data.get("vinted_sk", False))
    vinted_cz = st.checkbox("Vinted.cz", value=saved_data.get("vinted_cz", False))
    vinted_pl = st.checkbox("Vinted.pl", value=saved_data.get("vinted_pl", False))

frequency = st.slider(
    "Frekvencia hľadania",
    min_value=30,
    max_value=1440,
    value=saved_data.get("frequency", 30),
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

# Funkcia na kontrolu, či už bol inzerát poslaný
def is_ad_already_sent(ad_id):
    if not db:
        return False
    doc_ref = db.collection("sent_ads").document(str(ad_id))
    return doc_ref.get().exists

# Funkcia na uloženie inzerátu do databázy, aby sa neposielal znova
def mark_ad_as_sent(ad_id):
    if db:
        db.collection("sent_ads").document(str(ad_id)).set({"sent_at": firestore.SERVER_TIMESTAMP})

# 4. Uloženie nastavení do Firebase
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
            "frequency": frequency,
            "telegram_token": telegram_token,
            "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené!")

# 5. Skener pre Bazoš (vyberá konkrétne inzeráty s ID)
def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}&cenaod={min_price}&cenado={max_price}&Submit=Hľadať"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        ads = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select(".inzeraty") or soup.select(".inzerat")
            
            for item in items:
                title_elem = item.select_one(".nadpis a") or item.select_one("h2 a")
                price_elem = item.select_one(".cena")
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    
                    if not href or any(bad in href.lower() for bad in ["prispievat", "kontakt", "hodnotenie", "moje"]):
                        continue
                        
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    
                    # Získame unikátne ID inzerátu z URL (posledná číselná časť)
                    parts = href.strip("/").split("/")
                    ad_id = f"bazos_{domain}_" + (parts[-1] if parts and parts[-1].isdigit() else href)
                    
                    price_text = price_elem.get_text(strip=True) if price_elem else "Cena neuvedená"
                    
                    ads.append({
                        "id": ad_id,
                        "title": title,
                        "link": link,
                        "price": price_text,
                        "platform": f"Bazoš ({domain.upper()})"
                    })
        return ads
    except Exception as e:
        st.error(f"Chyba Bazoš: {e}")
        return []

st.divider()
st.subheader("🚀 Manuálne spustenie skenu")

if st.button("🔍 Skontrolovať nové inzeráty hneď"):
    if not telegram_token or not chat_id:
        st.warning("Najprv vyplň Telegram Token a Chat ID.")
    else:
        with st.spinner("Hľadám nové inzeráty..."):
            all_ads = []
            if bazos_sk:
                all_ads.extend(search_bazos(keyword, cena_od, cena_do, "sk"))
            if bazos_cz:
                all_ads.extend(search_bazos(keyword, cena_od, cena_do, "cz"))
            
            new_ads_found = 0
            
            # Prejdeme nájdené inzeráty a pošleme LEN tie, ktoré ešte nie sú v databáze (žiadne duplicity)
            for ad in all_ads:
                if not is_ad_already_sent(ad["id"]):
                    # Uložíme do databázy, aby sa už nabudúce neposlal
                    mark_ad_as_sent(ad["id"])
                    
                    # Zostavíme správu pre jeden konkrétny inzerát
                    msg = f"🚨 <b>Nový inzerát ({ad['platform']}):</b>\n\n• <a href='{ad['link']}'><b>{ad['title']}</b></a>\n💰 Cena: <b>{ad['price']}</b>"
                    
                    # Pošleme na Telegram samostatne
                    send_telegram_alert(telegram_token, chat_id, msg)
                    new_ads_found += 1
            
            st.session_state["latest_results"] = all_ads
            
            if new_ads_found > 0:
                st.success(f"Našiel som a odoslal {new_ads_found} nových inzerátov na Telegram!")
            else:
                st.info("Žiadne nové inzeráty (všetky nájdené už boli predtým odoslané).")

# 6. Zobrazenie výsledkov na webe
if "latest_results" in st.session_state:
    st.markdown("### 📋 Posledné skenované inzeráty:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            status_text = "✅ Už poslané" if is_ad_already_sent(ad["id"]) else "🆕 Nový (čaká na odoslanie)"
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}** | *{status_text}*")
    else:
        st.info("Žiadne záznamy.")

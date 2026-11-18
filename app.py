import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

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

def is_ad_already_sent(ad_id):
    if not db:
        return False
    doc_ref = db.collection("sent_ads").document(str(ad_id))
    return doc_ref.get().exists

def mark_ad_as_sent(ad_id):
    if db:
        db.collection("sent_ads").document(str(ad_id)).set({"sent_at": firestore.SERVER_TIMESTAMP})

# Uloženie nastavení do Firebase
if st.button("💾 Uložiť nastavenia", type="primary"):
    if db:
        config_data = {
            "keyword": keyword, "cena_od": cena_od, "cena_do": cena_do,
            "bazos_sk": bazos_sk, "bazos_cz": bazos_cz,
            "vinted_sk": vinted_sk, "vinted_cz": vinted_cz, "vinted_pl": vinted_pl,
            "frequency": frequency, "telegram_token": telegram_token, "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené!")

# 4. Skener pre Bazoš (vrátane parsovania času)
def parse_bazos_date(date_text):
    now = datetime.now()
    try:
        if "Dnes" in date_text:
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_text)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        elif "Včera" in date_text:
            time_match = re.search(r'(\d{1,2}):(\d{2})', date_text)
            if time_match:
                hour, minute = int(time_match.group(1)), int(time_match.group(2))
                return (now - timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            date_match = re.search(r'(\d{1,2})\.(\d{1,2})\.\s*(\d{4})', date_text)
            if date_match:
                day, month, year = map(int, date_match.groups())
                return datetime(year, month, day)
    except Exception:
        pass
    return now

def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}&cenaod={min_price}&cenado={max_price}&Submit=Hľadať"
    headers = {
        "User-Agent": "Mozilla/5.0",
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
                date_elem = item.select_one(".velikost10")
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    
                    if not href or any(bad in href.lower() for bad in ["prispievat", "kontakt", "hodnotenie", "moje"]):
                        continue
                        
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    
                    parts = href.strip("/").split("/")
                    ad_id = f"bazos_{domain}_" + (parts[-1] if parts and parts[-1].isdigit() else href)
                    
                    price_text = price_elem.get_text(strip=True) if price_elem else "Cena neuvedená"
                    date_text = date_elem.get_text(strip=True) if date_elem else ""
                    parsed_time = parse_bazos_date(date_text)
                    
                    ads.append({
                        "id": ad_id,
                        "title": title,
                        "link": link,
                        "price": price_text,
                        "time": parsed_time,
                        "platform": f"Bazoš ({domain.upper()})"
                    })
        return ads
    except Exception as e:
        st.error(f"Chyba Bazoš: {e}")
        return []

st.divider()

# 5. TESTOVACIE ROZHRANIE (Slider pre časové okno)
st.subheader("🧪 Testovacie rozhranie (Filtrovanie podľa času)")
test_hours = st.slider("Zvoľ časové okno (inzeráty za posledných X hodín)", min_value=1, max_value=24, value=5)

if st.button("🧪 Spustiť testovací filter"):
    with st.spinner("Sťahujem inzeráty na test..."):
        all_ads = []
        if bazos_sk:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "sk"))
        if bazos_cz:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "cz"))
            
        limit_time = datetime.now() - timedelta(hours=test_hours)
        filtered_ads = [ad for ad in all_ads if ad["time"] >= limit_time]
        
        st.success(f"Nájdených {len(filtered_ads)} inzerátov za posledných {test_hours} hodín:")
        for ad in filtered_ads:
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}** (*{ad['time'].strftime('%d.%m. %H:%M')}*)")

st.divider()

# 6. Ostré spustenie (Telegram notifikácie)
st.subheader("🚀 Ostré spustenie (Telegram notifikácie)")

if st.button("🔍 Skontrolovať a poslať na Telegram"):
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
            for ad in all_ads:
                if not is_ad_already_sent(ad["id"]):
                    mark_ad_as_sent(ad["id"])
                    msg = f"🚨 <b>Nový inzerát ({ad['platform']}):</b>\n\n• <a href='{ad['link']}'><b>{ad['title']}</b></a>\n💰 Cena: <b>{ad['price']}</b>"
                    send_telegram_alert(telegram_token, chat_id, msg)
                    new_ads_found += 1
            
            if new_ads_found > 0:
                st.success(f"Odoslaných {new_ads_found} nových inzerátov na Telegram!")
            else:
                st.info("Žiadne nové inzeráty na odoslanie.")

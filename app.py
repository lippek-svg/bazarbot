import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4ational import BeautifulSoup
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

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
            "frequency": frequency,
            "telegram_token": telegram_token,
            "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené!")

# 5. Skener pre Bazoš s filtrom na 24 hodín a cenu
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
                time_elem = item.select_one(".velikost10") or item.find(string=lambda t: t and ('dnes' in t.lower() || 'včera' in t.lower() || ':' in t))
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    
                    if not href or any(bad in href.lower() for bad in ["prispievat", "kontakt", "hodnotenie", "moje"]):
                        continue
                        
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    price_text = price_elem.get_text(strip=True) if price_elem else "Cena neuvedená"
                    
                    # Kontrola ceny (ak vieme cenu vyparsovať ako číslo)
                    price_val = 0
                    try:
                        import re
                        digits = re.findall(r'\d+', price_text.replace(" ", ""))
                        if digits:
                            price_val = int("".join(digits))
                    except:
                        pass
                    
                    # Filtrovanie podľa ceny zadaného rozsahu (ak je cena uvedená)
                    if price_val > 0 and not (min_price <= price_val <= max_price):
                        continue

                    item_data = {
                        "title": f"Bazoš ({domain.upper()}): {title}",
                        "link": link,
                        "price": price_text,
                        "telegram_text": f"• Bazoš ({domain.upper()}): <a href='{link}'>{title}</a> — <b>{price_text}</b>"
                    }
                    if item_data not in ads:
                        ads.append(item_data)
                        if len(ads) >= 5:
                            break
                            
            # Záložný zber, ak by štruktúra .inzeraty zlyhala, ale selektujeme len reálne detailné linky
            if not ads:
                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if any(rubric in href for rubric in ["/mobil/", "/pc/", "/elektro/", "/auto/", "/stroj/", "/ostatne/"]):
                        parts = href.strip("/").split("/")
                        if len(parts) >= 2 and parts[-1].isdigit():
                            title = a_tag.get_text(strip=True)
                            if not title or len(title) < 4:
                                continue
                            link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                            
                            item_data = {
                                "title": f"Bazoš ({domain.upper()}): {title}",
                                "link": link,
                                "price": "Overiť cenu",
                                "telegram_text": f"• Bazoš ({domain.upper()}): <a href='{link}'>{title}</a>"
                            }
                            if item_data not in ads:
                                ads.append(item_data)
                                if len(ads) >= 5:
                                    break
        return ads
    except Exception as e:
        st.error(f"Chyba Bazoš: {e}")
        return []

# 5.1 Vinted skener (odkaz na konkrétny katalóg filtrovaný na posledné hodiny / najnovšie)
def search_vinted(keyword, min_price, max_price, domain="sk"):
    url = f"https://www.vinted.{domain}/catalog?search_text={keyword}&price_from={min_price}&price_to={max_price}&order=newest_first"
    return [{
        "title": f"Vinted ({domain.upper()}): Najnovšie pre '{keyword}'",
        "link": url,
        "price": f"{min_price}€ - {max_price}€",
        "telegram_text": f"• Vinted ({domain.upper()}): <a href='{url}'>Nové inzeráty pre <b>{keyword}</b> (do {max_price}€)</a>"
    }]

st.divider()
st.subheader("🚀 Manuálne spustenie")

if st.button("🔍 Sledovať inzeráty hneď"):
    with st.spinner("Prehľadávam platformy (za posledných 24 hodín)..."):
        all_ads = []
        if bazos_sk:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "sk"))
        if bazos_cz:
            all_ads.extend(search_bazos(keyword, cena_od, cena_do, "cz"))
        if vinted_sk:
            all_ads.extend(search_vinted(keyword, cena_od, cena_do, "sk"))
        if vinted_cz:
            all_ads.extend(search_vinted(keyword, cena_od, cena_do, "cz"))
        if vinted_pl:
            all_ads.extend(search_vinted(keyword, cena_od, cena_do, "pl"))
            
        st.session_state["latest_results"] = all_ads
        
        if all_ads and telegram_token and chat_id:
            formatted_lines = [ad["telegram_text"] for ad in all_ads]
            msg = f"🚨 <b>Nové inzeráty za posledných 24h ({keyword}):</b>\n\n" + "\n".join(formatted_lines)
            send_telegram_alert(telegram_token, chat_id, msg)
            st.success("Filtrované inzeráty boli nájdené a odoslané na Telegram!")
        else:
            st.info("V zadanom cenovom rozsahu sa za posledných 24 hodín nič nenašlo.")

# 6. Zobrazenie výsledkov
if "latest_results" in st.session_state:
    st.markdown("### 📋 Výsledky skenovania:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}**")
    else:
        st.info("Žiadne záznamy.")

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import base64

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
keyword = st.text_input("Kľúčové slovo", value=saved_data.get("keyword", "auto"))

col_p1, col_p2 = st.columns(2)
with col_p1:
    cena_od = st.number_input("Cena od (€)", min_value=0, value=saved_data.get("cena_od", 500), step=10)
with col_p2:
    cena_do = st.number_input("Cena do (€)", min_value=0, value=saved_data.get("cena_do", 10000), step=10)

st.write("**Vyber platformy na sledovanie:**")
col1, col2 = st.columns(2)

with col1:
    bazos_sk = st.checkbox("Bazoš.sk", value=saved_data.get("bazos_sk", True))
    bazos_cz = st.checkbox("Bazoš.cz", value=saved_data.get("bazos_cz", False))

with col2:
    vinted_sk = st.checkbox("Vinted.sk", value=saved_data.get("vinted_sk", False))
    vinted_cz = st.checkbox("Vinted.cz", value=saved_data.get("vinted_cz", False))
    vinted_pl = st.checkbox("Vinted.pl", value=saved_data.get("vinted_pl", False))

st.info("🕒 Automatické sledovanie na pozadí je nastavené na interval **každých 60 minút**.")

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

def get_safe_doc_id(ad_id):
    encoded_bytes = base64.urlsafe_b64encode(str(ad_id).encode("utf-8"))
    return encoded_bytes.decode("utf-8").rstrip("=")

def is_ad_already_sent(ad_id):
    if not db:
        return False
    safe_id = get_safe_doc_id(ad_id)
    doc_ref = db.collection("sent_ads").document(safe_id)
    return doc_ref.get().exists

def mark_ad_as_sent(ad_id):
    if db:
        safe_id = get_safe_doc_id(ad_id)
        db.collection("sent_ads").document(safe_id).set({"sent_at": firestore.SERVER_TIMESTAMP})

def clean_old_sent_ads():
    """Automaticky vymaže z Firebase sent_ads záznamy staršie ako 48 hodín."""
    if not db:
        return
    try:
        limit_time = datetime.now() - timedelta(hours=48)
        old_docs = db.collection("sent_ads").where("sent_at", "<", limit_time).stream()
        
        batch = db.batch()
        count = 0
        for doc in old_docs:
            batch.delete(doc.reference)
            count += 1
            if count >= 400:
                batch.commit()
                batch = db.batch()
                count = 0
        if count > 0:
            batch.commit()
    except Exception as e:
        print(f"Chyba pri čistení databázy: {e}")

# Uloženie nastavení do Firebase
if st.button("💾 Uložiť nastavenia", type="primary"):
    if db:
        config_data = {
            "keyword": keyword, "cena_od": cena_od, "cena_do": cena_do,
            "bazos_sk": bazos_sk, "bazos_cz": bazos_cz,
            "vinted_sk": vinted_sk, "vinted_cz": vinted_cz, "vinted_pl": vinted_pl,
            "telegram_token": telegram_token, "chat_id": chat_id
        }
        db.collection("settings").document("user_config").set(config_data)
        st.success("Nastavenia boli uložené!")

# 4. Skener pre Bazoš
def parse_bazos_date_flag(date_text):
    current_date_str = datetime.now().strftime("%d.%m.%Y")
    clean_date_text = re.sub(r'\s+', '', date_text)
    clean_today = re.sub(r'\s+', '', current_date_str)
    
    if clean_today in clean_date_text or "dnes" in clean_date_text.lower():
        return True
    return False

def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/search.php?hledat={keyword}&cenaod={min_price}&cenado={max_price}&Submit=Hľadať"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8"
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
                    
                    is_today = parse_bazos_date_flag(date_text)
                    
                    ads.append({
                        "id": ad_id,
                        "title": title,
                        "link": link,
                        "price": price_text,
                        "is_today": is_today,
                        "date_text": date_text,
                        "platform": f"Bazoš ({domain.upper()})"
                    })
        return ads
    except Exception as e:
        return []

# 5. Skener pre Vinted (cez API)
def search_vinted(keyword, min_price, max_price, domain="sk"):
    url = f"https://www.vinted.{domain}/api/v2/catalog/items?search_text={keyword}&price_from={min_price}&price_to={max_price}&per_page=20"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        session.get(f"https://www.vinted.{domain}", timeout=5)
        
        response = session.get(url, timeout=10)
        ads = []
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            for item in items:
                item_id = item.get("id")
                title = item.get("title", "Bez názvu")
                url_path = item.get("url", "")
                link = f"https://www.vinted.{domain}{url_path}" if url_path else f"https://www.vinted.{domain}"
                
                price_struct = item.get("price", {})
                price_text = f"{price_struct.get('amount', '')} {price_struct.get('currency_code', 'EUR')}"
                
                created_ts = item.get("created_at_ts")
                parsed_time = datetime.fromtimestamp(created_ts) if created_ts else datetime.now()
                
                is_today = parsed_time.date() == datetime.now().date()
                
                ads.append({
                    "id": f"vinted_{domain}_{item_id}",
                    "title": title,
                    "link": link,
                    "price": price_text,
                    "is_today": is_today,
                    "time": parsed_time,
                    "date_text": parsed_time.strftime('%d.%m. %H:%M'),
                    "platform": f"Vinted ({domain.upper()})"
                })
        return ads
    except Exception as e:
        return []

st.divider()

# 6. TESTOVACIE ROZHRANIE
st.subheader("🧪 Testovacie rozhranie (Inzeráty za dnešný deň)")
st.write(f"Aktuálny zistený dátum: **{datetime.now().strftime('%d.%m.%Y')}**. Tlačidlo vyhľadá všetky inzeráty pridané dnes.")

if st.button("🧪 Spustiť test: Zobraziť dnešné inzeráty"):
    with st.spinner("Sťahujem dnešné inzeráty zo všetkých portálov..."):
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
            
        today_ads = [ad for ad in all_ads if ad["is_today"]]
        
        st.success(f"Nájdených **{len(today_ads)}** inzerátov pridaných **dnes**:")
        
        if today_ads:
            platforms_groups = {}
            for ad in today_ads:
                p = ad["platform"]
                if p not in platforms_groups:
                    platforms_groups[p] = []
                platforms_groups[p].append(ad)
                
            for platform_name, p_ads in platforms_groups.items():
                st.markdown(f"### 📌 {platform_name} ({len(p_ads)} inzerátov)")
                for ad in p_ads:
                    st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}** (*{ad['date_text']}*)")
        else:
            st.warning("Pre zadané kritériá sa dnes nenašli žiadne inzeráty.")
            
        with st.expander("🛠️ Zobraziť surový prehľad všetkých stiahnutých inzerátov (Debug)"):
            st.write(f"Celkovo stiahnutých položiek zo stránok (všetky dátumy): {len(all_ads)}")
            for ad in all_ads:
                st.write(f"- [{ad['platform']}] {ad['title']} | Dátum text: `{ad.get('date_text')}` | Je dnes: **{ad['is_today']}**")

st.divider()

# 7. OSTRÉ SPUSTENIE (Telegram notifikácie + Automatické čistenie DB)
st.subheader("🚀 Ostré spustenie (Telegram notifikácie)")

if st.button("🔍 Skontrolovať a poslať na Telegram"):
    if not telegram_token or not chat_id:
        st.warning("Najprv vyplň Telegram Token a Chat ID.")
    else:
        with st.spinner("Hľadám nové inzeráty a prečisťujem databázu..."):
            clean_old_sent_ads()
            
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
            
            new_ads_found = 0
            for ad in all_ads:
                if not ad["is_today"]:
                    continue
                    
                if not is_ad_already_sent(ad["id"]):
                    mark_ad_as_sent(ad["id"])
                    msg = f"🚨 <b>Nový inzerát ({ad['platform']}):</b>\n\n• <a href='{ad['link']}'><b>{ad['title']}</b></a>\n💰 Cena: <b>{ad['price']}</b>"
                    send_telegram_alert(telegram_token, chat_id, msg)
                    new_ads_found += 1
            
            if new_ads_found > 0:
                st.success(f"Odoslaných {new_ads_found} nových inzerátov na Telegram!")
            else:
                st.info("Žiadne nové inzeráty na odoslanie (všetky dnešné už boli notifikované).")

st.divider()

# 8. DIAGNOSTIKA / OVEROVACIA FUNKCIA KOMUNIKÁCIE S PORTÁLMI
st.subheader("🛡️ Diagnostika pripojenia k portálom")
st.write("Over, či portály odpovedajú a či tvoja IP adresa/server nie je blokovaná.")

if st.button("🩺 Spustiť diagnostický test pripojenia"):
    targets = {
        "Bazoš SK": "https://bazos.sk",
        "Bazoš CZ": "https://bazos.cz",
        "Vinted SK": "https://www.vinted.sk",
        "Vinted CZ": "https://www.vinted.cz",
        "Vinted PL": "https://www.vinted.pl"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for name, url in targets.items():
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                st.success(f"✅ **{name}**: OK (HTTP 200) — Stránka komunikuje a nie je zablokovaná.")
            elif res.status_code == 403 or res.status_code == 503:
                st.error(f"⛔ **{name}**: Blokované / Ochrana proti botom (HTTP {res.status_code})")
            else:
                st.warning(f"⚠️ **{name}**: Odpovedalo s kódom HTTP {res.status_code}")
        except Exception as e:
            st.error(f"❌ **{name}**: Chyba pripojenia ({e})")

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import requests
from bs4 import BeautifulSoup

# --- 1. INICIALIZÁCIA FIREBASE ---
if not firebase_admin._apps:
    # 1. Pokus načítať zo Streamlit Secrets ([firebase] tabuľka)
    try:
        firebase_secret = st.secrets.get("firebase")
        if firebase_secret:
            cred_dict = dict(firebase_secret)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
    except Exception:
        pass

    # 2. Fallback na Environment Variables (pre GitHub Actions / iné prostredie)
    if not firebase_admin._apps:
        env_secret = os.environ.get("FIREBASE_CREDENTIALS")
        if env_secret:
            cred_dict = json.loads(env_secret)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        elif os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None

# Zistenie Telegram tokenu a Chat ID zo Secrets alebo Environment Variables
TELEGRAM_TOKEN = "9264841857:AAHJR2NNilv2KHX3qQEBVuMiTTCh3HM6M6A"
CHAT_ID = st.secrets.get("CHAT_ID", os.environ.get("CHAT_ID", ""))

# --- 2. POMOCNÉ FUNKCIE NA VYHĽADÁVANIE A TELEGRAM ---
def send_telegram_message(message):
    if not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload)
        return res.status_code == 200
    except Exception:
        return False

def search_bazos(keyword, min_price, max_price, psc="", okolie=25, domain="sk"):
    clean_psc = str(psc).replace(" ", "").strip()
    url = (
        f"https://bazos.{domain}/search.php?"
        f"hledat={keyword}&rubriky=www&hlokalita={clean_psc}&humkreis={okolie}"
        f"&cenaod={min_price}&cenado={max_price}&Submit=H%BEada%F1" if domain == "sk" else
        f"https://bazos.{domain}/search.php?"
        f"hledat={keyword}&rubriky=www&hlokalita={clean_psc}&humkreis={okolie}"
        f"&cenaod={min_price}&cenado={max_price}&Submit=Hledat"
    )
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    ads = []
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return ads
            
        soup = BeautifulSoup(response.text, 'html.parser')
        inzeraty = soup.select('.inzeraty')
        
        for item in inzeraty:
            title_elem = item.select_one('.nadpis a')
            price_elem = item.select_one('.cena')
            loc_elem = item.select_one('.lokalita')
            
            if title_elem:
                title = title_elem.text.strip()
                link = "https://baz.os" + title_elem['href'] if title_elem['href'].startswith('/') else title_elem['href']
                price = price_elem.text.strip() if price_elem else "Cena neuvedená"
                location = loc_elem.text.strip() if location_elem else (loc_elem.text.strip() if loc_elem else "")
                
                ads.append({
                    "id": link,
                    "title": title,
                    "price": price,
                    "location": location,
                    "link": link
                })
    except Exception:
        pass
        
    return ads

# --- 3. STREAMLIT UI ---
st.title("🤖 BazarBOT Konfigurácia")

# Načítanie aktuálnych nastavení z Firebase
config = {}
if db:
    doc_ref = db.collection("settings").document("user_config")
    doc = doc_ref.get()
    if doc.exists:
        config = doc.to_dict()

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

# --- 4. ULOŽENIE A OKAMŽITÉ SPUSTENIE KONTROLY ---
if st.button("Uložiť nastavenia a overiť inzeráty", type="primary"):
    if not db:
        st.error("Nepodarilo sa pripojiť k databáze Firebase.")
    elif not keyword:
        st.warning("Zadajte kľúčové slovo pre vyhľadávanie.")
    else:
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
        
        # 1. Uložíme do Firebase[cite: 1]
        db.collection("settings").document("user_config").set(data_to_save)
        st.success("Nastavenia boli úspešne uložené do Firebase[cite: 1]!")
        
        # 2. Spustíme okamžité vyhľadávanie
        with st.spinner("Prehľadávam portály a kontrolujem nové inzeráty..."):
            all_ads = []
            
            if bazos_sk:
                all_ads.extend(search_bazos(keyword, cena_od_sk, cena_do_sk, psc_sk, okolie_sk, "sk"))
            if bazos_cz:
                all_ads.extend(search_bazos(keyword, cena_od_cz, cena_do_cz, psc_cz, okolie_cz, "cz"))
                
            # Načítanie histórie už poslaných
            sent_ref = db.collection("history").document("sent_ads")
            sent_doc = sent_ref.get()
            sent_ids = sent_doc.to_dict().get("ids", []) if sent_doc.exists else []
            
            new_sent_ids = list(sent_ids)
            sent_count = 0
            
            for ad in all_ads:
                if ad["id"] not in sent_ids:
                    msg = f"🔔 *Nový inzerát!*\n\n*{ad['title']}*\n💰 {ad['price']}\n📍 {ad['location']}\n🔗 [Odkaz na inzerát]({ad['link']})"
                    if send_telegram_message(msg):
                        new_sent_ids.append(ad["id"])
                        sent_count += 1
                        
            # Aktualizácia histórie vo Firebase
            if sent_count > 0:
                sent_ref.set({"ids": new_sent_ids[-200:]})
                st.success(f"Našiel som a odoslal som **{sent_count}** nových inzerátov na Telegram!")
            else:
                st.info("Žiadne nové inzeráty (všetky vyhovujúce inzeráty už boli v minulosti odoslané).")

st.divider()

# Testovacie tlačidlo pre istotu
st.subheader("🧪 Test Telegramu")
if st.button("Otestovať Telegram správu"):
    if CHAT_ID:
        success = send_telegram_message("🧪 Testovacia správa z BazarBOT rozhrania úspešná!")
        if success:
            st.success("Testovacia správa bola odoslaná!")
        else:
            st.error("Nepodarilo sa odoslať správu (skontrolujte CHAT_ID v Secrets).")
    else:
        st.warning("Chýba CHAT_ID v nastaveniach (Secrets).")

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os
import requests
from bs4 import BeautifulSoup

# Inicializácia Firebase
if not firebase_admin._apps:
    try:
        firebase_secret = st.secrets.get("firebase")
        if firebase_secret:
            cred_dict = dict(firebase_secret)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
    except Exception:
        pass

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

TELEGRAM_TOKEN = "9264841857:AAHJR2NNilv2KHX3qQEBVuMiTTCh3HM6M6A"
CHAT_ID = st.secrets.get("CHAT_ID", os.environ.get("CHAT_ID", ""))

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
                location = loc_elem.text.strip() if loc_elem else ""
                
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

st.title("🤖 BazarBOT Konfigurácia (Viacero kľúčových slov)")

# Načítanie konfigurácie
config = {}
if db:
    doc_ref = db.collection("settings").document("user_config")
    doc = doc_ref.get()
    if doc.exists:
        config = doc.to_dict()

saved_keywords = config.get("keywords", [{}, {}])
if len(saved_keywords) < 2:
    saved_keywords += [{}] * (2 - len(saved_keywords))

keywords_data = []

for i in range(2):
    kw_conf = saved_keywords[i]
    with st.expander(f"🔑 Kľúčové slovo #{i+1}: {kw_conf.get('keyword', 'Nenastavené')}", expanded=True):
        active = st.checkbox(f"Aktívne sledovať", value=kw_conf.get("active", True), key=f"active_{i}")
        keyword = st.text_input(f"Hľadaný výraz #{i+1}", value=kw_conf.get("keyword", ""), key=f"kw_{i}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**🇸🇰 Bazoš.sk**")
            b_sk = st.checkbox("Zapnúť SK", value=kw_conf.get("bazos_sk", True), key=f"bsk_{i}")
            c_od_sk = st.number_input("Cena od (€)", value=kw_conf.get("cena_od_sk", 0), key=f"codsk_{i}")
            c_do_sk = st.number_input("Cena do (€)", value=kw_conf.get("cena_do_sk", 1000), key=f"cdosk_{i}")
            p_sk = st.text_input("PSČ (SK)", value=kw_conf.get("psc_sk", ""), key=f"psk_{i}")
            o_sk = st.number_input("Okolie (km)", min_value=0, max_value=200, value=kw_conf.get("okolie_sk", 25), key=f"osk_{i}")
            
        with col2:
            st.markdown("**🇨🇿 Bazoš.cz**")
            b_cz = st.checkbox("Zapnúť CZ", value=kw_conf.get("bazos_cz", False), key=f"bcz_{i}")
            c_od_cz = st.number_input("Cena od (Kč)", value=kw_conf.get("cena_od_cz", 0), key=f"codcz_{i}")
            c_do_cz = st.number_input("Cena do (Kč)", value=kw_conf.get("cena_do_cz", 25000), key=f"cdoz_{i}")
            p_cz = st.text_input("PSČ (CZ)", value=kw_conf.get("psc_cz", ""), key=f"pcz_{i}")
            o_cz = st.number_input("Okolie (km) ", min_value=0, max_value=200, value=kw_conf.get("okolie_cz", 25), key=f"ocz_{i}")
            
        keywords_data.append({
            "active": active,
            "keyword": keyword,
            "bazos_sk": b_sk,
            "cena_od_sk": c_od_sk,
            "cena_do_sk": c_do_sk,
            "psc_sk": p_sk.replace(" ", "").strip(),
            "okolie_sk": o_sk,
            "bazos_cz": b_cz,
            "cena_od_cz": c_od_cz,
            "cena_do_cz": c_do_cz,
            "psc_cz": p_cz.replace(" ", "").strip(),
            "okolie_cz": o_cz,
        })

if st.button("Uložiť nastavenia a overiť inzeráty", type="primary"):
    if not db:
        st.error("Chýba pripojenie k Firebase.")
    else:
        db.collection("settings").document("user_config").set({"keywords": keywords_data})
        st.success("Nastavenia úspešne uložené!")
        
        with st.spinner("Prehľadávam portály pre všetky aktívne slová..."):
            all_ads = []
            sent_ref = db.collection("history").document("sent_ads")
            sent_doc = sent_ref.get()
            sent_ids = sent_doc.to_dict().get("ids", []) if sent_doc.exists else []
            
            new_sent_ids = list(sent_ids)
            sent_count = 0
            
            for item in keywords_data:
                if not item["active"] or not item["keyword"]:
                    continue
                if item["bazos_sk"]:
                    all_ads.extend(search_bazos(item["keyword"], item["cena_od_sk"], item["cena_do_sk"], item["psc_sk"], item["okolie_sk"], "sk"))
                if item["bazos_cz"]:
                    all_ads.extend(search_bazos(item["keyword"], item["cena_od_cz"], item["cena_do_cz"], item["psc_cz"], item["okolie_cz"], "cz"))
            
            for ad in all_ads:
                if ad["id"] not in sent_ids:
                    msg = f"🔔 *Nový inzerát!*\n\n*{ad['title']}*\n💰 {ad['price']}\n📍 {ad['location']}\n🔗 [Odkaz]({ad['link']})"
                    if send_telegram_message(msg):
                        new_sent_ids.append(ad["id"])
                        sent_count += 1
                        
            if sent_count > 0:
                sent_ref.set({"ids": new_sent_ids[-200:]})
                st.success(f"Odoslaných {sent_count} nových inzerátov!")
            else:
                st.info("Žiadne nové inzeráty.")

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

# 5. Skener pre Bazoš s diagnostikou
def search_bazos(keyword, domain="sk"):
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        st.write(f"🛠 **[Bazoš {domain.upper()}]** Status: `{response.status_code}` | Dĺžka: `{len(response.text)}`")
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
                        "title": f"Bazoš ({domain.upper()}): {title}",
                        "link": link,
                        "price": "Neuvedená",
                        "telegram_text": f"• Bazoš ({domain.upper()}): <a href='{link}'>{title}</a>"
                    }
                    if item not in ads:
                        ads.append(item)
                        if len(ads) >= 5:
                            break
        return ads
    except Exception as e:
        st.error(f"Chyba Bazoš: {e}")
        return []

# 5.1 Skener pre Vinted s diagnostikou API
def search_vinted(keyword, domain="sk"):
    url = f"https://www.vinted.{domain}/api/v2/catalog/items"
    params = {"search_text": keyword, "per_page": 5}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://www.vinted.{domain}/"
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        st.write(f"🛠 **[Vinted {domain.upper()}]** API Status: `{res.status_code}`")
        ads = []
        if res.status_code == 200:
            data = res.json()
            items = data.get("items", [])
            for item in items:
                title = item.get("title", "Neznámy názov")
                price_obj = item.get("price", {})
                price = f"{price_obj.get('amount', '')} {price_obj.get('currency_code', '€')}"
                link = item.get("url", "")
                
                ads.append({
                    "title": f"Vinted ({domain.upper()}): {title}",
                    "link": link,
                    "price": price,
                    "telegram_text": f"• Vinted ({domain.upper()}): <a href='{link}'>{title}</a> — <b>{price}</b>"
                })
        else:
            st.warning(f"Vinted {domain} vrátil blokovanie alebo chybu (Status {res.status_code}).")
        return ads
    except Exception as e:
        st.error(f"Chyba Vinted: {e}")
        return []

st.divider()
st.subheader("🚀 Manuálne spustenie")

if st.button("🔍 Sledovať inzeráty hneď"):
    with st.spinner("Prehľadávam platformy..."):
        all_ads = []
        if bazos_sk:
            all_ads.extend(search_bazos(keyword, "sk"))
        if bazos_cz:
            all_ads.extend(search_bazos(keyword, "cz"))
        if vinted_sk:
            all_ads.extend(search_vinted(keyword, "sk"))
        if vinted_cz:
            all_ads.extend(search_vinted(keyword, "cz"))
        if vinted_pl:
            all_ads.extend(search_vinted(keyword, "pl"))
            
        st.session_state["latest_results"] = all_ads
        
        if all_ads and telegram_token and chat_id:
            formatted_lines = [ad["telegram_text"] for ad in all_ads]
            msg = f"🔍 <b>Nájdené inzeráty ({keyword}):</b>\n\n" + "\n".join(formatted_lines)
            send_telegram_alert(telegram_token, chat_id, msg)
            st.success("Výsledky odoslané!")

# 6. Zobrazenie výsledkov
if "latest_results" in st.session_state:
    st.markdown("### 📋 Výsledky skenovania:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}**")
    else:
        st.info("Žiadne záznamy sa nenašli. Skontroluj stavové kódy vyššie.")

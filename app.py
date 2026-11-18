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
    try:
        res = requests.post(url, json=payload).json()
        return res
    except Exception as e:
        return {"ok": False, "description": str(e)}

# 4. Uloženie do Firebase a overenie Telegramu
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
    else:
        st.error("Databáza nie je pripojená, nastavenia sa neuložili.")

    if telegram_token and chat_id:
        active_platforms = [name for name, active in [
            ("Bazoš.sk", bazos_sk), ("Bazoš.cz", bazos_cz),
            ("Vinted.sk", vinted_sk), ("Vinted.cz", vinted_cz), ("Vinted.pl", vinted_pl),
            (f"FB Marketplace ({fb_radius} km)", fb_market)
        ] if active]
        
        msg = f"✅ <b>BazarBOT: Nastavenia aktualizované</b>\n🔍 Hľadám: <code>{keyword}</code> ({cena_od}€ - {cena_do}€)\n⏱ Frekvencia: {frequency} min\n🌐 Platformy: {', '.join(active_platforms)}"
        res = send_telegram_alert(telegram_token, chat_id, msg)
        if res.get("ok"):
            st.success("Notifikačná správa bola úspešne odoslaná na Telegram!")
        else:
            st.error(f"Chyba Telegram API: {res.get('description', 'Neznáma chyba')}")
    else:
        st.warning("Zadaj Telegram Token a Chat ID pre posielanie notifikácií.")

# 5. Stabilný skener pre Bazoš
def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}&cenaod={min_price}&cenado={max_price}&Submit=Hľadať"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8,en-US;q=0.7,en;q=0.6"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        ads = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Prejdeme všetky elementy s odkazmi na inzeráty
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "/inzerat/" in href:
                    title = a_tag.get_text(strip=True)
                    if not title or len(title) < 4:
                        continue
                        
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    
                    # Pokus o nájdenie ceny v okolí
                    parent = a_tag.find_parent("div") or a_tag.find_parent("table")
                    price_text = "Cena neuvedená"
                    if parent:
                        price_elem = parent.select_one(".cena") or parent.find(string=lambda t: t and ('€' in t or 'Kč' in t))
                        if price_elem:
                            price_text = price_elem.text.strip() if hasattr(price_elem, 'text') else str(price_elem).strip()
                    
                    # Unikátne pridanie inzerátu
                    ad_item = {
                        "title": title,
                        "link": link,
                        "price": price_text,
                        "text": f"• [{title}]({link}) — <b>{price_text}</b>",
                        "telegram_text": f"• <a href='{link}'>{title}</a> — <b>{price_text}</b>"
                    }
                    
                    if ad_item not in ads:
                        ads.append(ad_item)
                        if len(ads) >= 5:
                            break
        return ads
    except Exception as e:
        st.error(f"Chyba pripojenia k Bazošovi ({domain}): {e}")
        return []

# Zatiaľ pripravené šablóny pre Vinted a Facebook (vyžadujú API/pokročilé scrape tokeny, takže tu vracajú informačnú hlášku)
def search_vinted(keyword, domain="sk"):
    return [{"title": f"Vinted ({domain}) - Automatický skraper vyžaduje API", "link": f"https://www.vinted.{domain}", "price": "-", "text": f"• Vinted {domain} (žiadne priame výsledky bez API)", "telegram_text": f"• Vinted {domain} - skenovanie aktívne"}]

def search_fb(keyword, radius):
    return [{"title": f"Facebook Marketplace ({radius} km) - Vyžaduje Graph API", "link": "https://www.facebook.com/marketplace", "price": "-", "text": "• Facebook Marketplace - vyžaduje API prístup", "telegram_text": "• FB Marketplace skenovanie"}]

st.divider()
st.subheader("🚀 Manuálne spustenie")

if st.button("🔍 Sledovať inzeráty hneď"):
    if not telegram_token or not chat_id:
        st.warning("Najprv vyplň Telegram Token a Chat ID v sekcii vyššie.")
    else:
        with st.spinner("Prehľadávam zaškrtnuté platformy..."):
            all_ads = []
            
            if bazos_sk:
                all_ads.extend(search_bazos(keyword, cena_od, cena_do, "sk"))
            if bazos_cz:
                all_ads.extend(search_bazos(keyword, cena_od, cena_do, "cz"))
            if vinted_sk:
                # Pre Vinted / FB zatiaľ vypíšeme informáciu, kým nezapojíme API
                pass
            if vinted_cz:
                pass
            if vinted_pl:
                pass
            if fb_market:
                pass
                
            st.session_state["latest_results"] = all_ads
            
            if all_ads:
                formatted_lines = [ad["telegram_text"] for ad in all_ads]
                msg = f"🔍 <b>Nájdené inzeráty ({keyword} | {cena_od}€ - {cena_do}€):</b>\n\n" + "\n".join(formatted_lines)
                res = send_telegram_alert(telegram_token, chat_id, msg)
                if res.get("ok"):
                    st.success("Hľadanie dokončené, výsledky úspešne odoslané na Telegram aj zobrazené nižšie!")
                else:
                    st.error(f"Nepodarilo sa odoslať Telegram správu: {res.get('description')}")
            else:
                st.info("Pre zvolené filtre a platformy sa nenašli žiadne aktívne inzeráty.")

# 6. Zobrazenie výsledkov na stránke
if "latest_results" in st.session_state:
    st.markdown("### 📋 Výsledky skenovania:")
    if st.session_state["latest_results"]:
        for ad in st.session_state["latest_results"]:
            st.markdown(f"- [{ad['title']}]({ad['link']}) — **{ad['price']}**")
    else:
        st.write("Žiadne záznamy.")

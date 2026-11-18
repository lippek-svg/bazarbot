import os
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import base64

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
    except Exception as e:
        print(f"Chyba Firebase init: {e}")

db = firestore.client() if firebase_admin._apps else None

def send_telegram_alert(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_safe_doc_id(ad_id):
    encoded_bytes = base64.urlsafe_b64encode(str(ad_id).encode("utf-8"))
    return encoded_bytes.decode("utf-8").rstrip("=")

def is_ad_already_sent(ad_id):
    if not db:
        return False
    safe_id = get_safe_doc_id(ad_id)
    return db.collection("sent_ads").document(safe_id).get().exists

def mark_ad_as_sent(ad_id):
    if db:
        safe_id = get_safe_doc_id(ad_id)
        db.collection("sent_ads").document(safe_id).set({"sent_at": firestore.SERVER_TIMESTAMP})

def clean_old_sent_ads():
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
        print(f"Chyba pri čistení DB: {e}")

def parse_bazos_date_flag(date_text):
    current_date_str = datetime.now().strftime("%d.%m.%Y")
    clean_date_text = re.sub(r'\s+', '', date_text)
    clean_today = re.sub(r'\s+', '', current_date_str)
    if clean_today in clean_date_text or "dnes" in clean_date_text.lower():
        return True
    return False

def search_bazos(keyword, min_price, max_price, domain="sk"):
    url = f"https://bazos.{domain}/search.php?hledat={keyword}&cenaod={min_price}&cenado={max_price}&Submit=Hľadať"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
                    
                    if parse_bazos_date_flag(date_text):
                        ads.append({"id": ad_id, "title": title, "link": link, "price": price_text, "platform": f"Bazoš ({domain.upper()})"})
        return ads
    except Exception as e:
        print(f"Bazos error {domain}: {e}")
        return []

def main():
    if not db:
        print("Firebase nie je pripojený.")
        return

    try:
        config_doc = db.collection("settings").document("user_config").get()
        if not config_doc.exists:
            print("Žiadne uložené nastavenia vo Firebase.")
            return
        config = config_doc.to_dict()
    except Exception as e:
        print(f"Chyba načítania nastavení: {e}")
        return

    keyword = config.get("keyword", "iphone")
    cena_od = config.get("cena_od", 0)
    cena_do = config.get("cena_do", 1000)
    bazos_sk = config.get("bazos_sk", True)
    bazos_cz = config.get("bazos_cz", False)
    
    telegram_token = os.environ.get("TELEGRAM_TOKEN") or config.get("telegram_token")
    chat_id = os.environ.get("CHAT_ID") or config.get("chat_id")

    if not telegram_token or not chat_id:
        print("Chýbajú Telegram údaje.")
        return

    print(f"Spúšťam kontrolu pre kľúčové slovo: '{keyword}'...")
    clean_old_sent_ads()

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

    print(f"Skontrolované. Odoslaných nových inzerátov: {new_ads_found}")

if __name__ == "__main__":
    main()

import os
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
import json

# Inicializácia Firebase v GitHub Actions
firebase_secret = os.environ.get("FIREBASE_CREDENTIALS")
if firebase_secret:
    cred_dict = json.loads(firebase_secret)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client() if firebase_admin._apps else None

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Telegram token alebo Chat ID nie sú nastavené.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Chyba pri odosielaní správy na Telegram: {e}")

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
            print(f"Chyba pri načítaní Bazoš.{domain}: Status {response.status_code}")
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
    except Exception as e:
        print(f"Chyba pri parsovaní Bazoš.{domain}: {e}")
        
    return ads

def main():
    if not db:
        print("Firebase nie je inicializovaný.")
        return

    doc_ref = db.collection("settings").document("user_config")
    doc = doc_ref.get()
    if not doc.exists:
        print("Žiadna konfigurácia vo Firebase nebola nájdená.")
        return
        
    config = doc.to_dict()
    keyword = config.get("keyword", "")
    if not keyword:
        print("Nie je zadané žiadne kľúčové slovo.")
        return

    all_ads = []

    if config.get("bazos_sk", True):
        all_ads.extend(search_bazos(
            keyword=keyword,
            min_price=config.get("cena_od_sk", 0),
            max_price=config.get("cena_do_sk", 1000),
            psc=config.get("psc_sk", ""),
            okolie=config.get("okolie_sk", 25),
            domain="sk"
        ))

    if config.get("bazos_cz", False):
        all_ads.extend(search_bazos(
            keyword=keyword,
            min_price=config.get("cena_od_cz", 0),
            max_price=config.get("cena_do_cz", 25000),
            psc=config.get("psc_cz", ""),
            okolie=config.get("okolie_cz", 25),
            domain="cz"
        ))

    sent_ref = db.collection("history").document("sent_ads")
    sent_doc = sent_ref.get()
    sent_ids = sent_doc.to_dict().get("ids", []) if sent_doc.exists else []

    new_sent_ids = list(sent_ids)
    new_ads_found = 0

    for ad in all_ads:
        if ad["id"] not in sent_ids:
            message = f"🔔 *Nový inzerát!*\n\n*{ad['title']}*\n💰 {ad['price']}\n📍 {ad['location']}\n🔗 [Odkaz na inzerát]({ad['link']})"
            send_telegram_message(message)
            new_sent_ids.append(ad["id"])
            new_ads_found += 1

    if new_ads_found > 0:
        sent_ref.set({"ids": new_sent_ids[-200:]})
        print(f"Odoslaných {new_ads_found} nových inzerátov.")
    else:
        print("Žiadne nové inzeráty.")

if __name__ == "__main__":
    main()

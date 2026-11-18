def search_bazos(keyword, min_price, max_price, domain="sk"):
    # Úplne čistá URL na vyhľadávanie bez reštrikcií ceny, ak by robili problém
    url = f"https://bazos.{domain}/?hledat={keyword}&rubriky=bazos_{domain}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "sk-SK,sk;q=0.9,cs;q=0.8"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        ads = []
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Hľadáme akékoľvek odkazy, ktoré obsahujú /inzerat/
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "/inzerat/" in href:
                    title = a_tag.get_text(strip=True)
                    if not title or len(title) < 4 or "foto" in title.lower():
                        continue
                        
                    link = f"https://bazos.{domain}" + href if not href.startswith("http") else href
                    
                    ads.append({
                        "title": title,
                        "link": link,
                        "price": "Neznáma",
                        "text": f"• <a href='{link}'>{title}</a>",
                        "telegram_text": f"• <a href='{link}'>{title}</a>"
                    })
                    
                    if len(ads) >= 5:
                        break
        return ads
    except Exception as e:
        st.error(f"Chyba pripojenia: {e}")
        return []

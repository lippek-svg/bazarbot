# 5. Vylepšený skener inzerátov pre Bazoš
def search_bazos(keyword):
    url = f"https://bazos.sk/vyhladavanie.php?hledat={keyword}&rubriky=bazos_sk&hlokalita=&cenaod=&cenado=&Submit=Hľadať"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    
    ads = []
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Hľadáme inzeráty podrobnejšie (klasické riadky alebo boxy)
        items = soup.select(".inzeraty") or soup.select(".inzeratzobrazenie")
        
        for item in items[:5]:
            title_elem = item.select_one(".nadpis a") or item.select_one("h2 a")
            price_elem = item.select_one(".cena")
            if title_elem:
                title = title_elem.text.strip()
                link = "https://bazos.sk" + title_elem["href"] if title_elem.has_attr("href") else ""
                price = price_elem.text.strip() if price_elem else "Cena neuvedená"
                ads.append(f"• <a href='{link}'>{title}</a> ({price})")
    return ads

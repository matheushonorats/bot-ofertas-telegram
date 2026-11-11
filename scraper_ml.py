import re
import time
from curl_cffi import requests
from bs4 import BeautifulSoup
from config import Config
from affiliate import format_ml_affiliate_link
from database import is_deal_seen, get_setting

# Real ML category pages (avoid /ofertas/<slug> which redirects to homepage)
CATEGORY_URL_MAP = {
    "tecnologia": "https://www.mercadolivre.com.br/c/celulares-e-telefones",
    "celulares-e-telefones": "https://www.mercadolivre.com.br/c/celulares-e-telefones",
    "eletrodomesticos": "https://www.mercadolivre.com.br/c/eletrodomesticos",
    "casa-e-decoracao": "https://www.mercadolivre.com.br/c/casa-moveis-e-decoracao",
    "casa-moveis-e-decoracao": "https://www.mercadolivre.com.br/c/casa-moveis-e-decoracao",
    "beleza-e-cuidado-pessoal": "https://www.mercadolivre.com.br/c/beleza-e-cuidado-pessoal",
    "ferramentas": "https://www.mercadolivre.com.br/c/ferramentas",
    "supermercado": "https://www.mercadolivre.com.br/ofertas/supermercado",
    "mais-vendidos": "https://www.mercadolivre.com.br/mais-vendidos",
}

def clean_price(price_str: str) -> float:
    if not price_str:
        return 0.0
    cleaned = price_str.replace(".", "").replace(",", ".").strip()
    match = re.search(r"[\d\.]+", cleaned)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0
    return 0.0

def fetch_mercadolivre_deals(limit_per_category=5):
    """
    Scrapes hot deals from Mercado Livre categories without intra-batch duplicates.
    """
    categories = Config.ML_CATEGORIES
    min_discount = int(get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT)))
    deals = []
    seen_ids_in_batch = set()
    seen_titles_in_batch = set()

    for cat in categories:
        cat_clean = cat.strip().lower()
        url = CATEGORY_URL_MAP.get(cat_clean, f"https://www.mercadolivre.com.br/c/{cat_clean}")

        try:
            resp = requests.get(url, impersonate="chrome120", timeout=15)
            if resp.status_code != 200:
                print(f"[Mercado Livre] Status {resp.status_code} para categoria {cat_clean}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".poly-card, .ui-search-layout__item")

            count = 0
            for card in cards:
                if count >= limit_per_category:
                    break

                title_el = card.select_one(".poly-component__title, a.poly-component__title, .ui-search-item__title")
                if not title_el:
                    continue
                title = title_el.text.strip()
                norm_title = title.lower()

                if norm_title in seen_titles_in_batch:
                    continue

                link = title_el.get("href")
                if not link:
                    link_el = card.select_one("a")
                    link = link_el.get("href") if link_el else ""

                if not link or "mercadolivre.com" not in link:
                    continue

                # Strip query string AND #fragment so affiliate params stay in query string
                clean_link = link.split("?")[0].split("#")[0]

                # Extract product MLB ID (prefer clean URL, fallback to raw link wid=...)
                mlb_match = re.search(r"(MLB-?\d+)", clean_link) or re.search(r"(MLB-?\d+)", link)
                product_id = f"ml_{mlb_match.group(1).replace('-', '')}" if mlb_match else f"ml_{clean_link}"

                if product_id in seen_ids_in_batch:
                    continue

                if is_deal_seen(product_id, title=title):
                    continue

                # Image
                img_el = card.select_one("img")
                img_url = ""
                if img_el:
                    img_url = img_el.get("data-src") or img_el.get("src") or ""

                # Current price
                price_container = card.select_one(".poly-price__current") or card
                frac_el = price_container.select_one(".andes-money-amount__fraction")
                cents_el = price_container.select_one(".andes-money-amount__cents")

                if not frac_el:
                    continue

                curr_price_str = frac_el.text.strip()
                if cents_el:
                    curr_price_str += f",{cents_el.text.strip()}"
                curr_price = clean_price(curr_price_str)

                # Original price
                orig_container = card.select_one(".andes-money-amount--previous")
                orig_price_str = ""
                orig_price = 0.0
                if orig_container:
                    orig_frac = orig_container.select_one(".andes-money-amount__fraction")
                    orig_cents = orig_container.select_one(".andes-money-amount__cents")
                    if orig_frac:
                        orig_price_str = orig_frac.text.strip()
                        if orig_cents:
                            orig_price_str += f",{orig_cents.text.strip()}"
                        orig_price = clean_price(orig_price_str)

                # Calculate discount percent
                discount_percent = 0
                if orig_price > curr_price and orig_price > 0:
                    discount_percent = round(((orig_price - curr_price) / orig_price) * 100)
                else:
                    disc_el = card.select_one(".andes-money-amount__discount")
                    if disc_el and "%" in disc_el.text:
                        match = re.search(r"(\d+)%", disc_el.text)
                        if match:
                            discount_percent = int(match.group(1))
                            if orig_price == 0 and discount_percent > 0:
                                orig_price = round(curr_price / (1 - (discount_percent / 100)), 2)
                                orig_price_str = f"{orig_price:.2f}".replace(".", ",")

                # Filter by dynamic minimum discount
                if discount_percent < min_discount:
                    continue

                seen_ids_in_batch.add(product_id)
                seen_titles_in_batch.add(norm_title)

                affiliate_link = format_ml_affiliate_link(clean_link, shorten=False)

                deals.append({
                    "id": product_id,
                    "platform": "Mercado Livre",
                    "title": title,
                    "current_price": curr_price,
                    "current_price_str": curr_price_str,
                    "original_price": orig_price,
                    "original_price_str": orig_price_str,
                    "discount_percent": discount_percent,
                    "link": affiliate_link,
                    "image": img_url,
                    "category": cat_clean,
                    "end_time": int(time.time() + 86400 * 2),
                    "stock": 10
                })
                count += 1

        except Exception as e:
            print(f"[Mercado Livre] Erro ao raspar categoria {cat_clean}: {e}")

    return deals

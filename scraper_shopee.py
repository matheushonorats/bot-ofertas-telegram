import requests
from config import Config
from affiliate import format_shopee_affiliate_link
from database import is_deal_seen

def fetch_shopee_deals(limit=50):
    """
    Fetches hot deals from Shopee Flash Sale API.
    """
    url = f"https://shopee.com.br/api/v4/flash_sale/flash_sale_get_items?limit={limit}&offset=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://shopee.com.br/flash_sale",
        "Accept": "application/json"
    }

    deals = []
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code != 200:
            print(f"[Shopee] Status {resp.status_code} na API Flash Sale")
            return deals

        data = resp.json()
        items = data.get("data", {}).get("items", [])

        for item in items:
            item_id = str(item.get("itemid", ""))
            shop_id = str(item.get("shopid", ""))
            name = item.get("name", "").strip()

            if not item_id or not name:
                continue

            product_id = f"shopee_{shop_id}_{item_id}"
            if is_deal_seen(product_id):
                continue

            # Price calculations (Shopee divides prices by 100,000)
            raw_price = item.get("price", 0)
            raw_orig_price = item.get("price_before_discount", 0)

            curr_price = round(raw_price / 100000.0, 2)
            orig_price = round(raw_orig_price / 100000.0, 2) if raw_orig_price else 0.0

            # Discount
            discount_percent = item.get("raw_discount", 0)
            if not discount_percent and orig_price > curr_price and orig_price > 0:
                discount_percent = round(((orig_price - curr_price) / orig_price) * 100)

            if discount_percent < Config.MIN_DISCOUNT_PERCENT:
                continue

            # Image (Garante que só envia ofertas com foto)
            image_hash = item.get("image") or ""
            if not image_hash and item.get("promo_images"):
                image_hash = item.get("promo_images")[0]

            if not image_hash:
                continue

            image_url = f"https://down-br.img.susercontent.com/file/{image_hash}"

            # Product URL & Affiliate conversion
            product_url = f"https://shopee.com.br/product/{shop_id}/{item_id}"
            affiliate_url = format_shopee_affiliate_link(product_url, shop_id=shop_id, item_id=item_id)

            curr_price_str = f"{curr_price:.2f}".replace(".", ",")
            orig_price_str = f"{orig_price:.2f}".replace(".", ",") if orig_price > 0 else ""

            deals.append({
                "id": product_id,
                "platform": "Shopee",
                "title": name,
                "current_price": curr_price,
                "current_price_str": curr_price_str,
                "original_price": orig_price,
                "original_price_str": orig_price_str,
                "discount_percent": int(discount_percent),
                "link": affiliate_url,
                "image": image_url,
                "category": "Flash Sale"
            })

    except Exception as e:
        print(f"[Shopee] Erro ao buscar ofertas: {e}")

    return deals

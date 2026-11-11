from curl_cffi import requests
from config import Config
from affiliate import format_shopee_affiliate_link
from database import is_deal_seen, get_setting

def fetch_shopee_deals(limit=50):
    """
    Fetches hot deals from Shopee Flash Sale API without intra-batch duplicates.
    """
    url = f"https://shopee.com.br/api/v4/flash_sale/flash_sale_get_items?limit={limit}&offset=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://shopee.com.br/flash_sale",
        "Accept": "application/json"
    }

    min_discount = int(get_setting("min_discount", str(Config.MIN_DISCOUNT_PERCENT)))
    deals = []
    seen_ids_in_batch = set()
    seen_titles_in_batch = set()
    try:
        resp = requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
        if resp.status_code != 200:
            print(f"[Shopee] Status {resp.status_code} na API Flash Sale")
            return deals

        data = resp.json()
        items = data.get("data", {}).get("items", [])

        for item in items:
            item_id = str(item.get("itemid", ""))
            shop_id = str(item.get("shopid", ""))
            name = item.get("name", "").strip()
            norm_name = name.lower()

            if not item_id or not name:
                continue

            product_id = f"shopee_{shop_id}_{item_id}"
            if product_id in seen_ids_in_batch or norm_name in seen_titles_in_batch:
                continue
            if is_deal_seen(product_id, title=name):
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

            if discount_percent < min_discount:
                continue

            seen_ids_in_batch.add(product_id)
            seen_titles_in_batch.add(norm_name)

            # Image (Garante que só envia ofertas com foto)
            image_hash = item.get("image") or ""
            if not image_hash and item.get("promo_images"):
                image_hash = item.get("promo_images")[0]

            if not image_hash:
                continue

            image_url = f"https://down-br.img.susercontent.com/file/{image_hash}"

            # Product URL & Affiliate conversion (shortened right before sending)
            product_url = f"https://shopee.com.br/product/{shop_id}/{item_id}"
            affiliate_url = format_shopee_affiliate_link(product_url, shop_id=shop_id, item_id=item_id, shorten=False)

            # Extract Shopee product/shop voucher when populated
            coupon_text = ""
            v = item.get("voucher")
            if isinstance(v, dict):
                v_code = str(v.get("voucher_code") or "").strip()
                v_pct = v.get("discount_percentage") or 0
                v_val = v.get("discount_value") or 0
                if v_code:
                    if v_pct:
                        coupon_text = f"{v_code} ({int(v_pct)}% OFF)"
                    elif v_val:
                        val_str = f"{v_val / 100000.0:.2f}".replace(".", ",")
                        coupon_text = f"{v_code} (R$ {val_str} OFF)"
                    else:
                        coupon_text = v_code
                elif v_pct:
                    coupon_text = f"{int(v_pct)}% OFF com Cupom na página"
                elif v_val:
                    val_str = f"{v_val / 100000.0:.2f}".replace(".", ",")
                    coupon_text = f"R$ {val_str} OFF com Cupom na página"

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
                "coupon": coupon_text,
                "link": affiliate_url,
                "image": image_url,
                "category": "Flash Sale",
                "end_time": int(item.get("end_time", 0)),
                "stock": int(item.get("stock", 1))
            })

    except Exception as e:
        print(f"[Shopee] Erro ao buscar ofertas: {e}")

    return deals

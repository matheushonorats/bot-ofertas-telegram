import re
import time
import json
import hmac
import hashlib
import urllib.parse
import requests
from config import Config

def shorten_url(url: str) -> str:
    """
    Returns the clean official URL.
    Does not use third-party shorteners (like da.gd or is.gd) that show warning/interstitial pages
    or get blocked by mobile browsers. Both Shopee (s.shopee.com.br) and Mercado Livre
    (mercadolivre.com.br) links are kept on their official trusted domains.
    """
    return url

def generate_shopee_short_link(original_url: str) -> str:
    """
    Generates an official Shopee affiliate shortlink via Shopee Affiliate Open API
    if SHOPEE_APP_ID and SHOPEE_APP_SECRET are configured.
    """
    app_id = Config.SHOPEE_APP_ID
    secret = Config.SHOPEE_APP_SECRET

    if not app_id or not secret:
        return ""

    endpoint = "https://open-api.affiliate.shopee.com.br/graphql"
    timestamp = int(time.time())

    query = """
    mutation generateShortLink($input: ShortLinkInput!) {
      generateShortLink(input: $input) {
        shortLink
      }
    }
    """
    variables = {
        "input": {
            "originUrl": original_url,
            "subIds": ["whatsapp"]
        }
    }
    payload = json.dumps({"query": query, "variables": variables}, separators=(',', ':'))

    factor = f"{app_id}{timestamp}{payload}{secret}"
    signature = hmac.new(
        secret.encode("utf-8"),
        factor.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={timestamp}, Signature={signature}"
    }

    try:
        resp = requests.post(endpoint, headers=headers, data=payload, timeout=10)
        data = resp.json()
        short_link = data.get("data", {}).get("generateShortLink", {}).get("shortLink")
        if short_link:
            return short_link
    except Exception as e:
        print(f"[Shopee Affiliate API] Erro ao gerar link curto: {e}")

    return ""

def format_ml_affiliate_link(url: str, shorten: bool = True) -> str:
    """Formats Mercado Livre product URL with affiliate tag on official mercadolivre.com.br domain."""
    clean_url = url.split("?")[0].split("#")[0]

    # Use clean short catalog URL /p/MLB... when available for much shorter official links
    p_match = re.search(r"/p/(MLB\d+)", clean_url)
    if p_match:
        base_url = f"https://www.mercadolivre.com.br/p/{p_match.group(1)}"
    else:
        base_url = clean_url

    tag = Config.ML_AFFILIATE_TAG
    template = Config.ML_AFFILIATE_URL_TEMPLATE

    if template:
        final_url = template.format(url=base_url, tag=tag)
    elif tag:
        separator = "&" if "?" in base_url else "?"
        final_url = f"{base_url}{separator}{tag}"
    else:
        final_url = base_url

    return shorten_url(final_url) if shorten else final_url

def format_shopee_affiliate_link(url: str, shop_id: str = "", item_id: str = "", shorten: bool = True) -> str:
    """Formats Shopee product URL with affiliate shortlink, universal link or tracking tag."""
    # 1. Try official Shopee Affiliate API if credentials are provided
    if Config.SHOPEE_APP_ID and Config.SHOPEE_APP_SECRET:
        api_link = generate_shopee_short_link(url)
        if api_link:
            return api_link

    # 2. Try universal link template
    clean_url = url.split("?")[0].split("#")[0]
    if Config.SHOPEE_UNIVERSAL_LINK:
        if "{shop_id}" in Config.SHOPEE_UNIVERSAL_LINK and "{item_id}" in Config.SHOPEE_UNIVERSAL_LINK:
            final_url = Config.SHOPEE_UNIVERSAL_LINK.format(shop_id=shop_id, item_id=item_id)
        else:
            separator = "&" if "?" in Config.SHOPEE_UNIVERSAL_LINK else "?"
            final_url = f"{Config.SHOPEE_UNIVERSAL_LINK}{separator}url={clean_url}"
        return shorten_url(final_url) if shorten else final_url

    # 3. Official Shopee universal redirect (generates valid uls_trackid & utm_term server-side)
    tag = Config.SHOPEE_AFFILIATE_TAG
    if tag:
        aff_match = re.search(r"(?:an_|affiliate_id=)(\d+)", tag)
        if aff_match:
            affiliate_id = aff_match.group(1)
            sub_match = re.search(r"sub_id=([^&]+)", tag)
            sub_id = urllib.parse.quote(sub_match.group(1), safe="") if sub_match else "whatsapp"
            encoded_origin = urllib.parse.quote(clean_url, safe="")
            final_url = (
                f"https://s.shopee.com.br/an_redir"
                f"?origin_link={encoded_origin}&affiliate_id={affiliate_id}&sub_id={sub_id}"
            )
            return shorten_url(final_url) if shorten else final_url

        separator = "&" if "?" in clean_url else "?"
        final_url = f"{clean_url}{separator}{tag}"
    else:
        final_url = clean_url

    return shorten_url(final_url) if shorten else final_url

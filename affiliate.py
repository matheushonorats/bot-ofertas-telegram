import time
import json
import hmac
import hashlib
import requests
from config import Config

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
            "subIds": ["telegram_deals"]
        }
    }
    payload = json.dumps({"query": query, "variables": variables}, separators=(',', ':'))

    # Calculate HMAC-SHA256 signature
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

def format_ml_affiliate_link(url: str) -> str:
    """Formats Mercado Livre product URL with affiliate tag or custom template."""
    clean_url = url.split("?")[0]
    tag = Config.ML_AFFILIATE_TAG
    template = Config.ML_AFFILIATE_URL_TEMPLATE

    if template:
        return template.format(url=clean_url, tag=tag)

    if tag:
        separator = "&" if "?" in clean_url else "?"
        return f"{clean_url}{separator}{tag}"

    return clean_url

def format_shopee_affiliate_link(url: str, shop_id: str = "", item_id: str = "") -> str:
    """Formats Shopee product URL with affiliate shortlink, universal link or tracking tag."""
    # 1. Try official Shopee Affiliate API if credentials are provided
    if Config.SHOPEE_APP_ID and Config.SHOPEE_APP_SECRET:
        api_link = generate_shopee_short_link(url)
        if api_link:
            return api_link

    # 2. Try universal link template
    clean_url = url.split("?")[0]
    if Config.SHOPEE_UNIVERSAL_LINK:
        if "{shop_id}" in Config.SHOPEE_UNIVERSAL_LINK and "{item_id}" in Config.SHOPEE_UNIVERSAL_LINK:
            return Config.SHOPEE_UNIVERSAL_LINK.format(shop_id=shop_id, item_id=item_id)
        separator = "&" if "?" in Config.SHOPEE_UNIVERSAL_LINK else "?"
        return f"{Config.SHOPEE_UNIVERSAL_LINK}{separator}url={clean_url}"

    # 3. Fallback: append tracking tag
    tag = Config.SHOPEE_AFFILIATE_TAG
    if tag:
        separator = "&" if "?" in clean_url else "?"
        return f"{clean_url}{separator}{tag}"

    return clean_url

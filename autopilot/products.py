"""Store catalog for product promo videos.

Reads the store's public product feed (STORE_URL/products.json), so no Shopify API key is needed.
Only ACTIVE products appear in that feed, so drafts are never promoted by accident.
"""
import os

import requests

from . import config

UA = {"User-Agent": "shopify-automation/1.0"}
_cache = {}


def catalog():
    """All published products: [{handle, title, price, url, images, type}]."""
    if "all" in _cache:
        return _cache["all"]
    out, page = [], 1
    while page <= 10:
        r = requests.get(f"{config.STORE_URL}/products.json", params={"limit": 250, "page": page},
                         headers=UA, timeout=30)
        r.raise_for_status()
        items = r.json().get("products", [])
        if not items:
            break
        for p in items:
            prices = [float(v["price"]) for v in p.get("variants", []) if v.get("available", True)] or \
                     [float(v["price"]) for v in p.get("variants", [])]
            out.append({
                "handle": p["handle"],
                "title": p["title"],
                "type": p.get("product_type", ""),
                "price": min(prices) if prices else None,
                "from_price": len(set(prices)) > 1,
                "url": f"{config.STORE_URL}/products/{p['handle']}",
                "images": [i["src"] for i in p.get("images", []) if i.get("src")],
            })
        page += 1
    _cache["all"] = out
    return out


def find(handle):
    handle = (handle or "").strip().lower()
    return next((p for p in catalog() if p["handle"] == handle), None)


def price_text(p):
    if not p or p.get("price") is None:
        return ""
    return ("From " if p.get("from_price") else "") + f"${p['price']:.2f}"


def download_images(p, out_dir, limit=6):
    """Downloads up to `limit` product photos. Returns local paths (first = featured image)."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for k, src in enumerate(p.get("images", [])[:limit]):
        url = src + ("&" if "?" in src else "?") + "width=1600"
        path = os.path.join(out_dir, f"product_{k}.jpg")
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            paths.append(path)
        except Exception as e:  # noqa: BLE001
            print(f"  product image {k} failed: {str(e)[:100]}")
    return paths

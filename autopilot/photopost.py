"""Daily product photo post on the Facebook Page and Instagram (alongside the Reels).

Picks the next product in rotation (least recently posted first), writes a short caption with
the free AI providers, posts the product photo to the Page, then reuses Facebook's hosted JPEG
for the Instagram post. Posts on its own (no approval) and reports the links in Telegram.
"""
import html
import os
import random
import time

import requests
from PIL import Image

from . import config, llm, products, publish, state, telegram

ANGLES = [
    "spotlight: what it is and the one everyday problem it solves",
    "gift idea: who on your list would love this",
    "how to use it in 3 quick steps",
    "this or that: ask followers a simple question to comment on",
    "deal reminder: new customers get 10% off with code WELCOME10",
    "routine: how it fits into a morning or evening routine",
    "small upgrade: a little thing that makes home life nicer",
]


def _esc(s):
    return html.escape(str(s or ""), quote=False)


def _pick(st):
    cat = [p for p in products.catalog() if p.get("images")]
    if not cat:
        raise RuntimeError("No published products with photos found in the store feed")
    last = st.setdefault("photo_posts", {})  # handle -> ISO time last posted
    cat.sort(key=lambda p: (last.get(p["handle"], ""), random.random()))
    return cat[0]


def _caption(p, angle):
    prompt = f"""Write a social media photo-post caption for the online store Ashvara (ashvara.store),
which sells pet, self-care and home-fitness products.

Product: {p['title']}
Category: {p.get('type') or 'general'}
Price: {products.price_text(p)}
Post angle: {angle}

Rules:
- 2 to 4 short sentences, friendly and natural, 1 or 2 emojis at most.
- Start with a scroll-stopping first line.
- No medical or health claims (do not say it cures, treats, heals, relieves pain or fixes posture). Describe comfort, convenience, style and everyday use instead.
- Do not invent features that are not obvious from the product name.
- Do not include links or prices; they are added after your text.
Return JSON: {{"caption": "...", "hashtags": ["5 to 8 relevant hashtags without spaces"]}}"""
    out = llm.ask_json(prompt, temperature=0.9)
    tags = [h if h.startswith("#") else f"#{h}" for h in out.get("hashtags", []) if h][:8]
    return out["caption"].strip(), tags


def _link(p, platform):
    sep = "&" if "?" in p["url"] else "?"
    return f"{p['url']}{sep}utm_source={platform}&utm_medium=social&utm_campaign=ashvara-posts"


def _prepare(src, out_dir):
    """JPEG within Instagram's allowed shapes (4:5 to 1.91:1), padded with white if needed."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    ratio = w / h
    if ratio < 0.8 or ratio > 1.91:
        side = max(w, h)
        canvas = Image.new("RGB", (side, side), "white")
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        im = canvas
    im.thumbnail((1440, 1440))
    path = os.path.join(out_dir, "post.jpg")
    im.save(path, "JPEG", quality=90)
    return path


def _facebook_photo(path, message, published):
    publish.resolve_page()
    g = f"https://graph.facebook.com/{config.IG_API_VERSION}"
    with open(path, "rb") as f:
        r = requests.post(f"{g}/{config.FB_PAGE_ID}/photos", timeout=120, files={"source": f}, data={
            "message": message, "published": "true" if published else "false",
            "access_token": config.FB_PAGE_TOKEN}).json()
    if "id" not in r:
        raise RuntimeError(f"Facebook photo failed: {r}")
    img = requests.get(f"{g}/{r['id']}", timeout=30, params={
        "fields": "images", "access_token": config.FB_PAGE_TOKEN}).json().get("images") or [{}]
    post = r.get("post_id", r["id"])
    return f"https://www.facebook.com/{post}", img[0].get("source")


def _instagram_photo(image_url, caption):
    ig = publish._ig_user_id()
    if not (ig and config.IG_ACCESS_TOKEN):
        raise RuntimeError("Instagram account not found for this Page")
    g = f"https://{config.IG_GRAPH_HOST}/{config.IG_API_VERSION}"
    tok = config.IG_ACCESS_TOKEN
    r = requests.post(f"{g}/{ig}/media", timeout=60, data={
        "image_url": image_url, "caption": caption[:2150], "access_token": tok}).json()
    if "id" not in r:
        raise RuntimeError(f"Instagram photo failed: {r}")
    for _ in range(12):
        s = requests.get(f"{g}/{r['id']}", timeout=30, params={"fields": "status_code", "access_token": tok}).json()
        if s.get("status_code") in ("FINISHED", None):
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        time.sleep(5)
    pub = requests.post(f"{g}/{ig}/media_publish", timeout=60, data={"creation_id": r["id"], "access_token": tok}).json()
    if "id" not in pub:
        raise RuntimeError(f"Instagram publish failed: {pub}")
    link = requests.get(f"{g}/{pub['id']}", timeout=30, params={"fields": "permalink", "access_token": tok}).json()
    return link.get("permalink", f"media id {pub['id']}")


def run(st, dry=False, only=None):
    if not config.FB_PAGE_TOKEN:
        return print("Photo post skipped: FB_PAGE_TOKEN not set")
    p = _pick(st)
    angle = ANGLES[st.get("photo_angle", 0) % len(ANGLES)]
    text, tags = _caption(p, angle)
    price = products.price_text(p)
    head = f"{text}\n\n{p['title']}" + (f" · {price}" if price else "")
    fb_msg = f"{head}\nShop it: {_link(p, 'facebook')}\n\n{' '.join(tags)}"
    ig_cap = f"{head}\nTap the link in our bio to shop 🛒\n\n{' '.join(tags[:config.INSTAGRAM_HASHTAGS])}"

    out_dir = os.path.join(config.WORK_DIR, "photo")
    imgs = products.download_images(p, out_dir, limit=1)
    if not imgs:
        raise RuntimeError(f"Could not download a photo for {p['title']}")
    path = _prepare(imgs[0], out_dir)
    if dry:
        telegram.send_photo(path, f"🧪 Photo post preview (not posted)\n\n{_esc(fb_msg)[:900]}")
        return

    results = []
    targets = {o.lower() for o in (only or [])} or config.PUBLISH_TO  # e.g. "photo facebook" posts to Facebook only
    want_fb, want_ig = "facebook" in targets, "instagram" in targets
    fb_url, hosted = _facebook_photo(path, fb_msg, published=want_fb)
    if want_fb:
        results.append(f"Facebook: {fb_url}")
    if want_ig:
        try:
            results.append(f"Instagram: {_instagram_photo(hosted, ig_cap)}")
        except Exception as e:  # noqa: BLE001
            results.append(f"Instagram failed: {str(e)[:300]}")

    st.setdefault("photo_posts", {})[p["handle"]] = state.iso()
    st["photo_angle"] = st.get("photo_angle", 0) + 1
    print("\n".join(results))
    telegram.send(f"🖼 <b>Daily photo post</b>: {_esc(p['title'])}\n" + "\n".join(_esc(r) for r in results))

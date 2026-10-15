"""AI presenter ("face of Ashvara") for product videos, made with fal.ai (paid per second of video).

- `candidates(st)` creates the cast (6 people + 2 pets) and shows them in Telegram; each can be re-made.
- `clip(audio, start, end, image, out)` makes the presenter say one part of the voiceover (lip-synced),
  so it drops straight into the timeline over the same audio.

The presenter shows and explains the product to the viewer. The scripts never have them pose as a
customer or claim personal results, and every video's description says the presenter is AI-generated.
"""
import base64
import os
import subprocess
import time

import requests

from . import config, state, storage, telegram

QUEUE = "https://queue.fal.run"
CREDIT = "Presenter: AI-generated character (Kling AI Avatar via fal.ai), not a real customer."

# The Ashvara cast. Each one keeps the same face (one saved picture, reused in every video) and the same voice.
CAST = [
    {"id": "maya", "name": "Maya", "kind": "human", "voice": "en-US-AvaMultilingualNeural",
     "look": "a friendly woman in her late 20s with shoulder-length brown hair, wearing a cream knit sweater"},
    {"id": "priya", "name": "Priya", "kind": "human", "voice": "en-US-EmmaMultilingualNeural",
     "look": "a warm South Asian woman in her early 30s with long dark hair in a low ponytail, wearing a sage green top"},
    {"id": "sofia", "name": "Sofia", "kind": "human", "voice": "en-US-SerenaMultilingualNeural",
     "look": "a cheerful Latina woman in her mid 30s with curly black hair, wearing a light denim shirt"},
    {"id": "ethan", "name": "Ethan", "kind": "human", "voice": "en-US-AndrewMultilingualNeural",
     "look": "a friendly man in his early 30s with short light brown hair, wearing a navy crew-neck t-shirt"},
    {"id": "marcus", "name": "Marcus", "kind": "human", "voice": "en-US-BrianMultilingualNeural",
     "look": "an upbeat Black man in his early 30s with a short fade haircut and a trimmed beard, wearing a grey hoodie"},
    {"id": "leo", "name": "Leo", "kind": "human", "voice": "en-US-SteffanMultilingualNeural",
     "look": "a relaxed East Asian man in his late 20s with short black hair, wearing an olive overshirt"},
    # Dogs (different breeds and sizes)
    {"id": "biscuit", "name": "Biscuit", "kind": "pet", "species": "dog", "voice": "en-AU-WilliamMultilingualNeural",
     "look": "a happy golden retriever dog"},
    {"id": "pepper", "name": "Pepper", "kind": "pet", "species": "dog", "voice": "en-GB-OllieMultilingualNeural",
     "look": "a cute fawn French bulldog with big bat ears"},
    {"id": "milo", "name": "Milo", "kind": "pet", "species": "dog", "voice": "en-AU-WilliamMultilingualNeural",
     "look": "a playful tricolor beagle dog"},
    {"id": "coco", "name": "Coco", "kind": "pet", "species": "dog", "voice": "en-GB-AdaMultilingualNeural",
     "look": "a fluffy cream-colored Pomeranian dog"},
    {"id": "bear", "name": "Bear", "kind": "pet", "species": "dog", "voice": "en-GB-OllieMultilingualNeural",
     "look": "a big friendly black Labrador retriever dog"},
    # Cats (different breeds and colours)
    {"id": "luna", "name": "Luna", "kind": "pet", "species": "cat", "voice": "en-GB-AdaMultilingualNeural",
     "look": "a fluffy grey tabby cat with green eyes"},
    {"id": "oliver", "name": "Oliver", "kind": "pet", "species": "cat", "voice": "en-AU-WilliamMultilingualNeural",
     "look": "a chubby orange tabby cat"},
    {"id": "mochi", "name": "Mochi", "kind": "pet", "species": "cat", "voice": "en-US-SerenaMultilingualNeural",
     "look": "a fluffy white ragdoll cat with blue eyes"},
    {"id": "shadow", "name": "Shadow", "kind": "pet", "species": "cat", "voice": "en-GB-OllieMultilingualNeural",
     "look": "a sleek black cat with yellow eyes"},
]
# The saved cast (names, voices, personalities) lives in the repo: assets/cast/cast.json + assets/cast/<id>.jpg,
# so every video reuses exactly the same faces. The descriptions above are only used to (re)draw a face.
CAST_DIR = os.path.join("assets", "cast")
_DRAW = {c["id"]: c["look"] for c in CAST}
_DRAW["nina"] = _DRAW.pop("priya").replace("South Asian", "East Asian")
try:
    import json as _json
    with open(os.path.join(CAST_DIR, "cast.json"), encoding="utf-8") as _f:
        CAST = _json.load(_f)
    for _c in CAST:
        _c["draw"] = _c.get("draw") or _DRAW.get(_c["id"], _c["look"])
except FileNotFoundError:
    for _c in CAST:
        _c["draw"] = _c["look"]
BY_ID = {c["id"]: c for c in CAST}
DOG_WORDS = {"dog", "dogs", "puppy", "puppies", "leash", "harness", "collar", "chew", "fetch"}
CAT_WORDS = {"cat", "cats", "kitten", "kittens", "kitty", "litter", "scratching", "scratcher", "catnip"}
PET_WORDS = DOG_WORDS | CAT_WORDS | {"pet", "pets", "paw", "paws", "groom", "grooming", "fur", "shedding", "treat",
                                     "treats", "deshedding", "dematting"}


def available():
    return bool(config.FAL_KEY)


def _headers():
    return {"Authorization": f"Key {config.FAL_KEY}", "Content-Type": "application/json"}


def _data_uri(path, mime):
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def run(model, payload, wait_s=900):
    """Submit to fal's queue and wait for the result."""
    r = requests.post(f"{QUEUE}/{model}", headers=_headers(), json=payload, timeout=120)
    if r.status_code >= 300:
        raise RuntimeError(f"fal {model} submit failed ({r.status_code}): {r.text[:300]}")
    job = r.json()
    status_url, result_url = job["status_url"], job["response_url"]
    deadline = time.time() + wait_s
    while time.time() < deadline:
        s = requests.get(status_url, headers=_headers(), timeout=60).json()
        if s.get("status") == "COMPLETED":
            res = requests.get(result_url, headers=_headers(), timeout=60)
            if res.status_code >= 300:
                raise RuntimeError(f"fal {model} failed: {res.text[:300]}")
            return res.json()
        if s.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal {model} failed: {str(s)[:300]}")
        time.sleep(6)
    raise RuntimeError(f"fal {model} took longer than {wait_s}s")


def _download(url, path):
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


# ---------------- the cast ----------------
def _prompt(c):
    if c["kind"] == "pet":
        return (f"Vertical smartphone photo of {c['draw']} sitting and looking straight into the camera, face and "
                "chest centered in the upper middle of the frame, mouth closed, bright cozy modern living room "
                "softly out of focus, natural window light, realistic fur detail, no text, no people")
    return (f"Vertical smartphone selfie-video still of {c['draw']}, looking straight at the camera with a natural "
            "friendly smile, mouth closed, head and shoulders centered in the upper middle of the frame, bright "
            "cozy modern living room background softly out of focus, natural window light, realistic skin, "
            "authentic social media creator style, no text, no logos, nothing in hands")


def make_member(st, cid):
    c = BY_ID[cid]
    out_dir = os.path.join(config.WORK_DIR, "presenter")
    os.makedirs(out_dir, exist_ok=True)
    res = run(config.PRESENTER_IMAGE_MODEL, {"prompt": _prompt(c), "image_size": "portrait_16_9", "num_images": 1,
                                             "enable_safety_checker": True}, wait_s=300)
    n = st.setdefault("presenter_versions", {}).get(cid, 0) + 1
    st["presenter_versions"][cid] = n
    path = _download(res["images"][0]["url"], os.path.join(out_dir, f"{cid}-{n}.jpg"))
    st.setdefault("presenters", {})[cid] = storage.store(path, "presenter", f"{cid}-{n}.jpg")
    os.makedirs(CAST_DIR, exist_ok=True)
    import shutil
    shutil.copy(path, os.path.join(CAST_DIR, f"{cid}.jpg"))  # saved in GitHub with the cast
    telegram.send_photo(path, f"{'🐾' if c['kind'] == 'pet' else '🧑'} {c['name']}")
    return path


def candidates(st, only=None, missing_only=False):
    """Creates (or re-creates) the cast and shows each member in Telegram with a 'new look' button."""
    ids = [i for i in (only or [c["id"] for c in CAST]) if i in BY_ID]
    if missing_only:
        ids = [i for i in ids if i not in (st.get("presenters") or {})]
    made = []
    for cid in ids:
        try:
            make_member(st, cid)
            made.append(cid)
        except Exception as e:  # noqa: BLE001
            telegram.send(f"⚠️ Couldn't make {BY_ID[cid]['name']}: {str(e)[:200]}")
    if not made:
        return
    rows, row = [], []
    for cid in made:
        row.append((f"🔁 {BY_ID[cid]['name']}", f"prs:{cid}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    telegram.send("🎬 <b>The Ashvara cast</b> (" + ", ".join(BY_ID[c]["name"] for c in made) + ")\n"
                  "Each keeps this exact face and their own voice in every video. People present self-care and "
                  "fitness products; the dogs present dog products and the cats present cat products. Don't like one? Tap their name below "
                  "for a new look.", rows)


def redo(st, cid):
    if cid in BY_ID:
        telegram.send(f"🔁 Making a new look for {BY_ID[cid]['name']}...")
        candidates(st, [cid])


def _words(product):
    import re
    text = " ".join(str(product.get(k) or "") for k in ("title", "type", "handle")).lower()
    return set(re.findall(r"[a-z]+", text))


def is_pet_product(product):
    return bool(_words(product) & PET_WORDS)


def pick(st, product):
    """Next cast member for this product: a dog for dog products, a cat for cat products, any pet for other pet
    products, otherwise the person used least recently."""
    have_ids = have(st)
    w = _words(product or {})
    if w & DOG_WORDS and not w & CAT_WORDS:
        want = lambda c: c.get("species") == "dog"  # noqa: E731
    elif w & CAT_WORDS and not w & DOG_WORDS:
        want = lambda c: c.get("species") == "cat"  # noqa: E731
    elif w & PET_WORDS:
        want = lambda c: c["kind"] == "pet"  # noqa: E731
    else:
        want = lambda c: c["kind"] == "human"  # noqa: E731
    pool = [c for c in CAST if want(c) and c["id"] in have_ids] or [c for c in CAST if c["id"] in have_ids]
    if not pool:
        return None
    last = st.get("presenter_last", {})
    return min(pool, key=lambda c: last.get(c["id"], ""))


def due(st):
    """True if today's product video may use a presenter."""
    if not (config.PRESENTER and available() and have(st)):
        return False
    return st.get("presenter_days", {}).get(state.now().strftime("%Y-%m-%d"), 0) < config.PRESENTER_PER_DAY


def mark_used(st, cid):
    day = state.now().strftime("%Y-%m-%d")
    days = st.setdefault("presenter_days", {})
    days[day] = days.get(day, 0) + 1
    for d in sorted(days)[:-7]:
        days.pop(d)
    st.setdefault("presenter_last", {})[cid] = state.iso()


def _repo_image(st, cid):
    """The cast member's saved face in the repo (assets/cast/<id>.jpg)."""
    path = os.path.join(CAST_DIR, f"{cid}.jpg")
    return path if os.path.exists(path) else None


def have(st):
    refs = st.get("presenters") or {}
    return {c["id"] for c in CAST if _repo_image(st, c["id"]) or c["id"] in refs}


def image_path(st, cid, out_dir):
    return _repo_image(st, cid) or storage.fetch(st["presenters"][cid], out_dir)


# ---------------- making a talking clip ----------------
def clip(audio, start, end, image, out):
    """Lip-synced presenter video for audio[start:end]."""
    seg = out + ".m4a"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", audio,
                    "-c:a", "aac", "-b:a", "128k", seg], check=True, capture_output=True)
    res = run(config.PRESENTER_MODEL, {
        "image_url": _data_uri(image, "image/jpeg"),
        "audio_url": _data_uri(seg, "audio/mp4"),
        "prompt": "A friendly social media creator talking naturally to the camera, small natural head movements "
                  "and hand gestures, steady phone camera",
    })
    url = (res.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"no video in fal result: {str(res)[:200]}")
    return _download(url, out)


# ---------------- character sheets + "product in hand" scenes ----------------
EDIT_MODEL = "fal-ai/nano-banana/edit"   # keeps the same face/markings in new poses (~$0.04 per image)
VIEWS = {
    "human": [("full", "full body, standing, front view, relaxed natural pose"),
              ("three_quarter", "three-quarter view from the left, waist up"),
              ("profile", "right side profile, head and shoulders"),
              ("smile", "close-up portrait with a big genuine smile"),
              ("gesture", "waist up, mid-sentence, explaining something with one hand raised")],
    "pet": [("full", "full body, side view, standing"),
            ("three_quarter", "three-quarter view, sitting"),
            ("lying", "lying down, relaxed"),
            ("closeup", "close-up of the face, head tilted curiously")],
}


def _who(c):
    if c["kind"] == "pet":
        return (f"the exact same {c.get('species', 'pet')} as in the reference photo - identical breed, size, fur "
                "colour, markings and eye colour")
    return ("the exact same person as in the reference photo - identical face, hairstyle, skin tone, body type "
            "and outfit")


GEMINI_IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-2.5-flash-image-preview"]
_gemini_off = False  # set after Gemini refuses (no free image quota): use fal for the rest of the run


def _gemini_edit(images, prompt, out, aspect):
    """Same 'Nano Banana' model straight from Google with the bot's own Gemini key (free if the key's tier allows)."""
    global _gemini_off
    if _gemini_off or not config.GEMINI_API_KEY:
        raise RuntimeError("Gemini image editing not available")
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(open(p, "rb").read()).decode()}}
             for p in images] + [{"text": prompt}]
    last = ""
    for model in GEMINI_IMAGE_MODELS:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          params={"key": config.GEMINI_API_KEY}, timeout=180, json={
                              "contents": [{"parts": parts}],
                              "generationConfig": {"responseModalities": ["IMAGE"],
                                                   "imageConfig": {"aspectRatio": aspect}}})
        if r.status_code == 404:
            continue
        if r.status_code >= 300:
            last = f"{r.status_code}: {r.text[:200]}"
            if r.status_code in (429, 403, 400):
                _gemini_off = True
            break
        for cand in r.json().get("candidates", []):
            for part in (cand.get("content") or {}).get("parts", []):
                data = (part.get("inline_data") or part.get("inlineData") or {}).get("data")
                if data:
                    with open(out, "wb") as f:
                        f.write(base64.b64decode(data))
                    return out
        last = "no image in Gemini reply"
    raise RuntimeError(f"Gemini image edit failed ({last})")


def edit(images, prompt, out, aspect="9:16"):
    """Try Google's Gemini (free tier) first; fall back to fal.ai (~$0.04) if Gemini says no."""
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    try:
        path = _gemini_edit(images, prompt, out, aspect)
        print(f"  image via Gemini (free): {os.path.basename(out)}")
        return path
    except Exception as e:  # noqa: BLE001
        print(f"  Gemini image edit unavailable, using fal: {str(e)[:160]}")
    res = run(EDIT_MODEL, {"prompt": prompt, "num_images": 1, "aspect_ratio": aspect, "output_format": "jpeg",
                           "image_urls": [_data_uri(p, "image/jpeg") for p in images]}, wait_s=300)
    return _download(res["images"][0]["url"], out)


def sheet_views(cid):
    """Saved character-sheet pictures for this cast member (repo files), best first."""
    folder = os.path.join(CAST_DIR, cid)
    kind = BY_ID[cid]["kind"]
    return [os.path.join(folder, f"{v}.jpg") for v, _ in VIEWS[kind] if os.path.exists(os.path.join(folder, f"{v}.jpg"))]


def make_sheet(st, cid):
    """Draws the character from 4-5 angles (same face) into assets/cast/<id>/ and sends the sheet to Telegram."""
    from PIL import Image, ImageDraw, ImageFont
    c = BY_ID[cid]
    base = image_path(st, cid, os.path.join(config.WORK_DIR, "presenter"))
    folder = os.path.join(CAST_DIR, cid)
    os.makedirs(folder, exist_ok=True)
    paths = [base]
    for view, desc in VIEWS[c["kind"]]:
        prompt = (f"Character reference photo of {_who(c)}: {desc}. Same lighting style as the reference, plain soft "
                  "light-grey studio background, photorealistic, sharp focus, no text, no watermark.")
        try:
            paths.append(edit([base], prompt, os.path.join(folder, f"{view}.jpg"), aspect="3:4"))
        except Exception as e:  # noqa: BLE001
            print(f"sheet view {cid}/{view} failed: {str(e)[:200]}")
    tile_w, tile_h = 300, 400
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    img = Image.new("RGB", (tile_w * len(paths), tile_h + 50), "white")
    for i, p in enumerate(paths):
        tile = Image.open(p).convert("RGB")
        tile.thumbnail((tile_w, tile_h))
        img.paste(tile, (i * tile_w + (tile_w - tile.width) // 2, 50 + (tile_h - tile.height) // 2))
    ImageDraw.Draw(img).text((12, 10), f"{c['name']} - {c.get('vibe', '')}", fill="black", font=font)
    sheet = os.path.join(folder, "sheet.jpg")
    img.save(sheet, quality=85)
    telegram.send_photo(sheet, f"📋 {c['name']} character sheet")
    return sheet


def make_sheets(st, only=None):
    ids = [i for i in (only or [c["id"] for c in CAST]) if i in BY_ID]
    done = []
    for cid in ids:
        try:
            make_sheet(st, cid)
            done.append(BY_ID[cid]["name"])
        except Exception as e:  # noqa: BLE001
            telegram.send(f"⚠️ Character sheet for {BY_ID[cid]['name']} failed: {str(e)[:200]}")
    if done:
        telegram.send(f"✅ Character sheets saved for: {', '.join(done)}. These keep each face the same when the "
                      "bot draws them using a product.")


BEATS = [
    "close-up on the hands using it, the product in action",
    "medium shot actually using it, natural smile",
    "the happy result right after using it, product still in hand",
]


def product_scene(st, member, product_image, product_title, out, costar=None, beat=""):
    """A new photo of this cast member using the product (same face via the base photo + character sheet)."""
    refs = [image_path(st, member["id"], os.path.dirname(out))] + sheet_views(member["id"])[:2]
    partner = BY_ID.get(costar or member.get("partner") or "")
    if partner and partner["id"] in have(st):  # a chosen co-star, or an older couple, appear together
        refs += [image_path(st, partner["id"], os.path.dirname(out))]
    refs += [product_image]
    if member["kind"] == "pet":
        action = (f"enjoying or being cared for with the product from the last reference image ({product_title}), "
                  "in a bright cozy home, a human hand may appear but no human face")
    elif partner and partner["kind"] == "pet":
        action = (f"at home with their {partner.get('species', 'pet')} (the animal in the second-to-last reference "
                  "image - identical breed, fur colour and size), gently using the product from the last reference "
                  f"image ({product_title}) on or with the pet, both looking happy, a warm natural moment")
    elif partner:
        action = (f"together with their spouse (the person in the second-to-last reference image, identical face and "
                  f"outfit), using the product from the last reference image ({product_title}) at home, both smiling, "
                  "a warm natural moment")
    else:
        action = (f"holding and using the product from the last reference image ({product_title}) in a bright cozy "
                  "home, looking at the product with a natural smile")
    prompt = (f"Vertical smartphone UGC-style photo of {_who(member)} (the first reference images), {action}"
              + (f" - {beat}" if beat else "") + ". "
              "The product must look exactly like the last reference image (same shape, colours and details) and be "
              "clearly visible. Photorealistic, natural window light, no text, no logos added, no watermark.")
    return edit(refs, prompt, out)


I2V_MODEL = "fal-ai/kling-video/v2.5-turbo/standard/image-to-video"   # ~$0.21 per 5-second clip


def animate(still, motion, out):
    """Turns a 'using the product' photo into a 5-second clip with real motion."""
    res = run(config.PRESENTER_I2V_MODEL or I2V_MODEL, {
        "image_url": _data_uri(still, "image/jpeg"), "duration": "5",
        "prompt": f"{motion}. Natural, smooth, realistic motion, steady handheld phone camera, the product keeps its "
                  "exact shape and colours, faces stay the same.",
        "negative_prompt": "blur, distorted hands, extra fingers, morphing face, text, watermark, flicker"})
    url = (res.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"no video in fal result: {str(res)[:200]}")
    return _download(url, out)

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
    {"id": "biscuit", "name": "Biscuit", "kind": "pet", "voice": "en-AU-WilliamMultilingualNeural",
     "look": "a happy golden retriever dog"},
    {"id": "luna", "name": "Luna", "kind": "pet", "voice": "en-GB-AdaMultilingualNeural",
     "look": "a fluffy grey tabby cat with green eyes"},
]
BY_ID = {c["id"]: c for c in CAST}
PET_WORDS = ("pet", "dog", "cat", "paw", "puppy", "kitten", "groom", "leash", "collar", "litter", "treat")


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
        return (f"Vertical smartphone photo of {c['look']} sitting and looking straight into the camera, face and "
                "chest centered in the upper middle of the frame, mouth closed, bright cozy modern living room "
                "softly out of focus, natural window light, realistic fur detail, no text, no people")
    return (f"Vertical smartphone selfie-video still of {c['look']}, looking straight at the camera with a natural "
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
    telegram.send_photo(path, f"{'🐾' if c['kind'] == 'pet' else '🧑'} {c['name']}")
    return path


def candidates(st, only=None):
    """Creates (or re-creates) the cast and shows each member in Telegram with a 'new look' button."""
    ids = [i for i in (only or [c["id"] for c in CAST]) if i in BY_ID]
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
                  "fitness products; Biscuit and Luna present pet products. Don't like one? Tap their name below "
                  "for a new look.", rows)


def redo(st, cid):
    if cid in BY_ID:
        telegram.send(f"🔁 Making a new look for {BY_ID[cid]['name']}...")
        candidates(st, [cid])


def is_pet_product(product):
    text = " ".join(str(product.get(k) or "") for k in ("title", "type", "handle")).lower()
    return any(w in text for w in PET_WORDS)


def pick(st, product):
    """Next cast member for this product: a pet for pet products, otherwise the person used least recently."""
    have = st.get("presenters") or {}
    kind = "pet" if is_pet_product(product or {}) else "human"
    pool = [c for c in CAST if c["kind"] == kind and c["id"] in have] or [c for c in CAST if c["id"] in have]
    if not pool:
        return None
    last = st.get("presenter_last", {})
    return min(pool, key=lambda c: last.get(c["id"], ""))


def due(st):
    """True if today's product video may use a presenter."""
    if not (config.PRESENTER and available() and st.get("presenters")):
        return False
    return st.get("presenter_days", {}).get(state.now().strftime("%Y-%m-%d"), 0) < config.PRESENTER_PER_DAY


def mark_used(st, cid):
    day = state.now().strftime("%Y-%m-%d")
    days = st.setdefault("presenter_days", {})
    days[day] = days.get(day, 0) + 1
    for d in sorted(days)[:-7]:
        days.pop(d)
    st.setdefault("presenter_last", {})[cid] = state.iso()


def image_path(st, cid, out_dir):
    return storage.fetch(st["presenters"][cid], out_dir)


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

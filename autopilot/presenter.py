"""AI presenter ("face of Ashvara") for product videos, made with fal.ai (paid per second of video).

- `candidates(st)` makes 3 presenter looks and sends them to Telegram; tapping one saves it.
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
CREDIT = "Presenter: AI-generated person (Kling AI Avatar via fal.ai), not a real customer."

LOOKS = [
    "a friendly woman in her late 20s with shoulder-length brown hair, casual knit sweater",
    "a cheerful man in his early 30s with short dark hair and a neat beard, plain t-shirt",
    "a warm woman in her mid 30s with curly black hair, light denim shirt",
]


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


# ---------------- choosing the presenter ----------------
def candidates(st):
    out_dir = os.path.join(config.WORK_DIR, "presenter")
    os.makedirs(out_dir, exist_ok=True)
    refs = []
    for i, look in enumerate(LOOKS):
        prompt = (f"Vertical smartphone selfie-video still of {look}, looking straight at the camera with a natural "
                  "friendly smile, mouth closed, head and shoulders centered in the upper middle of the frame, bright "
                  "cozy modern living room background softly out of focus, natural window light, realistic skin, "
                  "authentic social media creator style, no text, no logos, nothing in hands")
        res = run(config.PRESENTER_IMAGE_MODEL, {"prompt": prompt, "image_size": "portrait_16_9", "num_images": 1,
                                                 "enable_safety_checker": True}, wait_s=300)
        path = _download(res["images"][0]["url"], os.path.join(out_dir, f"look{i + 1}.jpg"))
        refs.append(storage.store(path, "presenter", f"look{i + 1}.jpg"))
        telegram.send_photo(path, f"Presenter option {i + 1}")
    st["presenter_candidates"] = refs
    telegram.send("🧑 <b>Pick the face of Ashvara</b>\nThis AI presenter will open and close one product video a "
                  "day (you still approve every video). Tap the one you like, or reply <code>/presenters</code> "
                  "for 3 new options.",
                  [[(f"✅ Option {i + 1}", f"presenter:{i}") for i in range(len(refs))]])


def choose(st, idx):
    refs = st.get("presenter_candidates") or []
    if idx >= len(refs):
        return telegram.send("That option has expired. Reply /presenters for new ones.")
    st["presenter"] = refs[idx]
    telegram.send(f"👍 Presenter option {idx + 1} saved. Product videos will start using them "
                  f"(up to {config.PRESENTER_PER_DAY} a day).")


def due(st):
    """True if today's product video may use the presenter."""
    if not (config.PRESENTER and available() and st.get("presenter")):
        return False
    return st.get("presenter_days", {}).get(state.now().strftime("%Y-%m-%d"), 0) < config.PRESENTER_PER_DAY


def mark_used(st):
    day = state.now().strftime("%Y-%m-%d")
    days = st.setdefault("presenter_days", {})
    days[day] = days.get(day, 0) + 1
    for d in sorted(days)[:-7]:
        days.pop(d)


def image_path(st, out_dir):
    return storage.fetch(st["presenter"], out_dir)


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

"""Voiceover, visuals and final render - all free.

Voices:   rotating Microsoft Edge neural voices (edge-tts); Google gTTS as backup.
Footage:  Pexels / Pixabay (keys), NASA (no key, public domain), Wikimedia Commons
          (no key, CC0/PD/CC BY only), optional Cloudflare AI images, and an
          animated gradient as last resort. Source order is shuffled per video.
Render:   FFmpeg, 1080x1920, burned-in captions, rank badges for Top-5 videos.
"""
import asyncio
import base64
import html
import json
import math
import os
import random
import re
import subprocess

import requests

from . import config

W, H, FPS = config.WIDTH, config.HEIGHT, config.FPS
UA = {"User-Agent": "AshvaraAutopilot/1.0 (https://github.com/akachwaha27/shopify-automation)"}


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd[:6])}...\n{p.stderr[-1500:]}")
    return p.stdout


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", path]).strip())


# =========================== Voice ===========================
# Only the newest "Multilingual" neural voices: they have natural breathing, intonation and pacing.
# The older voices (Jenny, Guy, Aria...) sound noticeably more robotic, so they're no longer in the rotation.
VOICE_POOL = {
    "en": ["en-US-AndrewMultilingualNeural", "en-US-AvaMultilingualNeural", "en-US-BrianMultilingualNeural",
           "en-US-EmmaMultilingualNeural", "en-AU-WilliamMultilingualNeural", "en-GB-AdaMultilingualNeural",
           "en-GB-OllieMultilingualNeural", "en-US-SerenaMultilingualNeural", "en-US-SteffanMultilingualNeural"],
}
FALLBACK_VOICES = ["en-US-AndrewMultilingualNeural", "en-US-AvaMultilingualNeural",
                   "en-US-BrianMultilingualNeural", "en-US-EmmaMultilingualNeural"]


def voice_pool():
    if config.VOICES:  # user override: comma-separated list
        return [v.strip() for v in config.VOICES.split(",") if v.strip()]
    lang = config.LANGUAGE.split("-")[0]
    pool = VOICE_POOL.get(lang)
    try:  # keep only voices that exist right now (Microsoft adds/retires voices)
        import edge_tts
        live = {v["ShortName"] for v in asyncio.run(edge_tts.list_voices())}
        if pool:
            pool = [v for v in pool if v in live] or [v for v in FALLBACK_VOICES if v in live] or pool
        else:  # other languages: any neural voice for that language
            pool = sorted(v for v in live if v.lower().startswith(lang + "-"))[:12]
    except Exception as e:  # noqa: BLE001
        print("Could not list voices:", str(e)[:100])
    return pool or [config.VOICE]


def pick_voice(recent):
    pool = voice_pool()
    fresh = [v for v in pool if v not in recent[-2:]] or pool
    return random.choice(fresh)


async def _edge(text, mp3, words, voice, rate, pitch):
    import edge_tts
    com = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append({"start": chunk["offset"] / 1e7,
                              "end": (chunk["offset"] + chunk["duration"]) / 1e7, "word": chunk["text"]})


def _estimate_words(text, total):
    """No timing data (gTTS): spread words over the audio by length."""
    ws = text.split()
    weights = [len(w) + 2 for w in ws]
    t, out = 0.15, []
    span = max(total - 0.3, 0.5)
    for w, k in zip(ws, weights):
        d = span * k / sum(weights)
        out.append({"start": t, "end": t + d * 0.9, "word": w})
        t += d
    return out


def _speak(text, mp3, voice, rate):
    words = []
    asyncio.run(_edge(text, mp3, words, voice, f"{rate:+d}%", "+0Hz"))  # no pitch shift: it sounds robotic
    if os.path.getsize(mp3) < 1000 or not words:
        raise RuntimeError("empty audio")
    return words


def voiceover(text, out_dir, voice):
    """Natural pace (+0..5%). If the read lands far from TARGET_SECONDS, re-read once at an adjusted pace
    (kept within -8%..+10% so it never sounds slowed down or rushed)."""
    mp3 = os.path.join(out_dir, "voice.mp3")
    target = config.TARGET_SECONDS
    for v in (voice, config.VOICE):
        try:
            rate = random.randint(0, 5)
            words = _speak(text, mp3, v, rate)
            got = duration(mp3)
            if abs(got - target) > target * 0.08:
                new = int(round((1 + rate / 100) * got / target * 100 - 100))
                new = max(-8, min(10, new))
                if new != rate:
                    words = _speak(text, mp3, v, new)
                    print(f"voice pace {rate:+d}% -> {new:+d}% ({got:.1f}s -> {duration(mp3):.1f}s, target {target}s)")
            return mp3, words, f"AI-generated voice (Microsoft Edge neural TTS, {v})"
        except Exception as e:  # noqa: BLE001
            print(f"edge-tts voice {v} failed: {str(e)[:120]}")
    from gtts import gTTS  # backup engine
    gTTS(text, lang=config.LANGUAGE.split("-")[0]).save(mp3)
    return mp3, _estimate_words(text, duration(mp3)), "AI-generated voice (Google Text-to-Speech)"


# =========================== Captions & overlays ===========================
def _ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _clean(t):
    return re.sub(r"[{}\\]", "", str(t))


def subtitles(words, scenes, bounds, hook_text, path, group=3):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,3,2,80,80,620,1
Style: Rank,DejaVu Sans,210,&H0000D7FF,&H0000D7FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,9,4,8,60,60,200,1
Style: Label,DejaVu Sans,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,3,10,0,8,90,90,450,1
Style: Title,DejaVu Sans,80,&H0000D7FF,&H0000D7FF,&H00000000,&HA0000000,1,0,0,0,100,100,0,0,3,12,0,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for i in range(0, len(words), group):
        chunk = words[i:i + group]
        end = words[i + group]["start"] if i + group < len(words) else chunk[-1]["end"] + 0.3
        text = _clean(" ".join(w["word"] for w in chunk).upper())
        lines.append(f"Dialogue: 0,{_ts(chunk[0]['start'])},{_ts(end)},Default,,0,0,0,,{text}")
    for idx, (s, (a, b)) in enumerate(zip(scenes, bounds)):
        badge, label = _clean(s.get("badge", "")), _clean(s.get("label", ""))
        if badge:
            size = r"\fs210" if len(badge) <= 3 else r"\fs130"
            pop = r"{\fad(120,80)" + size + r"\fscx135\fscy135\t(0,220,\fscx100\fscy100)}"
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Rank,,0,0,0,,{pop}{badge}")
        if label and not (idx == 0 and hook_text and not badge):  # don't stack on the hook
            margin = "" if badge else r"\pos(540,300)"
            lines.append(f"Dialogue: 1,{_ts(a)},{_ts(b)},Label,,0,0,0,,{{\\fad(150,80){margin}}}{label.upper()}")
        if idx == 0 and hook_text and not badge:
            lines.append(f"Dialogue: 1,{_ts(0)},{_ts(b)},Title,,0,0,0,,"
                         r"{\fad(100,120)\fscx120\fscy120\t(0,200,\fscx100\fscy100)}" + _clean(hook_text).upper())
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
    return path


def _srt_ts(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(sec):02d},{int(round((sec % 1) * 1000)) % 1000:03d}"


def srt(words, path, max_words=7, max_chars=42):
    """Readable closed-caption track (separate from the burned-in captions)."""
    cues, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["word"] for x in cur)
        if len(cur) >= max_words or len(text) >= max_chars or w["word"].rstrip().endswith((".", "?", "!")):
            cues.append(cur)
            cur = []
    if cur:
        cues.append(cur)
    out = []
    for i, c in enumerate(cues, 1):
        end = cues[i][0]["start"] if i < len(cues) else c[-1]["end"] + 0.4
        out.append(f"{i}\n{_srt_ts(c[0]['start'])} --> {_srt_ts(end)}\n{' '.join(x['word'] for x in c)}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return path


def scene_bounds(scenes, words, total):
    """Start/end time of each scene, aligned to the actual spoken words."""
    counts = [max(len(s["text"].split()), 1) for s in scenes]
    tot, cum, starts = sum(counts), 0, []
    for c in counts:
        idx = min(int(round(cum / tot * len(words))), len(words) - 1) if words else 0
        starts.append(0.0 if cum == 0 or not words else words[idx]["start"])
        cum += c
    ends = starts[1:] + [total]
    return [(a, max(b, a + 0.8)) for a, b in zip(starts, ends)]


# =========================== Footage sources ===========================
def _download(url, path, headers=None, max_mb=120):
    with requests.get(url, stream=True, timeout=180, headers=headers) as r:
        r.raise_for_status()
        size = 0
        with open(path, "wb") as f:
            for c in r.iter_content(1 << 20):
                size += len(c)
                if size > max_mb << 20:
                    raise RuntimeError("file too large")
                f.write(c)
    return path


def _pexels(path, params):
    r = requests.get(f"https://api.pexels.com/{path}", params=params, timeout=30,
                     headers={"Authorization": config.PEXELS_API_KEY})
    r.raise_for_status()
    return r.json()


def pexels_video(query, base, used):
    for v in _pexels("videos/search", {"query": query, "orientation": "portrait", "size": "medium", "per_page": 10}).get("videos", []):
        files = [f for f in v["video_files"] if f.get("height") and f["height"] >= 1280 and f["width"] < f["height"]]
        if f"pex{v['id']}" in used or not files:
            continue
        used.add(f"pex{v['id']}")
        _download(min(files, key=lambda f: f["height"])["link"], base + ".mp4")
        return {"kind": "video", "path": base + ".mp4", "credit": f'{v["user"]["name"]} (Pexels) {v["url"]}'}


def pexels_photo(query, base, used):
    for p in _pexels("v1/search", {"query": query, "orientation": "portrait", "per_page": 10}).get("photos", []):
        if f"pexp{p['id']}" in used:
            continue
        used.add(f"pexp{p['id']}")
        _download(p["src"]["large2x"], base + ".jpg")
        return {"kind": "image", "path": base + ".jpg", "credit": f'{p["photographer"]} (Pexels) {p["url"]}'}


def _pixabay(path, params):
    r = requests.get(f"https://pixabay.com/api/{path}", timeout=30,
                     params={"key": config.PIXABAY_API_KEY, "safesearch": "true", "per_page": 20, **params})
    r.raise_for_status()
    return r.json()


def pixabay_video(query, base, used):
    hits = _pixabay("videos/", {"q": query[:100]}).get("hits", [])
    hits.sort(key=lambda h: h["videos"].get("large", {}).get("height", 0) < h["videos"].get("large", {}).get("width", 1))
    for v in hits:
        files = [f for f in (v["videos"].get(s) for s in ("medium", "large", "small")) if f and f.get("url")]
        if f"pxb{v['id']}" in used or not files:
            continue
        used.add(f"pxb{v['id']}")
        _download(files[0]["url"], base + ".mp4")
        return {"kind": "video", "path": base + ".mp4", "credit": f'{v["user"]} (Pixabay) {v["pageURL"]}'}


def pixabay_photo(query, base, used):
    for p in _pixabay("", {"q": query[:100], "image_type": "photo", "orientation": "vertical"}).get("hits", []):
        if f"pxbp{p['id']}" in used:
            continue
        used.add(f"pxbp{p['id']}")
        _download(p["largeImageURL"], base + ".jpg")
        return {"kind": "image", "path": base + ".jpg", "credit": f'{p["user"]} (Pixabay) {p["pageURL"]}'}


SPACE_WORDS = {"space", "planet", "rocket", "earth", "moon", "mars", "sun", "star", "stars", "galaxy", "nebula",
               "astronaut", "satellite", "orbit", "launch", "comet", "asteroid", "aurora", "telescope", "universe",
               "solar", "eclipse", "jupiter", "saturn", "venus", "spacecraft", "iss", "cosmos", "meteor", "hubble"}


def _nasa(query, base, used, media_type):
    if not SPACE_WORDS & set(re.findall(r"[a-z]+", query.lower())):
        return None  # NASA search returns loose matches; only use it for space/science scenes
    r = requests.get("https://images-api.nasa.gov/search", timeout=30,
                     params={"q": query, "media_type": media_type, "page_size": 15})
    r.raise_for_status()
    for item in r.json().get("collection", {}).get("items", []):
        d = item["data"][0]
        if f"nasa{d['nasa_id']}" in used:
            continue
        assets = requests.get(item["href"], timeout=30).json()
        prefs = ("~mobile.mp4", "~small.mp4", "~medium.mp4") if media_type == "video" else ("~large.jpg", "~medium.jpg", "~orig.jpg")
        url = next((a for p in prefs for a in assets if a.endswith(p)), None)
        if not url:
            continue
        used.add(f"nasa{d['nasa_id']}")
        ext = ".mp4" if media_type == "video" else ".jpg"
        _download(url.replace("http://", "https://"), base + ext)
        return {"kind": "video" if media_type == "video" else "image", "path": base + ext,
                "credit": f"NASA{' / ' + d['center'] if d.get('center') else ''}: \"{d.get('title', '')[:60]}\" (public domain)"}


def nasa_video(q, base, used):
    return _nasa(q, base, used, "video")


def nasa_photo(q, base, used):
    return _nasa(q, base, used, "image")


OK_LICENSE = re.compile(r"^(cc0|public domain|pd|cc by \d(\.\d)?|cc-by-\d(\.\d)?)", re.I)  # no share-alike


def _commons(query, base, used, kind):
    ftype = "video" if kind == "video" else "bitmap"
    stop = {"with", "from", "that", "this", "into", "over", "under", "about", "close", "view", "shot", "background"}
    keywords = [w for w in re.findall(r"[a-z]{4,}", query.lower()) if w not in stop]
    if not keywords:
        return None
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 12,
        "gsrsearch": f"{query} filetype:{ftype}", "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600})
    r.raise_for_status()
    for page in (r.json().get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if f"wm{page['pageid']}" in used or not OK_LICENSE.match(lic.strip()):
            continue
        name = page.get("title", "").lower()
        if not any(w in name for w in keywords):  # Commons search is loose: require a real match
            continue
        if kind == "video" and (info.get("size", 0) > 80 << 20 or info.get("duration", 99) < 3):
            continue
        if kind == "image" and info.get("width", 0) < 800:
            continue
        url = info.get("url") if kind == "video" else info.get("thumburl") or info.get("url")
        ext = os.path.splitext(url.split("?")[0])[1] or (".webm" if kind == "video" else ".jpg")
        artist = html.unescape(re.sub(r"<[^>]+>", " ", meta.get("Artist", {}).get("value", "Unknown")))
        artist = re.sub(r"\s+", " ", artist).strip()
        if "all rights reserved" in artist.lower() or "copyright" in name:
            continue
        artist = (artist[:len(artist) // 2].strip() if artist[:len(artist) // 2] == artist[len(artist) // 2:].strip()
                  else artist)[:60] or "Unknown"
        used.add(f"wm{page['pageid']}")
        _download(url, base + ext, headers=UA)
        return {"kind": kind, "path": base + ext,
                "credit": f"{artist} / Wikimedia Commons ({lic}) {info.get('descriptionurl', '')}"}


def commons_video(q, base, used):
    return _commons(q, base, used, "video")


def commons_photo(q, base, used):
    return _commons(q, base, used, "image")


def ai_image(prompt, base):
    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.CF_ACCOUNT_ID}"
           "/ai/run/@cf/black-forest-labs/flux-1-schnell")
    r = requests.post(url, headers={"Authorization": f"Bearer {config.CF_API_TOKEN}"}, timeout=120,
                      json={"prompt": prompt + ", vertical composition, cinematic, high detail, no text", "steps": 6})
    r.raise_for_status()
    with open(base + ".png", "wb") as f:
        f.write(base64.b64decode(r.json()["result"]["image"]))
    return {"kind": "image", "path": base + ".png", "credit": "AI image (FLUX.1-schnell via Cloudflare Workers AI)"}


def source_plan():
    """Per-video shuffled order of stock providers, so videos don't all look alike."""
    providers = []
    if config.PEXELS_API_KEY:
        providers.append((pexels_video, pexels_photo))
    if config.PIXABAY_API_KEY:
        providers.append((pixabay_video, pixabay_photo))
    random.shuffle(providers)
    # NASA only answers for space scenes; Commons last because its matches are looser
    return [(nasa_video, nasa_photo)] + providers + [(commons_video, commons_photo)]


def get_visual(scene, i, out_dir, used, plan):
    base = os.path.join(out_dir, f"s{i}")
    q = scene.get("stock_query") or scene.get("label") or "abstract background"
    has_ai = bool(config.CF_ACCOUNT_ID and config.CF_API_TOKEN)
    use_ai = has_ai and config.VISUALS in ("ai", "mixed")  # only called for AI shots (stock goes through visuals.pick)
    attempts = [lambda: ai_image(scene.get("image_prompt", q), base)] if use_ai else []
    for vid, pic in plan:  # video first, then photo, from each provider in this video's order
        attempts += [lambda f=vid: f(q, base, used), lambda f=pic: f(q, base, used)]
    if has_ai and not use_ai:
        attempts.append(lambda: ai_image(scene.get("image_prompt", q), base))
    for fn in attempts:
        try:
            res = fn()
            if res:
                return res
        except Exception as e:  # noqa: BLE001
            print(f"  visual attempt failed for scene {i}: {str(e)[:120]}")
    return {"kind": "gradient", "path": None, "credit": None}


# =========================== Render ===========================
FILL = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
PALETTES = [("0x0b1d51", "0x6a1b9a", "0x00897b"), ("0x1a237e", "0xc2185b", "0xff8f00"),
            ("0x004d40", "0x1565c0", "0x7b1fa2"), ("0x3e2723", "0xbf360c", "0xf9a825")]


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def render_remix(c, dur, out, teaser=False):
    """Edited version of a licensed clip: punch-in on the funniest moment, then an instant replay in slow
    motion with a zoom and a REPLAY tag. The whole clip stays visible on a blurred copy of itself."""
    full = duration(c["path"])
    peak = float(c.get("peak") or full / 2)
    layout = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,"
              f"eq=brightness=-0.08[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},setsar=1")
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p"]
    if teaser or dur < 4:  # short slot: just the funniest moment, zoomed in a little
        start = max(0.0, min(peak - dur / 2, full - dur))
        run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-stream_loop", "-1", "-i", c["path"], "-t", f"{dur:.3f}",
             "-vf", f"crop=iw/1.12:ih/1.12,{layout}"] + enc + [out])
        return out
    replay = min(3.0, dur * 0.35)          # screen time of the slow-motion replay
    main = dur - replay
    start = max(0.0, min(peak - main * 0.6, full - main))  # lead up to the moment, then the moment itself
    a, b = out + ".a.mp4", out + ".b.mp4"
    run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-stream_loop", "-1", "-i", c["path"], "-t", f"{main:.3f}",
         "-vf", layout] + enc + [a])
    src = replay / 2                        # half-speed: this much real footage fills the replay slot
    rs = max(0.0, min(peak - src / 2, full - src))
    tag = (f"drawtext=fontfile={FONT}:text='REPLAY':fontcolor=white:fontsize=64:box=1:boxcolor=0xE53935@0.9:"
           f"boxborderw=18:x=(w-text_w)/2:y=h*0.80")
    run(["ffmpeg", "-y", "-ss", f"{rs:.2f}", "-stream_loop", "-1", "-i", c["path"], "-t", f"{src:.3f}",
         "-vf", f"setpts=2*PTS,crop=iw/1.35:ih/1.35,{layout},{tag}", "-t", f"{replay:.3f}"] + enc + [b])
    with open(out + ".txt", "w") as f:
        f.write(f"file '{os.path.abspath(a)}'\nfile '{os.path.abspath(b)}'\n")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", out + ".txt", "-c", "copy", out])
    return out


def render_scene(vis, dur, out):
    if vis["kind"] == "remix":
        return render_remix(vis["clip"], dur, out, teaser=bool(vis["clip"].get("teaser")))
    common = ["-t", f"{dur:.3f}", "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "22", "-pix_fmt", "yuv420p", out]
    if vis["kind"] == "video":
        start = []
        if vis.get("offset"):
            start = ["-ss", f"{min(duration(vis['path']) / 2, 4):.2f}"]
        elif vis.get("center"):  # show the middle of the clip, where the action usually is
            start = ["-ss", f"{max(0.0, (duration(vis['path']) - dur) / 2):.2f}"]
        run(["ffmpeg", "-y", "-stream_loop", "-1"] + start + ["-i", vis["path"], "-vf", f"{FILL},fps={FPS}"] + common)
    elif vis["kind"] == "product":
        frames = int(dur * FPS) + 1
        z = random.choice(["min(1+0.0007*on,1.10)", "max(1.10-0.0007*on,1)"])
        vf = (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,"
              f"eq=brightness=-0.06[bg];[b]scale={int(W * 0.94)}:{int(H * 0.70)}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2-{int(H * 0.04)},scale={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
        run(["ffmpeg", "-y", "-loop", "1", "-i", vis["path"], "-vf", vf] + common)
    elif vis["kind"] == "image":
        frames = int(dur * FPS) + 1
        z = random.choice(["min(1+0.0009*on,1.15)", "max(1.15-0.0009*on,1)"])
        vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
        run(["ffmpeg", "-y", "-loop", "1", "-i", vis["path"], "-vf", vf] + common)
    else:  # animated gradient instead of a flat colour
        c0, c1, c2 = random.choice(PALETTES)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"gradients=s={W}x{H}:c0={c0}:c1={c1}:c2={c2}:n=3:speed=0.012:r={FPS}"] + common)
    return out


def pick_music():
    folder = "assets/music"
    tracks = [f for f in os.listdir(folder) if f.lower().endswith((".mp3", ".m4a", ".wav"))] if os.path.isdir(folder) else []
    return os.path.join(folder, random.choice(tracks)) if tracks else None


def make_clip_ranking(pkg, out_dir):
    """Funny clips that have their own sound: play #5 ... #1 with the original audio and on-screen ranks,
    no voiceover. Each clip is shown whole on a blurred copy of itself so nothing is cropped away."""
    os.makedirs(out_dir, exist_ok=True)
    scenes, parts, bounds, t = pkg["scenes"], [], [], 0.0
    for i, scene in enumerate(scenes):
        c = scene["clip"]
        if not os.path.exists(c.get("path") or ""):
            c["path"] = os.path.join(out_dir, f"clip{i}.mp4")
            _download(c["url"], c["path"])
        full = duration(c["path"])
        dur = min(full, config.CLIP_MAX_SECONDS)
        start = max(0.0, (full - dur) / 2)  # the middle, where the action usually is
        out = os.path.join(out_dir, f"part{i:02d}.mp4")
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                "-of", "csv=p=0", c["path"]], capture_output=True, text=True)
        audio = ("[0:a]aresample=44100,aformat=channel_layouts=stereo,loudnorm=I=-16:TP=-1.5:LRA=11[a0];"
                 "[a0][1:a]amix=inputs=2:duration=longest:normalize=0[a]") if probe.stdout.strip() else "[1:a]anull[a]"
        vf = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:2,"
              f"eq=brightness=-0.08[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
              f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},setsar=1[v]")
        run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}", "-i", c["path"], "-f", "lavfi", "-t", f"{dur:.2f}",
             "-i", "anullsrc=r=44100:cl=stereo", "-filter_complex",
             vf + ";" + audio,
             "-map", "[v]", "-map", "[a]", "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", out])
        parts.append(out)
        bounds.append((t, t + dur))
        t += dur
    ass = subtitles([], scenes, bounds, "", os.path.join(out_dir, "captions.ass"))
    extra = []
    if pkg.get("hook_text"):
        extra.append(f"Dialogue: 2,{_ts(0)},{_ts(min(2.8, t))},Default,,0,0,0,,{{\\fad(100,150)}}{_clean(pkg['hook_text']).upper()}")
    if pkg.get("end_text"):
        extra.append(f"Dialogue: 2,{_ts(max(0, t - 3.2))},{_ts(t)},Default,,0,0,0,,{{\\fad(150,100)}}{_clean(pkg['end_text']).upper()}")
    with open(ass, "a", encoding="utf-8") as f:
        f.write("\n".join(extra) + "\n")
    concat = os.path.join(out_dir, "parts.txt")
    with open(concat, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)
    final = os.path.join(out_dir, "final.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat, "-vf", f"ass={ass}", "-c:v", "libx264",
         "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-movflags", "+faststart", final])
    pkg["voice"] = "none (original clip sound)"
    pkg["visual_report"] = {"shots": len(parts), "checked": len(parts), "unchecked": 0, "filler": 0}
    try:
        from . import thumbnail
        thumbnail.make(parts[-1], min(1.0, bounds[-1][1] - bounds[-1][0]) / 2, pkg.get("thumbnail_text") or pkg["title"],
                       os.path.join(out_dir, "thumbnail.jpg"), badge="#1", accent_index=random.randrange(4))
    except Exception as e:  # noqa: BLE001
        print("Thumbnail failed:", str(e)[:150])
    credits = ["Audio: original sound of the clips (no voiceover).",
               "Stock footage (Pexels/Pixabay Content License): " + "; ".join(s["clip"]["credit"] for s in scenes)]
    with open(os.path.join(out_dir, "credits.json"), "w") as f:
        json.dump(credits, f)
    return final, credits


def make_video(pkg, out_dir, recent_voices=()):
    """Builds final.mp4. Sets pkg['voice']. Returns (path, credit_lines)."""
    if pkg.get("clip_audio"):
        return make_clip_ranking(pkg, out_dir)
    os.makedirs(out_dir, exist_ok=True)
    voice = pick_voice(list(recent_voices))
    audio, words, voice_credit = voiceover(pkg["script"], out_dir, voice)
    pkg["voice"] = voice if "Edge" in voice_credit else "gTTS"
    total = duration(audio) + 0.6
    scenes = pkg["scenes"]
    bounds = scene_bounds(scenes, words, total)
    hook = pkg.get("hook_text") or (pkg.get("title", "") if pkg.get("format") == "ranking" else "")
    ass = subtitles(words, scenes, bounds, hook, os.path.join(out_dir, "captions.ass"))

    used, credits, parts, plan = set(), [], [], source_plan()
    first_shot = {}  # scene index -> its first clean (caption-free) shot, used for the thumbnail
    report = {"shots": 0, "checked": 0, "unchecked": 0, "filler": 0}
    last_good = None  # most recent on-topic shot, reused (another part of it) when a scene finds nothing
    for i, (scene, (a, b)) in enumerate(zip(scenes, bounds)):
        dur = b - a
        n = 1 if dur < 3.6 else min(3, math.ceil(dur / 3.2))  # a fresh shot roughly every 3 seconds
        talk = None
        if pkg.get("presenter_image") and i in (0, len(scenes) - 1) and dur <= 12:
            try:  # AI presenter says this line on camera (lip-synced to the same voiceover)
                from . import presenter
                p = presenter.clip(audio, a, min(b, duration(audio)), pkg["presenter_image"],
                                   os.path.join(out_dir, f"presenter{i}.mp4"))
                talk = [{"kind": "video", "path": p, "credit": presenter.CREDIT, "checked": True}]
                pkg["presenter_used"] = True
            except Exception as e:  # noqa: BLE001
                print(f"  presenter clip failed for scene {i}: {str(e)[:200]}")
        if talk:
            shots = talk
        elif scene.get("product_image"):  # store promo: the real product photo, never cropped off
            shots = [{"kind": "product", "path": scene["product_image"], "credit": None, "checked": True}]
        elif scene.get("clip"):  # funny-clips format: this scene's clip was chosen (and watched) beforehand
            c = scene["clip"]
            if not os.path.exists(c.get("path") or ""):
                c["path"] = os.path.join(out_dir, f"clip{i}.mp4")
                _download(c["url"], c["path"])
            shots = [{"kind": "remix", "clip": c, "path": c["path"], "credit": c["credit"], "checked": True}]
        elif config.VISUALS == "ai":
            shots = [get_visual(dict(scene), f"{i}_{k}", out_dir, used, plan) for k in range(n)]
        else:
            from . import visuals
            shots = visuals.pick(pkg, i, n, out_dir, used)
            if config.VISUALS == "mixed" and len(shots) > 1 and config.CF_ACCOUNT_ID and config.CF_API_TOKEN:
                shots[1] = get_visual(dict(scene), f"{i}_1ai", out_dir, used, [])  # AI image for variety
            if not shots:  # nothing on-topic exists: AI image if available, else keep showing the last good shot
                if config.CF_ACCOUNT_ID and config.CF_API_TOKEN:
                    shots = [get_visual(dict(scene, stock_query=""), f"{i}_ai", out_dir, set(), [])]
                elif last_good:
                    shots = [dict(last_good, offset=True)]
                else:
                    shots = [{"kind": "gradient", "path": None, "credit": None}]
                report["filler"] += 1
        for k, vis in enumerate(shots):
            if vis.get("credit") and vis["credit"] not in credits:
                credits.append(vis["credit"])
            report["shots"] += 1
            report["checked" if vis.get("checked") else "unchecked"] += 1 if vis["kind"] != "gradient" else 0
            parts.append(render_scene(vis, dur / len(shots), os.path.join(out_dir, f"part{i:02d}_{k}.mp4")))
            first_shot.setdefault(i, (parts[-1], vis["kind"]))
            if vis["kind"] != "gradient" and not vis.get("offset"):
                last_good = vis
    pkg["visual_report"] = report

    concat = os.path.join(out_dir, "parts.txt")
    with open(concat, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in parts)

    final = os.path.join(out_dir, "final.mp4")
    music = pick_music()
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat, "-i", audio]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music, "-filter_complex",
                "[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-vf", f"ass={ass}", "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-t", f"{total:.2f}", "-movflags", "+faststart", final]
    run(cmd)

    srt(words, os.path.join(out_dir, "captions.srt"))
    try:
        from . import thumbnail
        top = next((i for i, sc in enumerate(scenes) if sc.get("badge") == "#1"), None)
        # prefer a real footage shot: the #1 reveal for rankings, else the first scene with real footage
        order = ([top] if top is not None else []) + [i for i in range(1, len(scenes))] + [0]
        pick = next((i for i in order if first_shot.get(i, (0, "gradient"))[1] != "gradient"), order[0])
        clip = first_shot[pick][0]
        thumbnail.make(clip, min(0.6, duration(clip) / 2), pkg.get("thumbnail_text") or pkg.get("hook_text")
                       or pkg["title"], os.path.join(out_dir, "thumbnail.jpg"), badge="#1" if top is not None else "",
                       accent_index=random.randrange(4))
    except Exception as e:  # noqa: BLE001
        print("Thumbnail failed:", str(e)[:150])

    stock = [c for c in credits if "(Pexels)" in c or "(Pixabay)" in c]
    other = [c for c in credits if c not in stock]
    credit_lines = [f"Voiceover: {voice_credit}."]
    if stock:
        credit_lines.append("Stock footage/photos (Pexels/Pixabay Content License): " + "; ".join(stock))
    credit_lines += other
    if music:
        credit_lines.append(f"Music: {os.path.basename(music)} (royalty-free, see assets/music/LICENSES.txt)")
    with open(os.path.join(out_dir, "credits.json"), "w") as f:
        json.dump(credit_lines, f)
    return final, credit_lines

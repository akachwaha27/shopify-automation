"""Footage that actually shows what the narration is talking about.

1. research()  - looks up the most-viewed Shorts on the same topic and keeps their thumbnails + titles.
                 They are only LOOKED AT to learn what viewers expect to see; nothing of theirs is reused.
2. plan()      - an AI "video editor" (seeing those thumbnails when Gemini is available) writes a shot list:
                 for every scene, the subject that must be on screen and 3 searches, specific -> broader,
                 each with the keywords a matching clip must be tagged with.
3. pick()      - gathers candidates from Pexels / Pixabay / NASA / Wikimedia, keeps only those whose tags
                 or titles mention the subject, then Gemini looks at each preview frame and keeps the ones
                 that clearly show it. Unchecked or off-topic clips are never used just to fill time.
"""
import json
import os
import re

import requests

from . import config, llm, state

UA = {"User-Agent": "AshvaraAutopilot/1.0 (https://github.com/akachwaha27/shopify-automation)"}
STOP = {"a", "an", "the", "of", "and", "or", "in", "on", "at", "to", "with", "for", "from", "by", "up", "over",
        "close", "closeup", "shot", "view", "video", "footage", "stock", "background", "slow", "motion", "4k", "hd"}
SPACE = {"space", "planet", "planets", "rocket", "moon", "mars", "galaxy", "nebula", "astronaut", "satellite",
         "orbit", "comet", "asteroid", "aurora", "telescope", "universe", "solar", "eclipse", "jupiter", "saturn",
         "venus", "spacecraft", "cosmos", "meteor", "nasa", "milky", "lunar", "star", "stars"}


# ------------------------------------------------------------------ words
def _stem(w):
    w = w.lower()
    for suf in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def _words(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP}


def _mentions(text_words, must):
    """True if any must-phrase is fully present (all its words) in the candidate's tags/title."""
    for phrase in must:
        need = _words(phrase)
        if need and need <= text_words:
            return True
    return False


# ------------------------------------------------------------------ 1. research
def research(topic, st=None):
    """Thumbnails + titles of the top Shorts on this topic (YouTube Data API key; ~100 quota units)."""
    if not (config.VISUAL_RESEARCH and config.YOUTUBE_API_KEY):
        return []
    if st is not None:  # daily cap so uploads always keep enough YouTube quota
        day = state.now().date().isoformat()
        used = st.setdefault("visual_searches", {})
        for d in [d for d in used if d != day]:
            used.pop(d)
        if used.get(day, 0) >= config.VISUAL_SEARCHES_PER_DAY:
            print("visual research: daily search cap reached")
            return []
        used[day] = used.get(day, 0) + 1
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", timeout=30, params={
            "part": "snippet", "q": topic["title"], "type": "video", "videoDuration": "short",
            "order": "relevance", "safeSearch": "strict", "regionCode": config.REGION,
            "relevanceLanguage": config.LANGUAGE, "maxResults": 8, "key": config.YOUTUBE_API_KEY})
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print("visual research failed:", str(e)[:150])
        return []
    refs = []
    for it in r.json().get("items", [])[:6]:
        sn = it.get("snippet", {})
        th = (sn.get("thumbnails") or {}).get("high") or (sn.get("thumbnails") or {}).get("medium") or {}
        if th.get("url"):
            refs.append({"title": sn.get("title", ""), "thumb": th["url"]})
    print(f"visual research: {len(refs)} reference Shorts for '{topic['title']}'")
    return refs


def _fetch_image(url, max_kb=900):
    try:
        r = requests.get(url, timeout=20, headers=UA)
        if r.status_code == 200 and len(r.content) < max_kb * 1024 and r.content[:4] != b"<!DO":
            return r.content
    except Exception:  # noqa: BLE001
        pass
    return None


# ------------------------------------------------------------------ 2. plan
PLAN_RULES = """For EVERY narration line, decide exactly what must be on screen.
- The shot must LITERALLY show what the line talks about: the named animal, object, place, food or action.
  Never a mood, metaphor or random people ("confused person", "chaos", "glitch", "funny moment" are banned).
- Search words must be plain nouns that stock libraries (Pixabay, Pexels, NASA) tag footage with:
  "red panda", "scrabble tiles", "basketball hoop", "full moon", "airplane cabin". No brand names, product
  names, people's names, team names, event names or years.
- If the exact subject can't exist as stock footage (a specific historic match, an app screen, a record),
  choose the closest real thing a viewer would instantly connect to it (1999 football comeback ->
  "soccer goal celebration"; phone battery glitch -> "smartphone charging").
- Each scene gets 3 searches from most specific to broader, each with "must": 1-3 keywords at least one of
  which a matching clip MUST be tagged with (singular nouns, e.g. ["panda"], ["moon", "lunar"]).
- "broll": 3 searches that fit the whole video (used only if a scene finds nothing)."""


def plan(pkg, topic, refs=()):
    """Writes pkg['shot_plan'] and pkg['visual_style']. Falls back to the writer's stock_queries."""
    scenes = pkg.get("scenes", [])
    lines = "\n".join(f"{i}. {s.get('text', '')}" + (f"  [on-screen label: {s['label']}]" if s.get("label") else "")
                      for i, s in enumerate(scenes))
    ref_titles = "\n".join(f"- Image {i}: {r['title']}" for i, r in enumerate(refs))
    images = [b for b in (_fetch_image(r["thumb"]) for r in refs) if b]
    prompt = f"""You are the video editor of a faceless YouTube Shorts channel that uses licensed stock footage.
Video: {pkg.get('title') or topic.get('title')}
Idea: {topic.get('angle', '')}
{f'''The images are thumbnails of the most-viewed Shorts on this topic right now:
{ref_titles}
Study what they show (which subjects, real footage or illustration, close-ups, setting, colors). Our video
should show the SAME KIND of subjects so viewers instantly recognize the topic, using our own stock footage.
Never copy their frames, faces, logos or branded material.''' if images else ''}

Narration lines:
{lines}

{PLAN_RULES}

Return JSON: {{"style": "one sentence: what viewers expect to see for this topic",
"broll": ["...", "...", "..."],
"scenes": [{{"line": 0, "subject": "what must be visible", "queries": [{{"q": "2-3 words", "must": ["..."]}},
{{"q": "...", "must": ["..."]}}, {{"q": "...", "must": ["..."]}}]}}]}}
One entry per narration line, in order."""
    data = None
    if images and llm.vision_available():
        try:
            data = llm.ask_vision_json(prompt, images[:6], temperature=0.3)
        except Exception as e:  # noqa: BLE001
            print("shot plan with images failed, using text only:", str(e)[:120])
    if data is None:
        try:
            data = llm.ask_json(prompt.replace("The images are thumbnails", "(Thumbnails unavailable.) The list are titles"),
                                temperature=0.3)
        except Exception as e:  # noqa: BLE001
            print("shot plan failed, using writer's searches:", str(e)[:120])
            data = {}
    by_line = {}
    for k, sp in enumerate(data.get("scenes") or []):
        idx = sp.get("line", k)
        if isinstance(idx, int) and 0 <= idx < len(scenes):
            by_line[idx] = sp
    out = []
    for i, s in enumerate(scenes):
        sp = by_line.get(i) or {}
        qs = [q for q in (sp.get("queries") or []) if isinstance(q, dict) and str(q.get("q", "")).strip()]
        if not qs:  # fall back to the writer's searches; must = the query's own nouns
            qs = [{"q": q, "must": [w for w in q.split() if w.lower() not in STOP][-1:]}
                  for q in (s.get("stock_queries") or [s.get("stock_query", "")]) if q]
        for q in qs:
            q["q"] = str(q["q"])[:60]
            q["must"] = [str(m) for m in (q.get("must") or [])][:3] or [q["q"].split()[-1]]
        out.append({"subject": sp.get("subject") or s.get("text", "")[:80], "queries": qs[:3]})
    pkg["shot_plan"] = out
    pkg["broll"] = [str(b)[:60] for b in (data.get("broll") or []) if b][:3]
    pkg["visual_style"] = str(data.get("style", ""))[:200]
    pkg["visual_refs"] = [r["title"] for r in refs]
    print("visual style:", pkg["visual_style"])
    return pkg


# ------------------------------------------------------------------ 3. candidates
def _pixabay_videos(q):
    r = requests.get("https://pixabay.com/api/videos/", timeout=30, params={
        "key": config.PIXABAY_API_KEY, "q": q[:100], "safesearch": "true", "per_page": 30})
    r.raise_for_status()
    out = []
    for v in r.json().get("hits", []):
        files = [f for f in (v["videos"].get(s) for s in ("medium", "large", "small")) if f and f.get("url")]
        if not files:
            continue
        thumb = next((f.get("thumbnail") for f in files if f.get("thumbnail")), None)
        out.append({"id": f"pxb{v['id']}", "kind": "video", "text": v.get("tags", ""), "preview": thumb,
                    "url": files[0]["url"], "ext": ".mp4", "portrait": files[0].get("height", 0) > files[0].get("width", 1),
                    "credit": f'{v["user"]} (Pixabay) {v["pageURL"]}'})
    return out


def _pixabay_photos(q):
    r = requests.get("https://pixabay.com/api/", timeout=30, params={
        "key": config.PIXABAY_API_KEY, "q": q[:100], "safesearch": "true", "per_page": 20, "image_type": "photo"})
    r.raise_for_status()
    return [{"id": f"pxbp{p['id']}", "kind": "image", "text": p.get("tags", ""), "preview": p.get("webformatURL"),
             "url": p["largeImageURL"], "ext": ".jpg", "portrait": p.get("imageHeight", 0) > p.get("imageWidth", 1),
             "credit": f'{p["user"]} (Pixabay) {p["pageURL"]}'} for p in r.json().get("hits", [])]


def _pexels_videos(q):
    r = requests.get("https://api.pexels.com/videos/search", timeout=30, headers={"Authorization": config.PEXELS_API_KEY},
                     params={"query": q, "per_page": 20})
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        files = sorted([f for f in v["video_files"] if f.get("height") and f.get("link") and min(f["height"], f["width"]) >= 720],
                       key=lambda f: f["height"] * f["width"])
        if not files:
            continue
        slug = v.get("url", "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
        out.append({"id": f"pex{v['id']}", "kind": "video", "text": slug, "preview": v.get("image"),
                    "url": files[0]["link"], "ext": ".mp4", "portrait": files[0]["height"] > files[0]["width"],
                    "credit": f'{v["user"]["name"]} (Pexels) {v["url"]}'})
    return out


def _pexels_photos(q):
    r = requests.get("https://api.pexels.com/v1/search", timeout=30, headers={"Authorization": config.PEXELS_API_KEY},
                     params={"query": q, "per_page": 15})
    r.raise_for_status()
    return [{"id": f"pexp{p['id']}", "kind": "image", "text": p.get("alt", "") + " " + p.get("url", "").replace("-", " "),
             "preview": p["src"].get("medium"), "url": p["src"]["large2x"], "ext": ".jpg",
             "portrait": p.get("height", 0) > p.get("width", 1), "credit": f'{p["photographer"]} (Pexels) {p["url"]}'}
            for p in r.json().get("photos", [])]


def _nasa_images(q):
    if not SPACE & {w.lower() for w in re.findall(r"[a-z]+", q.lower())}:
        return []  # NASA's search is loose: only for space scenes, and photos only (its videos have narrators/text)
    r = requests.get("https://images-api.nasa.gov/search", timeout=30, params={"q": q, "media_type": "image", "page_size": 20})
    r.raise_for_status()
    out = []
    for it in r.json().get("collection", {}).get("items", []):
        d, links = it["data"][0], it.get("links") or []
        prev = next((lk["href"] for lk in links if lk.get("href", "").endswith(".jpg")), None)
        if not prev:
            continue
        out.append({"id": f"nasa{d['nasa_id']}", "kind": "image", "preview": prev, "ext": ".jpg", "portrait": False,
                    "text": " ".join([d.get("title", ""), " ".join(d.get("keywords") or [])]),
                    "url": prev.replace("~thumb.jpg", "~large.jpg"), "fallback_url": prev.replace("~thumb.jpg", "~medium.jpg"),
                    "credit": f"NASA{' / ' + d['center'] if d.get('center') else ''}: \"{d.get('title', '')[:60]}\" (public domain)"})
    return out


OK_LICENSE = re.compile(r"^(cc0|public domain|pd|cc by \d(\.\d)?|cc-by-\d(\.\d)?)", re.I)


def _commons_photos(q):
    import html
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 15,
        "gsrsearch": f"{q} filetype:bitmap", "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
    r.raise_for_status()
    out = []
    for page in (r.json().get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "").strip()
        if not OK_LICENSE.match(lic) or info.get("width", 0) < 800:
            continue
        artist = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", meta.get("Artist", {}).get("value", "Unknown")))).strip()
        if "all rights reserved" in artist.lower():
            continue
        thumb = info.get("thumburl") or info.get("url")
        out.append({"id": f"wm{page['pageid']}", "kind": "image", "preview": thumb.replace("/1600px-", "/500px-"),
                    "url": thumb, "ext": ".jpg", "portrait": info.get("height", 0) > info.get("width", 1),
                    "text": page.get("title", "").replace("_", " ") + " " + re.sub(r"<[^>]+>", " ", meta.get("ImageDescription", {}).get("value", ""))[:200],
                    "credit": f"{artist[:60] or 'Unknown'} / Wikimedia Commons ({lic}) {info.get('descriptionurl', '')}"})
    return out


def _sources():
    """Videos first (Pexels, Pixabay), then photos; NASA only answers for space; Commons last."""
    src = []
    if config.PEXELS_API_KEY:
        src.append(_pexels_videos)
    if config.PIXABAY_API_KEY:
        src.append(_pixabay_videos)
    if config.PEXELS_API_KEY:
        src.append(_pexels_photos)
    if config.PIXABAY_API_KEY:
        src.append(_pixabay_photos)
    return src + [_nasa_images, _commons_photos]


VIDEO_SOURCES = ("_pexels_videos", "_pixabay_videos")


def candidates(query, used, kind=None):
    """All on-topic candidates for one search: tagged with one of the must-keywords, not used before.
    kind="video" / "image" limits which libraries are searched."""
    found, seen = [], set()
    for fn in _sources():
        if kind and (fn.__name__ in VIDEO_SOURCES) != (kind == "video"):
            continue
        try:
            items = fn(query["q"])
        except Exception as e:  # noqa: BLE001
            print(f"  {fn.__name__} failed for '{query['q']}': {str(e)[:100]}")
            continue
        for c in items:
            if c["id"] in used or c["id"] in seen or not c.get("preview"):
                continue
            words = _words(c["text"])
            if not _mentions(words, query["must"]):
                continue
            seen.add(c["id"])
            c["score_text"] = len(words & _words(query["q"])) + (1 if c["kind"] == "video" else 0) + (0.5 if c["portrait"] else 0)
            found.append(c)
    found.sort(key=lambda c: c["score_text"], reverse=True)
    return found


def verify(subject, line, cands, keep):
    """Gemini looks at the preview frames and scores how clearly each shows the subject (0-10)."""
    if not (config.VISUAL_CHECK and llm.vision_available()) or not cands:
        for c in cands:
            c["checked"] = False
        return cands[:keep]
    pool = cands[:8]
    imgs, idx = [], []
    for k, c in enumerate(pool):
        b = _fetch_image(c["preview"])
        if b:
            imgs.append(b)
            idx.append(k)
    if not imgs:
        return []
    prompt = f"""You check stock footage for a YouTube Short.
Narration for this shot: "{line}"
The shot must clearly show: {subject}
Images 0-{len(imgs) - 1} are preview frames of candidate clips. Score each 0-10:
10 = clearly shows exactly that subject; 6 = clearly the right subject, generic angle; 3 = loosely related;
0 = unrelated. Score 0 for anything with visible text, captions, watermarks, logos or brand names,
recognizable famous people, violence or anything not family-friendly.
Return JSON: {{"scores": [{{"image": 0, "score": 7}}]}}"""
    try:
        res = llm.ask_vision_json(prompt, imgs)
    except Exception as e:  # noqa: BLE001
        print("  visual check unavailable, using tag match only:", str(e)[:100])
        for c in cands:
            c["checked"] = False
        return cands[:keep]
    scores = {}
    for s in res.get("scores") or []:
        try:
            scores[idx[int(s["image"])]] = float(s["score"])
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    good = [(scores[k], pool[k]) for k in scores if scores[k] >= config.VISUAL_MIN_SCORE]
    good.sort(key=lambda t: (t[0], t[1]["kind"] == "video"), reverse=True)
    for sc, c in good:
        c["checked"], c["score"] = True, sc
    return [c for _, c in good][:keep]


def _download(c, base):
    from .media import _download as dl
    path = base + c["ext"]
    try:
        dl(c["url"], path, headers=UA if c["id"].startswith(("wm", "nasa")) else None)
    except Exception:  # noqa: BLE001
        if not c.get("fallback_url"):
            raise
        dl(c["fallback_url"], path)
    return {"kind": c["kind"], "path": path, "credit": c["credit"], "checked": c.get("checked", False),
            "subject": c.get("subject", "")}


def pick(pkg, i, n, out_dir, used):
    """Up to n verified, on-topic shots for scene i (fewer if fewer exist; never random filler)."""
    plan_ = (pkg.get("shot_plan") or [])
    sp = plan_[i] if i < len(plan_) else {"subject": pkg["scenes"][i].get("text", "")[:80], "queries": [
        {"q": q, "must": q.split()[-1:]} for q in pkg["scenes"][i].get("stock_queries", []) if q]}
    line = pkg["scenes"][i].get("text", "")
    chosen = []
    queries = list(sp["queries"]) + [{"q": b, "must": [w for w in b.split() if w.lower() not in STOP][-1:]}
                                     for b in pkg.get("broll", [])]
    # moving footage first: try every search for VIDEO clips; still photos only if no video exists
    for kind, qs in (("video", queries), ("image", sp["queries"])):
        for q in qs:
            if len(chosen) >= n or (kind == "image" and chosen):
                break
            cands = [c for c in candidates(q, used, kind) if c["id"] not in {x["id"] for x in chosen}]
            for c in verify(sp["subject"], line, cands, n - len(chosen)):
                used.add(c["id"])
                c["subject"] = sp["subject"]
                chosen.append(c)
    shots = []
    for k, c in enumerate(chosen):
        try:
            shots.append(_download(c, os.path.join(out_dir, f"s{i}_{k}")))
        except Exception as e:  # noqa: BLE001
            print(f"  download failed ({c['id']}): {str(e)[:100]}")
    if os.getenv("GITHUB_ACTIONS") and os.getenv("FOOTAGE_NOTICES"):
        for c in chosen:
            print(f"::notice title=scene {i} pick::{c.get('score', '-')}/10 {c['text'][:80]} ({c['credit'][:60]})")
    print(f"scene {i}: {len(shots)}/{n} shots for '{sp['subject']}'"
          + (f" ({sum(s['checked'] for s in shots)} checked by AI)" if shots else ""))
    return shots


def report(pkg):
    r = pkg.get("visual_report") or {}
    if not r.get("shots"):
        return ""
    return (f"🎞 Footage: {r['checked']}/{r['shots']} shots checked on-topic by AI"
            + (f", {r['unchecked']} matched by tags only" if r.get("unchecked") else "")
            + (f", {r['filler']} scene(s) with no matching footage" if r.get("filler") else ""))


def dump(pkg, path):
    with open(path, "w") as f:
        json.dump({"style": pkg.get("visual_style"), "refs": pkg.get("visual_refs"), "plan": pkg.get("shot_plan")}, f, indent=1)

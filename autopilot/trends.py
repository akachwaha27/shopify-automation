"""Collect trending signals and turn them into 5 safe, original video ideas."""
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import timedelta

import requests

from . import config, llm, state

# Hard filter: anything matching these never reaches the AI or you.
BLOCKLIST = re.compile(r"\b(" + "|".join([
    # politics / government
    "election", "elect", "vote", "voter", "ballot", "president", "senator", "congress", "parliament",
    "democrat", "republican", "gop", "trump", "biden", "harris", "vance", "modi", "putin", "zelensky",
    "netanyahu", "minister", "governor", "mayor", "campaign", "impeach", "tariff", "policy", "protest",
    "immigration", "border", "deport", "supreme court", "lawsuit", "sued", "indict", "trial", "verdict",
    # conflict / violence / tragedy
    "war", "attack", "shooting", "shooter", "gun", "killed", "kill", "dead", "death", "dies", "died",
    "murder", "stabbing", "terror", "bomb", "missile", "hostage", "gaza", "israel", "ukraine", "russia",
    "iran", "hamas", "crash", "accident", "fire", "earthquake", "hurricane", "flood", "tornado",
    "victim", "funeral", "obituary", "arrest", "police", "prison", "jail", "crime", "scandal",
    # sensitive / divisive
    "abortion", "religion", "church", "mosque", "islam", "christian", "jewish", "gay", "trans",
    "racist", "racism", "lgbt", "vaccine", "covid", "cancer", "overdose", "suicide", "drug",
    "nsfw", "onlyfans", "leak", "nude", "affair", "divorce", "cheating", "feud", "beef", "diss",
    "bitcoin", "crypto", "stock", "lottery", "betting", "casino",
]) + r")\b", re.I)


def google_trends():
    url = f"https://trends.google.com/trending/rss?geo={config.REGION}"
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    try:
        root = ET.fromstring(requests.get(url, timeout=30).content)
        for item in root.iter("item"):
            title = item.findtext("title", "")
            traffic = item.findtext("ht:approx_traffic", "", ns)
            news = [n.findtext("ht:news_item_title", "", ns) for n in item.findall("ht:news_item", ns)]
            out.append({"source": "Google Trends", "title": title, "signal": traffic,
                        "context": " | ".join(news[:2])})
    except Exception as e:  # noqa: BLE001
        print("Google Trends failed:", e)
    return out


def youtube_trending():
    if not config.YOUTUBE_API_KEY:
        return []
    out = []
    base = "https://www.googleapis.com/youtube/v3"
    try:
        r = requests.get(f"{base}/videos", timeout=30, params={
            "part": "snippet,statistics", "chart": "mostPopular", "regionCode": config.REGION,
            "maxResults": 50, "key": config.YOUTUBE_API_KEY}).json()
        for v in r.get("items", []):
            s = v["snippet"]
            out.append({"source": "YouTube Trending", "title": s["title"],
                        "signal": f'{int(v["statistics"].get("viewCount", 0)):,} views',
                        "context": " ".join(s.get("tags", [])[:6])})
        # Short-form signal: most-viewed Shorts from the last 48h (covers TikTok/Reels-style trends)
        after = (state.now() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = requests.get(f"{base}/search", timeout=30, params={
            "part": "snippet", "q": "#shorts", "type": "video", "videoDuration": "short",
            "order": "viewCount", "publishedAfter": after, "regionCode": config.REGION,
            "relevanceLanguage": config.LANGUAGE, "maxResults": 50, "key": config.YOUTUBE_API_KEY}).json()
        for v in r.get("items", []):
            out.append({"source": "YouTube Shorts (48h)", "title": v["snippet"]["title"],
                        "signal": "top viewed short", "context": v["snippet"].get("description", "")[:120]})
    except Exception as e:  # noqa: BLE001
        print("YouTube trends failed:", e)
    return out


SIGNALS = os.path.join("content", "viral_signals.json")


def viral_signals():
    """Today's most-viewed Shorts (48h), each scored by how far it beat its OWN channel's median views
    (method from youtube-agent-skill's swipe.py). Saved for the 9 AM Claude research task; ~160 quota units."""
    if not config.YOUTUBE_API_KEY:
        return None
    import statistics
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from yt_skill.swipe import classify
    base, key = "https://www.googleapis.com/youtube/v3", config.YOUTUBE_API_KEY
    after = (state.now() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get(f"{base}/search", timeout=30, params={
        "part": "snippet", "q": "#shorts", "type": "video", "videoDuration": "short", "order": "viewCount",
        "publishedAfter": after, "regionCode": config.REGION, "relevanceLanguage": config.LANGUAGE,
        "maxResults": 50, "key": key}).json()
    items = [i for i in r.get("items", []) if i.get("id", {}).get("videoId")]
    ids = [i["id"]["videoId"] for i in items]
    stats = {}
    for k in range(0, len(ids), 50):
        for v in requests.get(f"{base}/videos", timeout=30, params={"part": "statistics", "id": ",".join(ids[k:k + 50]),
                                                                    "key": key}).json().get("items", []):
            stats[v["id"]] = int(v.get("statistics", {}).get("viewCount", 0))
    chans = sorted({i["snippet"]["channelId"] for i in items})
    uploads = {}
    for k in range(0, len(chans), 50):
        for c in requests.get(f"{base}/channels", timeout=30, params={"part": "contentDetails,statistics",
                                                                      "id": ",".join(chans[k:k + 50]), "key": key}).json().get("items", []):
            uploads[c["id"]] = c["contentDetails"]["relatedPlaylists"]["uploads"]
    medians = {}
    for cid, pl in uploads.items():
        try:
            vids = [x["contentDetails"]["videoId"] for x in requests.get(f"{base}/playlistItems", timeout=30, params={
                "part": "contentDetails", "playlistId": pl, "maxResults": 12, "key": key}).json().get("items", [])]
            views = [int(v.get("statistics", {}).get("viewCount", 0)) for v in requests.get(
                f"{base}/videos", timeout=30, params={"part": "statistics", "id": ",".join(vids), "key": key}).json().get("items", [])]
            if len(views) >= 4:
                medians[cid] = statistics.median(views)
        except Exception:  # noqa: BLE001
            continue
    out = []
    for i in items:
        sn, vid = i["snippet"], i["id"]["videoId"]
        if BLOCKLIST.search(f'{sn.get("title", "")} {sn.get("description", "")}'):
            continue
        views, med = stats.get(vid, 0), medians.get(sn["channelId"])
        out.append({"title": sn.get("title", ""), "channel": sn.get("channelTitle", ""), "views": views,
                    "channel_median": int(med) if med else None,
                    "multiple": round(views / med, 1) if med else None,
                    "formula": classify(sn.get("title", "")), "url": f"https://www.youtube.com/shorts/{vid}"})
    out.sort(key=lambda x: (x["multiple"] or 0, x["views"]), reverse=True)
    data = {"date": state.now().date().isoformat(), "region": config.REGION,
            "note": "multiple = views / that channel's median views (>= 2 means it broke out)",
            "shorts": out, "google_trends": [{"title": t["title"], "context": t["context"]} for t in google_trends()]}
    os.makedirs(os.path.dirname(SIGNALS), exist_ok=True)
    with open(SIGNALS, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    print(f"viral signals: {len(out)} Shorts, {sum(1 for x in out if (x['multiple'] or 0) >= 2)} outliers")
    return data


def collect():
    raw = google_trends() + youtube_trending()
    safe = [t for t in raw if not BLOCKLIST.search(f'{t["title"]} {t["context"]}')]
    print(f"Collected {len(raw)} signals, {len(safe)} passed keyword filter")
    return safe


GENERIC = {"top", "5", "3", "why", "how", "what", "the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or",
           "you", "your", "are", "is", "that", "this", "these", "they", "do", "does", "can", "will", "way", "than",
           "think", "ever", "most", "really", "actually", "secretly", "didn", "t", "know", "need", "s", "with", "from",
           "about", "things", "thing", "every", "everyone", "completely", "absolute", "insane", "crazy", "weird", "weirdest",
           "funniest", "best", "worst", "facts", "fact", "ranked", "ranking", "explained", "it", "its", "has", "have"}


def _key(title):
    words = re.findall(r"[a-z0-9]+", title.lower().replace(",", ""))
    out = set()
    for w in words:
        if w in GENERIC:
            continue
        for suf in ("ies", "es", "s"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)] + ("y" if suf == "ies" else "")
                break
        out.add(w)
    return out


def is_repeat(title, past_keys):
    """Same idea reworded? True when most of the meaningful words match an earlier idea."""
    k = _key(title)
    if not k:
        return False
    for pk in past_keys:
        if not pk:
            continue
        common = len(k & pk)
        ratio = common / min(len(k), len(pk))
        if k == pk or (common >= 3 and ratio >= 0.6) or (common >= 2 and ratio >= 0.75):
            return True
    return False


def channel_titles(limit=500):
    """Titles of every video already on your YouTube channel (incl. private and ones made outside the bot)."""
    if not (config.YT_CLIENT_ID and config.YT_CLIENT_SECRET and config.YT_REFRESH_TOKEN):
        return []
    try:
        from . import publish
        yt = publish.yt_service()
        ch = yt.channels().list(part="contentDetails", mine=True).execute().get("items", [])
        uploads = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"] if ch else None
        titles, token = [], None
        while uploads and len(titles) < limit:
            r = yt.playlistItems().list(part="snippet", playlistId=uploads, maxResults=50, pageToken=token).execute()
            titles += [i["snippet"]["title"] for i in r.get("items", [])]
            token = r.get("nextPageToken")
            if not token:
                break
        print(f"channel: {len(titles)} existing video titles")
        return titles
    except Exception as e:  # noqa: BLE001
        print("could not read channel titles:", str(e)[:150])
        return []


def past_ideas(history=(), include_plan=True):
    """Every idea ever sent to you or made into a video (permanent archive + recent state + your channel),
    plus every row of the content plan sheet (so the bot's own ideas never duplicate the sheet)."""
    from . import library
    titles = list(history) + channel_titles()
    if include_plan:
        from . import plan
        titles += [r["title"] for r in plan.rows()]
    for day, b in sorted(library.load("ideas").items()):
        titles += [i.get("title", "") for i in b.get("ideas", [])]
    for v in library.load("videos").values():
        titles += [v.get("title", ""), v.get("idea_title", "")]
    seen, out = set(), []
    for t in titles:
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def same_subject(candidates, past):
    """AI check for repeats that use different words (e.g. 'useless inventions' vs 'absurd inventions',
    'phone hacks' vs 'phone camera tricks'). Returns the set of candidate indexes that repeat a past idea."""
    if not candidates or not past:
        return set()
    old = "\n".join(f"- {t}" for t in past[-300:])
    new = "\n".join(f"{i}. {t['title']} - {t.get('angle', '')}" for i, t in enumerate(candidates))
    prompt = f"""A YouTube Shorts channel must never repeat itself. Earlier ideas and videos:
{old}

New candidate ideas:
{new}

A candidate is a REPEAT if a viewer would feel it's the same video again: the same main subject or premise as
any earlier item, even with different wording or a different number of items (e.g. "useless inventions" =
"absurd inventions"; "phone hacks you ignore" = "smartphone tricks you didn't know"; "foods older than you
think" = "foods that are ancient"). A clearly different subject in the same format is NOT a repeat.
Also flag two candidates that repeat EACH OTHER (flag the second one).
Return JSON: {{"repeats": [{{"index": 0, "same_as": "the earlier title"}}]}}"""
    try:
        res = llm.ask_json(prompt, temperature=0)
    except Exception as e:  # noqa: BLE001
        print("repeat check unavailable:", str(e)[:120])
        return set()
    out = set()
    items = res if isinstance(res, list) else (res.get("repeats") or [])
    for r in items:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r["index"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < len(candidates):
            print(f"skipping repeated idea: {candidates[i]['title']} (same as: {r.get('same_as', '?')})")
            out.add(i)
    return out


def pick_topics(signals, history, n=None, extra_past=()):
    want = n or config.TOPICS_PER_DAY
    past = past_ideas(history) + list(extra_past)
    past_keys = [_key(t) for t in past]
    topics, rejected = [], []
    for attempt in range(4):  # later passes ask for replacements for any repeats
        need = want - len(topics)
        fresh = _ask_topics(signals, past + [t["title"] for t in topics] + rejected, need if attempt or n else None)
        word_ok = []
        for t in fresh:
            if is_repeat(t["title"], past_keys + [_key(x["title"]) for x in topics + word_ok]):
                print("skipping repeated idea:", t["title"])
                rejected.append(t["title"])
            else:
                word_ok.append(t)
        dupes = same_subject(word_ok, past + [t["title"] for t in topics])
        for i, t in enumerate(word_ok):
            if i in dupes:
                rejected.append(t["title"])
            elif len(topics) < want:
                topics.append(t)
        if len(topics) >= want:
            break
    topics.sort(key=lambda t: t.get("virality_score", 0) or 0, reverse=True)
    return topics


def _ask_topics(signals, covered, count=None):
    lines = "\n".join(f'- [{s["source"]}] {s["title"]} ({s["signal"]}) {s["context"]}' for s in signals[:120])
    prompt = f"""You are a YouTube Shorts growth strategist for a faceless, monetization-focused channel.
You know what the Shorts algorithm rewards: a strong hook, high swipe-through and completion rate,
rewatches/loops, comments and shares, and topics people are searching for right now.
Niche preference: {config.NICHE}. Audience region: {config.REGION}. Language: {config.LANGUAGE}.

Trending signals from the last 24-48h:
{lines}

ALREADY USED - every idea below was sent before. Do NOT repeat any of them, reword them, or pick the same subject
with a different title (e.g. if "Why soda cans explode at 30,000 feet" is listed, no soda-can-at-altitude idea at all).
Pick genuinely NEW subjects, and vary the themes (don't keep coming back to phones, tech settings or inventions):
{chr(10).join('- ' + t for t in covered[-250:]) or 'none'}

Choose exactly {count or config.TOPICS_PER_DAY} ideas for ORIGINAL Shorts of about one minute (55-65 seconds). Use the trends as inspiration
(ride the curiosity around them with a SAFE ANGLE); if the trends are weak, use proven evergreen Shorts ideas.
Mix FORMATS - use at least 4 different ones across the list, max 2 of the same:
- "ranking": Top 5 countdown with a clear, checkable measure ("Top 5 fastest animals on Earth")
- "story": original wholesome/mystery/twist mini story, clearly fiction (e.g. inspired by a trending holiday or event mood)
- "funny": kind, family-friendly humor: relatable everyday situations, funny-but-true facts, absurd observations
- "quiz": 3-question trivia challenge viewers play along with
- "tips": quick, genuinely useful everyday tips/hacks (tech, home, cooking, travel, productivity)
- "explainer": surprising "why/how" curiosity facts
- "clips": "Ranking the funniest animal moments" - real free stock clips of animals doing funny things
  (dogs, cats, goats, ducks, parrots, monkeys...), ranked #5 to #1. Keep it about ANIMALS only (one animal
  type or animals in general), e.g. "Ranking the funniest goat moments", "Top 5 funniest dog reactions"
{f'Include at least {config.RANKINGS_PER_DAY} "ranking" ideas.' if config.RANKINGS_PER_DAY else ''}
{f'Include exactly {config.CLIPS_PER_DAY} "clips" idea(s) (tone "funny").' if config.CLIPS_PER_DAY else ''}
{f'''FUNNY IS REQUIRED: include at least {config.FUNNY_PER_DAY} ideas with "tone": "funny" - at least one "funny" format
idea AND at least one FUNNY "ranking" (a Top 5 that is played for laughs, e.g. "Top 5 animals with ridiculous
sleeping habits", "Top 5 inventions that made no sense", "Top 5 weirdest world records"). Funny ideas must be
kind and family-friendly, and must not be pushed to the bottom: give them honest virality scores.''' if config.FUNNY_PER_DAY else ''}
Every idea also gets "tone": "funny" (played for laughs) or "normal".

Hard rules - reject any idea that:
- involves politics, elections, government, war, crime, death, disasters, religion, health/medical or financial
  advice, lawsuits, celebrity gossip/drama, real living people, or anything divisive, shocking or likely to offend;
- would need someone else's footage, music, characters or likeness;
- makes claims that can't be verified; or is aimed at young children.
Every idea must be advertiser-friendly and suitable for a general 13+ audience.

Return JSON: {{"topics": [{{"title": "short catchy working title", "angle": "one sentence on the video idea",
"format": "ranking|story|funny|quiz|tips|explainer|clips", "tone": "funny|normal", "trend_source": "which signal inspired it (or evergreen)",
"virality_score": 1-10, "why": "why it can win in the Shorts feed"}}]}}
Sort by virality_score descending."""
    data = llm.ask_json(prompt, temperature=0.8)
    topics = data if isinstance(data, list) else data.get("topics", [])
    topics = [t for t in topics if isinstance(t, dict) and t.get("title")]
    # second line of defence
    from .writer import fmt_of
    for t in topics:
        t["format"] = fmt_of(t)
        t["tone"] = "funny" if t["format"] == "funny" or str(t.get("tone", "")).lower().startswith("fun") else "normal"
    return [t for t in topics if not BLOCKLIST.search(t["title"] + " " + t["angle"])][: config.TOPICS_PER_DAY]

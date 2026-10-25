"""The content plan sheet: one row = one video, researched and scripted by Claude every morning.

content/plan.csv     rows written by the daily Claude research task (append-only; never edited by the bot)
content/status.json  the bot's status for each row: Ready -> Sent -> Making -> Preview -> Published
                     (or Not picked / Skipped / Failed). Kept separate so the two writers never clash.
"""
import csv
import io
import json
import os

from . import state

PLAN = os.path.join("content", "plan.csv")
STATUS = os.path.join("content", "status.json")
COLUMNS = ["id", "added", "format", "title", "thumbnail_text", "hook", "hook_score", "title_score", "script",
           "on_screen", "footage", "description", "hashtags", "tags", "pinned_comment", "virality_score",
           "why_it_works", "inspired_by", "sources",
           # added by the youtube-agent-skill pass (yt-script, yt-shorts, yt-package, yt-seo, yt-comment, yt-plan)
           "hook_runner_up", "runtime", "opening_text", "loop_point", "title_options", "thumbnail_brief",
           "search_queries", "comment_replies", "plan_promise",
           # Ashvara: Shopify product handle the promo is about (format "product")
           "product"]
VIDEO_STATUS = {"queued": "Making", "generating": "Making", "revoice": "Making", "awaiting_approval": "Preview",
                "approved": "Approved", "published": "Published", "rejected": "Skipped", "failed": "Failed",
                "not_posted": "Made, not posted"}


def rows():
    if not os.path.exists(PLAN):
        return []
    with open(PLAN, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if (r.get("id") or "").strip() and (r.get("title") or "").strip()]


def statuses():
    try:
        with open(STATUS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_status(s):
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False, sort_keys=True)


def ready(limit):
    s = statuses()
    today = state.now().date().isoformat()

    def usable(st):  # Ready, or an earlier day's idea that failed / wasn't picked (offered again)
        status = st.get("status", "Ready")
        return status == "Ready" or (status in ("Failed", "Not picked") and (st.get("sent") or "")[:10] < today)
    return [r for r in rows() if usable(s.get(r["id"], {}))][:limit]


def topic_of(r):
    try:
        score = int(float(r.get("virality_score") or 8))
    except ValueError:
        score = 8
    return {"title": r["title"], "angle": r.get("why_it_works") or r.get("hook", ""), "format": r.get("format") or "explainer",
            "tone": "funny" if "fun" in (r.get("format") or "").lower() else "normal", "virality_score": score,
            "trend_source": r.get("inspired_by") or "content plan", "plan_id": r["id"],
            "product": (r.get("product") or "").strip()}


def sync(st):
    """Derive every row's status from the bot's state (called on every state save)."""
    s, changed = statuses(), False

    def put(pid, **kw):
        nonlocal changed
        cur = s.get(pid, {})
        new = dict(cur, **{k: v for k, v in kw.items() if v is not None})
        if new != cur:
            new["updated"] = state.iso()
            s[pid] = new
            changed = True

    for bid, b in st.get("batches", {}).items():
        for i, t in enumerate(b.get("topics", [])):
            pid = t.get("plan_id")
            if not pid:
                continue
            if i not in b.get("selected", []):
                put(pid, status="Not picked" if b.get("status") == "closed" else "Sent", sent=bid)
    for vid, v in st.get("videos", {}).items():
        pid = (v.get("topic") or {}).get("plan_id")
        if not pid:
            continue
        link = ((v.get("results") or {}).get("YouTube") or [None])[0]
        put(pid, status=VIDEO_STATUS.get(v.get("status"), v.get("status")), video_id=vid,
            youtube=link, published=(v.get("uploaded_at") or "")[:10] or None)
    if changed:
        _save_status(s)


def as_table():
    """Rows merged with their status, for the Excel 'Content Plan' sheet."""
    s = statuses()
    return [dict(r, **{"status": s.get(r["id"], {}).get("status", "Ready"),
                       "youtube": s.get(r["id"], {}).get("youtube", ""),
                       "published": s.get(r["id"], {}).get("published", "")}) for r in rows()]


def to_csv(table):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for r in table:
        w.writerow({k: r.get(k, "") for k in COLUMNS})
    return buf.getvalue()

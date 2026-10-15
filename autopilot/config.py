"""All settings come from environment variables (GitHub Secrets / Variables)."""
import os


def env(name, default=None, cast=str):
    val = os.getenv(name)
    if val is not None:
        val = val.strip()  # secrets pasted with a stray space/newline break API keys
    if val is None or val == "":
        return default
    if cast is bool:
        return val.strip().lower() in ("1", "true", "yes", "on")
    return cast(val)


# --- Required secrets ---
TELEGRAM_BOT_TOKEN = env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = env("TELEGRAM_CHAT_ID")          # your personal chat id
GEMINI_API_KEY = env("GEMINI_API_KEY")
YOUTUBE_API_KEY = env("YOUTUBE_API_KEY")             # for reading trends
PEXELS_API_KEY = env("PEXELS_API_KEY")               # free stock video/photos (optional)
PIXABAY_API_KEY = env("PIXABAY_API_KEY")             # free stock video/photos (optional)

# --- Publishing (any you leave blank is skipped) ---
YT_CLIENT_ID = env("YT_CLIENT_ID")
YT_CLIENT_SECRET = env("YT_CLIENT_SECRET")
YT_REFRESH_TOKEN = env("YT_REFRESH_TOKEN")
YT_PRIVACY = env("YT_PRIVACY", "private")            # set Variable YT_PRIVACY=public after Google approves your API audit

FB_PAGE_ID = env("FB_PAGE_ID")                       # Facebook Page that gets the Reels
FB_PAGE_TOKEN = env("FB_PAGE_TOKEN")                 # Page token from tools/get_meta_token.py (doesn't expire)
IG_USER_ID = env("IG_USER_ID")
IG_ACCESS_TOKEN = env("IG_ACCESS_TOKEN") or FB_PAGE_TOKEN  # the same Page token works for Instagram
IG_GRAPH_HOST = env("IG_GRAPH_HOST", "graph.facebook.com")
IG_API_VERSION = env("IG_API_VERSION", "v23.0")

TIKTOK_ACCESS_TOKEN = env("TIKTOK_ACCESS_TOKEN")
TIKTOK_REFRESH_TOKEN = env("TIKTOK_REFRESH_TOKEN")
TIKTOK_CLIENT_KEY = env("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = env("TIKTOK_CLIENT_SECRET")
# draft = video lands in your TikTok inbox; you add a trending sound and tap Post (works without TikTok's audit).
# direct = posts straight to your profile (until TikTok audits the app this is private-only, SELF_ONLY).
TIKTOK_MODE = env("TIKTOK_MODE", "draft")
TIKTOK_PRIVACY = env("TIKTOK_PRIVACY", "SELF_ONLY")  # direct mode only; unaudited apps may only post SELF_ONLY
INSTAGRAM_HASHTAGS = env("INSTAGRAM_HASHTAGS", 5, int)  # Instagram allows at most 5 hashtags per post

# --- Optional AI images (free tier) instead of stock footage ---
CF_ACCOUNT_ID = env("CF_ACCOUNT_ID")
FAL_KEY = env("FAL_KEY")
PRESENTER = env("PRESENTER", True, bool)            # AI presenter on product videos (needs FAL_KEY + a chosen look)
PRESENTER_PER_DAY = env("PRESENTER_PER_DAY", 1, int)
PRESENTER_MODEL = env("PRESENTER_MODEL", "fal-ai/kling-video/ai-avatar/v2/standard")  # ~$0.056 per second
PRESENTER_IMAGE_MODEL = env("PRESENTER_IMAGE_MODEL", "fal-ai/flux/dev")
CF_API_TOKEN = env("CF_API_TOKEN")

# --- Store (Ashvara product promos) ---
STORE_URL = env("STORE_URL", "https://ashvara.store").rstrip("/")   # public product feed: STORE_URL/products.json
STORE_NAME = env("STORE_NAME", "Ashvara")
PLAN_ONLY = env("PLAN_ONLY", True, bool)             # true = daily list uses only content/plan.csv rows (no YouTube trend ideas)
PRODUCT_SHOT_EVERY = env("PRODUCT_SHOT_EVERY", 2, int)  # product photo on every Nth scene (others get matching stock b-roll)

# Where finished videos are posted (comma list: facebook,instagram,youtube,tiktok). Platforms not listed are skipped
# even if their keys exist; Telegram previews always happen.
PUBLISH_TO = {x.strip().lower() for x in env("PUBLISH_TO", "facebook,instagram").split(",") if x.strip()}

# --- Behaviour (GitHub Variables) ---
NICHE = env("NICHE", "home and lifestyle: pets (dogs and cats), self-care, home fitness, cozy home")
REGION = env("REGION", "US")
LANGUAGE = env("LANGUAGE", "en")
GEMINI_MODEL = env("GEMINI_MODEL")                      # blank = auto-pick newest free Flash model
VOICE = env("VOICE", "en-US-AndrewMultilingualNeural")  # fallback voice
VOICES = env("VOICES")                               # optional comma-separated pool; blank = built-in rotation
VISUALS = env("VISUALS", "stock")                    # stock | ai (Cloudflare) | mixed
VISUAL_RESEARCH = env("VISUAL_RESEARCH", True, bool)      # look at the top Shorts on each topic before choosing footage
VISUAL_SEARCHES_PER_DAY = env("VISUAL_SEARCHES_PER_DAY", 6, int)  # 100 YouTube quota units each; keeps uploads safe
VISUAL_CHECK = env("VISUAL_CHECK", True, bool)            # Gemini looks at every candidate clip before it's used
VISUAL_MIN_SCORE = env("VISUAL_MIN_SCORE", 6, float)      # 0-10: how clearly a clip must show the subject
CLIPS_PER_DAY = env("CLIPS_PER_DAY", 0, int)             # daily "funniest animal moments" ideas (off: free stock clips are rarely truly funny)
CLIP_MIN_FUNNY = env("CLIP_MIN_FUNNY", 5, float)         # 0-10: how funny AI must rate a clip to use it
CLIP_ORIGINAL_AUDIO = env("CLIP_ORIGINAL_AUDIO", False, bool)  # true = clips with their own sound get no voiceover (not monetizable: reused content)
CLIP_MAX_SECONDS = env("CLIP_MAX_SECONDS", 10, float)     # longest each clip plays in the no-voiceover version
TOPICS_PER_DAY = env("TOPICS_PER_DAY", 6, int)
RANKINGS_PER_DAY = env("RANKINGS_PER_DAY", 2, int)     # how many of the daily ideas are "Top 5" countdowns
FUNNY_PER_DAY = env("FUNNY_PER_DAY", 2, int)           # min funny ideas a day (1 funny short + 1 funny Top 5); 1+ is always made
MAX_VIDEOS_PER_DAY = env("MAX_VIDEOS_PER_DAY", 4, int)
AUTO_PICK_COUNT = env("AUTO_PICK_COUNT", 4, int)     # used if you don't reply
SELECT_TIMEOUT_HOURS = env("SELECT_TIMEOUT_HOURS", 3, float)
REQUIRE_APPROVAL = env("REQUIRE_APPROVAL", True, bool)
APPROVE_TIMEOUT_HOURS = env("APPROVE_TIMEOUT_HOURS", 2, float)  # auto-publish if you stay silent
TARGET_SECONDS = env("TARGET_SECONDS", 60, int)      # spoken length; videos land at ~55-65s
FACT_CHECK = env("FACT_CHECK", False, bool)          # check script facts against Wikipedia before rendering (set var FACT_CHECK=true to enable)
POLL_MINUTES = env("POLL_MINUTES", 12, float)        # how long each run stays online answering Telegram
# Peak Shorts viewing slots (local time of your audience). Each approved video takes the next free slot.
SCHEDULE_PUBLISH = env("SCHEDULE_PUBLISH", True, bool)
PUBLISH_TZ = env("PUBLISH_TZ", "America/New_York")
PUBLISH_SLOTS_WEEKDAY = env("PUBLISH_SLOTS_WEEKDAY", "12:15,15:15,19:15,21:15")
PUBLISH_SLOTS_WEEKEND = env("PUBLISH_SLOTS_WEEKEND", "10:15,14:15,19:15,21:15")
YT_DAILY_UPLOADS = env("YT_DAILY_UPLOADS", 4, int)   # ~2,100 quota units each; free quota is 10,000/day
KEEP_VIDEOS_DAYS = env("KEEP_VIDEOS_DAYS", 30, int)  # delete stored video files older than this (your PC sync keeps copies)
STATS_EVERY_HOURS = env("STATS_EVERY_HOURS", 2, float)  # refresh YouTube views/likes/comments for the dashboard
LIBRARY_DIR = env("LIBRARY_DIR", "archive")  # permanent archive of every video + every daily idea list

WIDTH, HEIGHT, FPS = 1080, 1920, 30
STATE_FILE = env("STATE_FILE", "state/state.json")
WORK_DIR = env("WORK_DIR", "work")
GITHUB_REPOSITORY = env("GITHUB_REPOSITORY")         # set automatically in Actions

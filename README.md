# Shopify Automation

Free, hands-off **product video** pipeline for [ashvara.store](https://ashvara.store), built from the
Zorbly AI Shorts bot and adapted for the store. It runs on GitHub Actions and you steer it
from Telegram.

```
Content sheet (content/plan.csv): one row = one product video, written by a daily Claude task
   ─► 10:17 AM ET Telegram: "Today's ideas" 📋  → tap numbers (or it picks the top ones itself)
   ─► voiceover + the store's own product photos + matching stock clips + captions + price end card
   ─► preview in Telegram [✅ Publish] [❌ Reject]  (auto-publishes after 2h if you stay silent)
   ─► Facebook Reels + Instagram Reels (set the PUBLISH_TO variable to add youtube / tiktok)
```

## What's different from shopify-automation
- New video format `product`: product photos come from the store's public feed
  (`STORE_URL/products.json`, no Shopify key needed; only Active products appear). The last scene shows the live
  price, and the product link is added to every caption.
- `PLAN_ONLY=true` (default): the daily list uses only content-sheet rows, never trending YouTube topics.
- Safety review also rejects medical/health claims, promised results, invented reviews and fake urgency.
- `#shorts` is kept for YouTube only.

## Minimum setup for Ashvara (about 45 minutes)
Add these under **Settings → Secrets and variables → Actions → Secrets** (steps for each are below):
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: a new bot from @BotFather (step 2)
- `GEMINI_API_KEY`: free at aistudio.google.com (step 3)
- `PIXABAY_API_KEY`: free stock clips for the in-between scenes (step 5)
- `FB_PAGE_ID`, `FB_PAGE_TOKEN`, `IG_USER_ID`: your **Ashvara** Facebook Page and Instagram (step 6)
- Optional: TikTok keys (step 7, use this repo's callback URL), YouTube keys (step 4)

Optional Variables: `STORE_URL` (default https://ashvara.store), `MAX_VIDEOS_PER_DAY` (suggest 2),
`AUTO_PICK_COUNT` (suggest 1), `PRODUCT_SHOT_EVERY` (default 2). Then enable GitHub Pages (Settings → Pages →
branch `main`, folder `/docs`) so the privacy/terms/callback pages exist for the Meta and TikTok apps.

---

## Original documentation (shopify-automation)


Free, hands-off short-video pipeline. It runs on **GitHub Actions**, which acts as a free server, and you control it through **Telegram**.

```
Every morning ─► Google Trends + YouTube Trending + top Shorts (48h)
              ─► keyword filter + AI filter remove anything controversial
              ─► Telegram: "Today's 5 ideas"  [🎬1] [🎬2] [🎬3] [🎬4] [🎬5] [⏭ Skip]
You tap 1–3 ideas (or ignore it: after 3h it makes the top 2 itself)
              ─► AI writes an original script ─► AI safety review (rewrites or drops)
              ─► voiceover + stock clips/AI images + captions ─► 1080×1920 MP4
              ─► stored in your repo's Releases ─► preview sent to Telegram [✅ Publish] [❌ Reject]
You tap Publish (or ignore it: after 2h it publishes itself)
              ─► YouTube Shorts + Facebook Reels + Instagram Reels + TikTok ─► "🚀 Posted" with links
```

If you never touch Telegram, it still runs every day on its own. Telegram just lets you steer it.

## Free tools used

| Job | Tool |
|---|---|
| Scheduler and server | GitHub Actions (cron) |
| Trends | Google Trends RSS (no key), YouTube Data API (free quota) |
| Script, safety review, titles, hashtags | Google Gemini (free), with automatic backups: Groq, Cerebras, Mistral and OpenRouter free tiers |
| Voice | edge-tts: rotates through ~14 US/UK/AU/CA/IE neural voices so each video sounds different; Google gTTS as backup |
| Visuals | Pixabay / Pexels (keys), NASA (no key, public domain, space and science scenes), Wikimedia Commons (no key, CC0/PD/CC BY only), optional Cloudflare AI images, animated gradient fallback. Source order is shuffled per video |
| Editing | FFmpeg |
| Storage | GitHub Releases on your repo |
| Publishing | Official YouTube, Facebook/Instagram Graph and TikTok Content Posting APIs |

**About TikTok and Instagram trends:** neither platform offers a free trends API, and scraping them breaks their terms. As a stand-in, the bot uses the most-viewed YouTube Shorts from the last 48 hours. The same short-form trends usually show up on TikTok and Reels at about the same time.

---

## Setup (about 1–2 hours, one time)

### 1. Create the repo
Create a **public** GitHub repo and upload this folder.

Public repos get unlimited free Actions minutes. A private repo has about 2,000 free minutes a month. If you go private, change the poll cron in `.github/workflows/autopilot.yml` from `*/20` to `0 * * * *` (hourly).

### 2. Telegram bot
1. In Telegram, message **@BotFather** and send `/newbot`. Copy the token it gives you; this is `TELEGRAM_BOT_TOKEN`.
2. Send your new bot any message.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. The number at `"chat":{"id":...}` is `TELEGRAM_CHAT_ID`.

### 3. AI (Gemini + free backups)
Go to https://aistudio.google.com, click **Get API key**, and use it as `GEMINI_API_KEY`.

If Gemini is busy, the bot automatically tries other free AI services in this order:
1. Gemini Flash, then Flash-Lite, then Gemma (same key)
2. **Groq** (optional): free key at https://console.groq.com/keys, saved as `GROQ_API_KEY`
3. **Cerebras** (optional): free key at https://cloud.cerebras.ai, saved as `CEREBRAS_API_KEY`
4. **Mistral** (optional): free "Experiment" plan key at https://console.mistral.ai/api-keys, saved as `MISTRAL_API_KEY`
5. **OpenRouter** (optional): free key at https://openrouter.ai/keys, saved as `OPENROUTER_API_KEY` (uses only `:free` models)

To see which services work, run the workflow with the command `aicheck`. The results arrive in Telegram.
6. **Cloudflare Workers AI** (optional): uses `CF_ACCOUNT_ID` / `CF_API_TOKEN` if you set them for images

### 4. YouTube (Google Cloud, free)
1. Go to https://console.cloud.google.com, create a project, and enable **YouTube Data API v3**.
2. Under **Credentials**, create an **API key**. This is `YOUTUBE_API_KEY`, used for reading trends.
3. Set up the **OAuth consent screen**: choose External and add yourself as a user. Then click **Publish app / In production**. If you skip this, the refresh token expires every 7 days. Using an unverified app with only yourself as the user is fine.
4. Under **Credentials**, create an **OAuth client ID** of type **Desktop app**. Download it as `client_secret.json`.
5. On your computer run:
   ```
   pip install google-auth-oauthlib
   python tools/get_youtube_token.py
   ```
   It prints `YT_CLIENT_ID`, `YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN`.
6. Google keeps API uploads from new projects **private** until the project passes an audit. Until then:
   - Set the Variable `YT_PRIVACY` to `private`.
   - Submit the free audit form: https://support.google.com/youtube/contact/yt_api_form
   - After approval, set `YT_PRIVACY` to `public`.

### 5. Stock footage (Pixabay and/or Pexels)
- **Pixabay:** create a free account at pixabay.com, then open https://pixabay.com/api/docs/. Your key appears in the "Parameters" section. Save it as `PIXABAY_API_KEY`.
- **Pexels (optional):** if Pexels is issuing keys again, get one at https://www.pexels.com/api/ and save it as `PEXELS_API_KEY`. When both keys are set, Pexels is tried first and Pixabay fills the gaps.

### 6. Facebook Reels + Instagram Reels (optional, one setup for both)
1. Make a **Facebook Page** for the channel. Switch Instagram to a **Creator** account and link it to that Page (Instagram → Settings → Accounts Center).
2. At https://developers.facebook.com, create an app (type **Business**).
3. In **Tools → Graph API Explorer**, pick your app and click **Get User Access Token** with `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `business_management`, `instagram_basic` and `instagram_content_publish`. Approve it for your Page and Instagram account.
4. Run `python tools/get_meta_token.py`. Paste the App ID, App secret and that token. It prints `FB_PAGE_ID`, `FB_PAGE_TOKEN` and `IG_USER_ID`. Save all three as Secrets. The Page token doesn't expire.

You don't need Meta app review, because you only post to accounts you own and you're an admin of the app. Captions are shortened per platform: Instagram gets at most 5 hashtags (its limit), and every caption keeps the footage credits and AI disclosure.

### 7. TikTok (optional)
1. At https://developers.tiktok.com, create an app and add **Login Kit** and **Content Posting API**. Add the scopes `user.info.basic` and `video.upload`. Set the Redirect URI to `https://akachwaha27.github.io/shopify-automation/callback.html`, and use the site's privacy and terms pages for the app's links.
2. Run `python tools/get_tiktok_token.py`. It prints `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` and `TIKTOK_REFRESH_TOKEN`. Re-run it about once a year.
3. **Draft mode (default, `TIKTOK_MODE=draft`):** each approved video lands in your TikTok inbox. Telegram sends you the caption. In the app, add a trending sound, paste the caption, turn on the AI-generated label and post. This works without TikTok's audit, and posting natively with a trending sound tends to get more reach.
4. **Direct mode (`TIKTOK_MODE=direct`, needs the `video.publish` scope):** posts automatically, but until TikTok audits the app, posts are private-only and your account must be private. After the audit, set `TIKTOK_PRIVACY` to `PUBLIC_TO_EVERYONE`.

### 7b. Your PC folder: videos, Excel and dashboard (optional)
The bot keeps a permanent record of every video and every daily idea list in `archive/`, and refreshes YouTube views, likes and comments every 2 hours (Variable `STATS_EVERY_HOURS`). To copy all of it to your PC:

1. Download `tools/sync_library.py` and run `python sync_library.py --setup`.
2. Enter the folder to use. It schedules a daily Windows task (plus at sign-in, and as soon as possible if the PC was off) and runs the first sync.

Your folder then holds `Videos/` (every published video named `<date> - <title>.mp4`), `Thumbnails/`, `Shorts Library.xlsx` (sheets: Videos, Daily Top 5 Ideas, Comments, Daily Totals) and `Dashboard.html`. Stored video files are kept on GitHub for 30 days (`KEEP_VIDEOS_DAYS`), so the PC must sync at least once in that window. Run `python sync_library.py` any time to sync now, or `--uninstall` to remove the task.

### How footage is chosen
Before rendering, the bot looks at the thumbnails and titles of the top Shorts on the same topic (YouTube search, max `VISUAL_SEARCHES_PER_DAY` = 6/day, 100 quota units each). An AI editor then writes a shot list: for every line, the subject that must be on screen and searches from specific to broad. Candidates from Pexels, Pixabay, NASA (photos, space scenes only) and Wikimedia must be tagged with the subject, and Gemini looks at each preview frame and keeps only clips scoring at least `VISUAL_MIN_SCORE` (6/10). Clips are never picked at random to fill time; a scene with no match reuses the last good shot (or an AI image if Cloudflare is set). The Telegram preview shows how many shots were checked. Turn off with `VISUAL_RESEARCH=false` / `VISUAL_CHECK=false`.

### Funny animal clip rankings (format letter `c`)
Off by default (`CLIPS_PER_DAY=0`); pick it any day by replying with the letter `c` (e.g. `3c`). The bot searches openly licensed clips only: Pixabay and Pexels, Wikimedia Commons (CC0, public domain or CC BY) and the Internet Archive (public domain or CC BY). Gemini watches three frames of each candidate, rates how funny it is and marks the funniest moment, and the five funniest become #5 to #1. Every clip is remixed: the video opens on a teaser of the #1 moment, each clip builds up to its funny moment, and then plays an instant slow-motion replay with a zoom and a REPLAY tag. Funny commentary is always added, because YouTube's reused-content rule doesn't monetize compilations without your own narration, even with permission. (`CLIP_ORIGINAL_AUDIO=true` turns commentary off for clips with sound, but those videos won't be monetizable.) Every clip's creator and license is credited in the description. No clips from YouTube, TikTok or other creators' channels are ever used.

### Content plan sheet (Claude-researched scripts)
`content/plan.csv` is a sheet where one row is one video. A Claude scheduled task fills it every morning at about 9 AM ET using the youtube-agent-skill workflow, and the bot sends the Ready rows (📋) in the daily Telegram list at ~10:17 AM ET, topped up with its own ideas. Picked rows are made from Claude's script word for word, and `content/status.json` tracks each row (Ready → Sent → Making → Preview → Published / Not picked / Skipped / Failed). The bot also writes `content/viral_signals.json` each morning: today's top Shorts ranked by how far each beat its own channel's median. Tools in `tools/yt_skill/` come from [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill) (MIT). Your PC copy is the "Content Plan" tab in `Shorts Library.xlsx`.

### 8. AI images (optional)
1. Create a free Cloudflare account. In the dashboard go to **AI → Workers AI** and create an API token.
2. Set `CF_ACCOUNT_ID` and `CF_API_TOKEN`.
3. Set the Variable `VISUALS` to `ai` (all AI images) or `mixed` (alternating stock clips and AI images).

### 9. Add the keys to GitHub
In the repo, go to **Settings → Secrets and variables → Actions**.

**Secrets:**
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `PIXABAY_API_KEY` (and/or `PEXELS_API_KEY`)
- `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
- `FB_PAGE_ID`, `FB_PAGE_TOKEN`, `IG_USER_ID` (`IG_ACCESS_TOKEN` only if it differs from the Page token)
- `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`
- `CF_ACCOUNT_ID`, `CF_API_TOKEN`

Any platform you leave blank is skipped.

**Variables** (all optional; defaults shown):

| Variable | Default | Meaning |
|---|---|---|
| `NICHE` | general science/tech/nature/food/travel | What kinds of topics to prefer |
| `REGION` | `US` | Trend country |
| `LANGUAGE` | `en` | Language of the video |
| `VOICES` | built-in rotation | Comma-separated edge-tts voices to rotate through |
| `VOICE` | `en-US-AndrewMultilingualNeural` | Fallback voice |
| `RANKINGS_PER_DAY` | `2` | How many daily ideas are Top 5 countdowns |
| `VISUALS` | `stock` | `stock`, `ai` or `mixed` |
| `MAX_VIDEOS_PER_DAY` | `4` (pinned in the workflow) | Hard daily cap. 4 is the max on the free 10,000-unit YouTube quota |
| `AUTO_PICK_COUNT` | `4` (pinned in the workflow) | How many topics it picks if you don't reply (always includes a funny short and a funny Top 5 when listed) |
| `SELECT_TIMEOUT_HOURS` | `3` | How long it waits for your pick |
| `REQUIRE_APPROVAL` | `true` | Send a preview before publishing |
| `APPROVE_TIMEOUT_HOURS` | `2` | Auto-publish after this long. `0` means always wait for you |
| `YT_PRIVACY` | `private` | Set to `public` after the audit passes |
| `TIKTOK_MODE` | `draft` | `draft` (finish in the TikTok app) or `direct` |
| `TIKTOK_PRIVACY` | `SELF_ONLY` | Direct mode only; change after the TikTok audit |
| `KEEP_VIDEOS_DAYS` | `30` | Days stored videos stay on GitHub before cleanup |
| `TARGET_SECONDS` | `60` (pinned in the workflow) | Spoken length. Scripts are rewritten until they fit and the voice pace is adjusted, so videos land at ~55-65s |

### 10. Test it
1. Go to **Actions → autopilot → Run workflow** and enter the command `test`. It renders one sample video and sends it to your Telegram without posting anywhere.
2. Then run it with `trends` to get today's topic list right away.
3. Change the time of the daily scan in the workflow file. The default is 11:53 UTC, which is 7:53 AM New York time during daylight saving time.

## Video formats
| | Format | What it is | YouTube category |
|---|---|---|---|
| 🏆 | ranking | Top 5 countdown, #5 to #1 with gold rank badges | Education |
| 📖 | story | Original mini story with a twist, labeled as fiction | Entertainment |
| 😂 | funny | Kind, family-friendly humor and relatable situations | Comedy |
| ❓ | quiz | 3-question trivia with on-screen Q1/✓ answers | Entertainment |
| 💡 | tips | Quick, safe everyday tips and hacks | Howto & Style |
| 🔬 | explainer | Surprising "why/how" facts | Education |

Each day's 5 ideas mix at least 4 formats. When picking, add a letter to change the format: `2s` story, `2f` funny, `2q` quiz, `2r` Top 5, `2t` tips, `2e` explainer.

### Built for the Shorts algorithm
- **Hook:** a hook line in the first second, plus on-screen hook text.
- **Payoff:** promised early and delivered at the end.
- **Pacing:** a new shot about every 3 seconds, with big word-by-word captions.
- **Loop:** the ending flows back into the opening, which encourages rewatches.
- **Comments:** each video ends with one specific question to drive comments.
- **Titles:** at most 60 characters, keyword first, honest.
- **Description:** a keyword-rich first line, 4 hashtags (`#shorts`, broad, niche, format), and 10-15 search tags.
- **Category:** the correct YouTube category is set for each format.
- **Variety:** voices, footage sources and formats rotate, so videos don't look mass-produced.

### Thumbnails and subtitles
- **Thumbnail:** every video gets a designed 1080×1920 thumbnail. It uses a vivid clean frame (the #1 reveal for countdowns) with 2–4 bold hook words in the upper third. It appears in your Telegram preview and is uploaded to YouTube.
  - YouTube only accepts custom thumbnails from **verified channels**. Verify once, for free, at https://www.youtube.com/verify.
- **Subtitles:** big captions are burned into the video. A separate closed-caption track (`.srt`) is also uploaded, which helps accessibility and search.
  - Uploading captions needs the `youtube.force-ssl` permission. Re-run `tools/get_youtube_token.py` once and replace `YT_REFRESH_TOKEN`.
- The "🚀 posted" message shows `thumbnail ✅/⚠️` and `subtitles ✅/⚠️`, with the reason if YouTube refused.

### Peak-time publishing
When you reply `publish`, the video uploads right away but goes public at the **next free peak Shorts slot** (US Eastern by default):
- **Weekdays:** 12:15 PM, 3:15 PM and 7:15 PM
- **Weekends:** 10:15 AM, 2:15 PM and 7:15 PM

That's just before the lunch, after-school/work and evening peaks. One video goes in each slot, so posts are spread out. YouTube itself flips the video to public at that time, so the bot doesn't need to be running.
- `publish now` skips scheduling and posts immediately.
- Variables to change it: `PUBLISH_TZ` (e.g. `Asia/Kolkata`), `PUBLISH_SLOTS_WEEKDAY`, `PUBLISH_SLOTS_WEEKEND`, and `SCHEDULE_PUBLISH=false` to turn scheduling off.
- While uploads are still private (before Google's API audit), the bot tells you the best slot so you can set **Schedule** in YouTube Studio yourself.

### Free-tier budget
| Service | Free limit | Per video | Allows |
|---|---|---|---|
| YouTube API | 10,000 units/day | ~2,100 (upload 1,600 + captions 400 + thumbnail 50 + comment 50) | **max 4/day** |
| Gemini (+ Groq/OpenRouter backups) | free tiers | ~5 calls | dozens/day |
| Pixabay | 100 searches/min | ~20 | dozens/day |
| Edge TTS voices | none | 1 | unlimited |
| GitHub Actions (public repo) | unlimited | ~5 min | unlimited |

- **Recommended: 3 videos/day.** One per peak slot keeps a quota buffer and stays clear of "mass-produced" signals.
- Previews, redos and tests use **no** YouTube quota.
- If 4 uploads already happened today (`YT_DAILY_UPLOADS`), approved videos wait until the quota resets at midnight Pacific.
- Stored video files are deleted after 14 days (`KEEP_VIDEOS_DAYS`).

### Tags and pinned comment
- **Tags:** each video gets a main search keyword that appears in the title and the description's first line. Tags are then built from YouTube's own search suggestions (real searches) for that keyword. They are ranked by how closely they match the title and description, and fill about 450–490 of the 500 allowed characters.
  - Tags that would be misleading are removed. That means any tag with a topic word not in the video, such as another game, a brand or a celebrity.
  - This follows what tag scorers like vidIQ reward, but their exact score isn't available to the bot. Check a few videos in the vidIQ extension and tell me what it flags.
- **Pinned comment:** an expert-style first comment (a bonus fact, a "which would you pick", or a challenge) is posted automatically. YouTube's API can't pin comments, so the "posted" message gives you a one-tap Studio link to pin it. This needs the same re-login as subtitles.

### Monetization and YouTube compliance
- **Original content:** every video has an original script, AI voice and licensed footage. Nothing is reuploaded.
- **Labels:** AI content is labeled (`containsSyntheticMedia`), every source is credited, and fiction says it is fiction.
- **Two safety layers:** a keyword blocklist plus an AI policy review that rejects anything political, violent, medical or financial, about real people, misleading, or not advertiser-friendly.
- **Your review:** this is your strongest protection against YouTube's "inauthentic / mass-produced content" rules. Watch previews and reply `change`, `redo` or `skip` when something feels generic. Description text says "approved by the channel owner" only when you actually approved the video.
- **Getting into the Partner Program:** you need to reach YouTube's Partner Program thresholds (for Shorts, currently around 1,000 subscribers plus 10M Shorts views in 90 days). Always check YouTube's current requirements.

## Telegram commands
**Daily ideas:** tap a number or type `1,3` (add a format letter, e.g. `2s`). `/now` gets fresh ideas, `/status` lists recent videos, `/help` shows all commands.

**After every preview** the bot sends a "what next?" guide. You can reply with:

| Reply | What happens |
|---|---|
| `publish` | Posts now to YouTube (plus Facebook/Instagram/TikTok if connected) |
| `change make it funnier` | Rewrites the video using your notes, e.g. `change shorter`, `change turn it into a quiz` |
| `redo` | Makes a brand-new version: new script, footage and voice |
| `voice` | Keeps the script, uses a different voice and fresh footage |
| `title Your New Title` | Changes only the title |
| `info` | Shows the full description, tags and credits |
| `skip` | Throws the video away |

**Several previews waiting:** add the video number (`publish 3`, `change 2 shorter`) or reply directly to the video. `publish all` and `skip all` also work.

The bot is online about 12 minutes of every 20 and replies within seconds while it's on. If you stay silent, the preview auto-publishes after `APPROVE_TIMEOUT_HOURS`.

## Policy safeguards built in
- **No reused content:** every video is a new script, voice and visuals. It never downloads or re-edits other creators' videos or music.
- **Controversy filter (two layers):**
  - A keyword blocklist in `autopilot/trends.py` (politics, war, crime, disasters, religion, health/finance, celebrity drama and similar). You can edit it.
  - Gemini's topic rules plus a separate strict review of every script. Anything flagged is rewritten once, then dropped.
- **Disclosure:**
  - YouTube `containsSyntheticMedia = true`
  - TikTok `is_aigc` label
  - A credits and AI disclosure block in every description
- **Credits:** Pixabay/Pexels creators are named with links, and the AI voice, AI images and any music are listed.
- **Honest metadata:** titles are reviewed for clickbait, with 3–5 relevant hashtags only.
- **Music:** off by default. Only royalty-free tracks that you drop into `assets/music/` are ever used.

Fully automatic AI channels can still be judged "mass-produced" by YouTube's monetization review. Glancing at the preview and occasionally adding your own touch (topic picks, a custom intro) helps.

## Good to know
- GitHub pauses scheduled workflows after 60 days with no repo activity. The bot's daily state commits normally prevent this; if it ever pauses, click **Enable workflow**.
- Free-tier limits (Gemini, Cloudflare, Pixabay, Pexels) change over time. 2–3 videos a day sits well inside them today.
- To change behavior, edit the prompts in `autopilot/writer.py` (script style) and `autopilot/trends.py` (topic choice).

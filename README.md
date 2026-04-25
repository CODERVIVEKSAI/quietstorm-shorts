# QuietStorm — daily auto-generated YouTube Shorts (MP4 only)

> "Work hard in silence. Let your success be your noise."

A free pipeline that generates 4 YouTube Shorts every morning by ~5 AM IST
(Quote of the Day, What If, Joke, Golden Lady ad). Each video is saved as a
downloadable MP4 artifact on GitHub Actions. **You upload to YouTube manually**
when (and if) you decide each one is good.

Plus workflows for:
- **Custom one-off videos** — give a free-form prompt, get a Short
- **Prompt-based edits** — "make it funnier", "more Indian English", etc.

Runs entirely on GitHub Actions free tier. **$0/month.**

---

## Stack (all free)

| Step | Tool | Why |
|---|---|---|
| Script | Gemini 1.5 Flash API | Generous free tier |
| Voiceover | `edge-tts` | Microsoft Edge TTS, free, with word-level SRT |
| Stock footage | Pexels API | Free, portrait videos |
| Assembly | `ffmpeg` | Burned captions, 9:16, music ducking |
| Orchestration | GitHub Actions | 2000 free min/month, matrix jobs |

---

## One-time setup

### 1. Get API keys (2 minutes)

**Gemini:** <https://aistudio.google.com/apikey> → Create API key → copy. Save as `GEMINI_API_KEY`.

**Pexels:** <https://www.pexels.com/api/> → sign up → copy your key. Save as `PEXELS_API_KEY`.

### 2. Push this code to GitHub

```bash
cd /Users/viveksaichanda/quietstorm-shorts
git init
git add .
git commit -m "Initial scaffold"
git branch -M main
gh repo create CODERVIVEKSAI/quietstorm-shorts --private --source=. --push
```

### 3. Add the 2 secrets

In the repo on GitHub: `Settings → Secrets and variables → Actions → New repository secret`. Add:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | from step 1 |
| `PEXELS_API_KEY` | from step 1 |

That's it. No YouTube setup, no OAuth, no environments.

### 4. (Optional) Background music

Drop royalty-free MP3/M4A files into `assets/music/`. The first one found is mixed at 12% under the voiceover.

Free sources:
- <https://pixabay.com/music/>
- YouTube Audio Library (<https://studio.youtube.com> → Audio library)

---

## Daily flow

1. **23:00 UTC (4:30 AM IST)** — GitHub Actions cron fires automatically.
2. **~10–15 min later** — 4 MP4s are ready as artifacts on the run.
3. **Whenever you want** — open the run, download the MP4s, watch them.
4. **Manual upload** — if you like a video, upload it to YouTube via the YouTube app or `studio.youtube.com`.

### How to download the MP4s

1. Go to `github.com/CODERVIVEKSAI/quietstorm-shorts/actions`
2. Click the latest "Daily Shorts" run
3. Scroll to **Artifacts** at the bottom
4. Click each: `video-quote-...`, `video-what_if-...`, `video-joke-...`, `video-golden_lady-...`
5. Each downloads a `.zip` containing `video.mp4`, `script.json`, `voice.mp3`, `captions.srt`
6. Unzip → double-click `video.mp4`

Artifacts are kept for **7 days** (tuned to stay under GitHub's free 500 MB storage cap).

**On mobile:** install the GitHub mobile app → open the workflow run → tap an artifact → saves to Files → open in any video player. Cron runs send a push notification.

---

## Custom videos (any topic, on demand)

`Actions → Custom Video → Run workflow`. Type a prompt:

> "A 30-second Short explaining why Hyderabadi biryani is unique"

One MP4 artifact appears in the run. Download as above.

## Editing a video with a prompt

`Actions → Edit Video → Run workflow`. Fill in:

- **format** — which type to regenerate (`quote`, `what_if`, `joke`, `golden_lady`, `custom`)
- **edit_prompt** — how to change it (e.g. *"make it 10s shorter"*, *"funnier punchline"*, *"Indian English voice cadence"*)
- **source_artifact_run** — (optional) the numeric run ID of the previous run if you want the AI to start from the previous script and edit it. Find it in the URL: `.../actions/runs/<THIS_NUMBER>`. Leave blank to regenerate from scratch with your edit as guidance.

A new MP4 artifact appears. Download as above.

---

## Changing things later

| What | Where |
|---|---|
| Channel name / handle | `data/channel.yml` → `handle`, `display_name` |
| Tagline | `data/channel.yml` → `tagline` |
| Voice per format | `data/channel.yml` → `voices:` |
| Daily schedule | `.github/workflows/scheduled.yml` → `cron:` |
| Golden Lady product rotation | `generators/golden_lady.py` → `PRODUCT_ROTATION` |
| Seed quotes | `data/seed_quotes.txt` (one per line) |
| Add a new format | Copy `generators/joke.py`, change `FORMAT` + prompt, add to `scheduled.yml` matrix |

---

## Browse available voices

```bash
python - <<'PY'
import asyncio, edge_tts
async def go():
    for v in await edge_tts.list_voices():
        if v["Locale"].startswith(("en-US", "en-IN", "en-GB")):
            print(v["ShortName"], "-", v["Gender"], "-", v["Locale"])
asyncio.run(go())
PY
```

---

## Run locally for testing (optional)

```bash
pip install -r requirements.txt
brew install ffmpeg            # or: sudo apt install ffmpeg

cp .env.example .env            # fill in GEMINI_API_KEY, PEXELS_API_KEY
export $(cat .env | xargs)

python -m generators.quote --run-id test1
# -> output/test1/quote/video.mp4
```

---

## Troubleshooting

- **"No Pexels videos found"** — the AI's `visual_query` was too specific. Edit the generator's prompt to ask for broader queries.
- **Captions out of sync** — switch to an `en-US-*` voice; word-boundary timing is most reliable there.
- **Cron never fires on schedule** — GitHub throttles `schedule:` triggers on idle repos. Push any commit once a week, or trigger manually via `workflow_dispatch`.
- **Artifact download is slow** — each artifact is ~30–80 MB. Use the GitHub mobile app on Wi-Fi.

---

## License

Private. Not for redistribution.

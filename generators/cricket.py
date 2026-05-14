"""Cricket meme-recap generator. Asks Gemini (with Google Search grounding,
via the `cricket` membership in GROUNDED_FORMATS) to surface yesterday's
most-talked-about cricket match across IPL, internationals, and major
T20 leagues, then writes a Shorts-style meme/roast script."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from generators.base import build

FORMAT = "cricket"


def _prompt() -> str:
    today = date.today()
    yesterday = today - timedelta(days=1)
    window_start = today - timedelta(days=2)
    return f"""You are writing a 50-second cricket recap as a YouTube Short in the
style of viral cricket-Twitter / cricket-meme accounts (the ones with millions
of views). Fan-culture humor.

TODAY IS {today.isoformat()}. Use Google Search to find the SINGLE most
talked-about cricket match that finished between {window_start.isoformat()}
and {today.isoformat()} — ideally yesterday ({yesterday.isoformat()}).
"Most talked-about" priority order:
  1. IPL playoff / final / qualifier (during IPL season).
  2. India international match (Test / ODI / T20I) — any opponent.
  3. ICC tournament match (World Cup, Champions Trophy, WTC).
  4. A regular IPL league-stage match if no playoff happened.
  5. A major T20 league final (PSL, BBL, CPL, SA20) if cricket is otherwise off-season.
  6. As a last resort: yesterday's biggest international fixture in any
     country (Eng/Aus/NZ/SA/Pak series).

Verify before writing:
- The teams playing, the exact date the match ended.
- Final score for both sides (in the right cricket notation — e.g. "264/2 in 19 overs").
- The result (won by X runs / wickets, super over, no-result, etc.).
- Star performances worth mentioning (only specific stats you can verify).

If you genuinely cannot find a cricket match in this window, fall back to the
biggest cricket talking point of the past week (a controversy, a player
return, a series wrap-up) — but say so explicitly in the `premise` field so
the reviewer knows.

TONE & HUMOR — read this carefully:
- Roast losing team's fans, not the players themselves (affectionate ribbing).
  Examples: "DC fans, how we feeling tonight?", "RCB fans, this one hurts different",
  "MI fans typing essays in the comments rn"
- Fast Gen-Z Indian-cricket-Twitter delivery: "broo", "actually mental", "lowkey
  insane", "the way that...", "no because", "pls", "matlab", "literally mein"
- Reference cricket fan culture: trolling Kohli for trophies / SRK for CSK / RCB
  finals trauma / MI playoff chokes / CSK uncle fanbase / India fans demanding
  changes after one loss. Use these tropes naturally — don't force them all in.
- Big claims, screenshot-able moments, bold opinions on form/captaincy.
- NO commentator boomer takes ("a brilliant innings"). Talk like the comments
  section, not Sky Sports.
- NO actual player insults — keep it about teams, fans, vibes.

Structure (~130-160 words / ~50 seconds):
- HOOK (3-5 words): savage opening claim or fan callout
- 2-3 sentences on what happened — the score, the chase, the choke, the carry job
- 1-2 sentences roasting the losing team's fan culture (or hyping the winning side)
- A wild opinion or stat-feeling claim (that you've verified)
- Punchline that screenshots well

NO fake numerical stats — every concrete number must be in your sources list.

Return JSON:
- script: 130-160 word voiceover
- title: under 60 chars, lowercase, screenshot-y
  (e.g. "dc fans, we need to talk", "csk just ended their entire season")
- premise: one-line match summary (e.g. "DC 264/2 lost to PBKS 265/4 on 2026-05-10")
- match_info: structured fields for the scoreboard graphic the video opens with:
    home_team:   string, team name as fans say it (e.g. "DC", "India", "MI")
    away_team:   string
    home_score:  string with full cricket notation when relevant
                 (e.g. "264/2 (19 ov)" or just "264/2" — keep it short)
    away_score:  string, same format
    competition: short string, max ~30 chars (e.g. "IPL 2026 Eliminator",
                 "T20I Series", "ICC Champions Trophy")
    match_date:  ISO date string (e.g. "2026-05-10")
- hashtags: 6-8 with # — include #cricket #shorts + team tags + #cricketmemes
- visual_queries: 3-6 generic cricket Pexels queries that follow the script's beats
  (e.g. ["cricket stadium night", "cricket bat batsman", "stadium crowd cheering",
   "cricket fielders", "cricket trophy"])
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--edit", default=None)
    parser.add_argument("--previous-script", default=None)
    parser.add_argument("--stage", default="all", choices=["all", "script", "video"])
    args = parser.parse_args()

    previous = json.loads(Path(args.previous_script).read_text()) if args.previous_script else None
    if args.edit or args.stage == "video":
        prompt = ""
    else:
        prompt = _prompt()

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit,
                previous_script=previous, stage=args.stage)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()

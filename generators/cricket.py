"""IPL cricket meme-recap generator. Pulls the latest IPL match from
TheSportsDB free API and writes a Shorts-style script in the cricket-Twitter
meme/roast voice — fan-culture humor, savage takes, no boomer commentary."""

import argparse
import json
from pathlib import Path
import requests
from generators.base import build

FORMAT = "cricket"

# Locked to IPL.
IPL_LEAGUE_ID = "4344"


def _latest_match() -> dict | None:
    try:
        resp = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id={IPL_LEAGUE_ID}",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        events = (data or {}).get("events") or []
        return events[0] if events else None
    except Exception as e:
        print(f"[cricket] API fetch failed: {e}")
        return None


def _prompt(match: dict | None) -> str:
    if match:
        home = match.get("strHomeTeam", "Team A")
        away = match.get("strAwayTeam", "Team B")
        h_score = match.get("intHomeScore") or match.get("strHomeScore") or "?"
        a_score = match.get("intAwayScore") or match.get("strAwayScore") or "?"
        date_str = match.get("dateEvent", "recently")
        match_block = f"""LATEST IPL MATCH ({date_str}):
{home}: {h_score}
{away}: {a_score}
"""
    else:
        match_block = (
            "NOTE: no recent IPL match data (off-season). Write a savage roast/recap "
            "about an iconic IPL rivalry, a famous choke, or the ongoing fan-war "
            "discourse. Keep it current-feeling — like a tweet that just went viral."
        )

    return f"""You are writing a 50-second IPL cricket recap as a YouTube Short
in the style of viral cricket-Twitter / cricket-meme accounts (the ones with
millions of views). Fan-culture humor.

{match_block}

TONE & HUMOR — read this carefully:
- Roast losing team's fans, not the players themselves (it's affectionate ribbing).
  Examples: "DC fans, how we feeling tonight?", "RCB fans, this one hurts different",
  "MI fans typing essays in the comments rn"
- Fast Gen-Z Indian-cricket-Twitter delivery: "broo", "actually mental", "lowkey
  insane", "the way that...", "no because", "pls", "matlab", "literally mein"
- Reference IPL fan culture: trolling Kohli for not winning trophies, CSK uncle
  fans, MI choking in playoffs, RCB always losing in finals, KKR fans only
  showing up when winning. Use these tropes naturally — don't force them all in.
- Big claims, screenshot-able moments, bold opinions on form/captaincy.
- NO commentator boomer takes ("a brilliant innings"). Talk like the comments
  section, not Sky Sports.
- NO actual player insults — keep it about teams, fans, vibes.

Structure (~130-160 words / ~50 seconds):
- HOOK (3-5 words): savage opening claim or fan callout
- 2-3 sentences on what happened — the score, the chase, the choke, the carry job
- 1-2 sentences roasting the losing team's fan culture (or hyping the winning side)
- A wild opinion or stat-feeling claim
- Punchline that screenshots well

NO fake numerical stats — only use the scores above. Vibes-based claims welcome.

Return JSON:
- script: 130-160 word voiceover
- title: under 60 chars, lowercase, screenshot-y
  (e.g. "dc fans, we need to talk", "csk just ended their entire season")
- premise: one-line match summary (e.g. "DC 264/2 lost to PBKS 265/4")
- hashtags: 6-8 with # — include #ipl #cricket #shorts + team tags + #cricketmemes
- visual_query: 2-3 word Pexels query — generic cricket imagery only
  (e.g. "cricket stadium night", "stadium floodlights crowd", "cricket ball stumps")
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--edit", default=None)
    parser.add_argument("--previous-script", default=None)
    args = parser.parse_args()

    previous = json.loads(Path(args.previous_script).read_text()) if args.previous_script else None
    if args.edit:
        prompt = ""
    else:
        match = _latest_match()
        prompt = _prompt(match)

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit, previous_script=previous)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()

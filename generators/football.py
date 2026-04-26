"""Football (soccer) match recap generator. Pulls the most recent finished
match from a rotating set of major leagues via TheSportsDB free API
(no API key required), then writes a Shorts-style commentary.

Uses Pexels generic football B-roll — not real broadcast footage (that's
copyrighted). The vibe is 'punchy commentator recap', not 'ESPN highlight reel'.
"""

import argparse
import json
from datetime import date
from pathlib import Path
import requests
from generators.base import build

FORMAT = "football"

# Rotating league IDs. Pick one per day so we cover different competitions.
# IDs from https://www.thesportsdb.com/api/v1/json/3/all_leagues.php (sport=Soccer)
LEAGUES = [
    ("4328", "English Premier League"),
    ("4335", "Spanish La Liga"),
    ("4332", "Italian Serie A"),
    ("4331", "German Bundesliga"),
    ("4334", "French Ligue 1"),
    ("4480", "UEFA Champions League"),
]


def _todays_league() -> tuple[str, str]:
    return LEAGUES[date.today().toordinal() % len(LEAGUES)]


def _latest_match(league_id: str) -> dict | None:
    """Fetch the most recent finished match for a league."""
    try:
        resp = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id={league_id}",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        events = (data or {}).get("events") or []
        if not events:
            return None
        # API returns most recent first
        return events[0]
    except Exception as e:
        print(f"[football] API fetch failed: {e}")
        return None


def _prompt(league_name: str, match: dict | None) -> str:
    if match:
        home = match.get("strHomeTeam", "Home")
        away = match.get("strAwayTeam", "Away")
        h_score = match.get("intHomeScore", "?")
        a_score = match.get("intAwayScore", "?")
        date_str = match.get("dateEvent", "recently")
        match_block = f"""LATEST MATCH ({league_name}, {date_str}):
{home} {h_score} - {a_score} {away}
"""
    else:
        match_block = f"NOTE: no recent match data available for {league_name}. Write a generic hype recap of the league's current vibe instead."

    return f"""You are writing a 50-second YouTube Shorts football match recap
in the style of viral football-Twitter / football-meme accounts. Fan-culture
humor, not commentator energy.

{match_block}

TONE & HUMOR — read this carefully:
- Roast losing team's fans, not the players themselves (affectionate ribbing).
  Examples: "Arsenal fans coping season 47", "United fans, how's that top 4
  push going", "Spurs fans, we need to check on you"
- Fast Gen-Z football-Twitter delivery: "actually mental", "broo", "the way",
  "lowkey", "no because", "pls", "this is diabolical"
- Reference football fan culture: City winning everything, Arsenal collapsing in
  spring, United's never-ending rebuild, Liverpool's "this is our year" energy,
  Real Madrid's UCL magic, Barca's financial crisis, Spurs Spursing. Use these
  tropes naturally — don't force them all in.
- Big claims, screenshot-able moments, bold takes on form/managers.
- NO commentator boomer takes ("a stunning piece of football"). Talk like the
  Twitter replies, not Match of the Day.
- NO actual player insults — keep it about teams, fans, vibes, narratives.

Structure (~130-160 words / ~50 seconds):
- HOOK (3-5 words): savage opening claim or fan callout
- 2-3 sentences on what happened — the scoreline, the upset, the dominance
- 1-2 sentences roasting the losing fans' coping (or hyping the winning narrative)
- A wild opinion ("this might end his manager era") or screenshot-able take
- Punchline that lands

NO fake stats — only use the scoreline above. Vibes-based claims welcome.

Return JSON:
- script: 130-160 word voiceover
- title: under 60 chars, lowercase okay
  (e.g. "arsenal fans, log off", "city just ended the title race")
- premise: one-line match summary (e.g. "Liverpool 4-1 over Spurs at Anfield")
- hashtags: 6-8 with # — include #football #shorts + league tag + team tags + #footballmemes
- visual_query: 2-3 word Pexels query — generic football imagery only
  (e.g. "football stadium goal", "soccer ball net", "stadium crowd lights")
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
        league_id, league_name = _todays_league()
        match = _latest_match(league_id)
        prompt = _prompt(league_name, match)

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit, previous_script=previous)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()

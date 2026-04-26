"""Cricket match recap generator. Pulls the most recent finished match from
a rotating set of cricket competitions via TheSportsDB free API and writes
a Shorts-style commentary."""

import argparse
import json
from datetime import date
from pathlib import Path
import requests
from generators.base import build

FORMAT = "cricket"

# Rotating cricket league IDs from TheSportsDB.
# Some leagues are seasonal — if no recent match, we fall back to a generic prompt.
LEAGUES = [
    ("4344", "Indian Premier League"),
    ("4458", "Big Bash League"),
    ("4516", "T20 World Cup"),
    ("4485", "ICC Cricket World Cup"),
    ("4787", "The Hundred"),
    ("4527", "Pakistan Super League"),
]


def _todays_league() -> tuple[str, str]:
    return LEAGUES[date.today().toordinal() % len(LEAGUES)]


def _latest_match(league_id: str) -> dict | None:
    try:
        resp = requests.get(
            f"https://www.thesportsdb.com/api/v1/json/3/eventspastleague.php?id={league_id}",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        events = (data or {}).get("events") or []
        return events[0] if events else None
    except Exception as e:
        print(f"[cricket] API fetch failed: {e}")
        return None


def _prompt(league_name: str, match: dict | None) -> str:
    if match:
        home = match.get("strHomeTeam", "Team A")
        away = match.get("strAwayTeam", "Team B")
        h_score = match.get("intHomeScore") or match.get("strHomeScore") or "?"
        a_score = match.get("intAwayScore") or match.get("strAwayScore") or "?"
        date_str = match.get("dateEvent", "recently")
        match_block = f"""LATEST MATCH ({league_name}, {date_str}):
{home}: {h_score}
{away}: {a_score}
"""
    else:
        match_block = (
            f"NOTE: no recent match data available for {league_name} (likely off-season). "
            "Write a generic hype recap about the league's most iconic moments or a famous "
            "rivalry instead — keep it punchy and current-feeling."
        )

    return f"""You are writing a 50-second YouTube Shorts cricket match recap.

{match_block}

TONE: Energetic cricket commentator with Gen-Z Indian-cricket-Twitter delivery.
Fast, punchy, slightly hyperbolic. Think YouTube Shorts cricket edits — quick
takes, big calls, one wild stat or moment that makes the viewer screenshot.

Structure (~75-90 words):
- HOOK (3-5 words): a wild opening line about the match or moment
- 2-3 sentences on what stood out — name the star, the moment, the turning point
- A bold opinion or "imagine if" stat
- One-line payoff that lands

NO fake stats — only use the scores above. If you don't know specific overs or
balls, keep it about momentum, the chase, the vibes.
Use cricket-flavored phrasing where natural ("masterclass", "absolute carnage",
"the chase was on", "bowled him for fun").
NO yelling. NO boomer "this is what cricket is all about" energy.

Return JSON:
- script: 75-90 word voiceover
- title: under 60 chars, lowercase okay (e.g. "rcb just broke the chase script")
- premise: one-line summary (e.g. "Mumbai Indians 195/4 chase vs CSK")
- hashtags: 6-8 with # (#cricket #shorts #ipl + team-specific)
- visual_query: 2-3 word Pexels query — generic cricket imagery only
  (e.g. "cricket stadium night", "cricket bat ball", "stadium floodlights crowd")
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

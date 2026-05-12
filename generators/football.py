"""Football (soccer) match recap generator. Asks Gemini (with Google Search
grounding, via the `football` membership in GROUNDED_FORMATS) to surface
yesterday's most talked-about football match across every major competition,
then writes a Shorts-style commentary in fan-Twitter voice."""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from generators.base import build

FORMAT = "football"


def _prompt() -> str:
    today = date.today()
    yesterday = today - timedelta(days=1)
    window_start = today - timedelta(days=2)
    return f"""You are writing a 50-second football match recap as a YouTube Short
in the style of viral football-Twitter / football-meme accounts. Fan-culture
humor, not commentator energy.

TODAY IS {today.isoformat()}. Use Google Search to find the SINGLE most
talked-about football match that finished between {window_start.isoformat()}
and {today.isoformat()} — ideally yesterday ({yesterday.isoformat()}).
"Most talked-about" priority order:
  1. UEFA Champions League / Europa League knockout match.
  2. A Premier League / La Liga / Serie A / Bundesliga / Ligue 1 match
     involving a top-6 club, especially a derby (NLD, Manchester derby,
     El Clásico, Madrid derby, Milan derby) or top-of-the-table clash.
  3. A national-team match in a major tournament (Euros, World Cup, AFCON,
     Copa América, Asian Cup) if one is currently running.
  4. A massive upset or 5+ goal blowout in any top-five league.
  5. As a last resort: yesterday's biggest fixture in any top-tier league.

Verify before writing:
- The two teams, the competition, and the exact match date.
- The final scoreline.
- The result narrative (comeback / dominant win / late winner / draw).
- Any specific player stat you mention (goals, assists, red cards).

If you genuinely cannot find a football match in this window, fall back to
the biggest football talking point of the past week (transfer saga, manager
sacking, controversy) — but say so explicitly in the `premise` field so the
reviewer knows.

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

NO fake stats — every concrete number must be in your sources list.

Return JSON:
- script: 130-160 word voiceover
- title: under 60 chars, lowercase okay
  (e.g. "arsenal fans, log off", "city just ended the title race")
- premise: one-line match summary (e.g. "Liverpool 4-1 over Spurs at Anfield, 2026-05-10")
- hashtags: 6-8 with # — include #football #shorts + league tag + team tags + #footballmemes
- visual_queries: 3-6 generic football Pexels queries that follow the script's beats
  (e.g. ["football stadium night", "soccer ball net", "stadium crowd cheering",
   "football celebration", "stadium floodlights"])
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

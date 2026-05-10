from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from giro_dashboard.fetch import fetch_html
from giro_dashboard.parse_firstcycling import (
    RaceRef,
    extract_gc_from_any,
    extract_stage_profile_image_url,
    parse_stage_standings,
    race_overview_url,
    stage_url,
)
from giro_dashboard.parse_oddschecker import find_next_stage_winner_market, parse_stage_winner_odds
from giro_dashboard.parse_reddit_predictions import attach_reddit_star_column, fetch_reddit_predictions
from giro_dashboard.render import RenderContext, render_dashboard


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race-id", type=int, default=13)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--stage", type=int, default=2)
    ap.add_argument(
        "--odds-mode",
        choices=("william-hill", "best-sportsbook"),
        default="william-hill",
        help="Oddschecker column strategy: single William Hill vs best among sportsbooks (exchanges always ignored).",
    )
    ap.add_argument("--out", type=str, default=str(Path("docs") / "index.html"))
    ap.add_argument(
        "--reddit-url",
        default="https://www.reddit.com/r/peloton/comments/1t8cnsw/predictions_thread_2026_giro_ditalia_stage_3/",
        help="r/peloton predictions thread (canonical URL). Override with env GIRO_REDDIT_PREDICTIONS_URL.",
    )
    ap.add_argument("--no-reddit", action="store_true", help="Skip Reddit predictions block.")
    args = ap.parse_args()

    race = RaceRef(race_id=args.race_id, year=args.year)
    s_url = stage_url(race=race, stage=args.stage)
    r_url = race_overview_url(race=race)

    stage_html = fetch_html(s_url)
    stage_df = parse_stage_standings(stage_html)

    # GC standings are reliably present on the stage page as one of the other tables.
    # The race overview can sometimes expose only incident/aux tables to table parsers.
    gc_candidates = [stage_html, fetch_html(r_url)]
    gc_df = extract_gc_from_any(gc_candidates)

    market = find_next_stage_winner_market()
    odds_mode_py = "william_hill" if args.odds_mode == "william-hill" else "best_sportsbook"
    odds_df = parse_stage_winner_odds(market.url, odds_mode=odds_mode_py)

    reddit_content = None
    if not args.no_reddit:
        env_r = os.environ.get("GIRO_REDDIT_PREDICTIONS_URL")
        reddit_url = (env_r if env_r is not None else args.reddit_url).strip()
        if reddit_url:
            reddit_content = fetch_reddit_predictions(reddit_url)

    odds_df, reddit_pick_warn = attach_reddit_star_column(odds_df, reddit_content)
    reddit_pick_legend = "Pick" in odds_df.columns

    profile_image_url = None
    profile_page_url = None
    profile_stage_number = None
    next_stage_n = args.stage + 1
    try:
        profile_page_url = stage_url(race=race, stage=next_stage_n)
        next_stage_html = fetch_html(profile_page_url)
        profile_image_url = extract_stage_profile_image_url(next_stage_html)
        if profile_image_url:
            profile_stage_number = next_stage_n
        else:
            profile_page_url = None
    except Exception:
        profile_image_url = None
        profile_page_url = None
        profile_stage_number = None

    if odds_mode_py == "william_hill":
        odds_note = (
            "Decimal odds from William Hill only (single sportsbook column; exchanges excluded)."
        )
    else:
        odds_note = (
            "Decimal = best price among sportsbooks only (exchange columns ignored)."
        )

    if reddit_pick_warn:
        odds_note = f"{odds_note} {reddit_pick_warn}".strip()

    ctx = RenderContext(
        title=f"Giro d'Italia {race.year} — Stage {args.stage}",
        stage_url=s_url,
        race_url=r_url,
        stage_number=args.stage,
        odds_url=market.url,
        odds_market_title=market.title,
        generated_at_utc=datetime.now(timezone.utc),
        odds_note=odds_note,
        profile_image_url=profile_image_url,
        profile_page_url=profile_page_url,
        profile_stage_number=profile_stage_number,
        reddit_pick_legend=reddit_pick_legend,
    )

    page = render_dashboard(
        ctx=ctx,
        stage_df=stage_df,
        gc_df=gc_df,
        odds_df=odds_df,
        reddit_content=reddit_content,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


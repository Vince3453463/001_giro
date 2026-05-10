from __future__ import annotations

import argparse
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
    parse_stage_standings,
    race_overview_url,
    stage_url,
)
from giro_dashboard.parse_oddschecker import find_next_stage_winner_market, parse_stage_winner_odds
from giro_dashboard.render import RenderContext, render_dashboard


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race-id", type=int, default=13)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--stage", type=int, default=2)
    ap.add_argument("--out", type=str, default=str(Path("docs") / "index.html"))
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
    odds_df = parse_stage_winner_odds(market.url)

    ctx = RenderContext(
        title=f"Giro d'Italia {race.year} — dashboard (MVP)",
        stage_url=s_url,
        race_url=r_url,
        odds_url=market.url,
        odds_market_title=market.title,
        generated_at_utc=datetime.now(timezone.utc),
    )
    page = render_dashboard(ctx=ctx, stage_df=stage_df, gc_df=gc_df, odds_df=odds_df)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


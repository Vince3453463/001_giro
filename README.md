# Giro dashboard (MVP)

Static Giro d'Italia dashboard generated daily from FirstCycling standings, Oddschecker stage-winner odds, and the r/peloton predictions thread for the **next** stage.

## What this does (MVP)

- Fetches and parses:
  - Stage results for `--stage` *N* (last completed stage you care about)
  - Overall GC (best-effort)
  - Next-stage winner odds (Oddschecker) and next-stage profile image (FirstCycling)
  - **Predictions thread** for stage *N + 1*: by default Reddit is searched for the official “Predictions Thread” post title matching `--year` and that stage number.
- Writes `docs/index.html` for GitHub Pages (publish from `/docs`).

### Reddit

- **Automatic:** with no URL flags, the builder queries `r/peloton` search and picks the newest post whose title matches *predictions*, *Giro* / *Giro d’Italia*, `--year`, and **stage *N + 1*** (same stage as profile/odds).
- **Override:** set `GIRO_REDDIT_PREDICTIONS_URL` or pass `--reddit-url https://...` if search fails or you want a specific thread.
- **Breakaway:** the thread sometimes stars **Breakaway** as a pick (any winner from the break, not one rider). Those labels are explained on the page and are **not** mapped onto the odds Pick column.

### GitHub Actions

The daily workflow runs `build_dashboard.py` with a configurable last-completed stage:

- Bump `DEFAULT_LAST_COMPLETED_STAGE` in [`.github/workflows/daily-build.yml`](.github/workflows/daily-build.yml) after each stage finishes, **or**
- Run **Actions → Daily dashboard build → Run workflow** and set the `stage` input.

## Local setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_dashboard.py --stage 3
```

Open `docs/index.html` in your browser.

## Sources

- Standings / profile: `https://firstcycling.com/`
- Odds: Oddschecker (see page footer)
- Predictions: `r/peloton` (see page)

## App link

[![Live Demo](https://img.shields.io/badge/Live-Demo-blue)](https://vince3453463.github.io/001_giro/)

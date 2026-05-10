# Giro dashboard (MVP)

Static Giro d'Italia dashboard generated daily from FirstCycling standings.

## What this does (MVP)
- Fetches and parses:
  - Stage results for a given stage
  - Overall GC standings (best-effort autodetect)
- Generates a static page at `docs/index.html` suitable for GitHub Pages (publish from `/docs`).

## Local setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/build_dashboard.py --stage 2
```

Open `docs/index.html` in your browser.

## Source
- Standings data: `https://firstcycling.com/`

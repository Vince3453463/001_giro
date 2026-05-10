from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd


@dataclass(frozen=True)
class RenderContext:
    title: str
    stage_url: str
    race_url: str
    generated_at_utc: datetime


def _df_to_html_table(df: pd.DataFrame) -> str:
    df2 = df.copy()
    df2 = df2.fillna("")
    return df2.to_html(index=False, classes="table", border=0, escape=True)


def render_dashboard(*, ctx: RenderContext, stage_df: pd.DataFrame, gc_df: pd.DataFrame) -> str:
    generated = ctx.generated_at_utc.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stage_html = _df_to_html_table(stage_df)
    gc_html = _df_to_html_table(gc_df)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{ctx.title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #0b1020;
      --panel: rgba(255,255,255,0.06);
      --text: #e8eefc;
      --muted: rgba(232,238,252,0.75);
      --border: rgba(232,238,252,0.16);
      --accent: #7aa2ff;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f6f7fb;
        --panel: rgba(0,0,0,0.04);
        --text: #0d1321;
        --muted: rgba(13,19,33,0.70);
        --border: rgba(13,19,33,0.16);
        --accent: #2f5bff;
      }}
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple Color Emoji", "Segoe UI Emoji";
      background: var(--bg);
      color: var(--text);
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 28px 16px 60px;
    }}
    header {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 24px;
      letter-spacing: 0.2px;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}
    @media (min-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr 1fr;
      }}
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 14px 10px;
      overflow: hidden;
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 16px;
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
    }}
    .table th, .table td {{
      padding: 8px 8px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
      text-align: left;
      white-space: nowrap;
    }}
    .table th {{
      position: sticky;
      top: 0;
      background: rgba(0,0,0,0.14);
    }}
    @media (prefers-color-scheme: light) {{
      .table th {{
        background: rgba(255,255,255,0.72);
      }}
    }}
    .note {{
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.35;
    }}
    .scroll {{
      overflow-x: auto;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>{ctx.title}</h1>
      <div class="meta">
        <span><strong>Updated</strong>: {generated}</span>
        <span><a href="{ctx.stage_url}" rel="noreferrer" target="_blank">Stage source</a></span>
        <span><a href="{ctx.race_url}" rel="noreferrer" target="_blank">Race source</a></span>
      </div>
    </header>

    <div class="grid">
      <section class="card">
        <h2>Stage results</h2>
        <div class="scroll">{stage_html}</div>
      </section>

      <section class="card">
        <h2>Overall GC</h2>
        <div class="scroll">{gc_html}</div>
      </section>
    </div>

    <div class="note">
      Data is copied from FirstCycling tables (MVP). Predictions and richer visuals can be layered on later.
    </div>
  </div>
</body>
</html>
"""


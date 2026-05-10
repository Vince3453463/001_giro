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
    odds_url: str | None = None
    odds_market_title: str | None = None


def _escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _df_to_html_table(df: pd.DataFrame, *, table_id: str) -> str:
    df2 = df.copy().fillna("")
    cols = [str(c) for c in df2.columns]

    thead = "<thead><tr>" + "".join(f"<th>{_escape_html(c)}</th>" for c in cols) + "</tr></thead>"

    body_rows: list[str] = []
    for i, row in enumerate(df2.itertuples(index=False, name=None)):
        tds = "".join(f"<td>{_escape_html(str(v))}</td>" for v in row)
        body_rows.append(f'<tr data-idx="{i}">{tds}</tr>')
    tbody = "<tbody>" + "".join(body_rows) + "</tbody>"

    return f'<table id="{_escape_html(table_id)}" class="table" border="0">{thead}{tbody}</table>'


def render_dashboard(
    *,
    ctx: RenderContext,
    stage_df: pd.DataFrame,
    gc_df: pd.DataFrame,
    odds_df: pd.DataFrame | None = None,
) -> str:
    generated = ctx.generated_at_utc.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stage_table_id = "stageTable"
    gc_table_id = "gcTable"
    odds_table_id = "oddsTable"
    stage_html = _df_to_html_table(stage_df, table_id=stage_table_id)
    gc_html = _df_to_html_table(gc_df, table_id=gc_table_id)
    odds_html = _df_to_html_table(odds_df, table_id=odds_table_id) if odds_df is not None else ""

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
    .controls {{
      display: flex;
      gap: 10px;
      align-items: center;
      margin: 6px 0 10px;
    }}
    .btn {{
      appearance: none;
      border: 1px solid var(--border);
      background: transparent;
      color: var(--text);
      padding: 6px 10px;
      border-radius: 10px;
      font-size: 12px;
      cursor: pointer;
    }}
    .btn:disabled {{
      opacity: 0.55;
      cursor: default;
    }}
    .count {{
      color: var(--muted);
      font-size: 12px;
      margin-left: auto;
    }}
  </style>
  <script>
    function setTableLimit(tableId, limit) {{
      const table = document.getElementById(tableId);
      if (!table) return;
      const rows = table.querySelectorAll("tbody tr[data-idx]");
      rows.forEach((tr) => {{
        const idx = parseInt(tr.getAttribute("data-idx"), 10);
        const show = (limit === null) || (idx < limit);
        tr.style.display = show ? "" : "none";
      }});
      const wrap = table.closest("[data-table-wrap]");
      if (!wrap) return;
      const expandBtn = wrap.querySelector("[data-action='expand']");
      const collapseBtn = wrap.querySelector("[data-action='collapse']");
      if (expandBtn) expandBtn.disabled = (limit === null);
      if (collapseBtn) collapseBtn.disabled = (limit !== null);
    }}
    function expandTable(tableId) {{ setTableLimit(tableId, null); }}
    function collapseTable(tableId, limit) {{ setTableLimit(tableId, limit); }}
    window.addEventListener("DOMContentLoaded", () => {{
      collapseTable("{stage_table_id}", 10);
      collapseTable("{gc_table_id}", 10);
      if (document.getElementById("{odds_table_id}")) {{
        collapseTable("{odds_table_id}", 10);
      }}
    }});
  </script>
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
        <div data-table-wrap class="scroll">
          <div class="controls">
            <button class="btn" data-action="expand" onclick="expandTable('{stage_table_id}')">Show full</button>
            <button class="btn" data-action="collapse" onclick="collapseTable('{stage_table_id}', 10)">Show top 10</button>
            <span class="count">Default: top 10</span>
          </div>
          {stage_html}
        </div>
      </section>

      <section class="card">
        <h2>Overall GC</h2>
        <div data-table-wrap class="scroll">
          <div class="controls">
            <button class="btn" data-action="expand" onclick="expandTable('{gc_table_id}')">Show full</button>
            <button class="btn" data-action="collapse" onclick="collapseTable('{gc_table_id}', 10)">Show top 10</button>
            <span class="count">Default: top 10</span>
          </div>
          {gc_html}
        </div>
      </section>
    </div>

    <section class="card" style="margin-top: 14px;">
      <h2>Predictions — next stage winner (odds)</h2>
      <div class="meta" style="margin-bottom: 8px;">
        {f'<span><a href=\"{ctx.odds_url}\" rel=\"noreferrer\" target=\"_blank\">Odds source</a></span>' if ctx.odds_url else ''}
        {f'<span>{_escape_html(ctx.odds_market_title)}</span>' if ctx.odds_market_title else ''}
      </div>
      <div data-table-wrap class="scroll">
        <div class="controls">
          <button class="btn" data-action="expand" onclick="expandTable('{odds_table_id}')">Show full</button>
          <button class="btn" data-action="collapse" onclick="collapseTable('{odds_table_id}', 10)">Show top 10</button>
          <span class="count">Default: top 10</span>
        </div>
        {odds_html if odds_df is not None else '<div class=\"note\">Odds not available.</div>'}
      </div>
    </section>

    <div class="note">
      Data is copied from FirstCycling tables (MVP). Predictions and richer visuals can be layered on later.
    </div>
  </div>
</body>
</html>
"""


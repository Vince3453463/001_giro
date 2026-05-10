from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from giro_dashboard.parse_reddit_predictions import RedditPredictionsContent, plain_text_preview


@dataclass(frozen=True)
class RenderContext:
    title: str
    stage_url: str
    race_url: str
    stage_number: int
    generated_at_utc: datetime
    odds_url: str | None = None
    odds_market_title: str | None = None
    odds_note: str | None = None
    profile_image_url: str | None = None
    profile_page_url: str | None = None
    profile_stage_number: int | None = None
    reddit_pick_legend: bool = False


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


def _reddit_markdown_to_html(md: str) -> str:
    raw = md or ""
    try:
        import markdown as md_lib

        html = md_lib.markdown(raw, extensions=["tables", "nl2br"])
    except Exception:
        return '<pre class="reddit-md reddit-fallback">' + _escape_html(raw) + "</pre>"
    html = re.sub(r'href="/', 'href="https://www.reddit.com/', html)
    html = re.sub(r"href='/", "href='https://www.reddit.com/", html)
    return html


def _render_reddit_predictions_section(content: RedditPredictionsContent | None) -> str:
    if content is None:
        return ""

    pl = _escape_html(content.permalink)
    tt = _escape_html(content.thread_title)

    if not content.success:
        err = _escape_html(content.error_note or "Information could not be found.")
        return f"""
    <section class="card reddit-thread-card" style="margin-top: 14px;">
      <h2>r/peloton — predictions thread</h2>
      <div class="meta" style="margin-bottom: 8px;"><span><a href="{pl}" rel="noreferrer" target="_blank">Open on Reddit</a></span></div>
      <p class="note">{err}</p>
    </section>
"""

    blocks: list[str] = [
        f"""
    <section class="card reddit-thread-card" style="margin-top: 14px;">
      <h2>r/peloton — predictions thread</h2>
      <div class="meta" style="margin-bottom: 8px;">
        <span><strong>{tt}</strong></span>
        <span><a href="{pl}" rel="noreferrer" target="_blank">Open on Reddit</a></span>
      </div>
"""
    ]

    if content.intro_md.strip():
        blocks.append(f'<div class="reddit-md reddit-intro">{_reddit_markdown_to_html(content.intro_md)}</div>')

    for i, sec in enumerate(content.sections):
        title_esc = _escape_html(sec.title)
        body_html = _reddit_markdown_to_html(sec.body_md)
        if sec.expandable:
            preview = _escape_html(plain_text_preview(sec.body_md))
            blocks.append(f"""
      <div class="reddit-section-block">
        <h3 class="reddit-h3">{title_esc}</h3>
        <div class="reddit-expand" id="reddit-expand-{i}">
          <p class="reddit-preview">{preview}</p>
          <div class="reddit-full reddit-md" hidden>{body_html}</div>
          <button type="button" class="btn" onclick="toggleRedditExpand(this)">Expand</button>
        </div>
      </div>
""")
        else:
            blocks.append(f"""
      <div class="reddit-section-block">
        <h3 class="reddit-h3">{title_esc}</h3>
        <div class="reddit-md">{body_html}</div>
      </div>
""")

    blocks.append("    </section>\n")
    return "".join(blocks)


def render_dashboard(
    *,
    ctx: RenderContext,
    stage_df: pd.DataFrame,
    gc_df: pd.DataFrame,
    odds_df: pd.DataFrame | None = None,
    reddit_content: RedditPredictionsContent | None = None,
) -> str:
    generated = ctx.generated_at_utc.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stage_table_id = "stageTable"
    gc_table_id = "gcTable"
    odds_table_id = "oddsTable"
    stage_html = _df_to_html_table(stage_df, table_id=stage_table_id)
    gc_html = _df_to_html_table(gc_df, table_id=gc_table_id)
    odds_html = _df_to_html_table(odds_df, table_id=odds_table_id) if odds_df is not None else ""

    profile_block = ""
    if ctx.profile_image_url and ctx.profile_stage_number is not None:
        p_src = _escape_html(ctx.profile_image_url)
        p_alt = _escape_html(f"Stage {ctx.profile_stage_number} profile (FirstCycling)")
        p_link = _escape_html(ctx.profile_page_url or "")
        profile_block = f"""
    <section class="card" style="margin-top: 14px;">
      <h2>Next stage profile — Stage {ctx.profile_stage_number}</h2>
      <div class="meta" style="margin-bottom: 8px;">
        <span><a href="{p_link}" rel="noreferrer" target="_blank">Stage page (FirstCycling)</a></span>
      </div>
      <div class="profile-img-wrap">
        <img src="{p_src}" alt="{p_alt}" loading="lazy" decoding="async" />
      </div>
    </section>
"""

    reddit_block = _render_reddit_predictions_section(reddit_content)

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
      .btn.btn-active {{
        background: rgba(40, 170, 80, 0.18);
        border-color: rgba(30, 140, 65, 0.42);
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
    .profile-img-wrap {{
      margin-top: 8px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--border);
      background: rgba(0,0,0,0.10);
    }}
    .profile-img-wrap img {{
      display: block;
      width: 100%;
      height: auto;
      vertical-align: middle;
    }}
    .reddit-thread-card .reddit-intro {{
      margin-bottom: 12px;
    }}
    .reddit-section-block {{
      margin-top: 14px;
    }}
    .reddit-h3 {{
      margin: 0 0 8px;
      font-size: 15px;
      font-weight: 600;
    }}
    .reddit-md {{
      font-size: 13px;
      line-height: 1.45;
      overflow-x: auto;
    }}
    .reddit-md table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin: 10px 0;
    }}
    .reddit-md th, .reddit-md td {{
      padding: 6px 8px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    .reddit-md pre {{
      overflow-x: auto;
      padding: 10px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: rgba(0,0,0,0.12);
    }}
    .reddit-preview {{
      color: var(--muted);
      margin: 0 0 8px;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
    }}
    .reddit-expand .btn {{
      margin-top: 4px;
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
    .btn.btn-active {{
      background: rgba(120, 220, 140, 0.26);
      border-color: rgba(90, 200, 120, 0.55);
      font-weight: 600;
    }}
    .btn.btn-active:disabled {{
      opacity: 1;
      cursor: default;
    }}
    .btn:disabled:not(.btn-active) {{
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
      if (expandBtn) {{
        expandBtn.disabled = (limit === null);
        expandBtn.classList.toggle("btn-active", limit === null);
      }}
      if (collapseBtn) {{
        collapseBtn.disabled = (limit !== null);
        collapseBtn.classList.toggle("btn-active", limit !== null);
      }}
    }}
    function expandTable(tableId) {{ setTableLimit(tableId, null); }}
    function collapseTable(tableId, limit) {{ setTableLimit(tableId, limit); }}
    function toggleRedditExpand(btn) {{
      const wrap = btn.closest(".reddit-expand");
      if (!wrap) return;
      const expanded = wrap.classList.toggle("expanded");
      const preview = wrap.querySelector(".reddit-preview");
      const full = wrap.querySelector(".reddit-full");
      if (preview) preview.hidden = expanded;
      if (full) full.hidden = !expanded;
      btn.textContent = expanded ? "Show less" : "Expand";
      btn.classList.toggle("btn-active", expanded);
    }}
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
        <span><strong>Stage results</strong>: Stage {ctx.stage_number}</span>
        <span><a href="{ctx.stage_url}" rel="noreferrer" target="_blank">Stage source (FirstCycling)</a></span>
        <span><a href="{ctx.race_url}" rel="noreferrer" target="_blank">Race source</a></span>
      </div>
    </header>

    <div class="grid">
      <section class="card">
        <h2>Stage results — Stage {ctx.stage_number}</h2>
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
        {f'<span>{_escape_html("Pick: ★ from r/peloton thread, matched to riders by surname (accent/spelling tolerant).")}</span>' if ctx.reddit_pick_legend else ''}
        {f'<span>{_escape_html(ctx.odds_note)}</span>' if ctx.odds_note else ''}
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
{profile_block}{reddit_block}
    <div class="note">
      Data is copied from FirstCycling tables (MVP). Predictions and richer visuals can be layered on later.
    </div>
  </div>
</body>
</html>
"""


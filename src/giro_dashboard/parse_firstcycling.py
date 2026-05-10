from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Iterable

import pandas as pd
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class RaceRef:
    race_id: int = 13
    year: int = 2026


def stage_url(*, race: RaceRef, stage: int) -> str:
    stage_str = f"{stage:02d}"
    return f"https://firstcycling.com/race.php?r={race.race_id}&y={race.year}&e={stage_str}"


def race_overview_url(*, race: RaceRef) -> str:
    return f"https://firstcycling.com/race.php?r={race.race_id}&y={race.year}"


def absolute_firstcycling_url(href: str) -> str:
    href = (href or "").strip()
    if href.startswith(("http://", "https://")):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://firstcycling.com" + href
    return "https://firstcycling.com/" + href.lstrip("./")


def extract_stage_profile_image_url(html: str) -> str | None:
    """
    Return absolute URL of the stage elevation/profile image on a FirstCycling stage page.
    """
    soup = BeautifulSoup(html, "html.parser")
    for im in soup.find_all("img"):
        src = (im.get("src") or "").strip()
        if not src:
            continue
        low = src.lower()
        if "/ritt_etapper/" in low.replace("\\", "/") and low.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return absolute_firstcycling_url(src)
    return None


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def clean_standings_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize FirstCycling tables:
    - Drop empty/unnamed columns (often country flags / icons).
    - Drop columns that are entirely blank.
    """
    out = _norm_cols(df)

    drop_cols: list[str] = []
    for c in out.columns:
        name = str(c).strip()
        if not name:
            drop_cols.append(c)
            continue
        if name.lower().startswith("unnamed"):
            drop_cols.append(c)
            continue

    if drop_cols:
        out = out.drop(columns=drop_cols, errors="ignore")

    # Drop columns that are all empty/whitespace after fill.
    out2 = out.copy().fillna("")
    keep_cols: list[str] = []
    for c in out2.columns:
        series = out2[c].astype(str).map(str.strip)
        if (series != "").any():
            keep_cols.append(c)
    out = out2[keep_cols]

    return out


def _score_table(cols: list[str], *, wanted_any: Iterable[str]) -> int:
    cols_l = [c.lower() for c in cols]
    score = 0
    for w in wanted_any:
        w = w.lower()
        if any(w in c for c in cols_l):
            score += 1
    return score


def _pick_best_table(dfs: list[pd.DataFrame], *, wanted_any: Iterable[str]) -> pd.DataFrame | None:
    best: tuple[int, int] | None = None  # (score, ncols)
    best_df: pd.DataFrame | None = None
    for df in dfs:
        df = _norm_cols(df)
        cols = list(df.columns)
        if len(cols) < 3:
            continue
        score = _score_table(cols, wanted_any=wanted_any)
        if score <= 0:
            continue
        key = (score, len(cols))
        if best is None or key > best:
            best = key
            best_df = df
    return best_df


def _read_html_tables(html: str) -> list[pd.DataFrame]:
    try:
        return [df for df in pd.read_html(StringIO(html))]
    except Exception:
        return []


def parse_stage_standings(html: str) -> pd.DataFrame:
    """
    Best-effort extraction of the stage results table from a FirstCycling stage page.
    """
    dfs = _read_html_tables(html)
    df = _pick_best_table(
        dfs,
        wanted_any=(
            "Rank",
            "Rnk",
            "#",
            "Rider",
            "Rider name",
            "Team",
            "Time",
            "Gap",
        ),
    )
    if df is not None:
        return clean_standings_table(df)

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No tables found on stage page.")

    # Fallback: pick the table with the most header-like cells matching expectations.
    best_score = -1
    best_rows: list[list[str]] | None = None
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        score = _score_table(headers, wanted_any=("Rank", "Rider", "Team", "Time", "Gap"))
        if score > best_score:
            best_score = score
            rows = []
            for tr in t.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)
            best_rows = rows

    if not best_rows or len(best_rows) < 2:
        raise ValueError("Could not extract stage standings table.")

    header = best_rows[0]
    data = best_rows[1:]
    return clean_standings_table(pd.DataFrame(data, columns=header))


def parse_gc_standings(html: str) -> pd.DataFrame:
    """
    Best-effort extraction of GC (overall) standings from a FirstCycling race page.
    The exact table varies; we try to auto-detect.
    """
    dfs = _read_html_tables(html)

    # GC on FirstCycling is often present as a Rider/Team/Time table without explicit "GC" headers.
    # We therefore score candidates by columns + size, while avoiding small incident tables (DNF/DNS).
    best_key: tuple[int, int, int] | None = None  # (score, rows, cols)
    best_df: pd.DataFrame | None = None
    for cand in dfs:
        cand = _norm_cols(cand)
        cols = [str(c).strip() for c in cand.columns]
        cols_l = [c.lower() for c in cols]

        if not any("rider" in c for c in cols_l):
            continue
        if not any("team" in c for c in cols_l):
            continue
        if not any("time" in c or "gap" in c for c in cols_l):
            continue

        # Prefer "overall-like" tables: many rows and no UCI points column.
        score = 0
        score += 3 if any("time" in c for c in cols_l) else 0
        score += 2 if any("gap" in c for c in cols_l) else 0
        score += 2 if not any(c == "uci" or "uci" in c for c in cols_l) else -2
        score += 1 if any(c in ("pos", "rank", "#") for c in cols_l) else 0

        rows = int(cand.shape[0])
        ncols = int(cand.shape[1])
        if rows < 20:
            # almost always not GC (typically incident lists)
            score -= 5

        key = (score, rows, ncols)
        if best_key is None or key > best_key:
            best_key = key
            best_df = cand

    if best_df is not None:
        return clean_standings_table(best_df)

    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        raise ValueError("No tables found on race overview page.")

    best_score = -1
    best_rows: list[list[str]] | None = None
    for t in tables:
        headers = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        score = _score_table(headers, wanted_any=("GC", "General", "Rank", "Rider", "Team", "Time", "Gap"))
        if score > best_score:
            best_score = score
            rows = []
            for tr in t.find_all("tr"):
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                if cells:
                    rows.append(cells)
            best_rows = rows

    if not best_rows or len(best_rows) < 2:
        raise ValueError("Could not extract GC standings table.")

    header = best_rows[0]
    data = best_rows[1:]
    return clean_standings_table(pd.DataFrame(data, columns=header))


def extract_gc_from_any(html_pages: list[str]) -> pd.DataFrame:
    """
    Try multiple candidate pages and return the first successful GC table.
    """
    last_err: Exception | None = None
    for html in html_pages:
        try:
            return parse_gc_standings(html)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    assert last_err is not None
    raise last_err


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


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
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
        return df

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
    return pd.DataFrame(data, columns=header)


def parse_gc_standings(html: str) -> pd.DataFrame:
    """
    Best-effort extraction of GC (overall) standings from a FirstCycling race page.
    The exact table varies; we try to auto-detect.
    """
    dfs = _read_html_tables(html)
    df = _pick_best_table(
        dfs,
        wanted_any=(
            "GC",
            "General",
            "Rank",
            "Rider",
            "Team",
            "Time",
            "Gap",
        ),
    )
    if df is not None:
        return df

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
    return pd.DataFrame(data, columns=header)


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


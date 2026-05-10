from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd
from bs4 import BeautifulSoup

from .fetch import fetch_html


@dataclass(frozen=True)
class OddsMarket:
    title: str
    url: str


def _abs_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if not href.startswith("/"):
        href = "/" + href
    return "https://www.oddschecker.com" + href


def find_next_stage_winner_market(giro_url: str = "https://www.oddschecker.com/cycling/giro-ditalia") -> OddsMarket:
    html = fetch_html(giro_url)
    soup = BeautifulSoup(html, "html.parser")

    # The Giro overview page includes a minitable linking to the next stage winner market.
    # We pick the first link that looks like a stage "Winner" market.
    for a in soup.select("a.minitable-header"):
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if "/winner" in href and "stage" in href:
            return OddsMarket(title=title or "Stage winner", url=_abs_url(href))

    # Fallback: any /winner link.
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if "/winner" in href and "/cycling/giro-ditalia/" in href:
            title = (a.get("title") or a.get_text(" ", strip=True) or "Stage winner").strip()
            return OddsMarket(title=title, url=_abs_url(href))

    raise ValueError("Could not find next stage winner market on Oddschecker page.")


def _bookmaker_code_to_name(soup: BeautifulSoup) -> dict[str, str]:
    """
    Oddschecker uses bookmaker codes in data attributes (e.g. WH, BF).
    We derive names from logo <img alt="..."> within elements that include data-bk.
    """
    m: dict[str, str] = {}
    for el in soup.find_all(attrs={"data-bk": True}):
        code = str(el.get("data-bk"))
        im = el.find("img")
        if not im:
            continue
        alt = (im.get("alt") or "").strip()
        if alt and len(alt) < 50:
            m.setdefault(code, alt)
    for im in soup.find_all("img"):
        alt = (im.get("alt") or "").strip()
        if not alt or len(alt) >= 50:
            continue
        parent = im.parent
        if parent and getattr(parent, "attrs", None) and parent.has_attr("data-bk"):
            code = str(parent.get("data-bk"))
            m.setdefault(code, alt)
    return m


def _parse_best_bookmakers(codes: str | None, *, bookie_map: dict[str, str]) -> str:
    if not codes:
        return ""
    parts = [p.strip() for p in str(codes).split(",") if p.strip()]
    names: list[str] = []
    for c in parts:
        names.append(bookie_map.get(c, c))
    # De-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return ", ".join(out)


def _label_row_sportsbook_slice(label_tr) -> slice | None:
    """
    Oddschecker separates Sportsbooks vs Exchanges via colspan on the label row.
    Returns a slice of column indices (into rider-row <td> lists) that belong to Sportsbooks only.
    """
    col = 0
    sports_slice: slice | None = None
    for td in label_tr.find_all(["td", "th"]):
        cs = int(td.get("colspan") or 1)
        txt = (td.get_text(strip=True) or "").strip()
        if txt == "Sportsbooks":
            sports_slice = slice(col, col + cs)
        col += cs
    return sports_slice


def _find_main_odds_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        if table.find("tr", class_="eventTableHeader") and table.find("tr", attrs={"data-bname": True}):
            return table
    return None


def _header_cell_bookmaker_code(td) -> str | None:
    if td.get("data-bk"):
        return str(td.get("data-bk")).strip() or None
    inner = td.find(attrs={"data-bk": True})
    if inner and inner.get("data-bk"):
        return str(inner.get("data-bk")).strip() or None
    return None


def _column_index_for_bookmaker(table, sb_slice: slice, bk_code: str) -> int | None:
    hdr = table.find("tr", class_="eventTableHeader")
    if not hdr:
        return None
    cells = hdr.find_all(["td", "th"])
    upper = min(sb_slice.stop, len(cells))
    for i in range(sb_slice.start, upper):
        code = _header_cell_bookmaker_code(cells[i])
        if code == bk_code:
            return i
    return None


def _fractional_to_decimal(frac: str) -> float | None:
    frac = frac.strip().replace("−", "-")
    if "/" not in frac:
        return None
    num_s, den_s = frac.split("/", 1)
    try:
        num_f = float(num_s.strip())
        den_f = float(den_s.strip())
    except ValueError:
        return None
    if den_f == 0:
        return None
    # UK fractional odds -> decimal (profit/stake representation).
    return (num_f + den_f) / den_f


def _cell_decimal_odds(td) -> float | None:
    """
    Parse decimal odds from one Oddschecker odds cell (Sportsbook or Exchange).
    """
    odig_raw = td.get("data-odig")
    if odig_raw is None:
        return None
    odig_s = str(odig_raw).strip()
    if odig_s in ("", "0", "0.0"):
        return None

    o_raw = (td.get("data-o") or "").strip()

    dec_from_frac = _fractional_to_decimal(o_raw)
    if dec_from_frac is not None:
        return dec_from_frac

    # Oddschecker sometimes omits the slash and puts the numerator only (e.g. "150" meaning 150/1).
    if o_raw and "/" not in o_raw:
        try:
            num_only = float(o_raw.replace("−", "-"))
            if num_only.is_integer() and num_only >= 1:
                return num_only + 1.0
        except ValueError:
            pass

    try:
        return float(odig_s)
    except ValueError:
        return None


def parse_stage_winner_odds(
    market_url: str,
    *,
    odds_mode: Literal["best_sportsbook", "william_hill"] = "william_hill",
) -> pd.DataFrame:
    html = fetch_html(market_url)
    soup = BeautifulSoup(html, "html.parser")

    bookie_map = _bookmaker_code_to_name(soup)

    table = _find_main_odds_table(soup)
    if table is None:
        raise ValueError("Could not find Oddschecker main odds table.")

    label_tr = table.find("tr", class_="all-odds-bookie-labels-row")
    sb_slice = _label_row_sportsbook_slice(label_tr) if label_tr else slice(1, 25)
    if sb_slice is None:
        sb_slice = slice(1, 25)

    wh_col: int | None = None
    wh_label = ""
    if odds_mode == "william_hill":
        wh_col = _column_index_for_bookmaker(table, sb_slice, "WH")
        if wh_col is None:
            raise ValueError("William Hill column not found in Oddschecker sportsbook grid.")
        wh_label = bookie_map.get("WH", "William Hill")

    rows: list[dict[str, object]] = []
    for tr in table.find_all("tr", attrs={"data-bname": True}):
        rider = (tr.get("data-bname") or "").strip()
        if not rider:
            continue

        cells = tr.find_all(["td", "th"])

        if odds_mode == "william_hill" and wh_col is not None:
            if wh_col >= len(cells):
                continue
            dec = _cell_decimal_odds(cells[wh_col])
            if dec is None:
                continue
            rows.append(
                {
                    "Rider": rider,
                    "Decimal": dec,
                    "Bookmaker": wh_label,
                    "Source": "Oddschecker",
                }
            )
            continue

        best_dec: float | None = None
        best_bks: list[str] = []

        for i in range(len(cells)):
            if not (sb_slice.start <= i < sb_slice.stop):
                continue

            td = cells[i]
            dec = _cell_decimal_odds(td)
            if dec is None:
                continue

            bk = (td.get("data-bk") or "").strip()
            if best_dec is None or dec > best_dec:
                best_dec = dec
                best_bks = [bk] if bk else []
            elif dec == best_dec and bk and bk not in best_bks:
                best_bks.append(bk)

        if best_dec is None:
            continue

        best_bks_str = _parse_best_bookmakers(",".join(best_bks), bookie_map=bookie_map)
        rows.append(
            {
                "Rider": rider,
                "Decimal": best_dec,
                "Bookmaker": best_bks_str,
                "Source": "Oddschecker",
            }
        )

    if not rows:
        raise ValueError("Could not extract odds rows from Oddschecker market page.")

    df = pd.DataFrame(rows)
    df = df.sort_values(by=["Decimal", "Rider"], ascending=[True, True], kind="mergesort")
    return df.reset_index(drop=True)


from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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


def parse_stage_winner_odds(market_url: str) -> pd.DataFrame:
    html = fetch_html(market_url)
    soup = BeautifulSoup(html, "html.parser")

    bookie_map = _bookmaker_code_to_name(soup)

    rows: list[dict[str, object]] = []
    for el in soup.find_all(attrs={"data-bname": True, "data-best-dig": True}):
        rider = (el.get("data-bname") or "").strip()
        best_dig = el.get("data-best-dig")
        if not rider or best_dig is None:
            continue
        try:
            dec = float(str(best_dig).strip())
        except ValueError:
            continue
        best_bks = _parse_best_bookmakers(el.get("data-best-bks"), bookie_map=bookie_map)
        rows.append(
            {
                "Rider": rider,
                "Decimal": dec,
                "Bookmaker": best_bks,
                "Source": "Oddschecker",
            }
        )

    if not rows:
        raise ValueError("Could not extract odds rows from Oddschecker market page.")

    df = pd.DataFrame(rows)
    df = df.sort_values(by=["Decimal", "Rider"], ascending=[True, True], kind="mergesort")
    return df.reset_index(drop=True)


from __future__ import annotations

import difflib
import html as html_lib
import json
import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

from .fetch import fetch_html


@dataclass(frozen=True)
class RedditSectionParsed:
    title: str
    body_md: str
    expandable: bool


@dataclass(frozen=True)
class RedditPredictionsContent:
    success: bool
    permalink: str
    thread_title: str
    intro_md: str
    sections: tuple[RedditSectionParsed, ...]
    error_note: str | None = None


def normalize_reddit_thread_url(url: str) -> str:
    u = (url or "").strip().split("?", maxsplit=1)[0].rstrip("/")
    if u.endswith(".json"):
        u = u[:-5].rstrip("/")
    return u


def json_api_url(thread_url: str) -> str:
    base = normalize_reddit_thread_url(thread_url)
    return base + ".json"


_H4_SECTION = re.compile(r"^####\s+(.+?)\s*$", re.MULTILINE)


def split_markdown_h4_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    text = (text or "").strip()
    if not text:
        return "", []

    matches = list(_H4_SECTION.finditer(text))
    if not matches:
        return text, []

    intro = text[: matches[0].start()].strip()
    pairs: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = (m.group(1) or "").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        pairs.append((title, body))
    return intro, pairs


def _section_should_expand(title: str, body_md: str) -> bool:
    if len(body_md.strip()) < 280:
        return False
    tl = title.lower()
    keys = ("stage breakdown", "rider discussion")
    return any(k in tl for k in keys)


def plain_text_preview(md: str, *, max_chars: int = 420) -> str:
    t = md or ""
    t = html_lib.unescape(t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    lines_out: list[str] = []
    for line in t.splitlines():
        st = line.strip()
        if st.startswith("|") and "|" in st[1:]:
            continue
        lines_out.append(line)
    t = " ".join(" ".join(lines_out).split())
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars].rsplit(" ", 1)[0].strip()
    return cut + "…"


def fetch_reddit_predictions(thread_url: str) -> RedditPredictionsContent:
    permalink = normalize_reddit_thread_url(thread_url)
    if not permalink:
        return RedditPredictionsContent(
            success=False,
            permalink="",
            thread_title="",
            intro_md="",
            sections=(),
            error_note="No Reddit thread URL was provided.",
        )

    try:
        raw = fetch_html(json_api_url(permalink))
        data = json.loads(raw)
        listing = data[0]["data"]["children"][0]["data"]
        thread_title = str(listing.get("title") or "").strip()
        selftext = html_lib.unescape(str(listing.get("selftext") or ""))
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
        return RedditPredictionsContent(
            success=False,
            permalink=permalink,
            thread_title="",
            intro_md="",
            sections=(),
            error_note=f"Reddit data could not be read ({type(exc).__name__}). The thread may be private, removed, or blocked.",
        )
    except Exception as exc:  # noqa: BLE001 - network / parsing resilience
        return RedditPredictionsContent(
            success=False,
            permalink=permalink,
            thread_title="",
            intro_md="",
            sections=(),
            error_note=f"Could not load Reddit thread ({type(exc).__name__}). Try again later.",
        )

    intro_md, pairs = split_markdown_h4_sections(selftext)
    if not pairs:
        if selftext.strip():
            pairs = [("Post", selftext.strip())]
            intro_md = ""

    sections: list[RedditSectionParsed] = []
    for title, body in pairs:
        title = title.strip() or "Section"
        body = body.strip()
        if not body:
            continue
        sections.append(
            RedditSectionParsed(
                title=title,
                body_md=body,
                expandable=_section_should_expand(title, body),
            )
        )

    if not sections and not intro_md.strip():
        return RedditPredictionsContent(
            success=False,
            permalink=permalink,
            thread_title=thread_title or "Predictions thread",
            intro_md="",
            sections=(),
            error_note="Thread loaded but no text body was found (empty selftext).",
        )

    return RedditPredictionsContent(
        success=True,
        permalink=permalink,
        thread_title=thread_title or "Predictions thread",
        intro_md=intro_md.strip(),
        sections=tuple(sections),
        error_note=None,
    )


# --- Star picks (e.g. ★★★ Magnier) matched onto Oddschecker rider names ---

_MD_BULLET = re.compile(r"^(?:\s*[*+-]\s+)+")
_STAR_UNI = re.compile(r"^(?P<stars>[★⭐🌟☆]+)\s+(?P<rest>.+)$")
_STAR_ASC = re.compile(r"^(?P<stars>\*{1,5})\s+(?P<rest>.+)$")


def _fold_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _clean_pick_token(raw: str) -> str:
    t = (raw or "").strip()
    t = re.sub(r"^[`]+|[`]+$", "", t)
    t = re.sub(r"\*+([^*]+)\*+", r"\1", t)
    t = t.strip(" .")
    return t.strip()


def _parse_star_picks_from_text(md: str) -> list[tuple[int, str]]:
    """Lines like '★★★ Magnier' or '★ De Lie, Groenewegen' → flat (n_stars, surname) pairs."""
    out: list[tuple[int, str]] = []
    for raw_line in (md or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("|"):
            continue
        line = _MD_BULLET.sub("", line)
        m = _STAR_UNI.match(line) or _STAR_ASC.match(line)
        if not m:
            continue
        stars = len(m.group("stars") or "")
        rest = (m.group("rest") or "").strip()
        if not stars or not rest:
            continue
        for part in rest.split(","):
            name = _clean_pick_token(part)
            if name:
                out.append((stars, name))
    return out


def extract_flat_star_picks(content: RedditPredictionsContent) -> list[tuple[int, str]]:
    if not content.success:
        return []
    prioritized: list[tuple[int, str]] = []
    fallback: list[tuple[int, str]] = []
    for sec in content.sections:
        picks = _parse_star_picks_from_text(sec.body_md)
        if not picks:
            continue
        if "stage breakdown" in sec.title.lower():
            prioritized.extend(picks)
        else:
            fallback.extend(picks)
    return prioritized if prioritized else fallback


def _suffix_forms(full_name: str) -> list[str]:
    parts = [p for p in re.split(r"[\s,]+", (full_name or "").strip()) if p]
    if not parts:
        return []
    max_n = min(4, len(parts))
    forms = [" ".join(parts[-n:]) for n in range(1, max_n + 1)]
    seen: set[str] = set()
    uniq_longest_first: list[str] = []
    for f in reversed(forms):
        k = _fold_name(f)
        if k in seen:
            continue
        seen.add(k)
        uniq_longest_first.append(f)
    return uniq_longest_first


def _rider_order_index(riders: list[str]) -> dict[str, int]:
    return {r: i for i, r in enumerate(riders)}


def _match_pick_to_rider(
    pick_folded: str,
    riders: list[str],
    assigned: set[str],
    fold_to_riders: dict[str, list[str]],
) -> str | None:
    cands = [r for r in fold_to_riders.get(pick_folded, []) if r not in assigned]
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        ro = _rider_order_index(riders)
        return sorted(cands, key=lambda r: ro.get(r, 999))[0]

    best_r: str | None = None
    best_sc = 0.0
    for rider in riders:
        if rider in assigned:
            continue
        for form in _suffix_forms(rider):
            sc = difflib.SequenceMatcher(None, pick_folded, _fold_name(form)).ratio()
            if sc > best_sc and sc >= 0.82:
                best_sc = sc
                best_r = rider
    return best_r


def build_rider_star_map(
    riders: list[str],
    picks: list[tuple[int, str]],
) -> tuple[dict[str, int], list[str]]:
    """
    Map full Oddschecker rider string → star count (1–5).
    Unmatched Reddit tokens returned as human-readable hints.
    """
    fold_to_riders: dict[str, list[str]] = {}
    for rider in riders:
        for form in _suffix_forms(rider):
            k = _fold_name(form)
            fold_to_riders.setdefault(k, []).append(rider)

    assigned: set[str] = set()
    stars_by_rider: dict[str, int] = {}
    unmatched: list[str] = []

    for n_star, raw_name in picks:
        pk = _fold_name(_clean_pick_token(raw_name))
        if not pk:
            continue
        rider = _match_pick_to_rider(pk, riders, assigned, fold_to_riders)
        if rider is None:
            unmatched.append(raw_name)
            continue
        assigned.add(rider)
        stars_by_rider[rider] = max(stars_by_rider.get(rider, 0), int(n_star))

    return stars_by_rider, unmatched


def attach_reddit_star_column(
    odds_df: pd.DataFrame,
    content: RedditPredictionsContent | None,
) -> tuple[pd.DataFrame, str | None]:
    """
    Insert a Pick column (★ characters) after Rider when thread star lines are present.
    Returns (dataframe, optional user-facing note for missing matches).
    """
    if content is None or odds_df is None or odds_df.empty:
        return odds_df, None
    if "Rider" not in odds_df.columns:
        return odds_df, None

    picks = extract_flat_star_picks(content)
    if not picks:
        return odds_df, None

    riders = [str(x) for x in odds_df["Rider"].tolist()]
    stars_by_rider, unmatched = build_rider_star_map(riders, picks)

    def cell_for(rider: str) -> str:
        n = stars_by_rider.get(rider, 0)
        return ("★" * n) if n else ""

    out = odds_df.copy()
    rider_idx = list(out.columns).index("Rider")
    out.insert(rider_idx + 1, "Pick", [cell_for(r) for r in riders])

    note: str | None = None
    if unmatched:
        tail = ", ".join(unmatched[:6])
        if len(unmatched) > 6:
            tail += ", …"
        note = (
            f"Thread star picks could not be matched to an odds row: {tail}. "
            "Names may differ from Oddschecker spelling."
        )
    return out, note

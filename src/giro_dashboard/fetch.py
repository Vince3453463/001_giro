from __future__ import annotations

import random
import time
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class FetchConfig:
    timeout_s: float = 30.0
    max_retries: int = 3
    backoff_s: float = 1.5
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    referer: str = "https://firstcycling.com/"


def fetch_html(url: str, *, cfg: FetchConfig | None = None) -> str:
    cfg = cfg or FetchConfig()

    def _finalize(resp: requests.Response) -> str:
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": cfg.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Referer": cfg.referer,
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )

    last_exc: Exception | None = None
    for attempt in range(cfg.max_retries):
        try:
            resp = session.get(url, timeout=cfg.timeout_s)
            if resp.status_code == 403:
                raise requests.HTTPError("403 Forbidden", response=resp)
            return _finalize(resp)
        except requests.HTTPError as exc:
            last_exc = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 403:
                raise

            # Some FirstCycling pages are behind bot protection.
            # If installed, cloudscraper can often pass the challenge.
            try:
                import cloudscraper  # type: ignore

                scraper = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "windows", "mobile": False}
                )
                scraper.headers.update(session.headers)
                resp2 = scraper.get(url, timeout=cfg.timeout_s)
                return _finalize(resp2)
            except Exception as exc2:  # noqa: BLE001
                last_exc = exc2
                if attempt == cfg.max_retries - 1:
                    break
        except Exception as exc:  # noqa: BLE001 - intentionally broad for retries
            last_exc = exc
            if attempt == cfg.max_retries - 1:
                break
            sleep_s = cfg.backoff_s * (2**attempt) + random.random() * 0.25
            time.sleep(sleep_s)

    assert last_exc is not None
    raise last_exc

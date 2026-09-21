#!/usr/bin/env python3
"""Doplní časy promítání Tady Vary z programu kina35.ifp.cz do festivalového kalendáře."""
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCE_ICS_URL = (
    "https://p135-caldav.icloud.com/published/2/"
    "MTMxMDA5NjY5NTEzMTAwOdhcg2MYG56bhwsEopP1dmHEGHwwMclRVaJXIAEpGRe1OJrqaeWjmqTBWVItYipUhKgtza_k3R5cz3TX9JQKYtQ"
)
PROGRAM_URL = "https://kino35.ifp.cz/cz/program/"
OUTPUT_PATH = "docs/tadyvary.ics"
PRAGUE = ZoneInfo("Europe/Prague")
DEFAULT_DURATION = timedelta(hours=3)
HEADERS = {
    "User-Agent": "tadyvary-kalendar-bot/1.0 (+https://github.com/wwwenca/tadyvary-kalendar)"
}

TADY_VARY_RE = re.compile(r"^Tady Vary (\d+)")
SLUG_RE = re.compile(r"/program/(event\d+-tady-vary-(\d+)-[^\"'#?]+)")
PERFBEGIN_RE = re.compile(r"perfbegin=([^\"&]+)")

session = requests.Session()
session.headers.update(HEADERS)
retry = Retry(
    total=4,
    backoff_factor=3,  # 3s, 6s, 12s, 24s
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
session.mount("https://", HTTPAdapter(max_retries=retry))


def fetch_source_calendar() -> Calendar:
    resp = session.get(SOURCE_ICS_URL, timeout=30)
    resp.raise_for_status()
    return Calendar.from_ical(resp.text)


def fetch_event_showtimes(event_url: str) -> list[datetime]:
    resp = session.get(event_url, timeout=30)
    resp.raise_for_status()
    times = []
    for raw in PERFBEGIN_RE.findall(resp.text):
        try:
            dt = datetime.strptime(unquote(raw), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        times.append(dt.replace(tzinfo=PRAGUE))
    return times


def fetch_kino35_showtimes() -> dict[int, list[datetime]]:
    resp = session.get(PROGRAM_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    showtimes: dict[int, list[datetime]] = {}
    seen_slugs = set()
    for link in soup.select('a[href*="/program/event"]'):
        m = SLUG_RE.search(link.get("href", ""))
        if not m or m.group(1) in seen_slugs:
            continue
        seen_slugs.add(m.group(1))
        number = int(m.group(2))
        event_url = f"https://kino35.ifp.cz/cz/program/{m.group(1)}"
        showtimes.setdefault(number, []).extend(fetch_event_showtimes(event_url))
        time.sleep(0.5)
    return showtimes


def is_all_day(component) -> bool:
    dtstart = component.get("DTSTART")
    return dtstart is not None and not hasattr(dtstart.dt, "hour")


def enrich(source_cal: Calendar, showtimes: dict[int, list[datetime]]) -> tuple[Calendar, int]:
    out = Calendar()
    for key, value in source_cal.items():
        out.add(key, value)

    updated = 0
    now_utc = datetime.now(timezone.utc)

    for component in source_cal.subcomponents:
        if component.name != "VEVENT":
            out.add_component(component)  # e.g. VTIMEZONE, zkopírovat beze změny
            continue

        summary = str(component.get("SUMMARY", ""))
        m = TADY_VARY_RE.match(summary)
        if m and is_all_day(component):
            number = int(m.group(1))
            event_date = component["DTSTART"].dt
            match = next(
                (t for t in showtimes.get(number, []) if t.date() == event_date),
                None,
            )
            if match:
                start_utc = match.astimezone(timezone.utc)
                end_utc = start_utc + DEFAULT_DURATION
                component["DTSTART"].dt = start_utc
                if "DTEND" in component:
                    component["DTEND"].dt = end_utc
                else:
                    component.add("DTEND", end_utc)
                component["SEQUENCE"] = int(component.get("SEQUENCE", 0)) + 1
                component["DTSTAMP"] = now_utc
                component["LAST-MODIFIED"] = now_utc
                updated += 1

        out.add_component(component)

    return out, updated


def main() -> None:
    source_cal = fetch_source_calendar()
    showtimes = fetch_kino35_showtimes()
    enriched_cal, updated = enrich(source_cal, showtimes)

    with open(OUTPUT_PATH, "wb") as f:
        f.write(enriched_cal.to_ical())

    print(f"Doplněno/aktualizováno {updated} promítání časem z kino35.ifp.cz")


if __name__ == "__main__":
    main()

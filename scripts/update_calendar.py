#!/usr/bin/env python3
"""Doplní časy promítání Tady Vary z programu kina35.ifp.cz do festivalového kalendáře."""
import re
import time as time_module
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SOURCE_ICS_URL = (
    "https://p135-caldav.icloud.com/published/2/"
    "MTMxMDA5NjY5NTEzMTAwOdhcg2MYG56bhwsEopP1dmHEGHwwMclRVaJXIAEpGRe1OJrqaeWjmqTBWVItYipUhKgtza_k3R5cz3TX9JQKYtQ"
)
# Interní AJAX endpoint kina pro rozpis konkrétního dne (viz /js/script-2.2023.js,
# funkce calendar_render/calendar_events). Vrací i dny, které ještě nejsou vidět
# v krátkém seznamu "nejbližších promítání" na homepage.
DAY_API_URL = "https://kino35.ifp.cz/sys/services/calendar.php"
DAY_API_REFERER = "https://kino35.ifp.cz/cz/"
OUTPUT_PATH = "docs/tadyvary.ics"
PRAGUE = ZoneInfo("Europe/Prague")
DEFAULT_DURATION = timedelta(hours=3)
HEADERS = {
    "User-Agent": "tadyvary-kalendar-bot/1.0 (+https://github.com/wwwenca/tadyvary-kalendar)"
}

TADY_VARY_RE = re.compile(r"^Tady Vary (\d+)")
# Číslo v názvu je nepovinné - starší záznamy na kino35 mívají jen "TADY VARY | <film>".
DAY_EVENT_NAME_RE = re.compile(r"^TADY VARY\s*(\d+)?", re.IGNORECASE)

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


def fetch_kino35_showtime(number: int, event_date: date) -> datetime | None:
    """Zeptá se denního rozpisu kina na konkrétní datum a vrátí čas "Tady Vary <number>", pokud ho kino už zveřejnilo."""
    resp = session.get(
        DAY_API_URL,
        params={"l": "cz", "d": event_date.strftime("%Y%m%d")},
        headers={"X-Requested-With": "XMLHttpRequest", "Referer": DAY_API_REFERER},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json() if resp.text.strip() else None
    if not isinstance(data, list):
        return None  # kino ještě pro tenhle den nemá zveřejněný rozpis (např. {"text":"noparams",...})

    for item in data:
        m = DAY_EVENT_NAME_RE.match(item.get("n", "").strip())
        if not m:
            continue
        digit = m.group(1)
        if digit is not None and int(digit) != number:
            continue  # jiné číslo Tady Vary - shoda jen podle data by nestačila
        hh, mm = (int(part) for part in item["t"].split(":"))
        return datetime.combine(event_date, time(hh, mm), tzinfo=PRAGUE)
    return None


def is_all_day(component) -> bool:
    dtstart = component.get("DTSTART")
    return dtstart is not None and not hasattr(dtstart.dt, "hour")


def enrich(source_cal: Calendar) -> tuple[Calendar, int]:
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
            match = fetch_kino35_showtime(number, event_date)
            time_module.sleep(0.3)

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
    enriched_cal, updated = enrich(source_cal)

    with open(OUTPUT_PATH, "wb") as f:
        f.write(enriched_cal.to_ical())

    print(f"Doplněno/aktualizováno {updated} promítání časem z kino35.ifp.cz")


if __name__ == "__main__":
    main()

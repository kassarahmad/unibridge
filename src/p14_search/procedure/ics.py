"""Minimal iCalendar (RFC 5545) writer for all-day deadline events."""

from __future__ import annotations

import datetime as dt
import hashlib


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> list[str]:
    """Lines longer than 75 octets are folded (CRLF + space), without splitting UTF-8 characters."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    out.append(cur)
    return [out[0]] + [" " + x for x in out[1:]]


def calendar(events: list[tuple[str, str, str]], stamp: dt.date) -> str:
    """events: (ISO date, summary, description). Deterministic UIDs and DTSTAMP (= reference date)."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UniBridge//Scholarship guide//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:ERDIS scholarship 2026/2027"]
    for date, summary, description in events:
        d = dt.date.fromisoformat(date)
        uid = hashlib.sha256(f"{date}|{summary}".encode()).hexdigest()[:20]
        lines += ["BEGIN:VEVENT", f"UID:{uid}@unibridge", f"DTSTAMP:{stamp:%Y%m%d}T000000Z",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{_escape(summary)}", f"DESCRIPTION:{_escape(description)}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(part for line in lines for part in _fold(line)) + "\r\n"

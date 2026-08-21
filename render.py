#!/usr/bin/env python3
"""
Render a dashboard image for a jailbroken Kindle Paperwhite 4 (1072x1448).

Output: dash.png, 8-bit grayscale, quantised to 16 levels.

Configuration comes from environment variables:
    ICS_URL     secret iCal address of your Google Calendar   (required)
    LATITUDE    default 43.6532
    LONGITUDE   default -79.3832
    TIMEZONE    default America/Toronto
    DAY_START   first hour on the rail, default 7
    DAY_END     last hour on the rail, default 22
"""

import datetime as dt
import json
import os
import sys
import urllib.request
import zoneinfo
from pathlib import Path

import recurring_ical_events
from icalendar import Calendar
from PIL import Image
from playwright.sync_api import sync_playwright

WIDTH, HEIGHT = 1072, 1448
GRAY_LEVELS = 16

TZ = zoneinfo.ZoneInfo(os.environ.get("TIMEZONE", "America/Toronto"))
LAT = float(os.environ.get("LATITUDE", "43.6532"))
LON = float(os.environ.get("LONGITUDE", "-79.3832"))
ICS_URL = os.environ.get("ICS_URL")
DAY_START = int(os.environ.get("DAY_START", "7"))
DAY_END = int(os.environ.get("DAY_END", "22"))

HERE = Path(__file__).parent

# WMO weather codes -> short human labels. Text rather than icons: it survives
# grayscale rendering and avoids emoji font surprises in headless Chromium.
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
}


def fetch_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
        "precipitation_probability_max"
        "&forecast_days=2"
        f"&timezone={TZ.key.replace('/', '%2F')}"
    )
    d = fetch_json(url)
    cur, daily = d["current"], d["daily"]
    return {
        "now": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "label": WMO.get(cur["weather_code"], "—"),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "pop": daily["precipitation_probability_max"][0] or 0,
        "tmr_high": round(daily["temperature_2m_max"][1]),
        "tmr_low": round(daily["temperature_2m_min"][1]),
        "tmr_label": WMO.get(daily["weather_code"][1], "—"),
    }


def get_events(day_start, day_end):
    """Return (timed, allday) event dicts for the window given."""
    if not ICS_URL:
        raise SystemExit("ICS_URL is not set. See README.")

    req = urllib.request.Request(ICS_URL, headers={"User-Agent": "kindle-dash"})
    with urllib.request.urlopen(req, timeout=45) as r:
        cal = Calendar.from_ical(r.read())

    timed, allday = [], []
    for e in recurring_ical_events.of(cal).between(day_start, day_end):
        start = e["DTSTART"].dt
        end = e.get("DTEND").dt if e.get("DTEND") else None
        title = str(e.get("SUMMARY", "(no title)"))
        loc = str(e.get("LOCATION", "")).strip()

        if isinstance(start, dt.datetime):
            start = start.astimezone(TZ)
            end = end.astimezone(TZ) if isinstance(end, dt.datetime) else start
            timed.append({"start": start, "end": end, "title": title, "loc": loc})
        else:
            allday.append({"title": title, "loc": loc})

    timed.sort(key=lambda x: x["start"])
    return timed, allday


def assign_columns(events):
    """Pack overlapping events into side-by-side columns."""
    for e in events:
        e["col"] = 0
        e["cols"] = 1

    group, group_end = [], None
    groups = []
    for e in events:
        if group_end is None or e["start"] < group_end:
            group.append(e)
            group_end = max(group_end or e["end"], e["end"])
        else:
            groups.append(group)
            group, group_end = [e], e["end"]
    if group:
        groups.append(group)

    for g in groups:
        cols = []  # end time of last event in each column
        for e in g:
            placed = False
            for i, end in enumerate(cols):
                if e["start"] >= end:
                    e["col"] = i
                    cols[i] = e["end"]
                    placed = True
                    break
            if not placed:
                e["col"] = len(cols)
                cols.append(e["end"])
        for e in g:
            e["cols"] = len(cols)
    return events


def fmt_time(d):
    s = d.strftime("%-I:%M")
    return s.replace(":00", "")


def build_html(weather, timed, allday, tomorrow, now):
    span_hours = DAY_END - DAY_START
    rail_h = 700  # px of rail body

    def y_for(moment):
        h = moment.hour + moment.minute / 60
        h = max(DAY_START, min(DAY_END, h))
        return (h - DAY_START) / span_hours * rail_h

    hour_marks = "".join(
        f'<div class="hour" style="top:{(h - DAY_START) / span_hours * rail_h}px">'
        f'<span>{(h - 1) % 12 + 1}</span></div>'
        for h in range(DAY_START, DAY_END + 1)
    )

    blocks = []
    for e in timed:
        top = y_for(e["start"])
        bot = y_for(e["end"])
        height = max(34, bot - top)
        width = 100 / e["cols"]
        left = e["col"] * width
        past = "past" if e["end"] < now else ""
        loc = f'<div class="loc">{esc(e["loc"])}</div>' if e["loc"] and height > 62 else ""
        blocks.append(
            f'<div class="ev {past}" style="top:{top}px;height:{height}px;'
            f'left:{left}%;width:calc({width}% - 8px)">'
            f'<div class="evtime">{fmt_time(e["start"])}</div>'
            f'<div class="evtitle">{esc(e["title"])}</div>{loc}</div>'
        )

    now_line = ""
    if DAY_START <= now.hour < DAY_END:
        now_line = f'<div class="nowline" style="top:{y_for(now)}px"></div>'

    allday_html = ""
    if allday:
        chips = "".join(f'<span class="chip">{esc(a["title"])}</span>' for a in allday[:4])
        allday_html = f'<div class="allday">{chips}</div>'

    tmr = ""
    if tomorrow:
        rows = "".join(
            f'<div class="trow"><span class="ttime">{fmt_time(e["start"])}</span>'
            f'<span class="ttitle">{esc(e["title"])}</span></div>'
            for e in tomorrow[:3]
        )
        more = len(tomorrow) - 3
        if more > 0:
            rows += f'<div class="trow"><span class="ttime"></span><span class="ttitle dim">+{more} more</span></div>'
        tmr = rows
    else:
        tmr = '<div class="trow"><span class="ttime"></span><span class="ttitle dim">Nothing scheduled</span></div>'

    template = (HERE / "template.html").read_text()
    return (
        template
        .replace("{{DATE}}", now.strftime("%A").upper())
        .replace("{{DATENUM}}", now.strftime("%-d %B").upper())
        .replace("{{TEMP}}", str(weather["now"]))
        .replace("{{FEELS}}", str(weather["feels"]))
        .replace("{{COND}}", weather["label"])
        .replace("{{HIGH}}", str(weather["high"]))
        .replace("{{LOW}}", str(weather["low"]))
        .replace("{{POP}}", str(weather["pop"]))
        .replace("{{HOURS}}", hour_marks)
        .replace("{{EVENTS}}", "".join(blocks))
        .replace("{{NOWLINE}}", now_line)
        .replace("{{ALLDAY}}", allday_html)
        .replace("{{TMRLABEL}}", weather["tmr_label"])
        .replace("{{TMRHIGH}}", str(weather["tmr_high"]))
        .replace("{{TMRLOW}}", str(weather["tmr_low"]))
        .replace("{{TMRROWS}}", tmr)
        .replace("{{UPDATED}}", now.strftime("%-I:%M %p").lower())
        .replace("{{RAILH}}", str(rail_h))
    )


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def shoot(html, out_path):
    tmp = HERE / "_render.html"
    tmp.write_text(html)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                          device_scale_factor=1)
        page.goto(tmp.resolve().as_uri())
        page.wait_for_function("document.fonts.ready.then(() => true)")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out_path))
        b.close()
    tmp.unlink(missing_ok=True)


def to_eink(path):
    """8-bit grayscale, 16 levels. Matches what eips can actually show."""
    img = Image.open(path).convert("L")
    if img.size != (WIDTH, HEIGHT):
        img = img.resize((WIDTH, HEIGHT), Image.LANCZOS)
    step = 255 / (GRAY_LEVELS - 1)
    img = img.point(lambda v: round(round(v / step) * step))
    img.save(path, "PNG", optimize=True)


def main():
    now = dt.datetime.now(TZ)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    weather = get_weather()
    timed, allday = get_events(today, today + dt.timedelta(days=1))
    tomorrow, _ = get_events(today + dt.timedelta(days=1), today + dt.timedelta(days=2))

    assign_columns(timed)
    html = build_html(weather, timed, allday, tomorrow, now)

    out = HERE / "dash.png"
    shoot(html, out)
    to_eink(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), "
          f"{len(timed)} events today, {len(tomorrow)} tomorrow")


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Render a dashboard image for a jailbroken Kindle Paperwhite 4 (1072x1448).

Output: dash.png, 8-bit grayscale, quantised to 16 levels.

Configuration comes from environment variables:
    ICS_URL     secret iCal address of your Google Calendar(s).      (required)
                Comma-separated for more than one; events from all
                are merged.
    LATITUDE    default 43.6532
    LONGITUDE   default -79.3832
    TIMEZONE    default America/Toronto
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

# How many of tomorrow's events to show: scales down as today gets busier,
# so a light today doesn't leave a blank gap above the tomorrow section.
TOMORROW_BASE_ROWS = 7
TOMORROW_MIN_ROWS = 2

TZ = zoneinfo.ZoneInfo(os.environ.get("TIMEZONE", "America/Toronto"))
LAT = float(os.environ.get("LATITUDE", "43.6532"))
LON = float(os.environ.get("LONGITUDE", "-79.3832"))
ICS_URLS = [u.strip() for u in os.environ.get("ICS_URL", "").split(",") if u.strip()]

HERE = Path(__file__).parent

# WMO weather codes -> short human labels.
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

# WMO weather codes -> icon category. A handful of hand-drawn flat shapes
# (solid fills, no gradients) rather than an icon font or emoji: those render
# unpredictably in headless Chromium and turn to mush at 16 gray levels.
WMO_ICON = {
    0: "sun", 1: "sun",
    2: "cloud-sun",
    3: "cloud",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain",
    61: "rain", 63: "rain", 65: "rain", 66: "rain", 67: "rain",
    80: "rain", 81: "rain", 82: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}

# Shared cloud silhouette: a flat-bottomed base plus three overlapping
# circles -- a small lobe lower-left, a medium lobe upper-left, and a
# dominant (tallest) lobe upper-right-of-center -- the classic rounded
# 3-lobe cloud glyph. Deep overlaps between adjacent lobes keep the
# outline smooth with no notches where they meet. Takes the silhouette's
# bounding box (x, y) to (x+w, y+h) so every cloud-derived icon can place
# it at a consistent ~1.6:1 (wider-than-tall) aspect ratio while still
# anchoring left/right/bottom edges to wherever that icon's other
# elements (rain/snow/bolt/mist/sun/moon) expect the cloud to sit.
def _cloud(x, y, w, h):
    rect_w, rect_h = w * 0.96, h * 0.45
    rect_x, rect_y = x + w * 0.04, y + h - h * 0.45
    return (
        f'<rect x="{rect_x:.1f}" y="{rect_y:.1f}" width="{rect_w:.1f}" '
        f'height="{rect_h:.1f}" rx="{rect_h / 2:.1f}"/>'
        f'<circle cx="{x + w * 0.20:.1f}" cy="{y + h * 0.62:.1f}" r="{h * 0.31:.1f}"/>'
        f'<circle cx="{x + w * 0.39:.1f}" cy="{y + h * 0.41:.1f}" r="{h * 0.38:.1f}"/>'
        f'<circle cx="{x + w * 0.70:.1f}" cy="{y + h * 0.48:.1f}" r="{h * 0.48:.1f}"/>'
    )


# Bounding boxes (x, y, w, h) for each cloud appearance below, chosen to
# keep the same left/right/bottom anchoring the old hand-tuned shapes
# had -- so rain/snow/bolt/mist/sun/moon accents stay correctly
# positioned relative to the new silhouette.
_CLOUD_TOP = _cloud(11, 5.5, 45, 27.5)

WEATHER_ICON_SVG = {
    "sun": (
        '<circle cx="32" cy="32" r="13"/>'
        '<g stroke="#000" stroke-width="5" stroke-linecap="round">'
        '<line x1="32" y1="4" x2="32" y2="14"/><line x1="32" y1="50" x2="32" y2="60"/>'
        '<line x1="4" y1="32" x2="14" y2="32"/><line x1="50" y1="32" x2="60" y2="32"/>'
        '<line x1="12" y1="12" x2="19" y2="19"/><line x1="45" y1="45" x2="52" y2="52"/>'
        '<line x1="12" y1="52" x2="19" y2="45"/><line x1="45" y1="19" x2="52" y2="12"/>'
        '</g>'
    ),
    "cloud-sun": (
        '<circle cx="24" cy="22" r="10"/>'
        '<g stroke="#000" stroke-width="4" stroke-linecap="round">'
        '<line x1="24" y1="2" x2="24" y2="8"/><line x1="4" y1="22" x2="10" y2="22"/>'
        '<line x1="10" y1="8" x2="14" y2="12"/><line x1="38" y1="8" x2="34" y2="12"/>'
        '</g>'
        # A slightly larger white "halo" copy of the cloud, drawn as one
        # filled pass so its own overlapping circles merge seamlessly, then
        # the real cloud on top at normal size. That leaves a clean margin
        # around the cloud's outer silhouette without seams where the cloud
        # overlaps itself.
        '<g fill="#fff">' + _cloud(10, 23.2, 52, 31.8) + '</g>'
        + _cloud(14, 24.1, 44, 26.9)
    ),
    "cloud": _cloud(8, 11.6, 53, 32.4),
    # Crescents: a solid circle with a second, offset circle in paper-white
    # drawn on top to bite out the crescent shape. Same halo-style technique
    # as the cloud icons -- no strokes/gradients, just two solid fills.
    "moon": (
        '<circle cx="32" cy="32" r="22"/>'
        '<circle cx="42" cy="24" r="19" fill="#fff"/>'
    ),
    "cloud-moon": (
        # Positioned further clear of the cloud than the sun is in
        # cloud-sun: a crescent has no rays poking out past its own
        # silhouette, so it needs more real separation to read at all
        # instead of being swallowed by the cloud's occlusion.
        '<circle cx="19" cy="15" r="12"/>'
        '<circle cx="25" cy="10" r="10" fill="#fff"/>'
        '<g fill="#fff">' + _cloud(10, 23.2, 52, 31.8) + '</g>'
        + _cloud(14, 24.1, 44, 26.9)
    ),
    "fog": (
        _CLOUD_TOP +
        '<g stroke="#000" stroke-width="5" stroke-linecap="round">'
        '<line x1="10" y1="42" x2="54" y2="42"/><line x1="14" y1="51" x2="50" y2="51"/>'
        '<line x1="18" y1="60" x2="46" y2="60"/></g>'
    ),
    "rain": (
        _CLOUD_TOP +
        '<g stroke="#000" stroke-width="5" stroke-linecap="round">'
        '<line x1="22" y1="38" x2="17" y2="54"/><line x1="34" y1="38" x2="29" y2="54"/>'
        '<line x1="46" y1="38" x2="41" y2="54"/></g>'
    ),
    # A standalone 6-armed snowflake rather than a cloud + dots: reads
    # unambiguously as snow at a glance instead of looking like drizzle.
    "snow": (
        '<circle cx="32" cy="32" r="4"/>'
        '<g stroke="#000" stroke-width="6" stroke-linecap="round">'
        '<line x1="32" y1="32" x2="58" y2="32"/>'
        '<line x1="32" y1="32" x2="45" y2="54.5"/>'
        '<line x1="32" y1="32" x2="19" y2="54.5"/>'
        '<line x1="32" y1="32" x2="6" y2="32"/>'
        '<line x1="32" y1="32" x2="19" y2="9.5"/>'
        '<line x1="32" y1="32" x2="45" y2="9.5"/>'
        '</g>'
        '<g stroke="#000" stroke-width="4" stroke-linecap="round">'
        '<line x1="49" y1="32" x2="55.9" y2="36"/><line x1="49" y1="32" x2="55.9" y2="28"/>'
        '<line x1="40.5" y1="46.7" x2="47.4" y2="50.7"/><line x1="40.5" y1="46.7" x2="40.5" y2="54.7"/>'
        '<line x1="23.5" y1="46.7" x2="23.5" y2="54.7"/><line x1="23.5" y1="46.7" x2="16.6" y2="50.7"/>'
        '<line x1="15" y1="32" x2="8.1" y2="36"/><line x1="15" y1="32" x2="8.1" y2="28"/>'
        '<line x1="23.5" y1="17.3" x2="16.6" y2="13.3"/><line x1="23.5" y1="17.3" x2="23.5" y2="9.3"/>'
        '<line x1="40.5" y1="17.3" x2="40.5" y2="9.3"/><line x1="40.5" y1="17.3" x2="47.4" y2="13.3"/>'
        '</g>'
    ),
    "storm": (
        _CLOUD_TOP +
        '<polygon points="34,36 22,54 30,54 26,64 46,42 36,42"/>'
    ),
}


def weather_icon(code, size=76, night=False):
    cat = WMO_ICON.get(code, "cloud")
    if night:
        cat = {"sun": "moon", "cloud-sun": "cloud-moon"}.get(cat, cat)
    body = WEATHER_ICON_SVG[cat]
    return f'<svg viewBox="0 0 64 64" width="{size}" height="{size}" fill="#000">{body}</svg>'


def is_night(d, sunrise, sunset):
    """Night by time-of-day only (ignores date), so it stays correct for
    hourly-forecast points that roll past midnight into tomorrow."""
    return d.time() < sunrise.time() or d.time() >= sunset.time()


def fetch_json(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get_weather(now):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&current=temperature_2m,apparent_temperature,weather_code"
        "&hourly=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,weather_code,"
        "precipitation_probability_max,precipitation_sum,sunrise,sunset"
        "&forecast_days=2"
        f"&timezone={TZ.key.replace('/', '%2F')}"
    )
    d = fetch_json(url)
    cur, daily, hourly = d["current"], d["daily"], d["hourly"]

    sunrise_dt = dt.datetime.fromisoformat(daily["sunrise"][0]).replace(tzinfo=TZ)
    sunset_dt = dt.datetime.fromisoformat(daily["sunset"][0]).replace(tzinfo=TZ)

    upcoming = []
    for t, temp, code in zip(hourly["time"], hourly["temperature_2m"], hourly["weather_code"]):
        when = dt.datetime.fromisoformat(t).replace(tzinfo=TZ)
        if when > now:
            upcoming.append({
                "hour": when, "temp": round(temp), "code": code,
                "is_night": is_night(when, sunrise_dt, sunset_dt),
            })
            if len(upcoming) == 7:
                break

    return {
        "now": round(cur["temperature_2m"]),
        "feels": round(cur["apparent_temperature"]),
        "code": cur["weather_code"],
        "is_night": is_night(now, sunrise_dt, sunset_dt),
        "label": WMO.get(cur["weather_code"], "—"),
        "high": round(daily["temperature_2m_max"][0]),
        "low": round(daily["temperature_2m_min"][0]),
        "pop": daily["precipitation_probability_max"][0] or 0,
        "precip_mm": daily["precipitation_sum"][0] or 0,
        "sunrise": fmt_sun(sunrise_dt),
        "sunset": fmt_sun(sunset_dt),
        "tmr_high": round(daily["temperature_2m_max"][1]),
        "tmr_low": round(daily["temperature_2m_min"][1]),
        "tmr_code": daily["weather_code"][1],
        "tmr_label": WMO.get(daily["weather_code"][1], "—"),
        "hourly": upcoming,
    }


def get_events(day_start, day_end):
    """Return (timed, allday) event dicts for the window given, merged across all configured calendars."""
    if not ICS_URLS:
        raise SystemExit("ICS_URL is not set. See README.")

    timed, allday = [], []
    for url in ICS_URLS:
        req = urllib.request.Request(url, headers={"User-Agent": "kindle-dash"})
        with urllib.request.urlopen(req, timeout=45) as r:
            cal = Calendar.from_ical(r.read())

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


def fmt_time(d):
    h = d.hour % 12 or 12
    suffix = "a" if d.hour < 12 else "p"
    return f"{h}:{d.minute:02d}{suffix}" if d.minute else f"{h}{suffix}"


def fmt_clock(d):
    return f"{d.hour % 12 or 12}:{d.minute:02d} {d.strftime('%p')}".lower()


def fmt_sun(d):
    return f"{d.hour % 12 or 12}:{d.minute:02d}{'a' if d.hour < 12 else 'p'}"


def fmt_hour_label(d):
    return f"{d.hour % 12 or 12}{'a' if d.hour < 12 else 'p'}"


def chips_html(allday):
    if not allday:
        return ""
    chips = "".join(f'<span class="chip">{esc(a["title"])}</span>' for a in allday[:4])
    return f'<div class="allday">{chips}</div>'


def build_html(weather, timed, allday, tomorrow, tomorrow_allday, now):
    rows = []
    now_marker = (
        '<div class="nowrow"><span class="bar"></span>'
        '<span class="tag">Now</span>'
        '<span class="bar"></span></div>'
    )
    if not timed:
        rows.append('<div class="aevent"><div class="body">'
                     '<div class="title dim">Nothing scheduled</div></div></div>')
    inserted = False
    for e in timed:
        if not inserted and now < e["start"]:
            rows.append(now_marker)
            inserted = True
        loc = f'<div class="loc">{esc(e["loc"])}</div>' if e["loc"] else ""
        rows.append(
            f'<div class="aevent"><span class="time">{fmt_time(e["start"])}</span>'
            f'<div class="body"><div class="title">{esc(e["title"])}</div>{loc}</div></div>'
        )
    if not inserted:
        rows.append(now_marker)

    hourly_html = "".join(
        f'<div class="hr"><span class="hlabel">{fmt_hour_label(h["hour"])}</span>'
        f'{weather_icon(h["code"], size=60, night=h["is_night"])}'
        f'<span class="htemp">{h["temp"]}&deg;</span></div>'
        for h in weather["hourly"]
    )

    if tomorrow:
        # A light "today" leaves room below the agenda, so show more of
        # tomorrow instead of leaving that space empty; a packed "today"
        # shows fewer so nothing gets crowded off the page.
        today_load = len(timed) + len(allday[:4])
        cap = max(TOMORROW_MIN_ROWS, TOMORROW_BASE_ROWS - today_load)

        rows2 = "".join(
            f'<div class="trow"><span class="ttime">{fmt_time(e["start"])}</span>'
            f'<span class="ttitle">{esc(e["title"])}</span></div>'
            for e in tomorrow[:cap]
        )
        more = len(tomorrow) - cap
        if more > 0:
            rows2 += f'<div class="trow"><span class="ttime"></span><span class="ttitle dim">+{more} more</span></div>'
        tmr = rows2
    elif not tomorrow_allday:
        tmr = '<div class="trow"><span class="ttime"></span><span class="ttitle dim">Nothing scheduled</span></div>'
    else:
        tmr = ""

    template = (HERE / "template.html").read_text()
    return (
        template
        .replace("{{DATE}}", now.strftime("%A").upper())
        .replace("{{DATENUM}}", f"{now.day} {now.strftime('%B')}".upper())
        .replace("{{TEMP}}", str(weather["now"]))
        .replace("{{FEELS}}", str(weather["feels"]))
        .replace("{{COND}}", weather["label"])
        .replace("{{WICON}}", weather_icon(weather["code"], night=weather["is_night"]))
        .replace("{{HIGH}}", str(weather["high"]))
        .replace("{{LOW}}", str(weather["low"]))
        .replace("{{POP}}", str(weather["pop"]))
        .replace("{{PRECIPMM}}", f'<b>{weather["precip_mm"]:.1f}mm</b>' if weather["precip_mm"] > 0 else "")
        .replace("{{SUNRISE}}", weather["sunrise"])
        .replace("{{SUNSET}}", weather["sunset"])
        .replace("{{HOURLY}}", hourly_html)
        .replace("{{EVENTS}}", "".join(rows))
        .replace("{{ALLDAY}}", chips_html(allday))
        .replace("{{TMRICON}}", weather_icon(weather["tmr_code"], size=54))
        .replace("{{TMRLABEL}}", weather["tmr_label"])
        .replace("{{TMRHIGH}}", str(weather["tmr_high"]))
        .replace("{{TMRLOW}}", str(weather["tmr_low"]))
        .replace("{{TMRALLDAY}}", chips_html(tomorrow_allday))
        .replace("{{TMRROWS}}", tmr)
        .replace("{{UPDATED}}", fmt_clock(now))
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

    weather = get_weather(now)
    timed, allday = get_events(today, today + dt.timedelta(days=1))
    tomorrow, tomorrow_allday = get_events(today + dt.timedelta(days=1), today + dt.timedelta(days=2))

    html = build_html(weather, timed, allday, tomorrow, tomorrow_allday, now)

    out = HERE / "dash.png"
    shoot(html, out)
    to_eink(out)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB), "
          f"{len(timed)} events today, {len(tomorrow)} tomorrow")


if __name__ == "__main__":
    sys.exit(main())

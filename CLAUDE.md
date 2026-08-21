# CLAUDE.md

Project context for Claude Code. Read this before changing anything.

## What this is

A weather and calendar dashboard for a **jailbroken Kindle Paperwhite 4 (10th gen)**.
GitHub Actions renders a PNG every 30 minutes and pushes it to a private branch.
The Kindle wakes on an RTC alarm, fetches the PNG, draws it with `eips`, and
suspends to RAM.

There is no server. There is no always-on machine. Don't introduce one.

## Hard constraints

These are properties of the hardware, not preferences. Changing them breaks the device.

- **Output is exactly 1072 × 1448 px.** Paperwhite 4 native resolution, portrait.
- **8-bit grayscale PNG, quantised to 16 levels.** No colour anywhere — not in
  CSS, not in the palette, not "it'll just render as gray." Anything relying on
  hue to convey meaning is invisible on this device.
- **No gradients, no soft shadows, no low-contrast text.** 16 levels bands badly.
  Solid fills and clear tonal separation only.
- **The Kindle runs busybox `sh`, not bash.** In `kindle/dash.sh`: no arrays, no
  `[[ ]]`, no `set -o pipefail`, no `${var,,}`, no process substitution. POSIX only.
- **The image must survive suspend.** E-ink holds the last drawn frame while the
  SoC is off. That's the entire battery strategy — never add anything that keeps
  the CPU or wifi awake between refreshes.

## Architecture

```
render.py          fetch data → build HTML → screenshot → quantise → dash.png
template.html      the layout; placeholders are {{TOKENS}}, replaced by string
                   substitution in build_html(). No template engine.
.github/workflows/ 30-min cron; force-pushes a single-commit `output` branch
kindle/dash.sh     wake → wifi up → curl → eips → wifi down → suspend
```

Data sources:
- **Weather:** Open-Meteo. No API key. Celsius. Free tier, no auth.
- **Calendar:** the calendar's secret `.ics` URL, parsed with `icalendar` +
  `recurring_ical_events`. Deliberately not Google OAuth — no token refresh,
  no consent screen, no client secret.

The `output` branch is force-pushed as a fresh single commit every run. This is
intentional: without it the repo grows by one PNG every 30 minutes forever. Don't "fix"
it into a normal commit history.

## Design intent

Read this before restyling anything.

The screen has no colour and is read from across a room, so **contrast comes from
font width**, not hue. One variable family (Archivo) set very wide for numerals
and very narrow for text. That substitution is the point of the design; don't
replace it with a second typeface or a colour accent.

**The agenda is a condensed chronological list, not a time-proportional rail.**
An earlier version positioned events by real start/end time on a fixed-height
rail; that was replaced deliberately because it burned most of the page on
whatever hours had no events. The list only spends space on what's actually
scheduled. The "NOW · h:mm" divider row (`.nowrow`) carries over the old
rail's one rule — it's still the heaviest thing on the page, inserted at the
correct chronological position between the list's past and future events.
Keep everything else quiet so that bar stays the loudest thing on the page.

**Weather icons are hand-drawn flat SVG, not emoji or an icon font.**
`render.py`'s `WEATHER_ICON_SVG` holds ~7 solid-black shapes (sun, cloud,
cloud-sun, fog, rain, snow, storm) built from basic primitives (circle, rect,
line, polygon) on a 64×64 viewBox, keyed off WMO code via `WMO_ICON`. Emoji
and icon fonts were rejected for rendering unpredictably in headless Chromium
and turning to mush at 16 gray levels; solid vector shapes with no gradients
sidestep both problems. Keep new icons in that same style — flat fills, thick
strokes, no fine detail that will disappear at ~40px on an e-ink screen.

If asked to make it "nicer," resist adding elements. The failure mode for this
page is clutter, not plainness.

## Running it

```sh
source .venv/bin/activate
ICS_URL="file://$PWD/test.ics" python render.py && open dash.png
```

`ICS_URL` accepts `file://`, so layout work needs no network and no secrets.
Iterate here — never debug design on the device.

To check against real calendar/weather data, `source local.sh && python
render.py` — `local.sh` (gitignored, copy from `local.sh.example`) holds real
secret calendar URLs and coordinates, same pattern as `kindle/config.sh`.

## Security rules

- **Never commit `test.ics` or any calendar data.** It's the full calendar in
  plaintext. It's in `.gitignore`; keep it there.
- **Never commit `local.sh`.** It holds real secret calendar URLs.
- **Never commit `kindle/config.sh`.** It holds the GitHub token.
- **Never echo or log `GITHUB_TOKEN`**, including in debug output.
- **Never suggest `curl -k` / `--insecure` in `dash.sh`.** That request carries
  the token. If TLS fails on the Kindle, the fix is an updated CA bundle.
- The Kindle's token must stay fine-grained, single-repo, Contents: Read.

## Confirmed on physical device

Verified on a real jailbroken PW4 (2026-08-21):

- `rtc1` is the writable wakealarm on this unit; the `rtc0`/`rtc1` probe in
  `find_rtc()` works as designed.
- The Kindle's CA bundle trusts GitHub's certificate chain — `curl` against
  `api.github.com` works with no TLS changes needed.
- `eips -c` before drawing is not the cause of any on-screen glitching; safe
  to keep for ghost-clearing.
- **`eips -g` must be called with `-f` (full update).** Its default is a
  partial update, which on this hardware attempts an unsupported "swipe"
  transition and prints debug text (`update_to_display: ...` / `swipe
  feature is not supported...`) directly onto the screen instead of a
  legible log. `draw()` in `dash.sh` always passes `-f` now — don't drop it.
- lipc frontlight property is **`flIntensity`** (camelCase, matching
  `wirelessEnable`/`cmState`/`battLevel`), not `fl_intensity` — the latter
  fails silently with `lipcErrNoSuchProperty`.
- **`eips`'s plain text mode (`eips [row] [col] string`) can't reach the
  lower screen on this hardware.** Row 55 works; row 150 already overflows
  its internal pixel math (`eips: pixel_in_range> ... pixel not in range`
  in dash.log, with nonsensical coordinates). `-x`/`-y` don't help either —
  for text (unlike image draws) they still go through the same row-based
  math, not real pixels. The true max valid row is somewhere in (55, 150),
  unconfirmed beyond that. Text drawn this way is also missing glyphs (no
  `%`, confirmed via `eips: paint_char> character "%" not available`) — it's
  a limited debug font, not a real character set. Keep any eips-drawn
  overlay text near the top of the screen and free of unusual punctuation.

## Known unknowns

Still open:

- How long wifi takes to reconnect after resume (30s is a guess). Testing
  so far has been over USB, which appears to interfere with both wifi
  association and suspend-to-RAM (`echo mem > /sys/power/state` may no-op
  while USB is attached) — retest unplugged, on battery, before trusting
  timing measured here.

When debugging the device, the log is at `/mnt/us/dash.log`. Ask for it rather
than guessing. It's self-trimming (`trim_log()`, capped at `LOG_MAX_LINES`)
so it's safe to leave running unattended for weeks without filling storage.

## Style

- Python: standard library where reasonable; the four deps in `requirements.txt`
  are the budget. Don't add a template engine, a web framework, or a config lib.
- Comments explain *why*, especially where something looks odd (the force-push,
  the PNG magic-byte check, the width-axis typography).
- Keep `dash.sh` readable over clever. It gets debugged over SSH on a 6" screen.

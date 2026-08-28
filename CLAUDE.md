# CLAUDE.md

Project context for Claude Code. Read this before changing anything.

## What this is

A weather and calendar dashboard for a **jailbroken Kindle Paperwhite 4 (10th gen)**.
GitHub Actions renders a PNG every 20 minutes (during the Kindle's active
hours only — see the `dashboard.yml` cron) and pushes it to a private branch.
The Kindle wakes on an RTC alarm every 20 minutes and fetches whatever's
newest — the two cadences don't need to match, the Kindle just always grabs
the latest available render. It draws the PNG with `eips` and
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
.github/workflows/ 20-min cron; force-pushes a single-commit `output` branch
kindle/dash.sh     wake → wifi up → curl → eips → wifi down → suspend
```

Data sources:
- **Weather:** Open-Meteo. No API key. Celsius. Free tier, no auth.
- **Calendar:** the calendar's secret `.ics` URL, parsed with `icalendar` +
  `recurring_ical_events`. Deliberately not Google OAuth — no token refresh,
  no consent screen, no client secret.

The `output` branch is force-pushed as a fresh single commit every run. This is
intentional: without it the repo grows by one PNG every 20 minutes forever. Don't "fix"
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
  transition. `draw()` in `dash.sh` always passes `-f` now — don't drop it.
- **The `update_to_display: ... / swipe feature is not supported in this
  platfom G2` message is harmless log noise, not a screen-corruption
  symptom.** Confirmed 2026-08-26: it prints to `dash.log` (via the script's
  `exec >>$LOG 2>&1`) on *every* `eips` display call each refresh — the
  `eips -c` clear, the `-f` image draw, and the un-flagged battery-text
  draw alike, `update_mode=FULL` included — yet the physical screen renders
  clean with nothing visible. Originally thought `-f` fully suppressed this
  message (it doesn't, on this hardware); what `-f` actually fixes is the
  partial-update image draw specifically. Safe to ignore in the log.
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

Verified 2026-08-24:

- **Power button already works as a manual refresh — no code needed.**
  `sleep_until_next()` doesn't check *why* `echo mem > /sys/power/state`
  returned, so any wake source (RTC alarm or power button) drops straight
  into the top of the loop and runs a normal fetch/draw cycle, then re-arms
  the RTC from that new "now." Confirmed on-device: pressing power while
  asleep redrew the screen with the latest image in ~20s. One known gap —
  during `QUIET_START`–`QUIET_END` this still no-ops like a scheduled wake
  would, so a power-button press overnight currently does nothing — decided
  to leave it that way rather than add a bypass (2026-08-24).

Verified 2026-08-24 (unattended, on battery, ~3 days):

- **Battery life: ~16 days per charge.** 97% Friday afternoon → 80% Monday
  4:49pm (~74h) is ~5.5%/day. Projected to the 8% auto-cutoff in `dash.sh`,
  that's roughly 16 days on `REFRESH_SECONDS=1800` (30 min) with
  `QUIET_START=23`/`QUIET_END=7`. Treat as a ballpark, not exact — li-ion
  discharge isn't perfectly linear, especially near empty. This closes out
  the "is 30s a safe wifi-reconnect guess" question by proxy: whatever the
  real number is, the battery budget has enough headroom that it doesn't
  matter for now.
- **Decided (2026-08-25): dropped `REFRESH_SECONDS` to 1200 (20 min)** to
  match the Actions cadence, using the headroom above. Active-hour fetch
  cycles go from 32/day to 48/day (1.5x); if drain scales with fetch
  cycles rather than bare RTC wakes, that's a projected ~11 days/charge
  instead of ~16 — still comfortable. `config.sh.example` reflects this;
  the real on-device `config.sh` isn't tracked in git and needs the same
  edit made by hand over SSH.
- **Low battery no longer exits awake.** The `<8%` branch in `dash.sh` used
  to `exit 0` right after drawing the warning, leaving the SoC idling at
  full power (framework already stopped, nothing else suspends it) for
  whatever's left of the charge. It now suspends (`echo mem >
  /sys/power/state`) with no RTC alarm armed, so the tail end of the
  battery is spent suspended instead of awake — only a physical wake
  (power button, USB) brings it back, at which point the script has
  already exited and needs restarting by hand, same as the on-screen
  message says.

## Known unknowns

Still open:

- **eips text-mode row ceiling isn't fully mapped.** Row 55 works, row 150
  overflows (`pixel_in_range` errors) — the real max is somewhere in
  between, unconfirmed beyond that. Only matters if something new ever
  needs to draw eips overlay text lower on the screen than the battery
  readout does today.

When debugging the device, the log is at `/mnt/us/dash.log`. Ask for it rather
than guessing. It's self-trimming (`trim_log()`, capped at `LOG_MAX_LINES`)
so it's safe to leave running unattended for weeks without filling storage.

## Known limitation: evening staleness from GitHub's cron queue

Confirmed 2026-08-24 by pulling Actions run history across 4 days and
converting to local time: there's a highly consistent ~100-120min dead zone
in the `schedule:` trigger's firing every single day, starting at almost
exactly 19:56-20:00 America/Toronto (= UTC midnight) and not resuming until
roughly 21:42-21:56. Same window, four days running — this is UTC-midnight
congestion on GitHub's shared free-tier cron queue (a huge fraction of
"daily" jobs across the whole platform fire at `0 0 * * *`), not something
specific to this repo, and not something the "5-25-45 past the hour" minute
offsets in `dashboard.yml` can dodge.

Effect: the queue usually manages one render right as it recovers
(~9:45-9:56pm) and then, some days, one more before the active-hours cutoff
— so the last image the Kindle displays before quiet hours often really is
from just before 10pm rather than closer to 11pm. This is the same
"schedule: is best-effort" limitation already known from earlier research,
just now pinned to a specific cause and time window rather than generic
flakiness.

**Optional future path: bypass the `schedule:` queue entirely.**
`workflow_dispatch` (manual/API-triggered runs) is not subject to this same
congestion — it fires immediately regardless of what the cron queue is
doing. So a small always-on device on the home network, hitting
`POST /repos/{owner}/{repo}/actions/workflows/{id}/dispatches` on its own
schedule instead of relying on GitHub's `schedule:` trigger, would sidestep
this specific problem entirely. Candidates discussed:

- **Repurpose an old Raspberry Pi 3** the household already owns as the
  trigger (not the renderer — keep the actual `render.py`/Playwright work
  on GitHub Actions' Ubuntu runners; a Pi 3's 1GB RAM makes a poor
  headless-Chromium host). Effectively free (idle power draw only, no
  recurring cost), and the dispatch token stays on hardware under direct
  control rather than a third party's. Tradeoffs: this contradicts the
  "no always-on machine" framing above, so treat that as superseded if this
  path is taken; needs a systemd service (not just a login cron) so it
  survives reboots/power blips, and SD cards wear under 24/7 writes (boot
  off USB storage if available, or keep writes minimal). Scope the
  dispatch token to `Actions: write` only on this repo — a different,
  narrower token than the Kindle's `Contents: Read` one.
- **n8n Cloud** as a hosted alternative — no hardware to maintain, and its
  credential storage is genuinely encrypted (AES-256 at rest on Cloud,
  FIPS-140-2), unlike cron-job.org's plaintext storage which ruled that
  option out earlier. But n8n dropped its free tier; Cloud pricing starts
  at $24/mo (2,500 executions), which is hard to justify against a Pi
  that's already sitting in a drawer.

## Deferred feature: Ecobee room sensors

Wanted (2026-08-25): per-room temperature from Ecobee remote sensors on the
dashboard — not the main thermostat reading, not humidity, specifically the
individual sensor breakdown.

Blocked on the same problem as above, for a different reason. Ecobee's API
has no local/LAN endpoint and no static key — it's an OAuth-style PIN
pairing flow whose refresh token *rotates on every call*, so it needs
somewhere to persist state between runs. That's real state this
architecture doesn't have anywhere for today (same "no token refresh, no
consent screen, no client secret" principle the calendar integration was
built around — see Architecture above).

Decided to wait for the Raspberry Pi rather than solve it via GitHub-secret
auto-rewriting (the other option considered: a second fine-grained PAT
scoped to `Secrets: write`, with a workflow step that persists Ecobee's
rotated token after every run — works, but is a new moving part that
silently breaks re-pairing if a run ever fails mid-chain). Once the Pi
exists for the cron-trigger project, it's the natural place for the Ecobee
token too — lives on local disk like any normal app credential, and the Pi
can just push current sensor readings into the repo for `render.py` to
pick up, no secret-rewriting involved.

Not started — revisit once the Pi is real.

Not started — revisit if the evening staleness becomes worth solving
outright rather than living with.

## Style

- Python: standard library where reasonable; the four deps in `requirements.txt`
  are the budget. Don't add a template engine, a web framework, or a config lib.
- Comments explain *why*, especially where something looks odd (the force-push,
  the PNG magic-byte check, the width-axis typography).
- Keep `dash.sh` readable over clever. It gets debugged over SSH on a 6" screen.

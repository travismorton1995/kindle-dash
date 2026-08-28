# CLAUDE.md

Project context for Claude Code. Read this before changing anything.

## What this is

A weather and calendar dashboard for a **jailbroken Kindle Paperwhite 4 (10th gen)**.
GitHub Actions renders a PNG every 20 minutes (during the Kindle's active
hours only — see `dashboard.yml`'s "Check active hours" step) and pushes it
to a separate private repo, `kindle-dash-output`. The Kindle wakes on an RTC
alarm every 20 minutes and fetches whatever's newest from there — the two
cadences don't need to match, the Kindle just always grabs the latest
available render. It draws the PNG with `eips` and suspends to RAM.

`kindle-dash` (this repo, the code) is public — unlimited GitHub Actions
minutes. The rendered image is a different story (real calendar event
titles, effectively a live schedule), so it lives somewhere that isn't
world-readable instead.

A small Raspberry Pi 3 on the home network (see "The Pi trigger" below)
triggers renders via `workflow_dispatch`, standing in for GitHub's own
`schedule:` trigger — which stopped firing entirely and isn't coming back
on its own. This is the one exception to "no always-on machine": it's
narrowly scoped to triggering, not rendering (that's still GitHub Actions),
and it exists because the alternative genuinely doesn't work — see below
before assuming it's a design choice that could just be reverted.

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
.github/workflows/ dashboard.yml; force-pushes dash.png to kindle-dash-output
pi/                trigger.sh + systemd units; runs on the Pi, calls
                   workflow_dispatch since schedule: doesn't work anymore
kindle/dash.sh     wake → wifi up → curl → eips → wifi down → suspend
```

Data sources:
- **Weather:** Open-Meteo. No API key. Celsius. Free tier, no auth.
- **Calendar:** the calendar's secret `.ics` URL, parsed with `icalendar` +
  `recurring_ical_events`. Deliberately not Google OAuth — no token refresh,
  no consent screen, no client secret.

`dash.png` is force-pushed as a fresh single commit to `kindle-dash-output`'s
`main` branch every run. This is intentional: without it that repo would
grow by one PNG every 20 minutes forever. Don't "fix" it into a normal
commit history.

`dashboard.yml` still declares a `schedule:` trigger, even though it's
confirmed dead (see "The Pi trigger" below) — left in deliberately as free
redundancy in case GitHub ever quietly fixes it, not an oversight. Don't
remove it, and don't rely on it either.

### The Pi trigger

An old Raspberry Pi 3, reflashed fresh 2026-08-27, runs `kindle-dash-trigger`
— a systemd timer (`pi/kindle-dash-trigger.timer` + `.service`) that fires
`pi/trigger.sh` every 20 minutes. That script POSTs to
`/repos/travismorton1995/kindle-dash/actions/workflows/dashboard.yml/dispatches`
using a fine-grained PAT scoped to `Actions: write` on this repo only,
stored in `pi/config.sh` on the Pi (chmod 600, not in git, same pattern as
`kindle/config.sh`). No active-hours logic duplicated there — `dashboard.yml`'s
own "Check active hours" step already gates whether a dispatch renders
anything, so the Pi just fires every 20 minutes regardless and lets most
outside-hours ones no-op.

Confirmed on the Pi (2026-08-27):
- **Reboot survival is empirically tested, not assumed.** Rebooted the Pi
  mid-session and watched the timer auto-start with zero manual
  intervention, fire on schedule (`OnBootSec=1min`), and successfully
  dispatch — network was ready in time.
- **`OnBootSec` fires unconditionally, not based on how overdue the last
  run was.** The last fire before that reboot was only ~3 minutes earlier
  (well under the 20-min interval) and it still fired again ~1 min after
  boot. This is the behavior you want: any power event, regardless of
  outage length, gets a fresh trigger within about a minute of coming back
  online, rather than waiting up to 20 minutes for the next slot.
  `Persistent=true` on the timer isn't actually doing meaningful work given
  this — that setting matters for `OnCalendar=`-style absolute-time timers,
  not the boot-relative ones used here. Harmless to leave, just don't
  assume it's load-bearing.
- **`sudo` is *not* passwordless on the Pi** — corrected 2026-08-28. Several
  early setup commands succeeded without a prompt, which was wrongly taken
  as a permanent `NOPASSWD` grant; that was actually a cached sudo
  timestamp riding a session authenticated locally, and it expired.
  `sudo -n true` now fails outright. Any `sudo` action from an agent
  session needs the device owner to run it himself, interactively — check
  with `sudo -n true` first rather than assuming.
- SSH access details, including the DHCP-IP-drift caveat and the
  Windows/Git-Bash mDNS resolution gotcha, are in this project's memory
  (`kindle_dash_pi_access`), not repeated here since they're
  environment-specific rather than project-architecture.

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
- **Never commit `kindle/config.sh` or `pi/config.sh`.** They hold GitHub tokens.
- **Never echo or log `GITHUB_TOKEN`**, including in debug output.
- **Never suggest `curl -k` / `--insecure` in `dash.sh`.** That request carries
  the token. If TLS fails on the Kindle, the fix is an updated CA bundle.
- Every token in this project is fine-grained, single-repo, and scoped to
  the one permission it actually needs — the Kindle's `Contents: Read` on
  `kindle-dash-output`, the Actions publish step's `Contents: Read and
  write` on `kindle-dash-output`, and the Pi trigger's `Actions: write` on
  `kindle-dash`. Don't consolidate these into one broader token for
  convenience — that's the whole point of keeping them separate.
- **GitHub's automatic secret-masking silently fails on short, simple
  values.** Confirmed: `LATITUDE`/`LONGITUDE` printed in plaintext in every
  run log despite being registered Secrets, while `ICS_URL` (long, high
  entropy) masked correctly in the same log. `dashboard.yml` works around
  this with an explicit `echo "::add-mask::${{ secrets.X }}"` step — keep
  that step, and use the same pattern for any future short secret.

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
- **`dash.sh` restarted spontaneously once, cause unconfirmed (2026-08-28,
  ~6:35am).** Preceded by a burst of very rapid wake events (7 wakes in
  under 5.5 minutes, some just seconds apart — not the RTC alarm's normal
  20-min cadence) with no physical handling of the device at the time
  (confirmed). Candidates: a kernel-level suspend/resume hang triggering a
  watchdog reset, or a race in `sleep_until_next()`'s clear-then-set
  wakealarm sequence causing a spurious immediate wake that cascaded.
  Neither confirmed — `dmesg` wasn't checked in time to catch kernel-level
  detail. One-off so far; watch for recurrence rather than chasing it blind
  from a single instance.
- **The first `eips` draw after that restart didn't reach the screen,
  despite `dash.log` showing a clean success.** Screen still showed the
  previous night's image at 7:25am, 9 minutes after `dash.log` logged
  `07:16:18 refreshed` with no errors — the eips output for that cycle is
  byte-for-byte identical to later, confirmed-working ones, so the log
  gives no visible signal anything was wrong. Recovered on its own by the
  next cycle and has drawn correctly every cycle since. Plausible
  mechanism, unconfirmed: `stop lab126_gui` runs once at startup, before
  the main loop begins — if that teardown hasn't fully released its hold
  on the display by the time the *first* loop iteration's `eips -g` fires,
  that draw could get silently swallowed by a not-yet-ready display
  driver, while every subsequent cycle (teardown long since settled) works
  fine. Not fixed — self-heals within one ~20-min cycle, only after an
  already-rare restart, so not worth a defensive change until/unless this
  recurs and the pattern holds.

When debugging the device, the log is at `/mnt/us/dash.log`. Ask for it rather
than guessing. It's self-trimming (`trim_log()`, capped at `LOG_MAX_LINES`)
so it's safe to leave running unattended for weeks without filling storage.

## schedule: is dead — history, for context

`dashboard.yml`'s `schedule:` trigger no longer fires, at all, ever. This
isn't a live problem anymore (the Pi trigger replaced it — see
Architecture above), but the history explains why that solution exists and
why re-enabling `schedule:` isn't a reasonable thing to try again later.

**Phase 1 (2026-08-24): partial, patterned unreliability.** Pulling Actions
run history across 4 days and converting to local time showed a highly
consistent ~100-120min dead zone in `schedule:` firing every single day,
starting almost exactly 19:56-20:00 America/Toronto (= UTC midnight) and
not resuming until roughly 21:42-21:56. This is UTC-midnight congestion on
GitHub's shared free-tier cron queue (a huge fraction of "daily" jobs
platform-wide fire at `0 0 * * *`) — not specific to this repo, and not
something minute-offset tweaks in the cron expression could dodge.

**Phase 2 (2026-08-27): total failure after going public.** Within hours of
`kindle-dash`'s visibility changing to public, `schedule:` stopped firing
entirely — zero runs for a full day, confirmed while `workflow_dispatch`
kept working flawlessly every single time. Attempted the documented
GitHub-side remediation (edit the cron trigger itself, push, run manually
to "re-register") — no effect even after several hours, well past the
"wait 2 hours" checkpoint that fix is supposed to need.

**Phase 3: GitHub Support closed the ticket as self-service-only.** Free-tier
personal accounts don't get human investigation of Actions-internals bugs
like this — routed to Community Discussions instead. Those discussions (a
handful of multi-month-old, still-unresolved threads with the identical
symptom: `schedule:` silently stops registering, `workflow_dispatch`
keeps working) confirm this is a known, long-standing, unfixed class of
GitHub bug, not something specific to this repo or something likely to
resolve itself soon.

One lead that went nowhere: a GitHub status incident ("Disruption with
GitHub Billing," started ~3.5h before the visibility change) overlapped
suspiciously with the timing, and public-repo unlimited Actions minutes is
a billing-relevant status change — plausible that a degraded billing
service caused a failed schedule-registration handshake. Included in the
Support ticket as a lead; GitHub's own incident updates never mentioned
Actions across ~17 hours of active investigation, so treat this as
unconfirmed, not as the explanation.

**Phase 4 (2026-08-27): fixed via the Pi trigger**, not via GitHub. See
Architecture above. A `/loop`-based bridge (this session manually firing
`workflow_dispatch` every 20 minutes) covered the gap between the ticket
closing and the Pi being ready — no longer needed, don't resurrect it
unless the Pi itself is offline for an extended period.

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
silently breaks re-pairing if a run ever fails mid-chain).

**The Pi exists now** (see Architecture above), so this is technically
unblocked — the Ecobee token could live on local disk like any normal app
credential, with the Pi pushing current sensor readings into the repo for
`render.py` to pick up, no secret-rewriting involved. Still not started;
revisit when this feature actually gets prioritized, not automatically
just because the Pi is available.

## Style

- Python: standard library where reasonable; the four deps in `requirements.txt`
  are the budget. Don't add a template engine, a web framework, or a config lib.
- Comments explain *why*, especially where something looks odd (the force-push,
  the PNG magic-byte check, the width-axis typography).
- Keep `dash.sh` readable over clever. It gets debugged over SSH on a 6" screen.

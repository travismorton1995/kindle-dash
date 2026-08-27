# kindle-dash

Weather and calendar dashboard for a jailbroken Kindle Paperwhite 4 (1072×1448).
GitHub Actions renders a PNG every 20 minutes and pushes it to a separate
private repo; the Kindle wakes on an RTC alarm every 20 minutes, fetches
whatever's newest, draws it, and suspends. A power-button press while asleep
also works as a manual refresh — nothing special about it, it's just another
wake source into the same loop.

No always-on machine, no third-party subscription, no calendar data on a public URL.

This repo (the code) is public — GitHub Actions minutes are unlimited on public
repos, and there's nothing sensitive in here. The *rendered image* is a
different story (real calendar event titles, effectively a live schedule), so
it publishes to a second, private repo instead: **kindle-dash-output**.

```
Actions (every 20 min, public repo)     Kindle (every 20 min)
  Open-Meteo ─┐                           wake on RTC alarm
  your .ics ──┼─→ HTML → Chromium         wifi on
              │   screenshot →            curl the PNG from
              │   16-level grayscale      kindle-dash-output (token auth)
              └─→ push to                 eips draws it
                  kindle-dash-output      wifi off → suspend to RAM
                  (private)
```

## Setup

### 1. Calendar URL

Google Calendar → the calendar's Settings → **Secret address in iCal format**.
Anyone with this URL can read the calendar, so treat it as a password.

To show more than one calendar (e.g. a shared family calendar and your
personal one), comma-separate their secret URLs in `ICS_URL`. Events from all
of them are merged into one list.

### 2. Two repos

This one (the code) can be **public** — that's what makes Actions minutes
unlimited. Create a **second, private** repo (e.g. `kindle-dash-output`) to
hold the rendered image; nothing else needs to live there.

On this (code) repo, Settings → Secrets and variables → Actions:
- **Secrets**: `ICS_URL`, `LATITUDE`, `LONGITUDE`, and `OUTPUT_REPO_TOKEN` (a
  fine-grained PAT scoped to *only* the output repo, `Contents: Read and
  write`, used by the publish step)
- **Variables**: `TIMEZONE` (defaults to Toronto / `America/Toronto` if you
  skip it)

`LATITUDE`/`LONGITUDE` go in Secrets rather than Variables on purpose: they
pin your home location. One catch worth knowing if you're setting this up
fresh — **GitHub's automatic secret-masking silently fails on short values**
like coordinates (confirmed: they printed in plaintext in every run's log
despite being registered Secrets, while a long string like `ICS_URL` masked
correctly right next to them). `dashboard.yml` works around this with an
explicit `echo "::add-mask::${{ secrets.LATITUDE }}"` step before anything
else touches them — keep that step if you're adapting this workflow.

Push this code, then Actions → Render dashboard → Run workflow. It should
push `dash.png` to the output repo's `main` branch.

The publish step force-pushes a fresh single commit each run, to both
`dash.png` and a small README explaining what that repo is. Without the
force-push you'd accumulate a PNG every 20 minutes forever.

### 3. Token for the Kindle

Settings → Developer settings → **Fine-grained personal access token**.
Scope it to the **output repo only**, **Contents: Read** only, with an
expiry — not this code repo, which the Kindle never needs to read.

That token sits in plaintext on the Kindle, so it should be able to do exactly
one thing: read the output repo's rendered image. Keep it separate from
`OUTPUT_REPO_TOKEN` above (that one's write-scoped, for Actions to publish
with) — the device is the kind of thing that can get lost or stolen, so it
should only ever hold read access.

### 4. Kindle

```sh
# on the Kindle, over USB or SSH
mkdir -p /mnt/us/extensions/dash
# copy kindle/dash.sh and kindle/config.sh (from kindle/config.sh.example) into it
chmod +x /mnt/us/extensions/dash/dash.sh
```

Run it once by hand from SSH before wiring it to KUAL or boot, so you can watch
`/mnt/us/dash.log`.

## Local iteration

You don't need the Kindle, or even the network, to work on the layout:

```sh
pip install -r requirements.txt
python -m playwright install chromium
ICS_URL="file:///path/to/a/saved.ics" python render.py
open dash.png
```

`ICS_URL` accepts a `file://` path, so you can save a copy of your calendar once
and iterate on the design offline.

To check against your real calendar and weather instead, copy `local.sh.example`
to `local.sh` (gitignored — holds real secrets, same as `kindle/config.sh`),
fill in `ICS_URL`/`LATITUDE`/`LONGITUDE`/`TIMEZONE`, then:

```sh
source local.sh && python render.py
```

## Things to verify on your specific device

These vary between Kindles and can't be looked up reliably — expect to discover
them by trying:

- **`rtc0` vs `rtc1`.** `dash.sh` probes both, but confirm which one it found in
  the log. If suspend never wakes, this is the first suspect. (Confirmed
  `rtc1` on a real PW4.)
- **TLS.** The Kindle's CA bundle is old. If `curl` fails with a certificate
  error, install a current bundle and point curl at it — don't reach for `-k`,
  since the request carries your token. (Confirmed working, no changes
  needed, on a real PW4.)
- **Wifi reconnect time.** The 30-second loop in `wifi_up` is generous
  headroom, not a tight guess — a full wake-to-refreshed cycle (wifi up,
  fetch, draw) measured 14-20s end to end on a real PW4. Note: testing over
  USB seems to interfere with both wifi association and suspend-to-RAM —
  measure unplugged, on battery, if you're re-verifying this.
- **`eips` ghosting.** `eips -c` before every draw is the conservative choice
  and isn't the source of on-screen glitches. If you see flashing you
  dislike, try dropping it and doing a full clear only every N refreshes.
- **`eips -g` needs `-f`.** Without it, `eips` defaults to a partial update
  that attempts an unsupported swipe transition on some hardware. Always pass
  `-f` (full update). Confirmed on a real PW4: with `-f` in place, the
  `swipe feature is not supported` message still shows up in `dash.log`
  (it prints for every `eips` display call regardless of mode, apparently
  harmless chatter on this hardware) but nothing renders on the actual
  screen — treat it as log noise, not a symptom.
- **Battery life.** ~16 days per charge measured at a 30-minute refresh
  interval, unattended and on battery; ~11 days projected at the current
  20-minute default. Below 8%, `dash.sh` draws a low-battery warning and
  suspends indefinitely (no RTC alarm armed) rather than idling awake —
  only a physical wake (power button, USB) brings it back, and the script
  needs restarting by hand at that point.

## Design notes

The screen is 16 levels of gray, 6 inches, read from across a room. There's no
colour to encode meaning with, so the layout uses **width** instead: one variable
font (Archivo) set very wide for numbers and very narrow for text.

The agenda is a condensed list, not a time-proportional rail — it spends space
on what's scheduled instead of on empty hours. The heavy "NOW" bar marks where
you are in the day; everything else stays quiet so that bar stays the loudest
thing on the page. Agenda events starting within the hour, or already
underway, get a bold pill outline — enough to catch the eye without
introducing a second heavy element to compete with the NOW bar.

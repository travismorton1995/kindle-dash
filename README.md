# kindle-dash

Weather and calendar dashboard for a jailbroken Kindle Paperwhite 4 (1072×1448).
GitHub Actions renders a PNG hourly into a private branch; the Kindle wakes on an
RTC alarm, fetches it, draws it, and suspends.

No always-on machine, no third-party subscription, no calendar data on a public URL.

```
Actions (hourly)                    Kindle (hourly)
  Open-Meteo ─┐                       wake on RTC alarm
  your .ics ──┼─→ HTML → Chromium     wifi on
              │   screenshot →        curl the PNG (token auth)
              │   16-level grayscale  eips draws it
              └─→ push to `output`    wifi off → suspend to RAM
```

## Setup

### 1. Calendar URL

Google Calendar → the calendar's Settings → **Secret address in iCal format**.
Anyone with this URL can read the calendar, so treat it as a password.

To show more than one calendar (e.g. a shared family calendar and your
personal one), comma-separate their secret URLs in `ICS_URL`. Events from all
of them are merged into one list.

### 2. Repo

Create it **private**. Then:

- Settings → Secrets and variables → Actions → **Secrets**: add `ICS_URL`
- Same page → **Variables**: add `LATITUDE`, `LONGITUDE`, `TIMEZONE`
  (defaults are Toronto / `America/Toronto` if you skip these)

Push this code, then Actions → Render dashboard → Run workflow. It should
create an `output` branch containing `dash.png`.

The workflow force-pushes a fresh single-commit branch each run. Without that
you'd accumulate a PNG an hour forever.

### 3. Token for the Kindle

Settings → Developer settings → **Fine-grained personal access token**.
Scope it to this one repository, **Contents: Read** only, with an expiry.

That token sits in plaintext on the Kindle, so it should be able to do exactly
one thing: read this repo.

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
- **Wifi reconnect time.** 30 seconds is a guess. If fetches fail intermittently
  after a suspend, raise the loop in `wifi_up`. Note: testing over USB seems
  to interfere with both wifi association and suspend-to-RAM — measure this
  unplugged, on battery.
- **`eips` ghosting.** `eips -c` before every draw is the conservative choice
  and isn't the source of on-screen glitches. If you see flashing you
  dislike, try dropping it and doing a full clear only every N refreshes.
- **`eips -g` needs `-f`.** Without it, `eips` defaults to a partial update
  that attempts an unsupported swipe transition on some hardware and prints
  debug text directly onto the screen. Always pass `-f` (full update).

## Design notes

The screen is 16 levels of gray, 6 inches, read from across a room. There's no
colour to encode meaning with, so the layout uses **width** instead: one variable
font (Archivo) set very wide for numbers and very narrow for text.

The agenda is a condensed list, not a time-proportional rail — it spends space
on what's scheduled instead of on empty hours. The heavy "NOW" bar marks where
you are in the day; everything else stays quiet so that bar stays the loudest
thing on the page.

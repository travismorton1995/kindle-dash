#!/bin/sh
# Kindle-side dashboard loop for a jailbroken Paperwhite 4.
#
# Wakes on an RTC alarm, brings wifi up, fetches one PNG, draws it, drops wifi,
# and suspends to RAM. The e-ink image persists through the suspend, so the
# screen shows the dashboard the whole time the SoC is doing nothing.
#
# Install to /mnt/us/extensions/dash/ and create config.sh alongside it.

set -u

DIR="$(dirname "$0")"
. "$DIR/config.sh"   # GITHUB_REPO, GITHUB_TOKEN, REFRESH_SECONDS, QUIET_START, QUIET_END

IMG=/tmp/dash.png
LOG=/mnt/us/dash.log
API="https://api.github.com/repos/${GITHUB_REPO}/contents/dash.png?ref=output"
exec >>"$LOG" 2>&1

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# Old Kindles have rtc0 on some models and rtc1 on others. Find the live one.
find_rtc() {
  for r in /sys/class/rtc/rtc1/wakealarm /sys/class/rtc/rtc0/wakealarm; do
    [ -w "$r" ] && { echo "$r"; return; }
  done
  echo ""
}
WAKEALARM="$(find_rtc)"

wifi_up() {
  lipc-set-prop com.lab126.cmd wirelessEnable 1
  i=0
  while [ $i -lt 30 ]; do
    [ "$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)" = "CONNECTED" ] && return 0
    sleep 1
    i=$((i + 1))
  done
  log "wifi did not connect"
  return 1
}

wifi_down() {
  lipc-set-prop com.lab126.cmd wirelessEnable 0
}

battery() {
  lipc-get-prop com.lab126.powerd battLevel 2>/dev/null || echo 100
}

fetch() {
  # -f so HTTP errors are failures; the token never appears in the URL.
  curl -sfL --max-time 90 \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github.raw" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -o "$IMG.tmp" "$API" || return 1

  # A truncated download drawn to the screen looks like a crash. Check the PNG
  # magic bytes before committing to it.
  head -c 4 "$IMG.tmp" | grep -q 'PNG' || { log "not a PNG"; rm -f "$IMG.tmp"; return 1; }
  mv "$IMG.tmp" "$IMG"
}

draw() {
  eips -c            # clear ghosting
  sleep 1
  eips -g "$IMG" -f  # -f: full update. Default is partial, which on this
                      # hardware attempts an unsupported swipe transition and
                      # spews "swipe feature is not supported" debug text onto
                      # the screen itself. Confirmed fixed on-device.

  # Battery readout, drawn by eips itself in its plain console font (not the
  # dashboard's Archivo styling — eips text mode can't do that).
  # TEMP: multiple calibration markers at once instead of one guess, so a
  # single photo reveals eips's row-to-pixel scale. Remove once the real
  # position (row X below) is confirmed and the others are deleted.
  eips 150 1 "ROW 150"
  eips 300 1 "ROW 300"
  eips 500 1 "ROW 500"
  eips 800 1 "ROW 800"
  eips 55 1 "BATT ${bat}%"
}

sleep_until_next() {
  secs="$1"
  if [ -n "$WAKEALARM" ]; then
    echo "" > "$WAKEALARM"
    echo "+${secs}" > "$WAKEALARM"
    echo mem > /sys/power/state
  else
    log "no writable wakealarm, falling back to sleep"
    sleep "$secs"
  fi
}

# ---- setup ----------------------------------------------------------------

log "starting (rtc=${WAKEALARM:-none})"

stop lab126_gui 2>/dev/null || stop framework 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.powerd flIntensity 0    # frontlight off; big battery win

# ---- loop -----------------------------------------------------------------

while true; do
  hour=$(date +%-H)
  bat=$(battery)

  if [ "$bat" -lt 8 ]; then
    log "battery ${bat}%, stopping"
    eips -c
    eips 5 20 "Battery low (${bat}%) - charge and restart dash"
    exit 0
  fi

  if [ "$hour" -ge "$QUIET_START" ] || [ "$hour" -lt "$QUIET_END" ]; then
    # Overnight: skip the fetch entirely, just sleep to the next check.
    log "quiet hours, skipping refresh (batt ${bat}%)"
    sleep_until_next "$REFRESH_SECONDS"
    continue
  fi

  if wifi_up; then
    if fetch; then
      draw
      log "refreshed (batt ${bat}%)"
    else
      log "fetch failed, keeping previous image"
    fi
  fi
  wifi_down

  sleep_until_next "$REFRESH_SECONDS"
done

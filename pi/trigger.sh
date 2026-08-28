#!/bin/sh
# Periodic GitHub Actions workflow_dispatch trigger for kindle-dash.
#
# Stands in for the schedule: trigger, which stopped registering entirely
# after kindle-dash's visibility changed to public (confirmed broken -- a
# GitHub Support ticket was closed as self-service-only for this account
# tier). workflow_dispatch has been 100% reliable throughout, unlike
# schedule:, so this bypasses schedule: rather than trying to fix it.
#
# No active-hours logic here on purpose: dashboard.yml's own "Check active
# hours" step already gates whether a dispatch actually renders anything,
# so duplicating that here would just be two places that can drift apart.
#
# Install alongside config.sh at ~/kindle-dash-trigger/, run via the
# kindle-dash-trigger.timer systemd unit (not cron -- see that unit for why).

set -u

DIR="$(dirname "$0")"
. "$DIR/config.sh"   # GITHUB_TOKEN, REF

LOG="$DIR/trigger.log"
LOG_MAX_LINES=5000
API="https://api.github.com/repos/travismorton1995/kindle-dash/actions/workflows/dashboard.yml/dispatches"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# Same reasoning as dash.sh's trim_log: keeps this safe to run unattended
# for months without the log growing forever.
trim_log() {
  [ -f "$LOG" ] || return
  lines=$(wc -l < "$LOG" 2>/dev/null || echo 0)
  if [ "$lines" -gt "$LOG_MAX_LINES" ]; then
    tail -n "$LOG_MAX_LINES" "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
}

trim_log

resp=$(curl -sS --max-time 30 -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "$API" \
  -d "{\"ref\":\"${REF}\"}")

if [ "$resp" = "204" ]; then
  log "dispatched (ref=${REF})"
else
  log "dispatch failed, HTTP ${resp} (ref=${REF})"
fi

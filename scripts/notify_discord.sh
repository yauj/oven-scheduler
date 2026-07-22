#!/usr/bin/env bash
# Posts a message to a Discord channel via an incoming webhook.
# Mirrors the sendDiscordMessage_ helper in the sibling Daily Prayer Video
# Apps Script project: a plain `content` string (so the mobile push preview
# shows the subject line) plus a colored embed for when Discord is opened.
#
# Usage: notify_discord.sh <success|warning|error> "<subject>" "<body>"
# Requires DISCORD_WEBHOOK_URL in the environment; silently skipped (with a
# log line, exit 0) if it's unset, so a missing webhook never fails the job.
set -euo pipefail

level="${1:?level (success|warning|error) required}"
subject="${2:?subject required}"
body="${3:?body required}"

if [ -z "${DISCORD_WEBHOOK_URL:-}" ]; then
  echo "DISCORD_WEBHOOK_URL is not set — skipping Discord notification."
  exit 0
fi

case "$level" in
  success) emoji="✅"; color=3066993 ;;   # green
  warning) emoji="⚠️"; color=15844367 ;;  # yellow
  error)   emoji="🚨"; color=15158332 ;;  # red
  *)       emoji="🔔"; color=8421504 ;;   # grey fallback
esac

payload=$(CONTENT="${emoji} **${subject}**" DESCRIPTION="$body" COLOR="$color" python3 -c '
import json
import os

print(json.dumps({
    "content": os.environ["CONTENT"],
    "embeds": [{"description": os.environ["DESCRIPTION"], "color": int(os.environ["COLOR"])}],
}))
')

http_code=$(curl -s -o /tmp/discord_notify_response.txt -w '%{http_code}' \
  -H "Content-Type: application/json" \
  -d "$payload" \
  "$DISCORD_WEBHOOK_URL") || http_code="curl_failed"

if [ "$http_code" != "204" ] && [ "$http_code" != "200" ]; then
  echo "Discord webhook returned ${http_code}: $(cat /tmp/discord_notify_response.txt 2>/dev/null || true)"
fi

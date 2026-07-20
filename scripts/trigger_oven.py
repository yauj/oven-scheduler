#!/usr/bin/env python3
"""
Trigger the Home Assistant script that starts the oven in convection bake
mode at 450F. Designed to be called on a coarse cron schedule (see
.github/workflows/trigger-oven.yml) and to be a safe no-op outside the
actual target time, so the workflow never needs manual DST adjustment.

Env vars required:
  HA_URL     Base URL of the Home Assistant instance, e.g. https://my-ha.example.com
  HA_TOKEN   Long-lived access token with permission to call services

Env vars optional:
  TARGET_HOUR     Target hour (24h, Pacific time) to fire at. Default 1 (1 AM).
  TARGET_MINUTE   Target minute. Default 0.
  WINDOW_MINUTES  How many minutes on either side of the target count as
                   "close enough" to fire. Default 7 (matches the 15-minute
                   cron cadence with margin for GitHub Actions scheduling lag).
  SCRIPT_ENTITY   The HA script entity to call. Default script.start_oven_convection_450.
  FORCE           If set to "1", skip the time check and fire immediately.
                   Used for manual workflow_dispatch testing.
"""
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def within_window() -> bool:
    target_hour = int(os.environ.get("TARGET_HOUR", "1"))
    target_minute = int(os.environ.get("TARGET_MINUTE", "0"))
    window = int(os.environ.get("WINDOW_MINUTES", "7"))

    now = datetime.now(PACIFIC)
    target_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    delta_minutes = abs((now - target_today).total_seconds()) / 60

    print(f"Current Pacific time: {now.isoformat()}; target: {target_today.isoformat()}; "
          f"delta: {delta_minutes:.1f} min; window: +/-{window} min")

    return delta_minutes <= window


def call_ha_script() -> None:
    ha_url = os.environ.get("HA_URL")
    ha_token = os.environ.get("HA_TOKEN")
    script_entity = os.environ.get("SCRIPT_ENTITY", "script.start_oven_convection_450")

    if not ha_url or not ha_token:
        print("ERROR: HA_URL and HA_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    # entity_id looks like script.start_oven_convection_450 -> service call
    # goes to script/<object_id>
    if "." not in script_entity:
        print(f"ERROR: SCRIPT_ENTITY '{script_entity}' is not a valid entity id "
              f"(expected domain.object_id).", file=sys.stderr)
        sys.exit(1)
    domain, object_id = script_entity.split(".", 1)

    url = f"{ha_url.rstrip('/')}/api/services/{domain}/{object_id}"
    req = urllib.request.Request(
        url,
        data=json.dumps({}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            print(f"HA responded {resp.status}: {body}")
            if resp.status >= 300:
                sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"ERROR calling Home Assistant: HTTP {e.code} - {e.read().decode('utf-8', 'ignore')}",
              file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR calling Home Assistant: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    force = os.environ.get("FORCE", "0") == "1"

    if not force and not within_window():
        print("Outside target window and FORCE not set — no-op, exiting cleanly.")
        sys.exit(0)

    if force:
        print("FORCE=1 set — skipping time check.")

    print("Within window (or forced) — calling Home Assistant to start the oven.")
    call_ha_script()
    print("Done.")


if __name__ == "__main__":
    main()

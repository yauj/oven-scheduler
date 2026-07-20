#!/usr/bin/env python3
"""
Connect directly to the SmartHQ cloud (via the gehomesdk library — no Home
Assistant involved) and schedule the oven to start convection-bake preheat
at 450F, delayed to begin at TARGET_START_HOUR:TARGET_START_MINUTE Pacific
(default 6:00 AM). Designed to be called a handful of times by a coarse
cron schedule (see .github/workflows/trigger-oven.yml) sometime in the
early-morning hours; this script has no time-of-day gate of its own and
just runs whenever it's invoked — GitHub's cron is best-effort and can run
a scheduled job substantially later than its nominal time, and the
intent here is "run once, sometime in that general window" rather than "run
at a precise minute," so a late invocation still doing its job is fine.
The no-clobber guard below is what keeps repeated ticks in the same
schedule window from re-arming the oven more than once.

Notes from live probing against the real appliance (readback after every
write, cross-checked against panel-set delay-starts):

- This oven advertises "Convection Multi Bake" (ErdOvenState.CONV_MUTLI_BAKE)
  rather than plain "Convection Bake" (ErdOvenState.CONV_BAKE) in its
  UPPER_OVEN_AVAILABLE_COOK_MODES. Sending CONV_BAKE was silently ignored by
  the appliance; CONV_MUTLI_BAKE is what the panel's "Convection Bake"
  button actually maps to on this model/ERD generation.
- The delay-start target time is NOT encoded as a duration or as a single
  minutes-since-midnight integer, despite gehomesdk's OvenCookSetting
  modeling it as a plain `delay_time: timedelta` (which erd_encode_timespan
  serializes as one big-endian 16-bit total-minutes value). The appliance
  actually wants two separate bytes: [hour_byte][minute_byte], 24h clock,
  e.g. 6:00 AM -> bytes (0x06, 0x00). Values that don't fit that shape
  (minute byte > 59, i.e. anything sent as "N minutes" for N >= 60 via the
  SDK's encoding) get silently rejected back to Off. Since
  timedelta.seconds caps at 86399 (just under 24h), erd_encode_timespan's
  `.seconds // 60` can never produce a value >= 1440 anyway, so target hours
  6 AM and later are structurally impossible to reach through
  OvenCookSetting.delay_time — this script instead builds the
  UPPER/LOWER_OVEN_COOK_MODE payload's raw hex directly and writes it via
  the low-level GeWebsocketClient.async_set_erd_value(), bypassing the
  OvenCookSetting/erd_encode_timespan path entirely for this one field.

Before writing the delay-start payload, this script reads back the oven's
current cook-mode ERD and aborts without writing if it isn't NO_MODE (off) —
so a preheat/cook someone else already set on the panel or app is never
clobbered. That specific failure (oven in use) is not retried, since a
fresh connection won't change it. Any other failure (auth, connection
timeout, appliance not appearing, write not verifying) is retried up to
RUN_RETRIES times with a RUN_RETRY_COOLDOWN_SECONDS pause between full
attempts, each with its own fresh connection.

Auth: SmartHQ accounts with MFA enabled can't complete a login unattended,
so this script never does a fresh username/password login. Instead it
authenticates with a long-lived refresh token obtained once, interactively,
via scripts/get_refresh_token.py (see docs/PLAN.md Phase "one-time auth
setup"). If GE forces that refresh token to expire, re-run
get_refresh_token.py and update the SMARTHQ_REFRESH_TOKEN secret.

Env vars required:
  SMARTHQ_USERNAME         SmartHQ account email
  SMARTHQ_REFRESH_TOKEN    Refresh token from scripts/get_refresh_token.py
  OVEN_MAC                 MAC address (appliance id) of the range, from
                             scripts/get_refresh_token.py's discovery output

Env vars optional:
  SMARTHQ_REGION      "US" or "EU". Default US.
  OVEN_CAVITY         "upper" or "lower" (which oven cavity's ERD codes to
                         use on a double oven). Default upper.
  TARGET_START_HOUR   Target hour (24h, Pacific time) the oven should
                         actually start preheating at. Default 6 (6 AM).
  TARGET_START_MINUTE Target start minute. Default 0.
  TARGET_TEMP         Target temperature, Fahrenheit. Default 450.
"""
import asyncio
import os
import sys
import time

import aiohttp
from gehomesdk import ErdCode, GeWebsocketClient
from gehomesdk.erd.values.oven import ErdOvenCookMode, ErdOvenState, OvenCookMode
from gehomesdk.erd.values.oven.oven_cook_mode_mapping import OVEN_COOK_MODE_MAP

CONNECT_TIMEOUT_SECONDS = 180
WRITE_RETRIES = 5
WRITE_VERIFY_DELAY_SECONDS = 10
RUN_RETRIES = 3
RUN_RETRY_COOLDOWN_SECONDS = 30

# CONV_MUTLI_BAKE + delayed=True encodes to ErdOvenCookMode.CONVMULTIBAKE_DELAYSTART.
DELAYED_COOK_MODE = OvenCookMode(oven_state=ErdOvenState.CONV_MUTLI_BAKE, delayed=True)


class OvenInUseError(RuntimeError):
    """Raised when the oven already has a cook mode set (not ours) — retrying
    a fresh connection won't change that, so callers should not retry this."""


def get_cook_mode_erd_code() -> "ErdCode":
    cavity = os.environ.get("OVEN_CAVITY", "upper").strip().lower()
    if cavity == "lower":
        return ErdCode.LOWER_OVEN_COOK_MODE
    if cavity == "upper":
        return ErdCode.UPPER_OVEN_COOK_MODE
    print(f"ERROR: OVEN_CAVITY '{cavity}' must be 'upper' or 'lower'.", file=sys.stderr)
    sys.exit(1)


def get_start_hour_minute() -> tuple[int, int]:
    start_hour = int(os.environ.get("TARGET_START_HOUR", "6"))
    start_minute = int(os.environ.get("TARGET_START_MINUTE", "0"))
    if not (0 <= start_hour <= 23) or not (0 <= start_minute <= 59):
        print(f"ERROR: TARGET_START_HOUR/MINUTE must be 0-23 / 0-59, "
              f"got {start_hour}:{start_minute}.", file=sys.stderr)
        sys.exit(1)
    return start_hour, start_minute


def build_delayed_cook_mode_hex(temperature: int, start_hour: int, start_minute: int) -> str:
    """Build the raw UPPER/LOWER_OVEN_COOK_MODE payload by hand. See the module
    docstring for why OvenCookSetting.delay_time can't express this field."""
    cook_mode_code = OVEN_COOK_MODE_MAP.inverse[DELAYED_COOK_MODE].value
    return (
        cook_mode_code.to_bytes(1, "big").hex()
        + temperature.to_bytes(2, "big").hex()
        + (0).to_bytes(2, "big").hex()  # cook_time
        + (0).to_bytes(2, "big").hex()  # probe_temperature
        + bytes([start_hour, start_minute]).hex()  # delay_time: [hour][minute]
        + (0).to_bytes(2, "big").hex()  # two_temp_cook_temperature
        + (0).to_bytes(2, "big").hex()  # two_temp_cook_time
    )


def get_current_oven_state(appliance, cook_mode_erd: "ErdCode") -> ErdOvenState:
    """Read the appliance's currently-cached cook-mode ERD and decode just the
    leading cook-mode byte into an ErdOvenState, so callers can check whether
    the oven is off (NO_MODE) before writing a new delay-start setting.

    Uses get_raw_erd_value() rather than the higher-level OvenCookSetting
    decode path so this doesn't depend on the delay_time field decoding
    cleanly — see the module docstring on why delay_time bytes here don't fit
    gehomesdk's OvenCookSetting/erd_encode_timespan shape.
    """
    raw = appliance.get_raw_erd_value(cook_mode_erd)
    if not raw:
        raise RuntimeError(f"No cached value for {cook_mode_erd.name} yet — can't confirm oven is off.")
    cook_mode_code = int(raw[0:2], 16)
    return OVEN_COOK_MODE_MAP[ErdOvenCookMode(cook_mode_code)].oven_state


async def start_oven() -> None:
    username = os.environ.get("SMARTHQ_USERNAME")
    refresh_token = os.environ.get("SMARTHQ_REFRESH_TOKEN")
    mac_addr = os.environ.get("OVEN_MAC")
    region = os.environ.get("SMARTHQ_REGION", "US")
    target_temp = int(os.environ.get("TARGET_TEMP", "450"))

    if not username or not refresh_token or not mac_addr:
        print("ERROR: SMARTHQ_USERNAME, SMARTHQ_REFRESH_TOKEN, and OVEN_MAC must be set.",
              file=sys.stderr)
        sys.exit(1)

    cook_mode_erd = get_cook_mode_erd_code()
    start_hour, start_minute = get_start_hour_minute()
    raw_hex = build_delayed_cook_mode_hex(target_temp, start_hour, start_minute)
    print(f"Scheduling delay-start for {start_hour:02d}:{start_minute:02d} local time "
          f"(raw {cook_mode_erd.name} payload: {raw_hex})")

    loop = asyncio.get_event_loop()
    # Password is unused on this path — a refresh token skips the full
    # login flow entirely, so it never re-triggers an MFA challenge.
    client = GeWebsocketClient(username, "", region, loop, refresh_token=refresh_token)

    done = asyncio.Event()
    result: dict = {"ok": False, "exc": None}

    async def on_connected(*_args):
        try:
            for _ in range(30):
                if mac_addr.upper() in client.appliances:
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError(f"Oven with MAC {mac_addr} never appeared after connecting.")

            appliance = client.appliances[mac_addr.upper()]

            # A write sent immediately after the appliance first appears has
            # been observed to be silently dropped (same bytes succeeded when
            # set from the oven's own panel, and succeeded from this script
            # after waiting longer) — likely a race while the appliance's
            # connection/state is still settling. 5s wasn't reliably enough;
            # 15s was, in testing. Give it a moment.
            await asyncio.sleep(15)

            current_state = get_current_oven_state(appliance, cook_mode_erd)
            print(f"Current {cook_mode_erd.name} state: {current_state.name}")
            if current_state != ErdOvenState.NO_MODE:
                raise OvenInUseError(
                    f"Oven is not off (current state: {current_state.name}) — "
                    "someone else may have set a preheat/cook already; refusing to "
                    "override it."
                )

            # Writes have been observed to be silently dropped by the
            # appliance (accepted by the SmartHQ cloud with no error, but
            # the appliance's own reported cook-mode state never changes) —
            # cause not fully understood, so verify the write actually
            # landed and retry a few times rather than trusting a clean
            # cloud ack alone.
            last_error = None
            for attempt in range(1, WRITE_RETRIES + 1):
                print(f"Attempt {attempt}/{WRITE_RETRIES}: setting {cook_mode_erd.name} -> {raw_hex}")
                await client.async_set_erd_value(appliance, cook_mode_erd, raw_hex)

                await asyncio.sleep(WRITE_VERIFY_DELAY_SECONDS)
                new_state = get_current_oven_state(appliance, cook_mode_erd)
                if new_state == DELAYED_COOK_MODE.oven_state:
                    print(f"Verified: {cook_mode_erd.name} is now {new_state.name}.")
                    result["ok"] = True
                    break

                last_error = (f"After write, {cook_mode_erd.name} reads {new_state.name}, "
                              f"expected {DELAYED_COOK_MODE.oven_state.name} — write did not stick.")
                print(f"{last_error} Retrying." if attempt < WRITE_RETRIES else last_error)
            else:
                result["exc"] = RuntimeError(last_error)
        except Exception as e:  # noqa: BLE001 - surface any failure to caller
            result["exc"] = e
        finally:
            done.set()

    client.add_event_handler("connected", on_connected)

    async with aiohttp.ClientSession() as session:
        run_task = loop.create_task(client.async_get_credentials_and_run(session))
        try:
            await asyncio.wait_for(done.wait(), timeout=CONNECT_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            result["exc"] = RuntimeError(
                f"Timed out after {CONNECT_TIMEOUT_SECONDS}s waiting to connect/send command.")
        finally:
            await client.disconnect()
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

    if not result["ok"]:
        raise result["exc"]


def main() -> None:
    for attempt in range(1, RUN_RETRIES + 1):
        print(f"Run attempt {attempt}/{RUN_RETRIES}: connecting to SmartHQ to start the oven.")
        try:
            asyncio.run(start_oven())
            print("Done.")
            return
        except OvenInUseError as e:
            # Retrying a fresh connection won't change whether the oven is
            # already in use — fail fast instead of burning the cooldown
            # budget on retries that can't succeed.
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:  # noqa: BLE001 - retry any other failure
            print(f"Attempt {attempt}/{RUN_RETRIES} failed: {e}", file=sys.stderr)
            if attempt == RUN_RETRIES:
                print(f"ERROR: all {RUN_RETRIES} attempts failed.", file=sys.stderr)
                sys.exit(1)
            print(f"Cooling down {RUN_RETRY_COOLDOWN_SECONDS}s before retrying.")
            time.sleep(RUN_RETRY_COOLDOWN_SECONDS)


if __name__ == "__main__":
    main()

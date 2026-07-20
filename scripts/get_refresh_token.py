#!/usr/bin/env python3
"""
One-time, interactive setup script. Run this locally (never in CI) to:

  1. Log into SmartHQ with your username/password, handling an MFA
     challenge if your account has one enabled.
  2. Print a long-lived refresh token to save as the SMARTHQ_REFRESH_TOKEN
     GitHub Actions secret — trigger_oven.py uses it to reconnect without
     ever repeating this interactive login (and without re-triggering MFA).
  3. Connect once over the websocket API and list discovered appliances,
     so you can find the oven's MAC address for the OVEN_MAC secret.

Usage:
  python scripts/get_refresh_token.py -u you@example.com

Re-run this if SMARTHQ_REFRESH_TOKEN ever stops working (GE can expire
refresh tokens; trigger_oven.py will fail loudly with an auth error if so).
"""
import argparse
import asyncio
import getpass
import sys

import aiohttp
from gehomesdk import GeSmartHqLogin, GeWebsocketClient


async def login_and_get_refresh_token(username: str, password: str, region: str) -> str:
    async with aiohttp.ClientSession() as session:
        login = GeSmartHqLogin(session)
        result = await login.async_login(username, password, region)

        if result.mfa_required:
            method = result.mfa_methods[0]
            print(f"MFA required — sending a verification code via {method}...")
            await login.async_send_code(method)
            code = input("Enter the verification code you received: ").strip()
            token = await login.async_submit_code(code)
        else:
            token = result.token

        return token["refresh_token"]


async def discover_appliances(username: str, refresh_token: str, region: str) -> None:
    loop = asyncio.get_event_loop()
    client = GeWebsocketClient(username, "", region, loop, refresh_token=refresh_token)
    done = asyncio.Event()

    async def on_connected(*_args):
        await asyncio.sleep(5)  # give appliances time to report in
        if not client.appliances:
            print("No appliances found yet — they may take longer to report in; "
                  "try running gehome-appliance-data instead for a longer listen.")
        for mac, appliance in client.appliances.items():
            print(f"  MAC: {mac}")
            print(f"    type: {getattr(appliance, 'appliance_type', 'unknown')}")
        done.set()

    client.add_event_handler("connected", on_connected)

    async with aiohttp.ClientSession() as session:
        run_task = loop.create_task(client.async_get_credentials_and_run(session))
        try:
            await asyncio.wait_for(done.wait(), timeout=60)
        except asyncio.TimeoutError:
            print("Timed out waiting to connect.", file=sys.stderr)
        finally:
            await client.disconnect()
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass


async def main_async(username: str, password: str, region: str) -> None:
    print("Logging in...")
    refresh_token = await login_and_get_refresh_token(username, password, region)

    print("\n=== Save this as the SMARTHQ_REFRESH_TOKEN GitHub Actions secret ===")
    print(refresh_token)
    print("======================================================================\n")

    print("Connecting to discover appliances (looking for your range's MAC address)...")
    await discover_appliances(username, refresh_token, region)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-u", "--username", required=True, help="Your SmartHQ username/email")
    parser.add_argument("-r", "--region", default="US", choices=["US", "EU"], help="SmartHQ region")
    args = parser.parse_args()

    password = getpass.getpass("SmartHQ password: ")
    asyncio.run(main_async(args.username, password, args.region))


if __name__ == "__main__":
    main()

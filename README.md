# oven-scheduler

Automatically starts a GE range in convection bake mode, Monday–Thursday.
A GitHub Actions workflow fires a handful of times between roughly 1:00
and 2:00 AM Pacific and connects directly to the SmartHQ cloud (via the
`gehomesdk` Python library) to schedule a delayed start. No Home Assistant
or other always-on server required.

Target temperature and start time are both configurable — see
`.github/workflows/trigger-oven.yml`. Every run posts a success or failure
alert to Discord via `scripts/notify_discord.sh` — set the optional
`DISCORD_WEBHOOK_URL` repo secret to enable it.

## Repo layout

```
docs/
  PLAN.md                  design notes and phase history
  PROPOSAL.md               trigger-service design & rationale
  SAFETY_NOTES.md            appliance feasibility/discovery notes
scripts/
  get_refresh_token.py       one-time interactive auth + appliance discovery
  trigger_oven.py            called by the GitHub Actions workflow
  notify_discord.sh          posts success/failure alerts to a Discord webhook
.github/workflows/
  trigger-oven.yml           the scheduled trigger (Mon-Thu, ~1 AM Pacific)
  keep-alive.yml              monthly commit so GitHub doesn't auto-disable the schedule
requirements.txt              gehomesdk + aiohttp
.env.example                  local-testing config template (never commit real .env)
```

## Local testing

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values (SMARTHQ_USERNAME, SMARTHQ_REFRESH_TOKEN, OVEN_MAC)
set -a && source .env && set +a
python scripts/trigger_oven.py
```

By default the script is a no-op unless the current Pacific time is within
`WINDOW_MINUTES` of `TARGET_HOUR:TARGET_MINUTE` (see the module docstring in
`scripts/trigger_oven.py`). To run it immediately regardless of time of day,
set `FORCE=1`:

```bash
FORCE=1 python scripts/trigger_oven.py
```

`FORCE=1` only skips the time-of-day check — it still connects to the real
oven and, if it's off, sends a real delay-start command targeting
`TARGET_START_HOUR:TARGET_START_MINUTE`. To watch it actually start
preheating without waiting until the next morning, also override the start
time to a couple minutes from now, e.g.:

```bash
FORCE=1 TARGET_START_HOUR=14 TARGET_START_MINUTE=32 python scripts/trigger_oven.py
```

Before writing anything, the script reads back the oven's current cook-mode
state and aborts (non-zero exit, no write) if it isn't off — so running this
locally is safe to try even if someone already started a manual preheat or
cook; you'll see something like:

```
ERROR: Oven is not off (current state: CONV_MUTLI_BAKE) — someone else may
have set a preheat/cook already; refusing to override it.
```

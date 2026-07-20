# oven-scheduler

Automatically starts a GE range in convection bake mode, Monday–Thursday.
A GitHub Actions workflow fires a handful of times between roughly 1:00
and 2:00 AM Pacific and connects directly to the SmartHQ cloud (via the
`gehomesdk` Python library) to schedule a delayed start. No Home Assistant
or other always-on server required.

Target temperature and start time are both configurable — see
`.github/workflows/trigger-oven.yml`.

## Repo layout

```
docs/
  PLAN.md                  design notes and phase history
  PROPOSAL.md               trigger-service design & rationale
  SAFETY_NOTES.md            appliance feasibility/discovery notes
scripts/
  get_refresh_token.py       one-time interactive auth + appliance discovery
  trigger_oven.py            called by the GitHub Actions workflow
.github/workflows/
  trigger-oven.yml           the scheduled trigger (Mon-Thu, ~1 AM Pacific)
  keep-alive.yml              monthly commit so GitHub doesn't auto-disable the schedule
requirements.txt              gehomesdk + aiohttp
.env.example                  local-testing config template (never commit real .env)
```

## Local testing

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
export $(grep -v '^#' .env | xargs)
python scripts/trigger_oven.py
```

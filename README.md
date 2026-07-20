# oven-scheduler

Automatically starts a GE Profile PHS930YPFS range in convection bake at
450°F, Monday–Thursday. A GitHub Actions workflow fires around 1:00 AM
Pacific and calls the SmartHQ cloud API directly (via the `gehomesdk`
Python library) to start the oven for 6:00 AM. No Home Assistant or other
always-on server required.

**Start here:** [`docs/PLAN.md`](docs/PLAN.md) is the full implementation
plan, phase by phase. [`docs/PROPOSAL.md`](docs/PROPOSAL.md) explains and
justifies both the SmartHQ-direct design (vs. Home Assistant) and the
trigger-service design (GitHub Actions cron with a DST-safe time gate).
[`docs/SAFETY_NOTES.md`](docs/SAFETY_NOTES.md) has the Phase 0
feasibility results — already confirmed: this oven starts unattended.

## Repo layout

```
docs/
  PLAN.md                  implementation plan (read this first)
  PROPOSAL.md               design & rationale (SmartHQ-direct + trigger service)
  SAFETY_NOTES.md            Phase 0 results + appliance discovery notes
scripts/
  get_refresh_token.py       one-time interactive auth + appliance discovery
  trigger_oven.py            called by the GitHub Actions workflow
.github/workflows/
  trigger-oven.yml           the scheduled trigger (Mon-Thu, ~1 AM Pacific)
  keep-alive.yml              optional monthly commit so GitHub doesn't auto-disable the schedule
requirements.txt              gehomesdk + aiohttp
.env.example                  local-testing config template (never commit real .env)
```

## Quick status

- [x] Phase 0: Safety/feasibility check done (`docs/SAFETY_NOTES.md`)
- [ ] Phase 1: One-time auth setup — refresh token + oven MAC address obtained
- [ ] Phase 2: Manual test of the actual start command (`FORCE=1 python scripts/trigger_oven.py`)
- [ ] Phase 3: `SMARTHQ_USERNAME` / `SMARTHQ_REFRESH_TOKEN` / `OVEN_MAC` GitHub secrets set, workflow enabled
- [ ] Phase 4: Failure notifications configured (`NTFY_TOPIC` secret, optional)
- [ ] Phase 5: Tested via manual `workflow_dispatch` (with and without `force`)
- [ ] Phase 6: Decided on keep-alive vs. manual repo check-ins

## Local testing

```bash
pip install -r requirements.txt
python scripts/get_refresh_token.py -u you@example.com   # one-time; handles MFA if enabled

cp .env.example .env   # fill in real values (username, refresh token, oven MAC)
export $(grep -v '^#' .env | xargs)
python scripts/trigger_oven.py            # respects the time window
FORCE=1 python scripts/trigger_oven.py    # bypasses it, fires immediately
```

# oven-scheduler

Automatically starts a GE Profile PHS930YPFS range in convection bake at
450°F, Monday–Thursday. A GitHub Actions workflow fires around 1:00 AM
Pacific and calls a Home Assistant script (via `geappliances-smarthq-
integration`) that schedules/starts the oven for 6:00 AM.

**Start here:** [`docs/PLAN.md`](docs/PLAN.md) is the full implementation
plan, phase by phase. [`docs/PROPOSAL.md`](docs/PROPOSAL.md) explains and
justifies the trigger-service design (GitHub Actions cron with a DST-safe
time gate). Fill in [`docs/SAFETY_NOTES.md`](docs/SAFETY_NOTES.md) first —
Phase 0 of the plan — before building anything else, since it determines
whether a fully unattended remote start is even possible on this model.

## Repo layout

```
docs/
  PLAN.md            implementation plan (read this first)
  PROPOSAL.md         trigger-service design & rationale
  SAFETY_NOTES.md      fill in during Phase 0
homeassistant/
  scripts.yaml         HA script template — needs real entity IDs filled in
scripts/
  trigger_oven.py       called by the GitHub Actions workflow
.github/workflows/
  trigger-oven.yml      the scheduled trigger (Mon-Thu, ~1 AM Pacific)
  keep-alive.yml         optional monthly commit so GitHub doesn't auto-disable the schedule
.env.example            local-testing config template (never commit real .env)
```

## Quick status

- [ ] Phase 0: Safety/feasibility check done (`docs/SAFETY_NOTES.md`)
- [ ] Phase 1: Home Assistant hosted somewhere reachable
- [ ] Phase 2: `geappliances-smarthq-integration` installed & authorized
- [ ] Phase 3: `homeassistant/scripts.yaml` filled in with real entity IDs and tested manually
- [ ] Phase 4: Long-lived HA token created, curl test passes
- [ ] Phase 5: `HA_URL` / `HA_TOKEN` GitHub secrets set, workflow enabled
- [ ] Phase 6: Failure notifications configured (`NTFY_TOPIC` secret, optional)
- [ ] Phase 7: Tested via manual `workflow_dispatch` (with and without `force`)
- [ ] Phase 8: Decided on keep-alive vs. manual repo check-ins

## Local testing

```bash
cp .env.example .env   # fill in real values
export $(grep -v '^#' .env | xargs)
python scripts/trigger_oven.py            # respects the time window
FORCE=1 python scripts/trigger_oven.py    # bypasses it, fires immediately
```

# Implementation Plan: Automated Oven Preheat Scheduler

**Goal:** Every Monday–Thursday, automatically start the GE Profile PHS930YPFS range at 6:00 AM Pacific in convection bake mode at 450°F, triggered by a job that fires at 1:00 AM Pacific.

**Status:** Draft plan for an agent/developer to execute step by step. Each phase has a concrete deliverable and a checkpoint before moving on. Do not skip Phase 0 — it determines whether the rest of the plan is even viable.

---

## Architecture summary

```
GitHub Actions (cron, Mon-Thu)  --HTTPS-->  Home Assistant REST API  --SmartHQ cloud API-->  GE oven
      1:00 AM PT trigger              /api/services/script/turn_on        (geappliances-smarthq-
                                                                             integration component)
```

Two hard requirements fall out of this that weren't obvious at the start:

1. **`geappliances-smarthq-integration` is a Home Assistant custom component, not a standalone library.** It only runs inside a live Home Assistant instance, and its OAuth setup flow is built around HA's own redirect helper (`https://my.home-assistant.io/redirect/oauth`). There is no way to skip HA and call the SmartHQ cloud API directly with this integration — so a Home Assistant instance running 24/7 somewhere is a prerequisite, not optional.
2. **HA does not need to be on the same network as the oven.** The integration talks to GE's SmartHQ cloud, not to the oven over LAN, so HA can run on a Raspberry Pi at home, a NAS, or a cheap always-on VPS — wherever is easiest to keep alive and reachable from GitHub's servers.

---

## Phase 0 — Feasibility and safety check (do this before building anything else)

This phase exists because we don't yet know two things that would sink the project if wrong: whether GE requires a physical confirmation on the range before a remote start will actually fire, and what services this specific model exposes through SmartHQ.

1. Install the SmartHQ mobile app, sign in, and confirm the range shows up with remote control / Wi-Fi connect enabled.
2. From the app, manually trigger a remote preheat once, physically standing near the oven. Observe:
   - Does it start immediately, or does it wait for a button press / knob turn on the unit itself?
   - Is there a "remote enable" toggle that has to be re-armed each time, or is it persistent?
3. Record the result in `docs/SAFETY_NOTES.md` (template included in this repo).
4. **Decision gate:** if the oven requires physical confirmation every time, a fully unattended 6:00 AM start is not achievable as designed — stop and revisit scope (e.g., have it only pre-heat once confirmed some days, or use it as a reminder/notification instead of a hard auto-start) before investing in Phases 1–5.

## Phase 1 — Home Assistant hosting

Pick one and stand it up:

- **Raspberry Pi / home server**, HA in Docker (`ghcr.io/home-assistant/home-assistant:stable`), exposed to the internet via a Cloudflare Tunnel or Tailscale Funnel (avoid raw port-forwarding).
- **Home Assistant Cloud (Nabu Casa)** add-on subscription (~$6.50/mo) — simplest path, gives a stable HTTPS remote URL with no networking setup, and is the option this plan assumes going forward unless you tell it otherwise.
- **Small VPS** running HA in Docker directly, with its own domain + TLS (e.g. via Caddy).

Deliverable: a Home Assistant instance reachable at a stable HTTPS URL, admin login working.

## Phase 2 — Install and authorize the integration

1. Install HACS if not already present, then add `geappliances-smarthq-integration` as a custom repository, or copy `custom_components/smarthq` into `/config/custom_components/smarthq` manually.
2. Register an OAuth application at the SmartHQ Developer Portal (developer.smarthq.com), redirect URI `https://my.home-assistant.io/redirect/oauth`.
3. Add the Client ID/Secret under HA Settings → Application Credentials.
4. Add the integration via Settings → Devices & Services, complete the OAuth login with the GE/SmartHQ account the oven is registered to.
5. Confirm entities appear for the range. Note the actual entity IDs generated (they depend on what services SmartHQ reports for this model) in `docs/SAFETY_NOTES.md` — you'll need the exact cook-mode select, temperature number, and start/trigger button entity IDs for Phase 3.

## Phase 3 — HA script: "start convection bake 450"

Build a single HA script entity that sequences the entity calls discovered in Phase 2 (exact entity IDs will vary by discovery, so this is a template to fill in):

```yaml
# homeassistant/scripts.yaml — copy into your HA config, adjust entity_ids
start_oven_convection_450:
  alias: "Start oven — convection bake 450F"
  sequence:
    - service: select.select_option
      target:
        entity_id: select.range_oven_cook_mode   # replace with real entity id
      data:
        option: "Convection Bake"
    - service: number.set_value
      target:
        entity_id: number.range_oven_temperature  # replace with real entity id
      data:
        value: 450
    - service: button.press
      target:
        entity_id: button.range_oven_start        # replace with real entity id
  mode: single
```

Test this manually from HA's Developer Tools → Services before wiring up any scheduling, so Phase 0's physical-confirmation question is answered with the exact flow you'll actually use.

## Phase 4 — Long-lived access token + REST call

1. In HA, create a Long-Lived Access Token (profile page) scoped to this automation. Treat it like a password.
2. Verify the call works from a shell before automating it:

```bash
curl -X POST \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  https://<your-ha-url>/api/services/script/start_oven_convection_450
```

3. `scripts/trigger_oven.py` (in this repo) wraps this call, adds error handling, and — critically — a **DST-safe time gate** so the workflow can run on a coarse cron schedule and still only fire once, at the right Pacific time, whether it's PST or PDT (see Phase 5).

## Phase 5 — GitHub Actions trigger

See `docs/PROPOSAL.md` for the full reasoning; summary of what's implemented in `.github/workflows/trigger-oven.yml`:

- Cron runs every 15 minutes across an hour-wide UTC window that covers 1:00 AM Pacific in both PST and PDT, Monday–Thursday.
- The workflow calls `scripts/trigger_oven.py`, which checks the real current time in `America/Los_Angeles` and only proceeds if it's within a couple minutes of 1:00 AM — otherwise it exits as a no-op. This means the schedule never needs manual DST adjustment.
- Secrets required in the repo (Settings → Secrets and variables → Actions): `HA_URL`, `HA_TOKEN`.

## Phase 6 — Failure notification

A silent failure here means a cold oven at 6 AM, which is worse than no automation at all — you won't know to intervene manually. Add a notification step so failures aren't silent:

- Simplest: a free [ntfy.sh](https://ntfy.sh) topic — one `curl` call in the workflow's failure step, push notification to your phone.
- Alternative: GitHub's own workflow-failure email notifications (on by default for the repo owner) — lower effort, less immediate.

Add this in `.github/workflows/trigger-oven.yml` as a step with `if: failure()`.

## Phase 7 — Testing plan

1. Manually dispatch the GitHub Actions workflow (`workflow_dispatch` trigger, included) outside the 1 AM window and confirm the time-gate correctly no-ops.
2. Temporarily narrow the time-gate window for a same-day test, or use `workflow_dispatch` with a `force` input (included) to bypass the gate and fire the oven immediately, so you can validate the whole chain without waiting for 1 AM.
3. Let it run unattended for the first real Mon–Thu cycle, but verify manually (visually or via HA history) that the oven actually reached temperature by 6 AM before fully trusting it.

## Phase 8 — Ongoing maintenance

- **GitHub disables scheduled workflows automatically after 60 days with no repository activity.** Since this repo may otherwise go untouched for months, either: (a) check in on it periodically, or (b) add a trivial "keep-alive" — e.g. a monthly workflow that touches a timestamp file and commits it — so the schedule never silently goes stale. Decide and document the choice in `docs/PROPOSAL.md`.
- Rotate the HA long-lived access token periodically; update the `HA_TOKEN` GitHub secret when you do.
- If GE changes the SmartHQ API or the integration updates its entity naming, `scripts/trigger_oven.py` will start failing loudly (see Phase 6) rather than silently — that's the trigger to revisit Phase 2/3.

# Implementation Plan: Automated Oven Preheat Scheduler

**Goal:** Every Monday–Thursday, automatically start the GE Profile PHS930YPFS range at 6:00 AM Pacific in convection bake mode at 450°F, triggered by a job that fires at 1:00 AM Pacific.

**Status:** Draft plan for an agent/developer to execute step by step. Each phase has a concrete deliverable and a checkpoint before moving on. Do not skip Phase 0 — it determines whether the rest of the plan is even viable.

---

## Architecture summary

```
GitHub Actions (cron, Mon-Thu)  --gehomesdk (websocket)-->  SmartHQ cloud  -->  GE oven
      1:00 AM PT trigger              async_set_erd_value(OVEN_COOK_MODE, ...)
```

No Home Assistant, no self-hosted server. `gehomesdk` (https://github.com/simbaja/gehome) is a
standalone Python SDK that talks to GE's SmartHQ cloud directly — the same library Home
Assistant's own GE integration wraps, minus HA's integration framework. The GitHub Actions job
installs it, authenticates, and sends the "start convection bake at 450°F" command straight to
the appliance over SmartHQ's websocket API. Nothing needs to run 24/7.

Two things worth knowing up front:

1. **This uses an unofficial, reverse-engineered API**, not GE's public SmartHQ Developer Portal
   API (that public API only exposes basic toggles like Sabbath mode — no cook mode, no remote
   start). `gehomesdk` reverse-engineers the same internal API the SmartHQ mobile app itself
   uses. It's plain HTTPS/OAuth2 + websocket, actively maintained, but has broken from
   unannounced GE-side changes before (most recently an MFA login flow change, fixed within about
   a week). Expect the occasional silent-failure period until the community SDK catches up —
   Phase 6's failure notification exists specifically because of this.
2. **MFA can't be solved unattended.** If your SmartHQ account has MFA enabled, a fresh
   username/password login requires a one-time code — impossible for a cron job to satisfy. The
   design sidesteps this: a one-time interactive script logs in once (handling MFA if prompted)
   and obtains a long-lived refresh token, which is stored as a GitHub secret. The scheduled job
   authenticates with that refresh token, which never re-triggers MFA. If GE ever expires the
   refresh token, you re-run the interactive script once and update the secret.

---

## Phase 0 — Feasibility and safety check (do this before building anything else)

This phase exists because we don't yet know two things that would sink the project if wrong: whether GE requires a physical confirmation on the range before a remote start will actually fire, and what services this specific model exposes through SmartHQ.

1. Install the SmartHQ mobile app, sign in, and confirm the range shows up with remote control / Wi-Fi connect enabled.
2. From the app, manually trigger a remote preheat once, physically standing near the oven. Observe:
   - Does it start immediately, or does it wait for a button press / knob turn on the unit itself?
   - Is there a "remote enable" toggle that has to be re-armed each time, or is it persistent?
3. Record the result in `docs/SAFETY_NOTES.md` (template included in this repo).
4. **Decision gate:** if the oven requires physical confirmation every time, a fully unattended 6:00 AM start is not achievable as designed — stop and revisit scope (e.g., have it only pre-heat once confirmed some days, or use it as a reminder/notification instead of a hard auto-start) before investing further.

**Status: done.** Confirmed 2026-07-19 — remote preheat starts unattended, and remote-enable is a persistent (not per-session) setting. See `docs/SAFETY_NOTES.md`.

## Phase 1 — One-time auth setup: refresh token + appliance discovery

1. Install dependencies locally: `pip install -r requirements.txt`.
2. Run the interactive setup script, using the SmartHQ account credentials the oven is registered to:

   ```bash
   python scripts/get_refresh_token.py -u you@example.com
   ```

3. If your account has MFA enabled, the script will prompt for a one-time code sent via
   email/SMS — this is the only time in the whole system a human is needed for auth.
4. The script prints a refresh token — save it, you'll store it as a GitHub secret in Phase 3.
5. It then connects and lists discovered appliances by MAC address. Identify which MAC
   corresponds to the range (if it's the only GE smart appliance on the account, there will only
   be one). Record it in `docs/SAFETY_NOTES.md`.

Deliverable: a refresh token and the oven's MAC address, both recorded (refresh token
somewhere safe, not committed to the repo — it's a credential).

## Phase 2 — Manual test of the actual start command

Before wiring up scheduling, confirm the command itself works end-to-end:

```bash
cp .env.example .env   # fill in SMARTHQ_USERNAME, SMARTHQ_REFRESH_TOKEN, OVEN_MAC
export $(grep -v '^#' .env | xargs)
FORCE=1 python scripts/trigger_oven.py    # bypasses the time gate, fires immediately
```

Watch the oven (or the SmartHQ app) to confirm it actually enters convection bake preheat at
450°F. This is also when Phase 0's physical-confirmation question gets its final real-world
confirmation, using the exact code path production will use.

## Phase 3 — GitHub Actions secrets

In the repo: Settings → Secrets and variables → Actions, add:

- `SMARTHQ_USERNAME`
- `SMARTHQ_REFRESH_TOKEN`
- `OVEN_MAC`

See `docs/PROPOSAL.md` for the full reasoning behind the trigger design; summary of what's
implemented in `.github/workflows/trigger-oven.yml`:

- Cron runs every 15 minutes across an hour-wide UTC window that covers 1:00 AM Pacific in both PST and PDT, Monday–Thursday.
- The workflow calls `scripts/trigger_oven.py`, which checks the real current time in `America/Los_Angeles` and only proceeds if it's within a couple minutes of 1:00 AM — otherwise it exits as a no-op. This means the schedule never needs manual DST adjustment.

## Phase 4 — Failure notification

A silent failure here means a cold oven at 6 AM, which is worse than no automation at all — you won't know to intervene manually. Add a notification step so failures aren't silent:

- Simplest: a free [ntfy.sh](https://ntfy.sh) topic — one `curl` call in the workflow's failure step, push notification to your phone.
- Alternative: GitHub's own workflow-failure email notifications (on by default for the repo owner) — lower effort, less immediate.

Already wired up in `.github/workflows/trigger-oven.yml` as a step with `if: failure()`; set the
optional `NTFY_TOPIC` secret to enable the push notification.

## Phase 5 — Testing plan

1. Manually dispatch the GitHub Actions workflow (`workflow_dispatch` trigger, included) outside the 1 AM window and confirm the time-gate correctly no-ops.
2. Use `workflow_dispatch` with the `force` input (included) to bypass the gate and fire the oven immediately, so you can validate the whole chain in CI without waiting for 1 AM.
3. Let it run unattended for the first real Mon–Thu cycle, but verify manually (visually or via the SmartHQ app's history) that the oven actually reached temperature by 6 AM before fully trusting it.

## Phase 6 — Ongoing maintenance

- **GitHub disables scheduled workflows automatically after 60 days with no repository activity.** Since this repo may otherwise go untouched for months, either: (a) check in on it periodically, or (b) rely on the included keep-alive workflow (`.github/workflows/keep-alive.yml`) — a monthly commit that touches a timestamp file so the schedule never silently goes stale.
- If `SMARTHQ_REFRESH_TOKEN` ever expires or is revoked, `trigger_oven.py` will fail loudly (see Phase 4) rather than silently — re-run `scripts/get_refresh_token.py` and update the secret.
- If GE changes the SmartHQ API or `gehomesdk` updates its ERD codes/entity naming, `trigger_oven.py` will similarly fail loudly — watch for a `gehomesdk` release that fixes it (historically ~days to a week after a break) and bump the pinned version in `requirements.txt`.

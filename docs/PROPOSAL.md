# Proposal: Trigger Service for the 1:00 AM Oven Call

## Requirement

Something needs to fire a call at 1:00 AM Pacific, Monday through Thursday, that tells the oven to start convection bake preheat at 450°F (which itself gives it 5 hours to reach temperature by 6:00 AM). This document proposes and justifies both the trigger mechanism and how it talks to the oven; `docs/PLAN.md` has the phase-by-phase execution steps.

## How to talk to the oven

**Direct SmartHQ cloud call via `gehomesdk` — chosen.** `gehomesdk` (https://github.com/simbaja/gehome) is a standalone, actively maintained Python SDK for GE's SmartHQ-connected appliances. It authenticates to the same internal SmartHQ API the mobile app uses and sends commands over a websocket connection — no intermediary server required.

**Home Assistant + `geappliances-smarthq-integration` — considered, not chosen.** This was the original design. It works, but Home Assistant is a custom component that only runs inside a live HA instance — meaning a whole extra service needs to be hosted 24/7 (Raspberry Pi, VPS, or a paid Nabu Casa subscription) just to proxy a single scheduled API call. Investigating the integration's source showed it's built directly on top of `gehomesdk` itself — HA isn't doing meaningfully more work here (token refresh, MFA, websocket session management all live in `gehomesdk`), so it added infrastructure without adding capability for this use case. Worth reconsidering only if the project grows into wanting a full smart-home dashboard, other integrations, or a UI beyond "one scheduled action."

**GE's official public SmartHQ Developer Portal API — ruled out.** GE does publish a real OAuth2 API at developer.smarthq.com, but it only exposes basic toggles (Sabbath mode, control lock) and notification settings — cooking features (cook mode, temperature, remote start) are not in its scope. Not usable for this project regardless of hosting choice.

Trade-off being made explicitly by going the `gehomesdk` route: this rides an **unofficial, reverse-engineered API**. It's plain HTTPS/OAuth2 (no MITM/cert-pinning tricks needed), actively maintained, and used in production by a sizeable Home Assistant user base — but GE has changed the underlying API without notice before (an MFA login flow change broke it in June 2026, fixed within about a week). Phase 4 of the plan (failure notification) exists specifically so a break here is loud, not silent.

## MFA and authentication

SmartHQ accounts with MFA enabled can't complete a fresh username/password login unattended — a cron job has no way to receive or enter a one-time code. The design handles this by separating auth into two steps: a one-time *interactive* login (`scripts/get_refresh_token.py`), run once by hand, which completes any MFA challenge and produces a long-lived refresh token; and the *scheduled, unattended* run (`scripts/trigger_oven.py`), which authenticates using only that refresh token and never re-triggers MFA. If GE ever expires or revokes the refresh token, the fix is to re-run the interactive script once and update the stored secret — the same shape as rotating any long-lived credential.

## Trigger mechanism

**GitHub Actions scheduled workflow — chosen.** Lives in this repo, version-controlled, free. Two known weaknesses, both addressed below rather than ignored:

1. GitHub's `schedule` cron triggers are best-effort and can lag anywhere from a couple minutes to, during high load periods, 15+ minutes past the specified time.
2. GitHub automatically disables scheduled workflows on a repo after 60 days without any commits/activity — a real risk for a "set and forget" personal automation.

**External cron cloud service** (cron-job.org, EasyCron, AWS EventBridge) was considered as an alternative — more precise timing, doesn't depend on repo activity — but adds a third-party dependency for no real benefit over GitHub Actions here, given the timing slop this design tolerates anyway (see below). Not chosen, but a reasonable fallback if GitHub Actions timing proves too loose in practice.

## Design that addresses both weaknesses

**Timing slop:** instead of one cron fire at exactly 1:00 AM PT, the workflow runs every 15 minutes across a window that covers 1:00 AM PT regardless of DST (`0,15,30,45 8-9 * * 1-4` in UTC — 8:00–9:15 UTC, Mon–Thu). Each run calls `scripts/trigger_oven.py`, which checks the actual wall-clock time in `America/Los_Angeles` and only proceeds if it's within ~7 minutes of 1:00 AM; every other invocation is a fast no-op. Net effect: even if any individual GitHub-scheduled run is delayed, one of the six windows in that hour will land close enough to 1:00 AM, and the DST transition twice a year needs zero manual changes to the cron expression.

Trade-off being made explicitly: the oven's schedule start ends up accurate to roughly ±10–15 minutes of "1:00 AM triggers a 6:00 AM start," not to the second. Given the trigger call itself just starts a preheat that has 5 hours of runway before it needs to be at temperature, this slop is irrelevant to when the oven actually reaches temperature.

**60-day auto-disable:** documented as a known risk in `docs/PLAN.md` Phase 6, mitigated by `.github/workflows/keep-alive.yml` — a trivial monthly commit — rather than left as a silent failure mode. Safe to delete that workflow if you'd rather just calendar-remind yourself to check the repo every couple months.

## Secrets and configuration required

| Secret | Purpose |
|---|---|
| `SMARTHQ_USERNAME` | SmartHQ account email |
| `SMARTHQ_REFRESH_TOKEN` | Long-lived refresh token from `scripts/get_refresh_token.py` |
| `OVEN_MAC` | MAC address (appliance id) of the range, from the same script's discovery output |
| `NTFY_TOPIC` (optional) | ntfy.sh topic for push notification on failure |

All set under the repo's Settings → Secrets and variables → Actions. None should ever be committed to the repo; `.env.example` shows the shape without real values.

## Recommendation

Ship the GitHub Actions + `gehomesdk` design above. Phase 0 of the plan (verifying the oven doesn't require physical confirmation to remote-start) was the actual risk to the project and is now resolved — the remaining risk is the unofficial API breaking unannounced, which is a maintenance cost to accept and monitor for, not a reason to add Home Assistant back in.

# Proposal: Trigger Service for the 1:00 AM Oven Call

## Requirement

Something needs to fire a single HTTPS call at 1:00 AM Pacific, Monday through Thursday, that tells Home Assistant to run the "start convection bake 450°F" script (which itself schedules/starts the oven for 6:00 AM). This document proposes and justifies the trigger mechanism; the call it triggers is specified in `docs/PLAN.md` Phases 3–4.

## Options considered

**Native Home Assistant automation** — a `time` trigger inside HA itself, no external system involved. Most reliable option technically (no network hop, no third-party scheduler), and HA handles DST natively via its timezone config. Downside: it lives entirely in HA's own config, not in this repo, so it's not independently version-controlled, testable, or visible outside the HA instance. Rejected only because you asked for something callable/external — worth reconsidering later if the GitHub Actions approach proves annoying to maintain.

**External cron cloud service** (cron-job.org, EasyCron, AWS EventBridge) hitting an HA webhook. More precise timing than GitHub Actions and doesn't depend on a git repo's activity level. Downside: another third-party account/dependency, some of the free tiers are less reliable than GitHub's infrastructure, and it adds nothing over GitHub Actions for this use case since we're already building a repo. Not chosen, but a reasonable fallback if GitHub Actions timing proves too loose in practice.

**GitHub Actions scheduled workflow — chosen.** Lives in this repo, version-controlled, free, and matches what you asked for. Two known weaknesses, both addressed below rather than ignored:

1. GitHub's `schedule` cron triggers are best-effort and can lag anywhere from a couple minutes to, during high load periods, 15+ minutes past the specified time.
2. GitHub automatically disables scheduled workflows on a repo after 60 days without any commits/activity — a real risk for a "set and forget" personal automation.

## Design that addresses both weaknesses

**Timing slop:** instead of one cron fire at exactly 1:00 AM PT, the workflow runs every 15 minutes across a window that covers 1:00 AM PT regardless of DST (`0,15,30,45 8-9 * * 1-4` in UTC — 8:00–9:15 UTC, Mon–Thu). Each run calls `scripts/trigger_oven.py`, which checks the actual wall-clock time in `America/Los_Angeles` and only proceeds if it's within ~7 minutes of 1:00 AM; every other invocation is a fast no-op. Net effect: even if any individual GitHub-scheduled run is delayed, one of the six windows in that hour will land close enough to 1:00 AM, and the DST transition twice a year needs zero manual changes to the cron expression.

Trade-off being made explicitly: the oven's schedule start ends up accurate to roughly ±10–15 minutes of "1:00 AM triggers a 6:00 AM start," not to the second. Given the trigger call itself just arms a 5-hour-out scheduled start, this slop is irrelevant to when the oven actually reaches temperature — it only matters if you want the *triggering call itself* precisely timestamped, which nothing here depends on. If that assumption is wrong, say so and this can move to the external-cron-service option instead.

**60-day auto-disable:** documented as a known risk in `docs/PLAN.md` Phase 8, with a proposed mitigation (a trivial monthly keep-alive commit) rather than left as a silent failure mode. Recommend deciding at setup time whether to add the keep-alive workflow or just calendar-remind yourself to check the repo every couple months — either is fine, but pick one instead of assuming GitHub will "just work" indefinitely on a quiet repo.

## Secrets and configuration required

| Secret | Purpose |
|---|---|
| `HA_URL` | Base HTTPS URL of your Home Assistant instance (Nabu Casa remote URL or your own domain) |
| `HA_TOKEN` | Long-lived access token scoped to this automation |

Both set under the repo's Settings → Secrets and variables → Actions. Neither should ever be committed to the repo; `.env.example` shows the shape without real values.

## Recommendation

Ship the GitHub Actions version as designed above. Treat Phase 0 of the plan (verifying the oven doesn't require physical confirmation to remote-start) as the actual risk to the project — the trigger-timing mechanics here are a solved problem, but no scheduling design fixes an oven that refuses to preheat unattended for safety reasons.

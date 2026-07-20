# Safety & Feasibility Notes (fill in during Phase 0)

Complete this before building the rest of the automation — see `docs/PLAN.md` Phase 0.

## Remote start behavior

- [x] Date tested: 2026-07-19
- [x] Does the SmartHQ app successfully start a remote preheat with nobody touching the oven? Y
- [x] If N: what confirmation does the oven require (button press, knob turn, timeout window)? N/A — starts unattended.
- [x] Is "remote enable" a one-time setting or does it need to be re-armed each session/each day? One-time/persistent — no re-arming needed.

## Appliance discovery (Phase 1)

Record what `scripts/get_refresh_token.py` reports, so `OVEN_MAC` can be set correctly.

- [ ] Oven MAC address: `___________`
- [ ] Single or double oven (affects `OVEN_CAVITY` — upper/lower)?
- [ ] Refresh token obtained and stored somewhere safe (not committed to the repo)?

## Decision

- [x] Feasible as designed (fully unattended 6 AM start) — proceed with Phases 1-6.
- [ ] Not feasible as designed — document why and the fallback chosen (e.g. notification-only,
      or a start that still requires a morning tap).

# Safety & Feasibility Notes (fill in during Phase 0)

Complete this before building the rest of the automation — see `docs/PLAN.md` Phase 0.

## Remote start behavior

- [ ] Date tested:
- [ ] Does the SmartHQ app successfully start a remote preheat with nobody touching the oven? (Y/N)
- [ ] If N: what confirmation does the oven require (button press, knob turn, timeout window)?
- [ ] Is "remote enable" a one-time setting or does it need to be re-armed each session/each day?

## Entity discovery (Phase 2)

Record the real entity IDs Home Assistant generates for this range once the
integration is set up, so `homeassistant/scripts.yaml` can be filled in accurately.

- [ ] Cook mode select entity: `select.___________`
- [ ] Available cook mode options (exact strings):
- [ ] Temperature number entity: `number.___________`
- [ ] Start/trigger button entity: `button.___________`
- [ ] Any additional entities needed (e.g. a separate "remote enable" switch)?

## Decision

- [ ] Feasible as designed (fully unattended 6 AM start) — proceed with Phases 1-8.
- [ ] Not feasible as designed — document why and the fallback chosen (e.g. notification-only,
      or a start that still requires a morning tap).

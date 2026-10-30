# tri-planner (v0)

A weekly triathlon planner that fits training into the week you *actually* have:
where you are each day, what kit and facilities are there and when they're open,
and which time slots you genuinely train in. It learns from what you log, re-plans
when life happens, and measures one thing: **completed ÷ planned hours**.

This is v0 from the council plan: run it on yourself (n=1) from November to prove
the idea before anything gets built for other people.

## Setup

```bash
pip install -e ".[fit,dev]"      # Python 3.11+
```

## Weekly loop (~15 minutes a week)

1. **Edit your constraints** in `examples/joe.yaml` (copy it): locations, facilities,
   opening windows (school pool only 16:00–19:00), weekly slots, and date overrides
   for Canterbury weekends, holidays and exams.
2. **Plan the week** (Sunday evening):
   ```bash
   tri-plan week examples/joe.yaml --week 2026-11-09 --phase base
   ```
   Writes to `out/<week>/`: `plan.md`, `plan.ics` (import into Google Calendar),
   one `.FIT` workout per swim/bike/run (copy to the watch's `GARMIN/NewFiles`
   folder over USB, or import in Garmin Connect), and adds the week's rows to
   `out/log.csv`.
3. **Log every session** in `out/log.csv` (open in Google Sheets, then File →
   Download → CSV back to the same path): `status` = `done` / `skipped` / `moved`,
   `reason` = `no_time` / `facility_closed` / `body` / `feeling_off` / `other`,
   `actual_min`, and `pain` = `yes` if anything hurt. Leave it blank if you forgot;
   blanks are treated as unknown, not skipped.
4. **Life happened mid-week?** Re-plan the rest of it:
   ```bash
   tri-plan replan examples/joe.yaml --week 2026-11-09 --now 2026-11-11T19:00 \
       --injury run:2026-11-16            # declared niggle: no running until then
       --unavailable "2026-11-12|thu-16:15-18:15@School"   # slot gone (pool shut, exam)
       --flag bike-long                   # move this even though it's within 24h
   ```
   Sessions in the next 24h stay put unless flagged. Only what has to move, moves,
   each with a reason. Injured-discipline load moves to an allowed one and the lost
   minutes go into a debt ledger. Two pain reports in a row on a discipline pause
   it and tell you to see a physio — it never diagnoses.
5. **Check the numbers**:
   ```bash
   tri-plan report --log out/log.csv
   ```

## The experiment

`--experiment-start 2026-11-09` alternates facility-aware weeks with time-only
weeks (the planner ignores facilities, like most apps). The report compares
completion by week type. Council gate: **facility-aware must beat time-only by
≥10 points**, and your own completion needs to hold **≥50% for 6 weeks** (term
baseline ~15%). If not, the wedge isn't real.

## How it works

- `config.py` — locations, facilities, windows, slots, overrides (validated)
- `targets.py` — weekly minutes per discipline (sprint/Olympic × base/build/taper), +10% ramp cap
- `sessions.py` — session library, Key vs Flex, indoor substitutes via any-of facilities
- `solver.py` — OR-Tools CP-SAT: hard facility/window/overlap/hard-day constraints;
  maximises Σ P(complete | slot) × value, minus churn and same-day stacking;
  names the binding constraint when a week can't work
- `adherence.py` — log I/O and a Beta-Binomial completion estimate per slot
- `replan.py` — 24h freeze, churn penalty, reason codes, injury remap, debt ledger, pain freeze
- `store.py` — append-only `plan_session_version` history (JSON Lines)
- `export.py` — `.ics` calendar and `.FIT` structured workouts
- `report.py` — experiment schedule and completion report

## Quality gates

```bash
pytest && ruff check . && mypy src
```

27 acceptance tests, one per criterion in the council's acceptance contract (AC-001 → AC-027).

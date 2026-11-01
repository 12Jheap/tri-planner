# tri-planner (v0)

Triathlon training that fits the week you *actually* have: where you are each day,
what's there (pool, bike, treadmill), when it's open, and when you're free. It learns
which slots you really train in, re-plans when life happens, and measures one thing:
**completed ÷ planned hours**.

## Setup

Python 3.11+.

```bash
pip install -e ".[fit]"
```

## Quick start (5 minutes)

```bash
tri-plan init        # answer a few questions -> athlete.yaml
tri-plan week        # plan next week
tri-plan today       # what's on today, and how to do it
```

`init` asks for your race, the hours you want to train, where you train and what's
there (and when the pool's open), and your free times each day. No YAML needed. You
can still edit `athlete.yaml` by hand later, e.g. to add holiday templates (see
`examples/joe.yaml`).

## The weekly loop

| When | Command | What it does |
|---|---|---|
| Sunday evening | `tri-plan week` | Plans next week. Writes `out/<week>/plan.md`, `plan.ics` (import into Google/Apple Calendar) and one `.FIT` workout per swim/bike/run (copy to your Garmin's `GARMIN/NewFiles` folder, or import in Garmin Connect). |
| Each day | `tri-plan today` | Today's sessions with plain-English instructions. |
| After training | `tri-plan log` | Asks about each session so far: done / skipped / moved, minutes, did anything hurt. Enter skips one for later. One-liner: `tri-plan log --session bike-long --status done --min 80` |
| Any time | `tri-plan show` | The whole week with what you've logged. |
| Life happened | `tri-plan replan --unavailable thu-pm` | Re-plans the rest of the week. |
| End of week | `tri-plan report` | Completion by week, slot and sport. |

### Re-planning

```bash
tri-plan replan --unavailable thu            # lost all of Thursday
tri-plan replan --unavailable thu-pm         # or just the afternoon ("thu 16:30", thu-am, 2026-11-12)
tri-plan replan --injury run:10              # calf niggle: no running for 10 days (run = 7, run:2026-11-20 = until then)
tri-plan replan --clear-injury run           # you're back, or the physio has cleared you
tri-plan replan --flag bike-long             # move this even though it's within 24h
```

- Sessions in the next 24h stay put unless you flag them. Only what has to move moves,
  and each move gives a reason.
- An injury moves that sport's load to another sport and keeps a record of the minutes
  you owe. It's remembered for future weeks until it runs out or you clear it.
- Two pain reports in a row on one sport pause it and tell you to see a physio. The
  planner never diagnoses.
- A Key session you logged as **skipped** gets one catch-up if there's room. A session
  you just haven't logged is treated as unknown, not missed.

## How much it plans

- **Volume comes from your `weekly_hours`**, not your free time (defaults: sprint 7h,
  Olympic 9h). Build weeks add ~10%, taper cuts ~40%. It never fills more than 80% of
  your free time, and never jumps more than 10% above what you actually did last week
  (only counted if you logged at least 70% of it).
- **Phase is automatic** from `race_date`: taper in the last 2 weeks, build for the 8
  weeks before that, base otherwise. Override with `--phase`.
- **Session lengths are capped for your race.** Sprint: long run ≤ 60', long ride ≤ 2h,
  swims ≤ 60'. Olympic: long run ≤ 80', long ride ≤ 2h30. Extra volume becomes more
  sessions, not longer ones.
- **Key** sessions are protected; **flex** sessions move or drop first. If the long ride
  doesn't fit any slot this week, it's shortened to the longest slot that can take it.

Effort is out of 5: 2 = you can chat, 3 = short sentences, 4 = a few words, 5 = flat out.

## The experiment

`tri-plan week --experiment-start 2026-11-09` alternates facility-aware weeks with
time-only weeks (where the planner ignores facilities, like most apps do). `report` compares
the two. Gate: **facility-aware must beat time-only by ≥10 points**, and completion must
hold **≥50% for 6 weeks** (term baseline ~15%).

## Files

Everything lives in `out/` (change with `--out`):
`log.csv` (also opens fine in Google Sheets), `plan_session_version.jsonl` (every plan
version, never overwritten), `injuries.json`, and one folder per week.

## How it works

- `config.py`: locations, facilities, windows, slots, overrides (validated)
- `targets.py`: weekly minutes per sport from target hours, phase and a +10% ramp cap
- `sessions.py`: session library, race-specific length caps, plain-English instructions
- `solver.py`: OR-Tools CP-SAT. Hard facility/window/overlap/hard-day constraints;
  maximises Σ P(complete | slot) × value, minus churn and same-day stacking
- `adherence.py`: log I/O, keeping the log in sync with the plan, Beta-Binomial per slot
- `replan.py`: 24h freeze, churn penalty, reason codes, injury remap, debt ledger, pain freeze
- `store.py`: append-only plan history and remembered injuries
- `friendly.py` / `wizard.py`: plain-English inputs and the `init` questions
- `export.py`: `.ics` calendar and `.FIT` structured workouts
- `report.py`: experiment schedule and completion report

## Quality gates

```bash
pip install -e ".[fit,dev]"
pytest && ruff check . && mypy src
```

37 acceptance tests, one per criterion in `docs/acceptance-contract.md` (AC-001–027, AC-055–064).

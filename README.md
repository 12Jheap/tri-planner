# tri-planner (v0)

Triathlon training that fits the week you *actually* have: where you are each day,
what's there (pool, bike, treadmill), when it's open, and when you're free. It learns
which slots you really train in, re-plans when life happens, and measures one thing:
**completed ÷ planned hours**.

## Setup

Python 3.11+.

```bash
pip install -e ".[fit,web]"
```

## Quick start: the website (easiest)

```bash
tri-plan web
```

Windows says `'tri-plan' is not recognized`? Switch your virtual environment on first
(`.venv\Scripts\activate`, you'll see `(.venv)`), or run `python -m planner web`, which
always works. Every `tri-plan ...` command can be run as `python -m planner ...`.

Your browser opens at http://localhost:8000. The first time, it asks you to set up:
your race, your current fitness (5k time, swim CSS, FTP, heart rate: all optional), where
you train and what's there (and when the
pool's open), and when you're free each day. Then:

- **Today**: your sessions with how to do each one, and one-tap **Done it** / **Skipped**.
  Sessions from earlier in the week that you haven't logged show up underneath.
- **Week**: the whole week. Plan it, download the calendar file and Garmin workouts.
- **Changed**: tick the slots you can't make, pause a sport for an injury, or say you're
  back. It re-plans the rest of the week and shows what moved and why.
- **Progress**: completion per week and per sport, and which slots you actually train in.
- **Setup**: change anything, including holiday/exam dates. There's an advanced editor for
  the raw file too.

**On your phone:** run `tri-plan web --host 0.0.0.0`, find your computer's IP address
(Mac: System Settings → Wi-Fi → Details; Windows: `ipconfig`), and open
`http://<that IP>:8000` on your phone while it's on the same wifi. Add it to your
home screen. Only do this on wifi you trust, because anyone on it can open the page.

The website and the commands below use the same files, so you can mix them.

## Quick start: the terminal

```bash
tri-plan init        # answer a few questions -> athlete.yaml
tri-plan week        # plan next week
tri-plan today       # what's on today, and how to do it
```

`init` asks the same questions as the website's setup page. You can still edit
`athlete.yaml` by hand later, e.g. to add holiday templates (see `examples/joe.yaml`).

## The weekly loop (terminal)

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

## How the plan is made

**You say when you're free and how fit you are now. It does the rest.**

1. **Sessions.** Each phase has a menu of real sessions. *Base* has one quality
   session per sport (tempo run, sweet-spot ride, CSS swim) on top of long and easy
   aerobic work. *Build* adds threshold Key sessions, VO2 repeats and a brick. *Taper*
   keeps short race-pace openers and cuts the volume. Every 4th week before the race is
   a lighter recovery week. The phase comes from your `race_date`.
2. **Your zones.** A recent 5k time gives run paces; swim CSS (or a 400m + 200m time
   trial) gives swim paces; FTP gives bike watts; threshold or max heart rate gives HR
   ranges. Each session becomes a structured workout (warm-up, main set, cool-down), e.g.
   *12 min easy · 4 × 6 min threshold @ 4:09–4:22/km, 2 min jog · 8 min easy*. The same
   steps and targets go into your calendar and the Garmin .FIT files. With no numbers,
   targets are by feel.
3. **Fitting it in.** The solver puts each session in a free slot where the kit is
   open. It spreads quality days, keeps hard sessions off long-session days, keeps the
   long ride and long run on different days, and prefers weekends for long sessions.
   Then aerobic sessions **grow into spare slot time** up to the week's budget. Interval
   sessions keep their shape.
4. **How much.** The budget starts from what you train now (`current_hours`) and grows
   about 10% a week from what you actually logged. Free time is a ceiling, not a target:
   filling every free minute is the fastest way to get injured, so it won't. Race week
   is short, with nothing on race day. In a packed week (exams) it keeps the most
   valuable sessions instead of giving up.

Effort, when there's no number: 3–4/10 easy (full sentences), 6–7/10 tempo (short
sentences), 7–8/10 threshold (a few words), 9/10 VO2.

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
- `profile.py`: your fitness numbers and the zones they give (run pace, swim pace, watts, HR)
- `targets.py`: weekly minutes per sport from current training, phase, ramp, recovery weeks
- `sessions.py`: session menus per phase, Key vs Flex, min/ideal/max lengths, facility needs
- `workouts.py`: each session as warm-up, main set and cool-down with your targets
- `solver.py`: OR-Tools CP-SAT. Hard facility/window/overlap/hard-day constraints;
  maximises Σ P(complete | slot) × value, minus churn, stacking and bad session pairings;
  then fills spare slot time
- `adherence.py`: log I/O, keeping the log in sync with the plan, Beta-Binomial per slot
- `replan.py`: 24h freeze, churn penalty, reason codes, injury remap, debt ledger, pain freeze
- `store.py`: append-only plan history and remembered injuries
- `friendly.py` / `wizard.py`: plain-English inputs and the `init` questions
- `service.py`: every action (plan, log, re-plan) in one place, used by both front ends
- `web.py` + `templates/` + `static/`: the local website (Flask)
- `export.py`: `.ics` calendar and `.FIT` structured workouts
- `report.py`: experiment schedule and completion report

## Quality gates

```bash
pip install -e ".[fit,web,dev]"
pytest && ruff check . && mypy src
```

49 acceptance tests, one per criterion in `docs/acceptance-contract.md` (AC-001–027, AC-055–076).

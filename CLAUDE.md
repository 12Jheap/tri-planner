# tri-planner

Facility-aware triathlon weekly planner. v0 = a Python CLI the founder (Joe, junior
triathlete, Garmin user) runs on himself to test one thesis: planning around *where you
are and what kit/facilities are open* raises **completed ÷ planned hours**.

## Context
- `docs/design.md` — verdict, positioning, phase plan with go/kill gates
- `docs/prd.md` — user stories (v0 = US-001..006, US-014..018; v1 hosted app = US-007..013)
- `docs/acceptance-contract.md` — AC-001..AC-088; AC-001..027 and AC-055..088 verified
  (US-014 usability, US-015 web app, US-016 sessions, US-017 import/season/move,
  US-018 strength opt-out, auto-sync, recovery check, Garmin HR, effort check)
- `docs/competitor-research.md` — competitor matrix and sources

## Scope rules
- v0 only until the Feb 2027 gate (own completion ≥50% for 6 weeks; no rival handles the
  scripted two-location week). Don't start v1 (web app, Stripe, Garmin push) without being asked.
- Out of scope: native app, AI chat coach, long-course, ML beyond the Beta-Binomial prior,
  Strava data, users under 18, injury diagnosis or "injury prevention" claims.
- Hard constraints are never broken: no session where its facility is missing or closed.

## Code
- `src/planner/`: config, profile (fitness numbers -> zones), targets, sessions (library +
  menus per phase), workouts (warm-up/main set/cool-down with targets), solver (OR-Tools CP-SAT
  + slot filling), adherence,
  replan, store (append-only JSONL + injuries), export (.ics/.FIT), report,
  activities (FIT import + matching to the plan), garmin (Personal API sync),
  wellness (sleep/HRV/resting HR -> recovery check, plain rules),
  friendly (plain-English CLI inputs), wizard (`init`), service (shared actions: the CLI
  and the web app both call `Workspace`), web (Flask app, templates/, static/), cli
- `tri-plan web` is a local, single-athlete site. It is not v1: no accounts, hosting or payments.
- Volume = what the athlete trains now, ramped ~10%/week from logged work, capped by free time.
  Don't reintroduce "fill every free minute": it's the fastest route to injury.
- Garmin key: only from `GARMIN_PERSONAL_API_KEY` or `~/.config/garmin/connect-personal-api-key`
  (0600). Never write it into the repo, the config or `out/`. Tests must not touch the real home
  (tests/conftest.py hides any real key).
- Garmin's JSON field names aren't documented to us: read them defensively (`wellness.find`),
  treat missing as "not available", and never change the plan without the athlete confirming.
- Every test is named `test_ac_NNN_...` and maps to a criterion in the contract. Keep that mapping.
- Example athlete config: `examples/joe.yaml` (holiday/exam dates are placeholders)

## Commands
```bash
pip install -e ".[fit,web,garmin,dev]"   # garmin needs Python 3.12+
pytest && ruff check . && mypy src     # all three must pass before committing
tri-plan week examples/joe.yaml --week 2026-11-09    # phase auto from race_date
tri-plan web examples/joe.yaml                       # local site on http://localhost:8000
python -m pytest                                     # if a stray `pytest` binary uses another Python
```

## Style
- Python 3.11+, typed, pydantic models, ruff line length 100
- Explain things to Joe plainly and briefly; he's a sixth-former, strong at maths, OOP-level Python

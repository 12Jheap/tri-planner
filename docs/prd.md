# PRD: Facility-aware triathlon planner ("Runna for tri")

Session: triathlon-app-like-runna-20261030-1759 · Design: design.md · 30 Oct 2026

## Overview

A weekly triathlon planner that builds and rebuilds the plan around the time, location, facilities and kit an athlete *actually* has, and proves it works by raising **completed ÷ planned hours**. Schedule and HRV adaptation are table stakes; facility/kit-aware placement plus a per-athlete adherence model is the wedge. Sold globally in English to adult sprint/Olympic triathletes; UK + US marketing first.

Two stages:
- **v0 — Engine on yourself (Nov 2026 → Apr 2027, ~2h/week, n=1).** Python script + config files + a Google Sheet log. No app, no users.
- **v1 — MVP web app (Jul → Dec 2027).** Installable PWA, free uni-club beta Oct–Dec, paid launch Jan 2028. Only built if v0 and the July concierge test pass their gates (design.md › Phase Plan).

## Goals

- v0: Joe's own completed ÷ planned hours ≥50% for 6 consecutive weeks (baseline ~15% in term).
- v0: Show facility-aware weeks beat time-only weeks on completion (input to the July concierge test).
- v1: Week 1 visible in ≤3 minutes, before paywall or install.
- v1: Concierge/beta median completed ÷ planned ≥70%; ≥50% of beta users still logging at week 6.
- v1: ≥30% of strangers on the waitlist pre-pay; ≥100 paying by 31 Mar 2028.

## Non-Goals

- Native iOS/Android app, watch app, widgets
- AI chat coach or LLM-generated plans
- Full Ironman (half distance added in US-019) and first-timer onboarding
- ML models beyond the Beta-Binomial adherence prior (no LightGBM/PyMC until v2, 1k+ users)
- HRV-driven automatic changes (v2; v1 readiness is self-reported)
- Phone health-store sync (a PWA can't read Apple Health / Health Connect)
- Strava data in any form
- Users under 18
- Injury diagnosis or "injury prevention" claims

## Quality Gates

- `pytest` — tests pass
- `ruff check .` — lint
- `mypy src` — type check
- v1 only: `pytest tests/e2e` (Playwright) — onboarding and Today-card flows

## User Stories

### v0 — Engine on yourself

### US-001: Constraint model — locations, facilities and slots
**Description:** As an athlete, I want to describe each place I train (school/term, home, travel) with its facilities, kit and time windows so that the plan never puts a session where I can't do it.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Accepts a YAML file defining locations, each with facilities (pool, wattbike, treadmill, road bike, gym) and per-facility opening windows (e.g. pool only after 16:00)
- [ ] Accepts a weekly calendar mapping each day to a location and listing available time slots
- [ ] Rejects config with overlapping slots or unknown facility names, with a clear error
- [ ] Supports date-range overrides (holiday block, exam week, travel)

### US-002: Load targets and session library
**Description:** As an athlete, I want weekly per-discipline targets from simple coaching rules so that the planner knows what a good week contains.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Returns weekly minutes per discipline for a sprint or Olympic template given phase (base/build/taper) and available hours
- [ ] Caps week-on-week load increase at a configurable ramp (default 10%)
- [ ] Each session has type, duration, intensity, required facilities, and a Key or Flex flag
- [ ] Session library includes indoor substitutes (wattbike for road bike, treadmill for outdoor run)

### US-003: Weekly planner (CP-SAT)
**Description:** As an athlete, I want the week placed into my real slots so that I get a plan I can actually complete.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Never places a session in a slot whose location lacks its required facility or is outside opening hours (hard constraint)
- [ ] Never places two hard sessions on consecutive days or a session overlapping another
- [ ] Objective maximises Σ P(complete | slot) × session value
- [ ] Returns a plan within 10 seconds for a 7-day, 30-slot week
- [ ] Returns "infeasible" with the binding constraint named when targets can't fit

### US-004: Logging and adherence model
**Description:** As an athlete, I want to tick each session Done / Skipped / Moved with a reason so that the planner learns which slots I really use.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Reads a Google Sheet (or CSV export) log with planned session ID, status, reason code, actual minutes
- [ ] Maintains a Beta-Binomial completion estimate per slot (day × time window × location), starting from a configurable prior
- [ ] Treats unlogged sessions as censored, not skipped
- [ ] Reports weekly completed ÷ planned hours and flags if logging response rate is below 70%
- [ ] Stores every completion row with a `source` field (manual / file / garmin_personal)

### US-005: Stable re-planning and injury substitution
**Description:** As an athlete, I want the rest of the week rebuilt when life or a niggle happens, without the whole plan reshuffling.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Freezes sessions in the next 24 hours unless the athlete flags them
- [ ] Penalises churn: a re-plan moves the fewest sessions needed, and every move carries a reason code
- [ ] An injury flag on a discipline (e.g. calf → no running for N days) remaps its load to allowed disciplines and records the shortfall in a per-discipline debt ledger
- [ ] Two consecutive pain reports freeze that discipline and output a "see a physio" message
- [ ] Every plan version is appended (never overwritten) to a `plan_session_version` table

### US-006: Export and experiment report
**Description:** As an athlete, I want the week on my calendar and watch, and a weekly report proving whether facility-awareness helps.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Exports the week as an .ics file with one event per session (title, duration, location, description)
- [ ] Exports structured workouts as .FIT files where the session type supports it
- [ ] Experiment mode alternates facility-aware and time-only weeks on a fixed schedule
- [ ] Weekly report shows completion ratio by week type, by slot, and by discipline

### US-014: Everyday usability and sane training load
**Description:** As an athlete who isn't a programmer, I want to set up, plan, log and re-plan in plain English, and get a training load a coach would sign off, so I keep using it.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Weekly volume starts from what the athlete trains now and ramps from what they actually did; free time is only a ceiling (build +10%, taper −40%) — amended 1 Nov 2026: no target-hours input
- [ ] No session exceeds the race-appropriate cap for its kind (e.g. sprint long run ≤ 60')
- [ ] A Key session too long for every slot is shortened to the longest slot that can host it, with a note, instead of failing the week
- [ ] After a plan or re-plan the log matches it: unlogged rows follow moves, dropped sessions are removed, logged rows never change
- [ ] A re-plan keeps earlier sessions in the stored week and only reschedules Key sessions logged as skipped, as Flex catch-ups
- [ ] `init` builds a valid config from plain answers (no YAML knowledge), and unquoted YAML times like 6:30 load as 06:30
- [ ] Plain-English inputs: --week this/next, --injury run[:days|:date], --unavailable thu / thu-pm / "thu 16:30" / a date
- [ ] `log` records done/skipped/moved with minutes, reason and pain, by asking one session at a time or in one line
- [ ] Declared injuries persist across commands, apply when planning a new week, and can be cleared (which also lifts a pain freeze)
- [ ] `today` shows today's sessions with plain-English instructions, and the phase is picked from the race date

### US-015: Local web app
**Description:** As an athlete, I want to plan, log and re-plan from a web page on my laptop or phone instead of the terminal. It's single-athlete and runs on my own computer: no accounts, no hosting, no payments (that's still v1).
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] `tri-plan web` serves Today, Week, Changed, Progress and Setup; with no config the first page is Setup
- [ ] The setup form creates and edits the config without YAML; bad input is rejected with a reason and the file is left alone; an existing config round-trips unchanged
- [ ] Planning a week from the website writes the same plan, .ics, .FIT and log as the CLI, and offers the .ics and a .zip of workouts to download
- [ ] From Today or Week: Done (minutes, something hurt, another time), Skipped with one reason tap, and Undo
- [ ] "Something's changed" re-plans from ticked slots, a new or cleared injury and flagged sessions, and shows a receipt for every move
- [ ] Every form needs the page's secret token, so another website open in your browser can't change your plan or log

- [ ] With no settings file or a broken one (and the real clock, as on a fresh install), every page reaches Setup in one redirect and says what's wrong; no page ever redirects to itself

### US-016: Personalised sessions planned into your availability
**Description:** As an athlete, I want to say when I'm free and how fit I am now, and get real sessions (tempo, threshold, CSS, bricks) with my own paces, watts and heart rates, fitted into those slots, so the plan feels like it was written for me.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] A 5k time, swim CSS (or 400m + 200m time trials), FTP and threshold or max HR give personal run pace, swim pace, bike power and HR zones that don't overlap; missing numbers fall back to effort; impossible numbers are rejected
- [ ] Base has tempo, sweet-spot and CSS work; build adds threshold Key sessions plus VO2 and a brick; taper keeps short race-pace openers; every 4th week before the race is a lighter recovery week with no hard sessions
- [ ] Every session is a structured workout (warm-up, main set, cool-down) that adds up to its planned length, with targets from your zones, and the same steps and targets go into the calendar event and the .FIT file
- [ ] Sessions are fitted into your free slots and aerobic sessions grow into spare slot time up to the week's budget, never past a session's maximum, the next session, or a facility's opening hours; volume grows from what you train now and what you actually did
- [ ] Across a real season: no hard session on the same day as a long one, long ride and long run on different days, nothing on race day, and a packed exam week keeps its most valuable sessions instead of failing
- [ ] The profile page asks for current fitness and shows your zones; each session page shows why, a zone timeline and every step with your targets; the interface uses no emoji

### US-017: Less logging, season view, moving sessions, the experiment
**Description:** As an athlete, I want my watch to do the logging, to see the whole season to race day, to move a session myself when I know better, and to run the facility-aware experiment from the website, so the 6-week test actually happens.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] The experiment is switched on from the Profile page: weeks then alternate facility-aware / time-only, test weeks are labelled, and the season shows which is which
- [ ] The season view lists every week to race day with its phase, recovery weeks, holidays and exams, what was planned and done, and the volume the planner is heading for (≤10%/week growth, a ceiling for the distance, never more than free time)
- [ ] You can move a session to any later slot where its kit is open and there's room; the plan, log and files follow, a logged session can't be moved, and breaking a coaching rule is allowed but flagged
- [ ] Activity files (.fit, a .zip export, or a folder) tick off the matching planned session: same sport and week, same day = done, other day = moved; a brick's run leg is merged; extras are reported, not forced in; nothing is imported twice and sessions you logged yourself are left alone
- [ ] "Sync from Garmin" uses Garmin's Personal API client with your key from ~/.config/garmin or GARMIN_PERSONAL_API_KEY, downloads recent activities' original files and ticks off sessions; no key or a refused key gives a plain message; the key is stored readable only by you and never in the project
- [ ] On Today you can sync from Garmin or add activity files; imported sessions show time, distance and heart rate, and you can still say something hurt

Note: this uses Garmin's **Personal API** (one athlete's own data, pulled with a personal
key), which fits v0. US-013's push integration via the Training/Health APIs stays v1.

### US-018: Strength opt-out, auto-sync, recovery check, Garmin heart rates, effort check
**Description:** As an athlete, I want to drop sessions I'll do elsewhere, have Garmin do the syncing without me pressing anything, get a plain recovery check each morning, reuse the heart rates Garmin already knows, and be told when my easy days weren't easy.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Profile lets you opt out of strength sessions; none are planned and their time goes to swim, bike and run, so the week isn't shorter
- [ ] Opening Today syncs with Garmin in the background at most every 30 minutes (activities and this morning's recovery data); the time of the last sync is shown, and a failed sync never breaks the page
- [ ] The recovery check reads last night's sleep, HRV and resting heart rate from Garmin and applies three plain rules (2+ flags = low, 1 = watch, 0 = good); missing data is "not available", never an alarm
- [ ] On a low-recovery day with a quality session planned, Today offers to make it easy (same time, place and sport, easy effort); nothing changes unless you press it, and logged or already-easy sessions can't be eased
- [ ] Your threshold, max and resting heart rate can be read from Garmin; they are shown next to your current values and only saved when you tick and confirm, and your zones follow
- [ ] When your watch's average heart rate for an easy session was above your easy zone, the session says so; hard sessions and sessions without heart rate aren't flagged

Note: the recovery check offers a change and never makes one. It is the athlete's own
signals, not a diagnosis (no injury or "injury prevention" claims). Plain rules only.

### US-019: Half distance
**Description:** As an athlete, I want to train for a half (1.9km / 90km / 21.1km) with the volume, long sessions and double days it needs, without the plan getting reckless.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Half distance is a race option (Profile and init) with bike-heavy splits, more volume (10h default, ramping to a 16h ceiling), a 12-week build, and a clear note that half-iron races need you to be 18
- [ ] Half sessions go long-course: long rides up to 4h, long runs up to 2h with fuelling notes, a long brick as a Key build session with a proper run off the bike, and race-pace (tempo) work rather than sprint-style VO2
- [ ] A half week on a school timetable uses double days when it needs to, never two sessions of the same sport in a day (a brick counts as a run), keeps the long ride and long run on different days and puts them at the weekend when the slots allow

Note: added at Joe's request (scope change, 1 Nov 2026). Full Ironman stays out of scope.
Half-iron races require athletes to be 18 on race day; the app says so where the race is chosen.

### US-020: Season and plan agree; half workouts are race-specific
**Description:** As an athlete, I want the volume Season shows for a week to be what I get when I plan it, and my half-distance sessions to train half-distance race efforts, not longer Olympic sessions.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Planning any week targets the same volume the Season view shows for it (one shared rule); weeks planned far ahead say they assume you complete the weeks before, and a past week you didn't log holds volume flat instead of growing it
- [ ] Half workouts differ from Olympic ones: race-effort blocks (76–83% FTP) in the long ride, a half-marathon-pace finish to the long run, longer CSS reps, long sweet-spot intervals and a brick that runs at half-marathon effort, with the same targets on the watch

### US-021: Sessions fit short slots and the week spreads out
**Description:** As a student with short school-day slots and long weekends, I want weekday slots used and the weekend not overloaded, so the plan is one I can recover from.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] A session too long for a slot can run there shortened, down to its sensible minimum (a Key session that fits nowhere at all is rescued shorter with a note); full length is used whenever it fits, and the shortened workout still adds up
- [ ] On a timetable of short weekday slots and long weekends, weekday slots are used, quality sessions go midweek, the long ride and long run take different weekend days, and no weekend day carries two long sessions or more than its fair share plus the long session

### US-022: Run it as a home server you can trust
**Description:** As an athlete running the planner on an old laptop at home, I want my data backed up, a proper server, a calendar that keeps itself current and an icon on my phone, so it behaves like an app I can rely on.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] A backup zip of your settings and history is written once a day when the site is used (newest 14 kept), can be downloaded from Profile and made with `tri-plan backup`; it never holds the Garmin key, old backups or the server log
- [ ] `tri-plan web` serves with a production server (waitress) when it's installed and falls back to Flask's when it isn't, writing a backup as it starts; Windows start and update scripts are included; the site can be added to a phone's home screen (manifest + icons); Profile shows the running version
- [ ] The site offers one calendar link to subscribe to: it holds last week, this week and every planned week after, and reflects re-plans and moved sessions without downloading anything again

### US-023: Fitness tests keep your zones current
**Description:** As an athlete, I want the plan to test my fitness every 8 weeks (and straight away when a number is missing), so my paces, power and HR targets keep up with me instead of going stale.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] A fitness test is planned when a number is missing or 8+ weeks old, in place of that sport's quality session; at most two in a week; never in a recovery, taper, race or time-only week, for a paused sport, for something you can't measure, or when switched off
- [ ] Test sessions are real protocols (a 5 km time trial as a distance step, a 20-minute all-out bike test, a 400 m + 200 m swim test) and only go where they can be measured: a pool for the swim, the wattbike for power
- [ ] After a test, Today asks for the result; saving it updates the number (CSS from the 400 m and 200 m times, FTP as 95% of the 20-minute power), the date measured, your zones, the history and this week's calendar and watch files; a bad result changes nothing; the next test is due 8 weeks later
- [ ] Changing a fitness number on Profile counts as measuring it today (unchanged numbers keep their dates), and fitness tests can be switched off there

### US-024: Effort and training load
**Description:** As an athlete, I want to say how hard each session felt (or have my watch say it), so the plan sees what a week took out of me and holds back after a very hard one.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Marking a session done asks how hard it felt (1-10, optional); a session logged without it can be rated later with one tap; the command line takes --effort; anything outside 1-10 is refused
- [ ] If you answer the watch's "how did that feel?" question, that effort score arrives with the imported activity (Garmin's 10-100 scale becomes 1-10); an activity without one leaves effort blank
- [ ] A week's load is minutes x effort (unrated sessions count at the week's average and it says so); a jump of more than 30% on recent weeks is flagged; a week that felt very hard (average 7.5+ over at least 3 rated sessions) makes the next week hold its volume instead of adding 10%, on Season and in the plan alike, with a note saying why

### US-025: A weekly rhythm: review the week, plan the next
**Description:** As an athlete, I want an honest look back at each week and a nudge to plan the next one, so the weekly loop happens without me having to remember it.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] From Friday, Today offers to plan next week if it isn't planned yet (one tap); not earlier in the week, not once it's planned, and not when you're looking at another day
- [ ] Once a week is over (or on its Sunday) the Week page reviews it: share of planned time done, key sessions done, each sport, average effort, what was skipped and why, one plain verdict, and a button to plan next week; if too little is logged it says it can't judge

Note: US-022..025 were chosen as the next steps after US-021 (17 Nov 2026); see `docs/roadmap.md`.

### v1 — MVP web app (only if gates pass)

### US-007: 3-minute onboarding to week-1 preview
**Description:** As a time-crunched adult, I want to see my first week in under 3 minutes so that I know it fits my life before I pay.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Onboarding asks only: race + date, 5k/10k time, 100m swim pace, FTP (optional), locations with facilities, weekly slots
- [ ] Displays a full week-1 plan before any paywall or install prompt
- [ ] Median onboarding time ≤3 minutes in usability tests (n≥5)
- [ ] Offers ready-made location profiles (Work week, Work trip, Home, Family holiday)

### US-008: Today card and logging
**Description:** As an athlete, I want one-tap Done / Skipped / Moved so that logging takes seconds.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Today card displays today's sessions with Done / Skipped / Moved buttons at thumb height (≥48px targets)
- [ ] Skipped requires exactly one reason tap (No time / Facility closed / Body / Feeling off)
- [ ] An unlogged session triggers one prompt next morning and is never auto-marked skipped
- [ ] Today card works offline and syncs when back online

### US-009: Change receipts and Undo
**Description:** As an athlete, I want to see what changed and why so that I trust a plan that moves.
**Agent:** Advocate
**Acceptance Criteria:**
- [ ] Every automatic change displays a one-line receipt (what moved, why) with Undo
- [ ] Changes to Key sessions or readiness-driven changes ask for confirmation first
- [ ] Tomorrow's sessions lock at 21:00 local time

### US-010: Reminders and calendar
**Description:** As an athlete, I want sessions in my calendar and a nudge before them.
**Agent:** Herald
**Acceptance Criteria:**
- [ ] Provides a subscribable .ics feed URL that updates after every re-plan
- [ ] Offers PWA install only after the week-1 preview, with an iOS Add-to-Home-Screen walkthrough
- [ ] Sends a web push reminder at a user-chosen time before each session (installed PWA only)

### US-011: Billing
**Description:** As a founder, I want season-based subscriptions so that the business works in a seasonal sport.
**Agent:** Herald
**Acceptance Criteria:**
- [ ] Stripe Checkout supports £79.99/yr, £12.99/mo and Founding-250 £59.99/yr, plus USD/EUR equivalents
- [ ] 14-day trial; cancellation in two taps; no plan is ever stranded within 14 days of a race
- [ ] Free off-season mode keeps the account and history after a subscription lapses
- [ ] Trial→paid is tracked by segment (student/adult) and sync method (file/Garmin)

### US-012: Safety, privacy and compliance
**Description:** As a founder, I want the legal basics right before the first outside user.
**Agent:** Skeptic
**Acceptance Criteria:**
- [ ] Rejects sign-up when date of birth gives age under 18
- [ ] Collects explicit consent for health data (readiness, injury) separately from terms
- [ ] User can export all their data (JSON/CSV) and delete their account from settings
- [ ] Injury input is user-declared only; no copy anywhere claims diagnosis or injury prevention
- [ ] DPIA written and ICO registration done before beta (manual check)

### US-013: Garmin integration (behind a flag)
**Description:** As a Garmin owner, I want sessions on my wrist without manual imports.
**Agent:** Alchemist
**Acceptance Criteria:**
- [ ] Core loop (plan, log, re-plan) works with the Garmin flag off
- [ ] When enabled, pushes only changed sessions to Garmin via the Training API after each re-plan
- [ ] Garmin-sourced activity rows are tagged `garmin_api` and excluded from pooled cross-user estimates
- [ ] Go/no-go recorded on 1 Sep 2027 based on developer-programme approval

## Technical Notes

- **v0 layout:** `src/planner/` — `config.py` (pydantic models for locations/slots), `targets.py`, `solver.py` (OR-Tools CP-SAT), `adherence.py` (scipy Beta), `replan.py`, `export.py` (icalendar; .FIT via Garmin's FIT SDK), `report.py`. Config in YAML; log in Google Sheet exported to CSV (or read via `gspread`). Personal Garmin key via `requests` + `fitdecode` is optional for v0.
- **v1:** FastAPI + Postgres (SQLAlchemy/Alembic), cron worker for re-plans, server-rendered Jinja + HTMX as an installable PWA (keeps the stack in Python), `pywebpush`, Stripe, `authlib` + `httpx` for Garmin OAuth. The v0 engine becomes the `planner` package imported by the API unchanged.
- **Data model (from day one):** `athlete`, `location`, `facility`, `slot`, `plan_session_version` (append-only), `completion` (with `source`, `reason_code`), `adherence_prior`.
- **Solver objective:** maximise Σ_s Σ_k x[s,k] · P̂(complete | k) · value(s) − λ · churn, subject to facility, window, overlap, hard-day-spacing and per-discipline target constraints.

## Dependencies

- Python 3.11+, `ortools`, `pydantic`, `pyyaml`, `pandas`, `scipy`, `icalendar`, `pytest`, `ruff`, `mypy`
- Garmin FIT SDK (writing .FIT); Garmin Connect Developer Program approval (v1, optional)
- Stripe account; ICO registration; liability-insurance quote before charging

# Roadmap

The one question v0 has to answer by **Feb 2027**: does planning around where you are and
what's open raise **completed ÷ planned hours**? Gate: your own completion ≥50% for 6 weeks
in a row, facility-aware weeks beating time-only weeks by ≥10 points, and no rival handling
the scripted two-location week. Everything below is ranked by how much it helps answer that.

## Done (17 Nov 2026)

| Story | What it gives you |
|---|---|
| US-022 Home server | Daily backups (14 kept) + download from Profile + `tri-plan backup`; waitress instead of Flask's dev server; Windows start/update scripts; add-to-home-screen icon; one calendar link that stays current; version on Profile. Guide: `docs/server.md` |
| US-023 Fitness tests | A 5k TT, 20-min FTP test or 400/200 m swim test replaces that sport's quality session when a number is missing or 8+ weeks old (max two a week; never in recovery, taper, race, time-only or injured weeks). Enter the result and every zone, calendar and watch file updates. Progress shows the history |
| US-024 Effort and load | 1–10 effort on every log (or from the watch's "how did that feel?"). Weekly load = minutes × effort, with a flag for a >30% jump. A week averaging 7.5+ holds next week's volume instead of adding 10% |
| US-025 Weekly rhythm | Each finished week gets a review on the Week page (done vs planned, key sessions, per sport, skips and why, one honest verdict). From Friday, Today offers to plan next week |

## Next (before the gate)

1. **Run the experiment for real.** Switch it on (Profile), log every session for six
   weeks, let Garmin sync do the typing. No code fixes a missing log. *(You)*
2. **Race plan for the half.** In race week: swim/bike/run targets from your zones,
   fuelling per hour, transition checklist, as one page and a watch workout.
3. **Learn from skip reasons.** If one slot keeps being skipped for "facility closed" or
   "no time", suggest changing or dropping it on Profile. Suggest only: the athlete confirms.
4. **Check Garmin wellness fields on a real account.** Sleep/HRV/resting-HR are read
   defensively because Garmin's names aren't documented to us; confirm them on your data.
5. **Optional site password** for anyone who runs it beyond Tailscale. Low priority while
   it's only you.
6. **Merge this branch to main** once you're happy with it on the laptop.

## Later (only if the gate passes: v1)

Hosted app with accounts, payments, Garmin Training API push, other athletes' data for the
adherence prior. Each needs its own go-ahead; see `docs/prd.md` US-007..013.

## Not doing

AI chat coach, full Ironman, Strava data, users under 18, ML beyond the Beta-Binomial
prior, injury diagnosis or "injury prevention" claims, and "fill every free minute".

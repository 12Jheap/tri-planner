# Design Document: Runna-style triathlon training app

Council session `triathlon-app-like-runna-20261030-1759` · 30 Oct 2026 · Strategist, Scout, Skeptic, Alchemist, Advocate, Herald · 3 rounds, all six agents shifted position in Round 2.

## Overview

**Verdict: viable as a portfolio project that can become a real bootstrapped business with an acquisition exit. Not venture-scale, and the "little competition" premise is wrong.**

The tri-app market is not empty. 12+ adaptive/AI tri coaches are live (Humango, TriDot, MOTTIV, Athletica, AI Endurance, Transition, TrainerRoad, TrainingPeaks plans, newer AI entrants), Garmin gives away a free adaptive Triathlon Coach (sprint to 70.3) and bought TrainingPeaks (Jul 2026). Adapting to missed sessions and HRV/sleep is table stakes, and the £10–20/month price point is exactly where incumbents already sit.

The one gap every agent agreed is real: **no product plans around which facilities and kit you have, where, and when** (pool hours, wattbike vs road bike, term vs home vs travel), and none substitutes across disciplines on injury while keeping load. It has gone unsolved for years (Athletica's 2024 constraint beta failed; Garmin Coach has had no facility model since 2018). That is a **wedge** (the reason to switch), not a **moat** (~6–18 month lead before a capable incumbent copies). The only possible moat is *proven* adherence: "the plan you'll actually complete", measured by completed ÷ planned hours, plus the first-party data log that proves it.

Market ceiling (revised after founder pushback — see below): sell globally in English from day one. GB ~120k racing triathletes + US ~303k unique active USA Triathlon members (2025) ≈ 420k in two markets; adding Europe, Australia and Canada plausibly takes it towards ~1M (estimate, not data). At £79.99/yr: 1% of US+UK ≈ £340k ARR; 1% of ~1M ≈ £800k; 3% ≈ £2.4M. That's a real bootstrapped business with a credible acquisition exit after 2+ seasons of proven retention — still not VC-scale.

## Founder Pushback (30 Oct 2026) — what changed

| Founder point | Council response | Change |
|---|---|---|
| Why only the UK market? | Fair. UK was only ever the marketing beachhead, not the ceiling. | Ceiling recomputed globally (above). Product launches in English with £/$/€ pricing; marketing starts UK + US. |
| Garmin plans are fixed and web-only | Partly wrong. Garmin's own blog calls Triathlon Coach adaptive (sleep, recovery, fitness) and sign-up is in the Garmin Connect app. But forum users report opaque, erratic changes (e.g. a 2h bike flipping to a rest day hours later), training-day selection is only documented for Run Coach, and there's no facility/kit model at all. | Garmin stays the main free rival, but the pitch sharpens: "Garmin adapts to your body; we adapt to your actual week." |
| Garmin hasn't done anything with TrainingPeaks | True so far — acquired July 2026, three months ago. | Downgraded from product threat to forward-looking platform risk (Garmin controls the biggest coach platform *and* the data pipe). |
| Strava/Runna is irrelevant, run-only | Correct as a competitor. | Removed from the competitor set. Kept only as the UX benchmark and as exit precedent (Strava bought a plan app; it's a likely buyer or multisport entrant). |

## Product

**Positioning:** "A plan for the week you actually have." Facility/kit-aware weekly re-planner for time-crunched adult sprint/Olympic triathletes.

**Beachhead (paying):** working adults 25–50, 5–10h/week, sprint/Olympic, mostly Garmin. They feel schedule + facility pain hardest and pay.
**Free beta / founder story:** uni tri club members 18+. Not the revenue base.
**Excluded:** under-18s (ICO Children's Code + health data), long-course, first-timers (high drop-out).

**MVP (Must):** weekly availability slots · location profiles with facilities/kit (Work week, Work trip, Home, Family holiday / Term, Home) · rule-based planner + CP-SAT slot placement · one-tap Done / Skipped / Moved with reason code · re-plan with receipts + Undo · sprint/Olympic templates · completion tracker (completed ÷ planned hours).
**Not in MVP:** native app, AI chat coach, long-course, ML models, HRV-driven auto changes.

## Engine (Alchemist)

- Deterministic coaching rules set weekly load per discipline. OR-Tools CP-SAT places sessions into slots (athlete × day × window × location × facilities). Objective: maximise expected *completed* training value = P(athlete trains in this slot) × session value.
- Adherence P learned per athlete with a Beta-Binomial from one-tap logs. It moves key sessions out of slots the athlete never actually uses (Joe's 06:30 slot problem).
- Hard constraints never broken (no swim on a no-pool day). Discipline substitution keeps aerobic load and records a per-discipline debt ledger.
- No thrash: freeze next 24h, churn penalty, reason code on every move. Readiness only *downgrades* intensity.
- Data: append-only `plan_session_version`; `source` on every completion row; Garmin API rows never feed pooled models; no Strava.
- v0 (now → Easter 2027, n=1): Google Sheet + weekly Python script (`pandas`, `ortools`, `scipy.stats.beta`, `icalendar`, personal Garmin key via `fitdecode`). v1 (beta): FastAPI + Postgres, Stripe, web push, Garmin OAuth/push. v2 (1k+ users): LightGBM adherence model vs Beta baseline, PyMC hierarchical priors.

## User Experience (Advocate)

1. **Today card** with Done / Skipped / Moved at thumb height; Skipped = one reason tap. Unlogged → one prompt next morning, never auto-skipped, no red X. These taps are the core dataset.
2. **Week 1 visible before paywall/install**, built from real slots in ≤3 minutes. Ability from 3 questions (5k/10k, 100m swim pace, FTP if known) + week-1 benchmarks.
3. **Every change gets a receipt + Undo.** Key sessions and readiness changes ask first. No silent changes, no chat.
4. **Reminders that arrive:** subscribed .ics calendar feed by default; PWA install offered after week-1 preview with an iOS walkthrough.
- Copy from Runna: onboarding order, first workout before paywall, "not feeling 100%" flow (+ body-part option: calf → rides).

## Growth & Monetisation (Herald)

- £79.99/yr default, £12.99/mo, Founding-250 at £59.99/yr. Stripe on a PWA, not app stores.
- Sell the season. Free off-season mode → shareable season recap → January replan. **Launch January 2028, never autumn.**
- Channels: build-in-public → own uni tri club (beta) → adult clubs via club codes.
- PMF test: ≥35% of payers return for season 2. <20% = a one-race tool, not a business.
- ~£45 net/payer/season → £100k/yr needs ~2,200 UK payers.

## Risk Assessment (Skeptic)

- **Platform:** Garmin is competitor and gatekeeper. API froze Mar–Oct 2026; reopened with a free tier reportedly capped ~1,000 users; AI-training clause reported, unverified. → Core loop works with Garmin off; read the live agreement before applying.
- **Health data:** HRV/sleep/injury/readiness = UK GDPR Article 9. Before the first outside user: explicit consent, DPIA, ICO registration, export + deletion.
- **Injury liability:** user-declared, never diagnosed. Written ramp caps. Two consecutive pain reports freeze that sport + physio referral. No "AI coach" or "injury prevention" claims. Liability insurance quote before charging.
- **Minors:** 18+ only, verify DOB (some freshers are 17).
- **Copy risk:** incumbents or a general LLM chatbot handling typed constraints. Mitigation: prove adherence fast, own one niche.
- **Founder time:** realistic build window is ~3 months between A-levels and uni.

## Tension Resolutions

| Tension | Agents | Resolution | Reasoning |
|---|---|---|---|
| Is facility/kit planning defensible? | Scout ↔ Skeptic | Wedge, not moat. Moat = proven adherence + niche ownership | Gap is real and long-unsolved, but copyable in ~6–18 months |
| Who pays, who tests? | Strategist ↔ Herald | Adults 25–50 pay; uni students 18+ are free beta + story | Student channel is cheap but doesn't reach payers |
| Garmin dependency | Alchemist ↔ Skeptic | Garmin optional for input; first-party one-tap logs are the core signal | Avoids gatekeeper + AI-clause risk; moat data stays first-party |
| Watch push timing | Herald ↔ Alchemist/Advocate | Apply when exams end; push in beta if approved by 1 Sep 2027, required for paid launch; .FIT/.ics + calendar always as fallback | Paying Garmin owners judge it on "is it on my wrist at 06:00" |
| Phone health sync | Advocate ↔ Alchemist | Dropped for v1 | A PWA can't read Apple Health / Health Connect |

## Decision Log

| Decision | Options Considered | Chosen | Reasoning |
|---|---|---|---|
| Business shape | Venture / bootstrapped / portfolio | Portfolio → bootstrapped business, acquisition exit | ~£340k ARR at 1% of US+UK; ~£0.8–2.4M at 1–3% of ~1M global (estimate) |
| Market | UK only / global | Global English-language from day one; UK + US marketing first | Distribution (clubs, races) is local; the product isn't |
| Differentiator | Schedule / HRV / facilities / coach chat | Facility + kit + schedule-aware planning, proven by adherence | Schedule + HRV already table stakes |
| Platform | Native / PWA | Installable PWA + Stripe | Ships faster, better margin; calendar feed covers reminders |
| Engine | ML / LLM / rules + optimisation | Rules + CP-SAT + Beta-Binomial adherence | Works at n=1, explainable, no ML before ~5k rows |
| Headline metric | Engagement / retention / adherence | Completed ÷ planned hours | Directly tests the thesis; Joe's baseline ~15% |
| Pricing | Monthly / per-race / annual | £79.99/yr default, £12.99/mo, Founding £59.99 | Season-based sport; undercuts Runna |
| Launch | Autumn 2027 / Jan 2028 | January 2028 | Tri season planning starts in January |

## Phase Plan & Kill Gates

| When | Work | Go | Kill |
|---|---|---|---|
| Nov 2026–Feb 2027 (~2h/wk) | Run spreadsheet planner on yourself. Hands-on trial of Garmin Triathlon Coach, Transition, Humango, TriCoach AI (+ free ChatGPT control) with one scripted week: school (wattbike/treadmill, pool only after 16:00) + home weekend (road bike, pool 20km) + Wednesday calf strain + 2 missed sessions | Own completion ≥50% for 6 weeks | A rival produces a valid two-location week that holds load |
| Mar–Apr 2027 | Landing page + constraint quiz, 10 adult interviews, weekly build-in-public post | ≥100 sign-ups (aim 200 by June, ≥25% strangers) | <40 sign-ups |
| May–Jun 2027 | Exams. Nothing. | — | — |
| Jul 2027 | Concierge test, 15–20 adults, 6 weeks: facility-aware vs time-only weeks. Apply to Garmin developer programme | Median completed ÷ planned ≥70%; facility-aware beats time-only by ≥10 pts | No uplift from facilities |
| Aug–Sep 2027 | Build PWA. Garmin push go/no-go 1 Sep. GDPR/DPIA/ICO done | ≥30% of strangers pre-pay | <30% pre-pay → no paid launch |
| Oct–Dec 2027 (first uni term) | Free beta with uni clubs; launch assets done by 15 Dec | ≥50% still checking in at week 6 | <40% active at week 8 |
| Jan 2028 | Paid launch | ≥100 paying by 31 Mar; ≥20% adult trial→paid | Below that → stays a portfolio piece |

Thresholds (15/10-point uplift, week-6, 20%) are heuristics, not data.

## Unverified

Garmin Starter tier fee/cap and AI-training clause (press reports, not Garmin's own agreement); Training API swim/brick support; whether a .FIT workout can be loaded onto a Garmin from a phone alone; Transition billing period.

## Key Sources

- Garmin acquires TrainingPeaks: https://www.garmin.com/en-US/newsroom/press-release/corporate/garmin-acquires-trainingpeaks-and-trainheroic-leading-endurance-and-strength-training-platforms-for-athletes-and-coaches/
- Strava acquires Runna: https://dcrainmaker.com/2025/04/strava-acquires-runna-thoughts-forward.html
- Garmin API pause / reopening: https://the5krunner.com/2026/09/14/garmin-developer-api-access-paused/ · https://openwearables.io/blog/garmin-connect-developer-program-reopened · https://developer.garmin.com/gc-developer-program/overview
- GB triathlon participation: https://endurance.biz/2026/featured-news/triathlon-participation-in-great-britain-showing-signs-of-recovery-and-signals-a-new-normal/
- USA Triathlon 2025 impact report (303k unique active members): https://www.usatriathlon.org/news/2026/february/04/usa-triathlon-releases-2025-impact-report-highlighting-strategic-growth-membership-event-momentum-and-progress-toward-la28
- Garmin Coach for triathletes (adaptive, Connect app sign-up): https://www.garmin.com/en-CA/blog/?p=32255
- Garmin forum, Triathlon Coach erratic changes: https://forums.garmin.com/sports-fitness/running-multisport/f/forerunner-970/413521/why-the-workouts-always-change-in-one-day-in-triathlon-coach
- Full competitor matrix and sources: deliberation/round1/scout.md

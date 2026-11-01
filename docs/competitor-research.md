# Scout Position: Runna-style triathlon app

**Core recommendation:** The premise is mostly false. AI and adaptive triathlon coaching is crowded: there are 12+ live products, and two of them are owned by the platform giants. Adapting to schedule and to readiness (HRV/sleep) is now **table stakes**, so neither is a differentiator. The one gap I could verify is **facility- and kit-aware planning**. I found no product that models pool opening hours, equipment that depends on where you are, or term/holiday/travel "context profiles". None does injury swaps across disciplines that keep the training load the same. Pitched as "a plan you will actually complete", that is the white space.

**Key argument:**
Schedule adaptation is everywhere:
- **Humango** sets time per day for each sport and replans after missed weeks.
- **Athletica's** Workout Wizard swaps sessions to fit the time available.
- **MOTTIV** regenerates the plan from a weekly-hours slider.
- **TriDot** caps sessions per discipline and cuts load automatically after more than 5 sick days.
- **Garmin's free Triathlon Coach** (sprint to 70.3) rebuilds daily.

Readiness is also covered:
- **Athletica** has an HRV engine.
- **AI Endurance** uses HRV and DFA α1.
- **Transition's** "Recovery Intelligence" reads Garmin overnight HRV, sleep and stress.
- Free hobby tools on intervals.icu do this too.

New AI-native entrants keep arriving: TriCoach AI (~200 users), Transition (4.7★ from 86 ratings), and a free open-source triathlon custom GPT for ChatGPT. Every one of them pitches "adapts to your life". None models **where you are and what kit you have**:
- TriDot's preferences are only long-session days plus a maximum number of sessions per discipline.
- Athletica's time-constraint beta was called "does not work at all" by users. Staff said constraints are a "strong suggestion" that the planner may ignore.

That is evidence this is a hard constraint-satisfaction problem, not a missing checkbox. It suits Joe's maths. Joe's own numbers (9–10h planned vs ~1.4h done) show an **adherence failure caused by plans that could not be done**: no morning pool, the wrong bike at the wrong house. Other tools miss exactly this.

The incumbents are also consolidating:
- **Strava** bought Runna (Apr 2025) and The Breakaway (May 2025). Runna already sells *run-only plans "for triathletes"*.
- **Garmin** bought TrainingPeaks (Jul 2026) and gives Triathlon Coach away free.

On market size: Runna has 25k UK App Store ratings, while the largest tri-only apps have 30–90 (TrainerRoad's 8k is mostly cyclists). Triathlon looks uncrowded because the niche is small and fragmented, not because nobody serves it.

**Garmin API access, briefly:** New applications were **paused from Mar to Oct 2026**. The programme reopened on 21 Oct 2026:
- **Startup tier:** free for up to 1,000 users and includes the Training API, so you can push workouts to the watch. Data is push-only with no history backfill. You need a public website and a privacy policy, and new apps carry an "unverified" label with connection limits while under review.
- **Above 1,000 users:** you move to Enterprise, with a $1,000 entry credit plus a negotiated per-monthly-active-user fee, billed from 1 Apr 2027. These figures come from press reports.
- **AI use:** the revised agreement reportedly bans training your own models on Garmin data. Using it to plan for the user it came from, with consent, appears allowed. That is a third-party reading I could not verify.
- **Strava:** its API reportedly bans *any* AI use of its data, so Strava cannot be the fallback data source.

**Risks if ignored:**
- **Me-too launch.** A product built on "adapts to schedule + HRV" enters against a free Garmin coach and £6.99/mo Connect+. Joe's £10–20/mo price is exactly where Humango, MOTTIV, Athletica and TrainingPeaks already sit (~$19–20/mo).
- **Platform risk.** Garmin closed its API for 7 months without notice, now owns a direct competitor (TrainingPeaks), and charges unknown per-user fees above 1,000 users. The Strava route is closed for AI.
- **Underestimating the constraint problem.** Athletica shows that a weak constraint solver produces the same "it ignored my constraints" complaint Joe has today.

**Dependencies on other domains:**
- **Strategist:** Which segment? The facility gap is sharpest for people who live in several places: students and juniors, shift workers, travellers. I found no reliable UK triathlon participation numbers, so market size needs sourcing. The small tri niche (going by rating counts) points to bootstrapped or small-exit plans rather than venture funding.
- **Skeptic:** Test whether facility-awareness actually makes people buy or is just nice to have. Forum users reject tools for being "too data-heavy".
- **Alchemist:** Garmin Startup is push-only with no backfill, so new users start with no data. The AI/ML clause points to rules plus per-user optimisation, not a model trained across users.
- **Advocate:** Capturing facility profiles (pool timetables, kit at each location) must take under ~2 minutes. TriCoach's users name simplicity as the top thing they value.
- **Herald:** "AI that adapts to you" is everyone's claim. The message needs a hard proof point, such as plan-completion rate.

---

## Appendix: Feature matrix (checked 30 Oct 2026)

Columns: (a) adapts to schedule and missed sessions, (b) facility/kit availability, (c) readiness (HRV/sleep/injury). "n/s" means not stated in the sources. ⚠ means unverified or secondary source.

| Product (owner) | (a) Schedule / missed | (b) Facility / kit | (c) Readiness | Garmin | Price | Traction signal |
|---|---|---|---|---|---|---|
| Runna (Strava) | Set run days; drag/skip; missed sessions not re-planned [1][2] | None | Manual "Not Feeling 100%"; no HRV [3] | Yes, pushes workouts | £15.99/mo, £99.99/yr; Strava bundle £119.99/yr [4] | 4.8★ / 25k UK ratings [5]; ~90k members at acquisition [6]; **run-only** "for triathletes" [7] |
| Garmin Triathlon Coach (Garmin) | Daily rebuild; choose training days ⚠[8][9] | None found | Sleep and recovery; HRV as input not confirmed [8] | Native | Free with a compatible watch; Connect+ £6.99/mo [10] | Sprint to 70.3 only ⚠[9] |
| TrainingPeaks (Garmin, Jul 2026) | Coach-driven; no auto-adaptation ⚠[11] | None | Performance chart is descriptive only | Yes | $19.95/mo, $134.99/yr [12] | "Millions" (vendor claim) [13] |
| TriDot | Max sessions per discipline; long-day setting; auto-reduce after >5 days off sick [14][15] | Heat, altitude and humidity only; no pool or kit [16] | "Recovery signals"; HRV n/s | Yes [17] | $14.99–$249/mo [16] | 4.6★ / 32 (new app) [17] |
| Humango (Human Powered Health) | Time per day per sport; replan [18][19] | None found | Sleep, fatigue, HR; HRV n/s [19] | Yes | $8.99–$28.99/mo; triathlon on top tiers [19] | 3.6★ / 60 US [19] |
| MOTTIV | Weekly-hours slider regenerates the plan; missed n/s [20] | None | None | Premium tier only | Free / $19.99/mo [21] | 4.8★ / 71 [22] |
| TrainerRoad | Adaptive for bike; run/swim "generic" (users) [23][24] | Built around indoor bike | Bike only ("Turn It Down") [25] | Yes | £19.99 (billing period unclear) [26] | 4.8★ / 8k UK, mostly cyclists [26] |
| Athletica | Workout Wizard fits time; availability-constraint beta unreliable (2024) [27][28] | None (indoor tips only) | HRV readiness engine [27] | Yes | $19.90/mo, $189/yr [27] | n/s |
| AI Endurance | Missed sessions and check-ins [29] | None | HRV, RHR, DFA α1 [29] | Yes | $12.99/mo [29] | n/s |
| 2PEAK | "100% Adaptive", Pause Insurance [30] | Indoor-trainer toggle; no pool | "Regeneration Battery"; HRV n/s | Yes | €12–20/mo, 6-month minimum [30] | n/s |
| JOIN | Instant adapt to availability and skipped rides [31] | n/a | n/s | n/s | €16.99/mo [31] | **Cycling only** |
| Transition (AI-native, 2024–26) | Missed, travel, drag-drop, Google/Apple calendar sync [32] | Smart-trainer control; pool **not** modelled | HRV, sleep, stress via Garmin [32] | Yes | $19 / $29 tiers ⚠ (periods unclear) [32] | 4.7★ / 86 [32] |
| TriCoach AI (solo dev, Apr 2026) | Plain-language constraints [33][34] | Adapts to a bike-free week (partial) | n/s | Via intervals.icu | n/s | ~200 users, "a few" paying [33][34] |
| Training Agent / Open Tri Coach (free, intervals.icu) | Weekly plan | None | HRV, sleep, RHR [35][36] | Via intervals.icu | Free | Hobby scale |

**No product found models pool hours, equipment by location, or term/holiday context profiles.** Strongest near-misses: TriDot (discipline caps), Athletica (time-constraint beta), TriCoach AI (bike-free week).

**Garmin Connect Developer Program:** paused Mar–Oct 2026 [37][38]; reopened 21 Oct 2026 with Personal (free), Startup (free, ≤1,000 users, includes Training API) and Enterprise ($1,000 entry credit plus per-user fee from 1 Apr 2027) ⚠ press reports [39][40][41]. AI-training restriction ⚠ third-party reading [41]. Strava API bans AI use of its data ⚠ secondary [42].

### Sources
[1] https://intercom.help/runna/en/articles/10137793-how-to-use-and-manage-your-training-calendar
[2] https://the5krunner.com/runna/
[3] https://intercom.help/runna/en/articles/12809806-feeling-unwell-how-to-adapt-your-training-plan
[4] https://the5krunner.com/2026/10/14/is-runna-free/
[5] https://apps.apple.com/gb/app/runna/id1594204443
[6] https://dcrainmaker.com/2025/04/strava-acquires-runna-thoughts-forward.html
[7] https://www.runna.com/en-gb/training/triathlon
[8] https://www.garmin.com/en-US/blog/?p=35760 ; https://www.gneta.app/blog/garmin-coach-review (competitor blog)
[9] https://shopsavvy.com/answers/is-the-garmin-forerunner-970-good-for-triathlons.md
[10] https://the5krunner.com/2026/04/20/garmin-connect-plus-review/
[11] https://www.sensai.fit/blog/runna-vs-trainingpeaks-2026 (competitor blog)
[12] https://trainingpeaks.com/pricing/for-athletes/
[13] https://www.garmin.com/en-US/newsroom/press-release/corporate/garmin-acquires-trainingpeaks-and-trainheroic-leading-endurance-and-strength-training-platforms-for-athletes-and-coaches/
[14] https://tridot.com/resource-library/updating-your-preferences
[15] https://support.tridot.com/hc/en-us/articles/5632284661133-Does-my-schedule-adjust-if-I-m-sick-or-injured
[16] https://tridot.com/pricing
[17] https://apps.apple.com/us/app/tridot-triathlon-training/id6754208848
[18] https://fueledbylolz.com/2024/08/28/humango-review/
[19] https://apps.apple.com/app/id1554430755
[20] https://mymottiv.com/help-center-articles/add-or-subtract-workouts
[21] https://www.mymottiv.com/pricing
[22] https://apps.apple.com/app/id1561001166
[23] https://www.trainerroad.com/forum/t/train-now-for-running-and-swimming/100720
[24] https://www.trainerroad.com/forum/t/triathlon-ai-training-plans/107235
[25] https://www.trainerroad.com/forum/t/coming-soon-updated-training-approach/107244
[26] https://apps.apple.com/gb/app/trainerroad/id934224107
[27] https://athletica.ai/sports/triathlon
[28] https://forum.athletica.ai/t/beta-program-daily-time-availability-constraints/1173
[29] https://www.triathlete.com/gear/tech-wearables/ai-triathlon-training-apps
[30] https://www.2peak.com/pricing/
[31] https://join.cc/pricing
[32] https://apps.apple.com/us/app/transition-triathlon-training/id6670714598
[33] https://forum.intervals.icu/t/tricoach-ai-200-triathletes-from-15-countries-in-4-months-come-see-whats-different/132270
[34] https://forum.slowtwitch.com/t/im-building-a-triathlon-training-app-and-im-looking-for-honest-feedback/1299252
[35] https://forum.intervals.icu/t/training-agent-free-ai-coach-that-plans-your-week-from-your-intervals-icu-data-cycling-running-swimming-triathlon/132768
[36] https://forum.intervals.icu/t/open-triathlon-coach-for-chatgpt-public-beta/130773
[37] https://the5krunner.com/2026/09/14/garmin-developer-api-access-paused/
[38] https://tryterra.co/blog/garmin-connect-developer-program-pause
[39] https://the5krunner.com/2026/10/22/garmin-personal-api/
[40] https://stack-archive.com/blog/garmin-connect-api-personal-tier-free-access-2026/ ; https://idevice.com/garmin-reopens-its-connect-api-with-free-personal-keys-and-a-fee-for-big-apps.md
[41] https://openwearables.io/blog/garmin-connect-developer-program-reopened
[42] https://tryterra.co/blog/strava-api-changes-2026
Other context: Strava/Breakaway https://athletechnews.com/strava-acquires-another-training-app-reaches-2-2b-valuation/ ; Runna funding https://sifted.eu/articles/strava-buys-runna-deal-fitness-app

**Could not verify:** Garmin Triathlon Coach's full adaptation logic and device list; Transition and TrainerRoad billing periods; Garmin's per-user Enterprise rate; the exact wording of Garmin's AI clause; user or revenue numbers for any tri-only competitor; UK triathlon participation size.

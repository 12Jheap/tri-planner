"""What to actually do in each session: warm-up, main set, cool-down, with targets.

`workout_for(session, profile)` turns e.g. a 45-minute threshold run into
"12 min easy · 4 × 6 min threshold (4:09–4:22/km) with 2 min jog · 9 min easy",
sized so the steps add up to the session's length. Targets come from your
profile (paces, watts, heart rate); without numbers they fall back to effort.
The same steps go into the .FIT file for your watch.
"""

from __future__ import annotations

from pydantic import BaseModel

from planner.profile import ZONE_NAMES, Profile, Zone, mmss
from planner.sessions import Session


class Step(BaseModel):
    label: str
    seconds: int
    zone: Zone
    target: str = ""
    metres: int | None = None  # swim steps are distances
    note: str = ""


class Block(BaseModel):
    reps: int = 1
    steps: list[Step]

    @property
    def seconds(self) -> int:
        return self.reps * sum(s.seconds for s in self.steps)

    def summary(self) -> str:
        def part(s: Step) -> str:
            size = f"{s.metres}m" if s.metres else _dur(s.seconds)
            return size

        if self.reps == 1 and len(self.steps) == 1:
            s = self.steps[0]
            tgt = f" ({s.target})" if s.target and s.zone not in ("easy", "recovery") else ""
            return f"{part(s)} {s.label.lower()}{tgt}"
        work, *rest = self.steps
        tgt = f" ({work.target})" if work.target else ""
        text = f"{self.reps} × {part(work)} {work.label.lower()}{tgt}"
        if rest:
            r = rest[0]
            text += f", {part(r) if not r.metres else _dur(r.seconds)} {r.label.lower()}"
        return text


class Workout(BaseModel):
    discipline: str
    blocks: list[Block]
    note: str = ""

    @property
    def seconds(self) -> int:
        return sum(b.seconds for b in self.blocks)

    @property
    def metres(self) -> int:
        return sum(b.reps * sum(s.metres or 0 for s in b.steps) for b in self.blocks)

    @property
    def summary(self) -> str:
        text = " · ".join(b.summary() for b in self.blocks)
        if self.metres:
            text += f" · {self.metres:,}m total"
        return text

    def flat(self) -> list[Step]:
        return [s for b in self.blocks for _ in range(b.reps) for s in b.steps]

    def segments(self) -> list[tuple[str, int]]:
        """(zone, seconds) in order, for drawing a timeline."""
        out: list[tuple[str, int]] = []
        for s in self.flat():
            if out and out[-1][0] == s.zone:
                out[-1] = (s.zone, out[-1][1] + s.seconds)
            else:
                out.append((s.zone, s.seconds))
        return out

    @property
    def zones_used(self) -> list[str]:
        return list(dict.fromkeys(z for z, _ in self.segments()))


def _dur(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds % 60:
        return f"{mmss(seconds)} min"
    return f"{seconds // 60} min"


class _Builder:
    def __init__(self, session: Session, profile: Profile) -> None:
        self.s = session
        self.p = profile
        self.disc = "bike" if session.kind == "brick" else session.discipline
        self.total = session.duration_min * 60

    def step(self, label: str, minutes: float, zone: Zone, note: str = "",
             disc: str | None = None) -> Step:
        return Step(label=label, seconds=round(minutes * 60), zone=zone,
                    target=self.p.target(disc or self.disc, zone), note=note)

    def intervals(self, wu: float, cd: float, works: float | tuple[float, ...], rest: float,
                  zone: Zone, label: str, rest_label: str = "easy", rest_zone: Zone = "easy",
                  max_reps: int = 6) -> list[Block]:
        """Warm-up, reps of work + rest, cool-down; spare time goes into the warm-up.

        With several rep lengths to choose from, picks the one that fits the most time
        in the target zone (longer reps win a tie), e.g. 3 × 12 rather than 2 × 12
        plus a 20-minute warm-up.
        """
        avail = self.total / 60
        if wu + cd > avail * 0.6:  # short session: shorter warm-up and cool-down
            f = avail * 0.6 / (wu + cd)
            wu, cd = wu * f, cd * f
        main = avail - wu - cd
        options = works if isinstance(works, tuple) else (works,)

        def quality(w: float) -> tuple[float, float]:
            n = max(1, min(max_reps, main // (w + rest)))
            return (n * w if n * (w + rest) <= main else 0, w)

        work = max(options, key=quality)
        # Each rep is work + its recovery; fit as many as the time allows (at least one).
        reps = int(max(1, min(max_reps, main // (work + rest))))
        if reps * (work + rest) > main:  # very short session: shrink the one rep to fit
            shrink = max(main, 1) / (work + rest)
            work, rest = work * shrink, rest * shrink
        spare = max(0.0, main - reps * (work + rest))
        # Up to 5 spare minutes lengthen the warm-up; the rest is easy aerobic time
        # after the main set, where it adds volume without blunting the reps.
        extra_wu = min(spare, 5.0)
        after = spare - extra_wu
        blocks = [
            Block(steps=[self.step("Warm-up", wu + extra_wu, "easy",
                                   "build gradually; finish with a few faster minutes")]),
            Block(reps=reps, steps=[self.step(label, work, zone),
                                    self.step(rest_label, rest, rest_zone)]),
        ]
        if after >= 5:
            blocks.append(Block(steps=[self.step("Easy aerobic", after, "easy")]))
            after = 0
        blocks.append(Block(steps=[self.step("Cool-down", cd + after, "easy")]))
        return blocks

    # ---- run -----------------------------------------------------------------------
    @property
    def half(self) -> bool:
        return self.s.race == "half"

    @property
    def building(self) -> bool:
        return self.s.phase == "build"

    def run(self) -> list[Block]:
        k, m = self.s.kind, self.total / 60
        if self.half and k == "long" and m >= 75:
            fuel = "practise race fuelling: a gel or drink every 30 minutes"
            if self.building:  # finish at the pace you'll race the half marathon
                return [Block(steps=[self.step("Easy", m - 35, "easy", fuel)]),
                        Block(steps=[self.step("Half-marathon effort", 25, "race",
                                               "the pace you'll hold off the bike")]),
                        Block(steps=[self.step("Easy", 10, "easy")])]
            return [Block(steps=[self.step("Easy", m - 15, "easy", fuel)]),
                    Block(steps=[self.step("Finish steady", 15, "steady")])]
        if self.half and k == "tempo":
            return self.intervals(10, 5, (10, 15, 20), 3, "race", "Half-marathon effort",
                                  "Easy jog", max_reps=3)
        if k == "easy_strides" and m >= 25:
            return [
                Block(steps=[self.step("Easy run", m - 9, "easy")]),
                Block(reps=6, steps=[
                    self.step("Stride", 20 / 60, "sprint", "smooth and quick, not a sprint"),
                    self.step("Walk / jog back", 70 / 60, "recovery")]),
            ]
        if k == "long" and m >= 45:
            fuel = "take a drink or gel every 30–40 minutes" if m >= 75 else ""
            return [Block(steps=[self.step("Easy", m - 10, "easy", fuel)]),
                    Block(steps=[self.step("Finish steady", 10, "steady")])]
        if k == "tempo":
            return self.intervals(10, 5, (6, 8, 10), 2, "tempo", "Tempo", "Easy jog",
                                  max_reps=4)
        if k == "threshold":
            return self.intervals(12, 8, (5, 6, 8), 2, "threshold", "Threshold", "Jog",
                                  max_reps=5)
        if k == "vo2":
            return self.intervals(15, 8, (2, 3), 2, "vo2", "Hard", "Jog", "recovery",
                                  max_reps=6)
        if k == "openers":
            return self.intervals(10, max(5, int(m) - 10 - 8), 1, 1, "threshold",
                                  "Race pace", "Easy", max_reps=4)
        return [Block(steps=[self.step("Easy run", m, "easy")])]

    # ---- bike ----------------------------------------------------------------------
    def bike(self) -> list[Block]:
        k, m = self.s.kind, self.total / 60
        fuel = "practise race fuelling: 60–90 g of carbs an hour, drink every 15 minutes"
        if self.half and k == "long" and m >= 120 and self.building:
            reps = int(min(3, (m - 30) // 30))
            steady = m - 20 - reps * 30 - 10
            blocks = [Block(steps=[self.step("Easy spin", 20, "easy")]),
                      Block(reps=reps, steps=[
                          self.step("Half race effort", 25, "race",
                                    "the effort you'll hold for 90 km; aero position"),
                          self.step("Easy", 5, "easy")])]
            if steady >= 5:
                blocks.append(Block(steps=[self.step("Steady endurance", steady, "steady",
                                                     fuel)]))
            blocks.append(Block(steps=[self.step("Easy spin", 10, "easy")]))
            return blocks
        if self.half and k == "long" and m >= 75:
            return [Block(steps=[self.step("Easy spin", 15, "easy")]),
                    Block(steps=[self.step("Steady endurance", m - 25, "steady", fuel)]),
                    Block(steps=[self.step("Easy spin", 10, "easy")])]
        if self.half and k == "tempo":
            return self.intervals(10, 5, (15, 20, 30), 5, "tempo", "Sweet spot", "Easy",
                                  max_reps=3)
        if self.half and k == "brick" and m >= 90:
            run = max(20, min(30, int(m) // 4))
            ride = m - run
            return [
                Block(steps=[self.step("Easy spin", 15, "easy")]),
                Block(steps=[self.step("Steady", ride - 45, "steady", fuel)]),
                Block(steps=[self.step("Half race effort", 30, "race",
                                       "finish the ride at race effort")]),
                Block(steps=[self.step("Run off the bike: settle", 10, "steady",
                                       "change shoes fast; quick short steps", disc="run")]),
                Block(steps=[self.step("Run at half-marathon effort", run - 10, "race",
                                       disc="run")]),
            ]
        if k == "long":
            if m >= 75:
                return [Block(steps=[self.step("Easy spin", 15, "easy")]),
                        Block(steps=[self.step("Steady endurance", m - 25, "steady",
                                               "eat and drink every 20 minutes")]),
                        Block(steps=[self.step("Easy spin", 10, "easy")])]
            return [Block(steps=[self.step("Steady endurance", m, "steady")])]
        if k == "tempo":
            return self.intervals(10, 5, (10, 12, 15, 20), 3, "tempo", "Sweet spot", "Easy",
                                  max_reps=4)
        if k == "threshold":
            return self.intervals(15, 10, (6, 8, 10), 3, "threshold", "Threshold", "Easy",
                                  max_reps=4)
        if k == "vo2":
            return self.intervals(15, 10, 3, 3, "vo2", "Hard", "Easy spin", "recovery",
                                  max_reps=6)
        if k == "openers":
            return self.intervals(15, max(5, int(m) - 15 - 12), 1, 2, "threshold",
                                  "Race effort", "Easy", max_reps=4)
        if k == "brick":
            run = max(8, min(30 if m >= 100 else 20, int(m) // 4))  # longer leg for a half
            ride = m - run
            easy = min(10, ride * 0.3)
            race = min(10, ride * 0.3)
            return [
                Block(steps=[self.step("Easy spin", easy, "easy")]),
                Block(steps=[self.step("Steady", ride - easy - race, "steady")]),
                Block(steps=[self.step("Race effort", race, "tempo",
                                       "finish the ride at race effort")]),
                Block(steps=[self.step("Run off the bike", run, "steady",
                                       "change shoes fast; short quick steps for the first "
                                       "few minutes", disc="run")]),
            ]
        return [Block(steps=[self.step("Endurance", m, "easy")])]

    # ---- swim ----------------------------------------------------------------------
    def swim_set(self, label: str, reps: int, metres: int, zone: Zone, rest_s: int,
                 note: str = "") -> Block:
        secs = int(metres / 100 * self.p.swim_speed(zone))
        tgt = self.p.target("swim", zone)
        work = Step(label=label, seconds=secs, zone=zone, metres=metres, target=tgt, note=note)
        steps = [work]
        if rest_s:
            steps.append(Step(label="rest", seconds=rest_s, zone="recovery"))
        return Block(reps=reps, steps=steps)

    def swim(self) -> list[Block]:
        k, m = self.s.kind, self.total / 60
        short = m < 35
        wu = self.swim_set("Easy", 1, 200 if short else 400, "easy", 0, "mix in some backstroke")
        cd = self.swim_set("Easy", 1, 100 if short else 200, "easy", 0)
        fixed: list[Block] = []
        main: tuple[str, int, Zone, int]
        if k == "technique":
            fixed = [self.swim_set("Drill", 6, 50, "easy", 20,
                                   "catch-up, fingertip drag, 6-kick switch")]
            main = ("Steady", 100, "steady", 15)
        elif k == "css" and self.half:  # longer reps for a 1.9 km swim
            main = (("CSS", 200, "threshold", 20) if self.s.intensity >= 4
                    else ("Tempo", 300, "tempo", 30))
        elif k == "css":
            main = (("CSS", 100, "threshold", 15) if self.s.intensity >= 4
                    else ("Tempo", 200, "tempo", 20))
        elif k == "speed":
            fixed = [self.swim_set("Fast", 8, 50, "vo2", 30, "fast but long and smooth")]
            main = ("Steady", 100, "steady", 15)
        elif k == "race_pace":
            fixed = [self.swim_set("Race pace", 6, 50, "threshold", 20)]
            main = ("Easy", 100, "easy", 15)
        elif self.half:
            main = ("Steady", 400, "steady", 30)
        else:
            main = ("Steady", 200, "steady", 20)
        label, dist, zone, rest = main
        left = self.total - sum(b.seconds for b in [wu, cd, *fixed])
        one = int(dist / 100 * self.p.swim_speed(zone)) + rest
        reps = max(2, left // one)
        # Quality sets stay a sensible size (e.g. ≤ 1200m at CSS); spare time becomes pull.
        limit = 1600 if self.half else 1200
        cap = {"threshold": limit, "tempo": limit}.get(zone, 10_000) // dist
        note = "sight forwards every 6–8 strokes, like open water" if self.half and \
            dist >= 300 else ""
        out = [wu, *fixed, self.swim_set(label, int(min(reps, cap)), dist, zone, rest, note)]
        left -= int(min(reps, cap)) * one
        pull = int(100 / 100 * self.p.swim_speed("steady")) + 15
        if left >= 2 * pull:
            out.append(self.swim_set("Pull, steady", int(left // pull), 100, "steady", 15,
                                     "pull buoy; long, strong strokes"))
        return [*out, cd]

    # ---- strength ------------------------------------------------------------------
    def strength(self) -> list[Block]:
        m = self.total / 60
        rounds = max(1, int((m - 10) // 10))
        moves = ("squats ×15, reverse lunges ×10 each, glute bridges ×15, plank 40s, "
                 "press-ups ×10, single-leg calf raises ×15 each, side plank 30s each")
        return [
            Block(steps=[self.step("Mobility warm-up", 5, "easy", "leg swings, hips, ankles",
                                   disc="strength")]),
            Block(reps=rounds, steps=[self.step("Circuit", (m - 10) / rounds, "steady", moves,
                                                disc="strength")]),
            Block(steps=[self.step("Stretch", 5, "recovery", disc="strength")]),
        ]


def workout_for(session: Session, profile: Profile | None = None) -> Workout:
    b = _Builder(session, profile or Profile())
    fn = {"run": b.run, "bike": b.bike, "swim": b.swim, "strength": b.strength}
    blocks = fn[session.discipline]()
    for blk in blocks:  # strength and substitutes have no meaningful pace targets
        for st in blk.steps:
            if session.discipline == "strength":
                st.target = ""
    return Workout(discipline=session.discipline, blocks=blocks)


ZONE_ORDER = list(ZONE_NAMES)

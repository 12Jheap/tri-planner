"""Training load: how much a week took out of you, not just how long it was.

Session load = minutes × effort (1–10), the "session-RPE" method coaches have used
for decades because it needs no gadgets and tracks fatigue well. A week's load is
the sum. Two plain uses:

- Progress shows load per week, and flags a jump of more than 30% on your recent
  average (the pattern that most often comes before illness or a niggle).
- If a week *felt* very hard (average effort 7.5+ across at least 3 rated sessions),
  the next week holds its volume instead of adding 10%.

Sessions you didn't rate count at the week's average effort, and the week says so.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from pydantic import BaseModel

from planner.adherence import LogRow

HARD_WEEK_RPE = 7.5  # average effort at which a week counts as "very hard"
MIN_RATED = 3  # sessions needed before the average means anything
SPIKE = 1.3  # this week's load vs the average of the previous three


class WeekLoad(BaseModel):
    week: date
    done_min: int
    rated_min: int
    rated: int  # sessions with an effort score
    sessions_done: int
    mean_rpe: float | None  # minutes-weighted
    load: int | None  # minutes × effort, estimated for unrated minutes
    estimated: bool = False
    spike: bool = False

    @property
    def hard(self) -> bool:
        return self.mean_rpe is not None and self.rated >= MIN_RATED \
            and self.mean_rpe >= HARD_WEEK_RPE


def weekly_loads(rows: Iterable[LogRow]) -> list[WeekLoad]:
    weeks: dict[date, list[LogRow]] = defaultdict(list)
    for r in rows:
        if r.completed_min:
            weeks[r.week].append(r)
    out: list[WeekLoad] = []
    for wk, rs in sorted(weeks.items()):
        done = sum(r.completed_min for r in rs)
        rated = [r for r in rs if r.rpe]
        rated_min = sum(r.completed_min for r in rated)
        mean = sum(r.completed_min * (r.rpe or 0) for r in rated) / rated_min if rated_min \
            else None
        load = round(mean * done) if mean is not None else None
        recent = [w.load for w in out[-3:] if w.load]
        spike = bool(load and len(recent) >= 2 and load > SPIKE * sum(recent) / len(recent))
        out.append(WeekLoad(
            week=wk, done_min=done, rated_min=rated_min, rated=len(rated), sessions_done=len(rs),
            mean_rpe=round(mean, 1) if mean is not None else None, load=load,
            estimated=mean is not None and rated_min < done, spike=spike,
        ))
    return out

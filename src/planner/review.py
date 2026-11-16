"""The week in review: what you planned, what you did, and one honest line about it.

Shown on the Week page once a week is over (or on its Sunday). Plain arithmetic on
the plan and your log; nothing is inferred that you didn't record.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from pydantic import BaseModel

from planner.adherence import LogRow
from planner.load import WeekLoad
from planner.solver import Plan

SPORTS = ("swim", "bike", "run", "strength")


class WeekReview(BaseModel):
    week: date
    planned_min: int
    done_min: int
    sessions: int
    logged: int
    key_total: int
    key_done: int
    by_sport: dict[str, tuple[int, int]]  # sport -> (done, planned) minutes
    skipped: list[tuple[str, str]]  # (session title, reason)
    top_reason: str | None
    mean_rpe: float | None
    load: int | None
    verdict: str

    @property
    def ratio(self) -> float:
        return self.done_min / self.planned_min if self.planned_min else 0.0

    @property
    def unlogged(self) -> int:
        return self.sessions - self.logged


def _verdict(ratio: float, key_done: int, key_total: int, unlogged: int, sessions: int) -> str:
    if sessions and unlogged / sessions > 0.3:
        return (f"{unlogged} of {sessions} sessions aren't logged, so this is a guess. "
                "Log them (or sync Garmin) to see the real picture.")
    keys = f"{key_done} of {key_total} key sessions" if key_total else "no key sessions"
    if ratio >= 0.9:
        return f"Strong week: you did what you planned, with {keys}."
    if ratio >= 0.7:
        return f"Solid week, {keys}. Consistency like this is what builds fitness."
    if ratio >= 0.5:
        if key_total and key_done == key_total:
            return "About half the volume, but every key session done. Those matter most."
        return (f"About half done, {keys}. If the same slots keep getting missed, change "
                "them on Profile rather than planning sessions you won't do.")
    return (f"A light week ({ratio:.0%}), {keys}. It happens. If it wasn't illness or exams, "
            "look at which slots failed and make next week's plan one you can actually hit.")


def review_week(week: date, plan: Plan, rows: list[LogRow], load: WeekLoad | None
                ) -> WeekReview:
    by_id = {r.session_id: r for r in rows}
    keys = [p for p in plan.placements if p.session.key]
    done = {sid for sid, r in by_id.items() if r.completed_min}
    by_sport = {}
    for sport in SPORTS:
        mine = [r for r in rows if r.discipline == sport]
        if mine:
            by_sport[sport] = (sum(r.completed_min for r in mine),
                               sum(r.planned_min for r in mine))
    titles = {p.session.id: p.session.title for p in plan.placements}
    skipped = [(titles.get(r.session_id, r.session_id), r.reason or "other")
               for r in rows if r.status == "skipped"]
    reasons = Counter(reason for _, reason in skipped)
    planned = sum(r.planned_min for r in rows)
    done_min = sum(r.completed_min for r in rows)
    logged = sum(r.logged for r in rows)
    key_done = sum(p.session.id in done for p in keys)
    ratio = done_min / planned if planned else 0.0
    return WeekReview(
        week=week, planned_min=planned, done_min=done_min, sessions=len(rows), logged=logged,
        key_total=len(keys), key_done=key_done, by_sport=by_sport, skipped=skipped,
        top_reason=reasons.most_common(1)[0][0] if len(skipped) >= 2 else None,
        mean_rpe=load.mean_rpe if load else None, load=load.load if load else None,
        verdict=_verdict(ratio, key_done, len(keys), len(rows) - logged, len(rows)),
    )

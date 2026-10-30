"""Experiment mode and the weekly report (US-006).

The whole bet is that planning around facilities beats planning around time
alone. Experiment mode alternates week types on a fixed schedule so you can
measure it on yourself: in time-only weeks the planner ignores facilities, the
way most apps do, and you train what you can.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Literal

from planner.adherence import LogRow, weekly_summaries
from planner.config import week_start

WeekType = Literal["facility_aware", "time_only"]


def week_type(week: date, experiment_start: date | None) -> WeekType:
    """Alternate weekly: the experiment's first week is facility-aware, the next time-only."""
    if experiment_start is None:
        return "facility_aware"
    n = (week_start(week) - week_start(experiment_start)).days // 7
    if n < 0:
        return "facility_aware"
    return "facility_aware" if n % 2 == 0 else "time_only"


def _table(title: str, groups: dict[str, list[LogRow]]) -> list[str]:
    lines = [f"### By {title}", "", f"| {title.title()} | Planned | Done | Completion | Logged |",
             "|---|---|---|---|---|"]
    for key, rs in sorted(groups.items()):
        planned = sum(r.planned_min for r in rs)
        done = sum(r.completed_min for r in rs)
        logged = sum(r.logged for r in rs)
        ratio = done / planned if planned else 0
        lines.append(f"| {key} | {planned / 60:.1f}h | {done / 60:.1f}h | {ratio:.0%} | {logged}/{len(rs)} |")
    return [*lines, ""]


def completion_by(rows: Iterable[LogRow], attr: str) -> dict[str, float]:
    groups: dict[str, list[LogRow]] = defaultdict(list)
    for r in rows:
        groups[str(getattr(r, attr))].append(r)
    return {
        k: (sum(r.completed_min for r in rs) / sum(r.planned_min for r in rs))
        if sum(r.planned_min for r in rs) else 0.0
        for k, rs in groups.items()
    }


def weekly_report(rows: list[LogRow]) -> str:
    """Markdown report: overall, by week type, by slot and by discipline."""
    lines = ["# Training completion report", ""]
    for s in weekly_summaries(rows):
        lines.append(f"- {s.line()}")
    lines.append("")
    for title, attr in (("week type", "week_type"), ("slot", "slot_key"), ("discipline", "discipline")):
        groups: dict[str, list[LogRow]] = defaultdict(list)
        for r in rows:
            groups[str(getattr(r, attr))].append(r)
        lines += _table(title, groups)
    by_type = completion_by(rows, "week_type")
    if {"facility_aware", "time_only"} <= set(by_type):
        diff = (by_type["facility_aware"] - by_type["time_only"]) * 100
        verdict = "facility-awareness is helping" if diff >= 10 else "no clear uplift yet (target ≥10 pts)"
        lines.append(f"**Experiment:** facility-aware weeks {diff:+.0f} pts vs time-only — {verdict}.")
    return "\n".join(lines)

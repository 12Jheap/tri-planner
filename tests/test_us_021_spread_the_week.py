"""US-021: Sessions fit short slots and the week spreads out (v0)."""

from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import date
from pathlib import Path

from conftest import MONDAY, make_config

from planner.config import calendar_for_week
from planner.service import Workspace
from planner.sessions import BIKE_KIT, Session
from planner.solver import plan_week
from planner.workouts import workout_for

FIXTURE = Path(__file__).parent / "fixtures" / "short_weekday_slots.yaml"


def test_ac_094_sessions_shrink_to_fit_a_short_slot_but_not_below_their_minimum():
    """AC-094 [unit-test]: A session too long for a slot can run there shortened, down to its sensible minimum (a Key session that fits nowhere at all is rescued shorter with a note); full length is used whenever it fits, and the shortened workout still adds up"""
    cfg = make_config([{"day": "wed", "start": "06:45", "end": "07:30", "location": "School"}])
    slots = calendar_for_week(cfg, MONDAY)
    sweet = Session(id="bike-tempo", discipline="bike", kind="tempo", duration_min=75,
                    intensity=3, requires=[BIKE_KIT], key=True, min_min=45, max_min=90)
    plan = plan_week([sweet], slots, cfg)
    placed = plan.placement("bike-tempo")
    assert placed is not None and placed.session.duration_min == 45
    w = workout_for(placed.session)
    assert w.seconds == 45 * 60 and any(b.reps >= 2 for b in w.blocks)
    # Flex sessions never go below their minimum: it just doesn't fit this week.
    flex = sweet.model_copy(update={"min_min": 60, "key": False})
    assert plan_week([flex], slots, cfg).dropped
    # A Key session that fits nowhere at all is rescued shorter, and you're told why.
    rescued = plan_week([sweet.model_copy(update={"min_min": 60})], slots, cfg)
    assert rescued.placements[0].session.duration_min == 45
    assert rescued.notes and "75' → 45'" in rescued.notes[0]
    roomy = make_config([{"day": "sat", "start": "08:00", "end": "11:00", "location": "School"},
                         {"day": "wed", "start": "06:45", "end": "07:30", "location": "School"}])
    full = plan_week([sweet], calendar_for_week(roomy, MONDAY), roomy).placement("bike-tempo")
    assert full is not None and full.session.duration_min == 75


def test_ac_095_a_school_week_spreads_out_instead_of_piling_onto_the_weekend(tmp_path):
    """AC-095 [e2e-test]: On a timetable of short weekday slots and long weekends, weekday slots are used, quality sessions go midweek, the long ride and long run take different weekend days, and no weekend day carries two long sessions or more than its fair share plus the long session"""
    shutil.copy(FIXTURE, tmp_path / "athlete.yaml")
    ws = Workspace(tmp_path / "athlete.yaml", tmp_path / "out")
    for week in (date(2026, 11, 2), date(2026, 11, 23)):
        res = ws.plan_week(week)
        by_day: dict[date, list[Session]] = defaultdict(list)
        for p in res.plan.placements:
            assert p.slot.on is not None
            by_day[p.slot.on].append(p.session)
        weekdays = [d for d in by_day if d.weekday() < 5]
        assert len(weekdays) >= 4, week  # Mon-Thu all used
        quality = [s for ss in by_day.values() for s in ss if s.intensity >= 3]
        assert any(d.weekday() < 5 for d, ss in by_day.items()
                   for s in ss if s in quality), week
        longs = {s.discipline: d for d, ss in by_day.items() for s in ss if s.kind == "long"}
        assert longs["bike"] != longs["run"] and {longs["bike"].weekday(),
                                                  longs["run"].weekday()} == {5, 6}
        for d, ss in by_day.items():
            if d.weekday() >= 5:
                assert sum(s.kind == "long" for s in ss) == 1
                others = sum(s.duration_min for s in ss if s.kind != "long")
                assert others <= 90, (week, d, [s.label for s in ss])
        assert res.plan.planned_minutes >= 0.9 * sum(res.targets.values())

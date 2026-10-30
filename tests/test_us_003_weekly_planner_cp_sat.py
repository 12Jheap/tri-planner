"""US-003: Weekly planner (CP-SAT) (v0)."""

from collections import defaultdict
from datetime import timedelta
from itertools import pairwise

from conftest import DAYS, make_config, make_session

from planner.config import calendar_for_week
from planner.sessions import build_week_sessions
from planner.solver import plan_week, slot_uid
from planner.targets import weekly_targets


def test_ac_009_never_places_a_session_in_a_slot_whose_location_lacks_its_re(monday):
    """AC-009 [e2e-test]: Never places a session in a slot whose location lacks its required facility or is outside opening hours (hard constraint)"""
    cfg = make_config(
        [
            {"day": "mon", "start": "06:30", "end": "07:30", "location": "School"},
            {"day": "mon", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "wed", "start": "06:30", "end": "07:30", "location": "School"},
            {"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"},
        ]
    )
    slots = calendar_for_week(cfg, monday)
    sessions = [make_session("swim-key", "swim", 45), make_session("bike-key", "bike", 60)]
    # Even if the athlete is most reliable at 06:30, the swim can't go there (no morning pool)
    # and can't go Home (no pool at all).
    p = {"mon-06:30-07:30@School": 1.0, "wed-06:30-07:30@School": 1.0, "sat-08:00-11:00@Home": 1.0}
    plan = plan_week(sessions, slots, cfg, p)
    assert plan.status in ("optimal", "feasible")
    swim = plan.placement("swim-key")
    assert swim is not None and swim.slot.day == "mon" and swim.start.hour >= 16
    for pl in plan.placements:
        loc = cfg.location(pl.slot.location)
        assert pl.facility_ok
        assert pl.session.fits(loc, pl.slot.day, pl.start, pl.end)

    # Whole-week check on a realistic set of sessions.
    week = build_week_sessions(weekly_targets("sprint", "base", 900), "sprint", "base")
    full = make_config(
        [{"day": d, "start": "06:30", "end": "07:30", "location": "School"} for d in DAYS[:5]]
        + [{"day": d, "start": "16:15", "end": "18:15", "location": "School"} for d in DAYS[:5]]
        + [{"day": d, "start": "08:00", "end": "11:00", "location": "Home"} for d in DAYS[5:]]
    )
    plan = plan_week(week, calendar_for_week(full, monday), full)
    for pl in plan.placements:
        assert pl.session.fits(full.location(pl.slot.location), pl.slot.day, pl.start, pl.end)


def test_ac_010_never_places_two_hard_sessions_on_consecutive_days_or_a_sess(monday):
    """AC-010 [unit-test]: Never places two hard sessions on consecutive days or a session overlapping another"""
    cfg = make_config(
        [{"day": d, "start": "16:15", "end": "18:15", "location": "School"} for d in DAYS[:5]]
        + [{"day": d, "start": "08:00", "end": "11:00", "location": "Home"} for d in DAYS[5:]]
    )
    sessions = [
        make_session("bike-thr", "bike", 50, 4),
        make_session("run-thr", "run", 40, 4),
        make_session("swim-thr", "swim", 40, 4),
        make_session("bike-end", "bike", 75, 2, key=False),
        make_session("run-easy", "run", 40, 1, key=False),
        make_session("strength", "strength", 30, 2, key=False),
    ]
    plan = plan_week(sessions, calendar_for_week(cfg, monday), cfg)
    assert plan.status in ("optimal", "feasible")
    hard_days = sorted(pl.slot.on for pl in plan.placements if pl.session.hard)
    assert len(hard_days) == 3
    for a, b in pairwise(hard_days):
        assert (b - a) >= timedelta(days=2)
    by_slot = defaultdict(list)
    for pl in plan.placements:
        by_slot[slot_uid(pl.slot)].append(pl)
    for pls in by_slot.values():
        pls.sort(key=lambda p: p.start)
        for a, b in pairwise(pls):
            assert a.end <= b.start  # no overlap
        assert pls[-1].end <= pls[-1].slot.end


def test_ac_011_objective_maximises_p_complete_slot_session_value(monday):
    """AC-011 [unit-test]: Objective maximises Σ P(complete | slot) × session value"""
    cfg = make_config(
        [
            {"day": "mon", "start": "16:15", "end": "17:15", "location": "School"},
            {"day": "thu", "start": "16:15", "end": "17:15", "location": "School"},
        ]
    )
    slots = calendar_for_week(cfg, monday)
    s = make_session("bike", "bike", 45)
    mon, thu = "mon-16:15-17:15@School", "thu-16:15-17:15@School"
    plan = plan_week([s], slots, cfg, {mon: 0.2, thu: 0.9})
    assert plan.placement("bike").slot.day == "thu"
    assert abs(plan.objective - 0.9 * s.value) < 0.01
    plan = plan_week([s], slots, cfg, {mon: 0.9, thu: 0.2})
    assert plan.placement("bike").slot.day == "mon"
    # With room for only one flex session, the higher-value one wins.
    small = make_session("small", "run", 30, 1, key=False)
    big = make_session("big", "run", 60, 2, key=False)
    one_slot = make_config([{"day": "mon", "start": "16:15", "end": "17:15", "location": "School"}])
    plan = plan_week([small, big], calendar_for_week(one_slot, monday), one_slot)
    assert [p.session.id for p in plan.placements] == ["big"]
    assert [s.id for s in plan.dropped] == ["small"]


def test_ac_012_returns_a_plan_within_10_seconds_for_a_7_day_30_slot_week(monday):
    """AC-012 [metric]: Returns a plan within 10 seconds for a 7-day, 30-slot week"""
    times = [("06:00", "07:00"), ("07:15", "08:15"), ("12:00", "13:00"), ("16:15", "18:15"),
             ("19:00", "20:00")]
    slots = []
    for d in DAYS:
        for start, end in times:
            slots.append({"day": d, "start": start, "end": end, "location": "School"})
    slots = slots[:30]
    cfg = make_config(slots)
    week = build_week_sessions(weekly_targets("olympic", "build", 1200), "olympic", "build")
    cal = calendar_for_week(cfg, monday)
    assert len(cal) == 30
    plan = plan_week(week, cal, cfg)
    assert plan.status in ("optimal", "feasible")
    assert plan.solve_seconds < 10


def test_ac_013_returns_infeasible_with_the_binding_constraint_named_when_ta(monday):
    """AC-013 [unit-test]: Returns "infeasible" with the binding constraint named when targets can't fit"""
    no_pool = make_config(
        [{"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"}]
    )
    plan = plan_week([make_session("swim-key", "swim", 40)], calendar_for_week(no_pool, monday), no_pool)
    assert plan.status == "infeasible"
    assert "swim-key" in plan.reason and "pool" in plan.reason

    tiny = make_config([{"day": "mon", "start": "16:15", "end": "17:15", "location": "School"}])
    plan = plan_week(
        [make_session("a", "bike", 50), make_session("b", "run", 50)],
        calendar_for_week(tiny, monday),
        tiny,
    )
    assert plan.status == "infeasible" and "capacity" in plan.reason

    three_days = make_config(
        [{"day": d, "start": "16:15", "end": "18:15", "location": "School"} for d in DAYS[:3]]
    )
    hard = [make_session(f"h{i}", disc, 40, 4) for i, disc in enumerate(["bike", "run", "swim"])]
    plan = plan_week(hard, calendar_for_week(three_days, monday), three_days)
    assert plan.status == "infeasible"
    assert "no hard sessions on consecutive days" in plan.reason

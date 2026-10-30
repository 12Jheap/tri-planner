"""Weekly planner: places sessions into real slots with OR-Tools CP-SAT (US-003).

Hard constraints (never broken):
- a session only goes where its facilities exist and are open (facility-aware mode),
- sessions in a slot must fit in the slot (no overlaps),
- at most one session per discipline per day (strength exempt),
- at most one hard session per day and never hard sessions on consecutive days,
- every Key session is placed (or the plan is infeasible, with the reason named),
- frozen sessions stay where they are.

Objective: maximise Σ P(complete | slot) × session value − churn penalty × moves.
So sessions migrate towards the slots this athlete actually uses.
"""

from __future__ import annotations

import time as _time
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Literal

from ortools.sat.python import cp_model
from pydantic import BaseModel

from planner.config import AthleteConfig, Slot, minutes_between
from planner.sessions import Session

DEFAULT_P = 0.75
SCALE = 1000
STEP = 15  # minutes; granularity for fitting a session inside a facility window


def slot_uid(slot: Slot) -> str:
    """Unique id of a dated slot within a plan."""
    return f"{slot.on}|{slot.key}"


def _add(t: time, minutes: int) -> time:
    return (datetime.combine(date(2000, 1, 1), t) + timedelta(minutes=minutes)).time()


class Placement(BaseModel):
    session: Session
    slot: Slot
    start: time
    reason: str | None = None  # why it moved, on a re-plan
    facility_ok: bool = True  # False only possible in time-only experiment weeks

    @property
    def starts_at(self) -> datetime:
        assert self.slot.on is not None
        return datetime.combine(self.slot.on, self.start)

    @property
    def end(self) -> time:
        return _add(self.start, self.session.duration_min)


class Plan(BaseModel):
    status: Literal["optimal", "feasible", "infeasible"]
    placements: list[Placement] = []
    dropped: list[Session] = []
    reason: str | None = None
    objective: float = 0.0
    facility_aware: bool = True
    solve_seconds: float = 0.0

    @property
    def planned_minutes(self) -> int:
        return sum(p.session.duration_min for p in self.placements)

    def placement(self, session_id: str) -> Placement | None:
        return next((p for p in self.placements if p.session.id == session_id), None)

    def assignment(self) -> dict[str, str]:
        return {p.session.id: slot_uid(p.slot) for p in self.placements}


def _earliest_offset(s: Session, slot: Slot, config: AthleteConfig, facility_aware: bool) -> int | None:
    """Earliest minute offset inside the slot where the session can run, or None."""
    if s.duration_min > slot.minutes:
        return None
    if not facility_aware or not s.requires:
        return 0
    loc = config.location(slot.location)
    for off in range(0, slot.minutes - s.duration_min + 1, STEP):
        start = _add(slot.start, off)
        if s.fits(loc, slot.day, start, _add(start, s.duration_min)):
            return off
    return None


def _needs(s: Session) -> str:
    return " + ".join("/".join(f.value for f in g) for g in s.requires) or "nothing"


def plan_week(
    sessions: list[Session],
    slots: list[Slot],
    config: AthleteConfig,
    p_complete: Mapping[str, float] | None = None,
    *,
    facility_aware: bool = True,
    fixed: Mapping[str, str] | None = None,
    previous: Mapping[str, str] | None = None,
    churn_penalty: float = 0.3,
    stacking_penalty: float = 0.25,
    default_p: float = DEFAULT_P,
    time_limit: float = 10.0,
) -> Plan:
    """Place `sessions` into dated `slots`.

    p_complete: slot.key -> probability the athlete actually trains in that slot.
    fixed: session_id -> slot_uid that must not change (frozen sessions).
    previous: session_id -> slot_uid from the last plan; moving away costs `churn_penalty`.
    stacking_penalty: cost of each session beyond the first on the same day (spreads load).
    """
    started = _time.perf_counter()
    p_complete = p_complete or {}
    fixed = dict(fixed or {})
    previous = previous or {}
    by_uid = {slot_uid(k): k for k in slots}

    offsets: dict[tuple[str, str], int] = {}
    for s in sessions:
        for k in slots:
            off = _earliest_offset(s, k, config, facility_aware)
            if off is not None:
                offsets[(s.id, slot_uid(k))] = off

    # Fast, readable diagnosis before modelling.
    for s in sessions:
        if s.key and not any(sid == s.id for sid, _ in offsets):
            return Plan(
                status="infeasible",
                facility_aware=facility_aware,
                reason=(
                    f"no slot this week can host Key session '{s.id}' "
                    f"({s.duration_min}', needs {_needs(s)}): check facilities, opening "
                    f"windows and slot lengths"
                ),
            )
    key_minutes = sum(s.duration_min for s in sessions if s.key)
    capacity = sum(k.minutes for k in slots)
    if key_minutes > capacity:
        return Plan(
            status="infeasible",
            facility_aware=facility_aware,
            reason=f"capacity: Key sessions need {key_minutes}' but only {capacity}' is free",
        )

    forbidden_pairs: set[tuple[str, str, str]] = set()  # (uid, sid_a, sid_b) found by post-check
    for _ in range(6):
        plan = _solve(
            sessions, slots, by_uid, offsets, p_complete, fixed, previous, churn_penalty,
            stacking_penalty, default_p, time_limit, facility_aware, forbidden_pairs, config,
        )
        if plan.status == "infeasible":
            break
        clash = _window_clash(plan, config)
        if clash is None:
            break
        forbidden_pairs.add(clash)
    plan.solve_seconds = _time.perf_counter() - started
    return plan


def _solve(
    sessions: list[Session],
    slots: list[Slot],
    by_uid: dict[str, Slot],
    offsets: dict[tuple[str, str], int],
    p_complete: Mapping[str, float],
    fixed: Mapping[str, str],
    previous: Mapping[str, str],
    churn_penalty: float,
    stacking_penalty: float,
    default_p: float,
    time_limit: float,
    facility_aware: bool,
    forbidden_pairs: set[tuple[str, str, str]],
    config: AthleteConfig,
) -> Plan:
    m = cp_model.CpModel()
    x = {pair: m.NewBoolVar(f"x[{pair[0]},{pair[1]}]") for pair in offsets}
    assumptions: dict[int, str] = {}
    literals: list[cp_model.IntVar] = []

    def assume(name: str) -> cp_model.IntVar:
        lit = m.NewBoolVar(name)
        assumptions[lit.Index()] = name
        literals.append(lit)
        return lit

    by_session: dict[str, list[cp_model.IntVar]] = defaultdict(list)
    by_slot: dict[str, list[tuple[Session, cp_model.IntVar]]] = defaultdict(list)
    sess = {s.id: s for s in sessions}
    for (sid, uid), var in x.items():
        by_session[sid].append(var)
        by_slot[uid].append((sess[sid], var))

    for s in sessions:
        vars_ = by_session.get(s.id, [])
        if s.key:
            m.Add(sum(vars_) == 1).OnlyEnforceIf(assume(f"place Key session '{s.id}'"))
        else:
            m.Add(sum(vars_) <= 1)

    for sid, uid in fixed.items():
        if (sid, uid) in x:
            m.Add(x[(sid, uid)] == 1).OnlyEnforceIf(assume(f"keep frozen session '{sid}'"))

    for uid, items in by_slot.items():
        m.Add(sum(s.duration_min * v for s, v in items) <= by_uid[uid].minutes)
    for uid, a, b in forbidden_pairs:
        m.Add(x[(a, uid)] + x[(b, uid)] <= 1)

    days = sorted({k.on for k in slots if k.on is not None})
    per_day_disc: dict[tuple[object, str], list[cp_model.IntVar]] = defaultdict(list)
    hard_on: dict[object, list[cp_model.IntVar]] = defaultdict(list)
    for (sid, uid), var in x.items():
        s, day = sess[sid], by_uid[uid].on
        if s.discipline != "strength":
            per_day_disc[(day, s.discipline)].append(var)
        if s.hard:
            hard_on[day].append(var)
    one_per_day = assume("one session per discipline per day")
    for vars_ in per_day_disc.values():
        m.Add(sum(vars_) <= 1).OnlyEnforceIf(one_per_day)
    spacing = assume("no hard sessions on consecutive days")
    hd = {}
    for d in days:
        if hard_on.get(d):
            hd[d] = m.NewBoolVar(f"hard[{d}]")
            m.AddMaxEquality(hd[d], hard_on[d])
            m.Add(sum(hard_on[d]) <= 1).OnlyEnforceIf(spacing)
    for d in days:
        nxt = d + timedelta(days=1)  # type: ignore[operator]
        if d in hd and nxt in hd:
            m.Add(hd[d] + hd[nxt] <= 1).OnlyEnforceIf(spacing)

    terms = []
    for (sid, uid), var in x.items():
        p = p_complete.get(by_uid[uid].key, default_p)
        terms.append(round(SCALE * p * sess[sid].value) * var)
    move_penalty = round(SCALE * churn_penalty)
    for sid, uid in previous.items():
        if sid in sess and sid not in fixed:
            stay = x.get((sid, uid))
            # Moving (or dropping) a previously placed session costs a fixed penalty.
            terms.append(move_penalty * stay if stay is not None else 0)
    # Spread the load: every session beyond the first on a day costs a little.
    per_day: dict[object, list[cp_model.IntVar]] = defaultdict(list)
    for (_sid, uid), var in x.items():
        per_day[by_uid[uid].on].append(var)
    stack_cost = round(SCALE * stacking_penalty)
    for d, vars_ in per_day.items():
        if len(vars_) > 1 and stack_cost:
            extra = m.NewIntVar(0, len(vars_), f"extra[{d}]")
            m.Add(extra >= sum(vars_) - 1)
            terms.append(-stack_cost * extra)
    m.Maximize(sum(terms))
    m.AddAssumptions(literals)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.Solve(m)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solver.parameters.num_workers = 1
        solver.Solve(m)
        core = [assumptions[i] for i in solver.SufficientAssumptionsForInfeasibility() if i in assumptions]
        reason = "; ".join(core) if core else "no feasible arrangement found within the time limit"
        return Plan(status="infeasible", facility_aware=facility_aware, reason=f"conflict: {reason}")

    placements: list[Placement] = []
    for uid, items in by_slot.items():
        chosen = [s for s, v in items if solver.Value(v)]
        chosen.sort(key=lambda s: (offsets[(s.id, uid)], not s.key))
        slot, cursor = by_uid[uid], 0
        for s in chosen:
            off = max(cursor, offsets[(s.id, uid)])
            start = _add(slot.start, off)
            loc = config.location(slot.location)
            ok = s.fits(loc, slot.day, start, _add(start, s.duration_min))
            placements.append(Placement(session=s, slot=slot, start=start, facility_ok=ok))
            cursor = off + s.duration_min
    placements.sort(key=lambda p: p.starts_at)
    placed = {p.session.id for p in placements}
    return Plan(
        status="optimal" if status == cp_model.OPTIMAL else "feasible",
        placements=placements,
        dropped=[s for s in sessions if s.id not in placed],
        objective=solver.ObjectiveValue() / SCALE,
        facility_aware=facility_aware,
    )


def _window_clash(plan: Plan, config: AthleteConfig) -> tuple[str, str, str] | None:
    """Two sessions sharing a slot can push one outside its facility window."""
    if not plan.facility_aware:
        return None
    by_slot: dict[str, list[Placement]] = defaultdict(list)
    for p in plan.placements:
        by_slot[slot_uid(p.slot)].append(p)
    for uid, ps in by_slot.items():
        for p in ps:
            if p.session.duration_min and minutes_between(p.start, p.slot.end) < p.session.duration_min:
                first = next(q for q in ps if q is not p)
                return (uid, p.session.id, first.session.id)
            if not p.facility_ok:
                other = next((q for q in ps if q is not p), None)
                if other is not None:
                    return (uid, p.session.id, other.session.id)
    return None

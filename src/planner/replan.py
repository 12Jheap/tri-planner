"""Re-plan the rest of the week when life (or a niggle) happens (US-005).

Rules:
- Sessions starting in the next 24 hours are frozen unless you flag them.
- Churn is penalised: only the sessions that need to move, move.
- Every move carries a reason code.
- An injury on a discipline (you declare it — this app never diagnoses) remaps
  that discipline's sessions to an allowed one and records what you lost in a
  per-discipline debt ledger.
- Two pain reports in a row on a discipline freeze it and tell you to see a physio.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from planner.adherence import LogRow
from planner.config import AthleteConfig, calendar_for_week, week_start
from planner.sessions import REQUIRES, Session
from planner.solver import Plan, plan_week, slot_uid

Reason = Literal[
    "injury_remap",
    "discipline_frozen",
    "missed_session_rescheduled",
    "slot_unavailable",
    "athlete_flagged",
    "better_slot",
    "no_room",
]

# Substitute discipline and minutes multiplier for similar aerobic load.
# Cycling costs less per minute than running, so lost run time becomes more bike time.
SUBSTITUTES: dict[str, list[tuple[str, float]]] = {
    "run": [("bike", 1.3)],
    "swim": [("bike", 1.0)],
    "bike": [("swim", 1.0), ("run", 0.75)],
}
MAX_SUB_INTENSITY = 3  # substitutes never go above tempo
PHYSIO = (
    "Pain reported in your last two {d} sessions. {d} is paused. "
    "See a physio before restarting — this planner doesn't diagnose injuries."
)


class Injury(BaseModel):
    discipline: str
    until: date  # inclusive
    note: str = ""

    def active(self, on: date) -> bool:
        return on <= self.until


class DebtLedger(BaseModel):
    """Discipline-specific minutes lost to substitutions, to win back later."""

    minutes: dict[str, int] = {}

    def add(self, discipline: str, mins: int) -> None:
        self.minutes[discipline] = self.minutes.get(discipline, 0) + mins


class Move(BaseModel):
    session_id: str
    from_slot: str | None
    to_slot: str | None
    reason: Reason


class ReplanResult(BaseModel):
    plan: Plan
    moves: list[Move]
    notes: list[str]
    ledger: DebtLedger
    frozen_disciplines: list[str]


def frozen_by_pain(rows: Iterable[LogRow]) -> dict[str, str]:
    """Disciplines whose last two completed sessions both reported pain -> message."""
    done: dict[str, list[LogRow]] = defaultdict(list)
    for r in rows:
        if r.status in ("done", "moved"):
            done[r.discipline].append(r)
    out = {}
    for disc, rs in done.items():
        last = sorted(rs, key=lambda r: r.on)[-2:]
        if len(last) == 2 and all(r.pain for r in last):
            out[disc] = PHYSIO.format(d=disc)
    return out


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def substitute(
    sessions: list[Session], blocked: set[str], ledger: DebtLedger
) -> tuple[list[Session], dict[str, str]]:
    """Replace sessions of blocked disciplines. Returns (sessions, {new_id: original_id})."""
    out: list[Session] = []
    origin: dict[str, str] = {}
    for s in sessions:
        if s.discipline not in blocked:
            out.append(s)
            continue
        ledger.add(s.discipline, s.duration_min)
        options = [(d, k) for d, k in SUBSTITUTES.get(s.discipline, []) if d not in blocked]
        if not options:
            continue
        disc, mult = options[0]
        new = Session(
            id=f"{s.id}-as-{disc}",
            discipline=disc,  # type: ignore[arg-type]
            kind="substitute",
            duration_min=max(20, _round5(s.duration_min * mult)),
            intensity=min(s.intensity, MAX_SUB_INTENSITY),
            requires=REQUIRES[disc],
            key=s.key,
        )
        out.append(new)
        origin[new.id] = s.id
    return out, origin


def replan(
    config: AthleteConfig,
    previous: Plan,
    now: datetime,
    *,
    p_complete: Mapping[str, float] | None = None,
    done_ids: Iterable[str] = (),
    skipped_ids: Iterable[str] | None = None,
    flagged: Iterable[str] = (),
    unavailable_slots: Iterable[str] = (),
    injuries: Iterable[Injury] = (),
    log: Iterable[LogRow] = (),
    ledger: DebtLedger | None = None,
    churn_penalty: float = 0.3,
) -> ReplanResult:
    """Rebuild the rest of the week from `now`.

    done_ids: sessions already completed this week.
    skipped_ids: sessions logged as skipped. Only these past Key sessions get a
        catch-up; unlogged ones are unknown, not missed. None = treat every past,
        not-done Key session as missed.
    flagged: sessions you want moved even if they're in the next 24h.
    unavailable_slots: slot uids (see solver.slot_uid) that are no longer possible.
    """
    ledger = ledger or DebtLedger()
    done, flagged_set, gone = set(done_ids), set(flagged), set(unavailable_slots)
    skipped = None if skipped_ids is None else set(skipped_ids)
    horizon = now + timedelta(hours=24)
    notes: list[str] = []

    pain = frozen_by_pain(log)
    notes.extend(pain.values())
    blocked = {i.discipline for i in injuries if i.active(now.date())} | set(pain)

    # Re-plan the plan's own week (you may be re-planning on the Sunday before it starts).
    dates = [p.slot.on for p in previous.placements if p.slot.on is not None]
    monday = week_start(min(dates)) if dates else week_start(now.date())
    slots = [
        k for k in calendar_for_week(config, monday)
        if k.starts_at >= now and slot_uid(k) not in gone
    ]
    prev_assign = previous.assignment()
    fixed: dict[str, str] = {}
    to_plan: list[Session] = []
    missed: set[str] = set()
    planned_ids = {p.session.id for p in previous.placements}
    for p in previous.placements:
        s = p.session
        if s.id in done:
            continue
        if p.starts_at < now:
            was_missed = skipped is None or s.id in skipped
            if s.key and was_missed and f"{s.id}-redo" not in planned_ids:
                # Missed Key session: try to fit it back in, under a new id so the
                # original's log row stays as the record. It goes back in as Flex:
                # a catch-up is a bonus and must never make the week infeasible.
                rid = s.id if s.id.endswith("-redo") else f"{s.id}-redo"
                redo = Session(**{**s.model_dump(exclude={"value"}), "id": rid, "key": False})
                to_plan.append(redo)
                missed.add(redo.id)
            continue
        to_plan.append(s)
        uid = slot_uid(p.slot)
        if (
            p.starts_at < horizon
            and s.id not in flagged_set
            and uid not in gone
            and s.discipline not in blocked
        ):
            fixed[s.id] = uid

    to_plan, origin = substitute(to_plan, blocked, ledger)
    for disc in sorted(blocked - set(pain)):
        notes.append(f"{disc} paused (declared injury); its load moved to other disciplines.")
    if ledger.minutes:
        owed = ", ".join(f"{d} {m}'" for d, m in ledger.minutes.items())
        notes.append(f"Discipline debt to win back later: {owed}.")

    # Substitutes inherit their original's slot as the churn reference.
    reference = {sid: prev_assign[origin.get(sid, sid)] for sid in
                 [s.id for s in to_plan] if origin.get(sid, sid) in prev_assign}
    new = plan_week(
        to_plan, slots, config, p_complete,
        fixed=fixed, previous=reference, churn_penalty=churn_penalty,
    )
    if new.status == "infeasible":
        notes.append(f"Couldn't fit everything: {new.reason}")
        return ReplanResult(
            plan=new, moves=[], notes=notes, ledger=ledger, frozen_disciplines=sorted(blocked)
        )

    moves: list[Move] = []
    for p in new.placements:
        sid = p.session.id
        before = reference.get(sid)
        after = slot_uid(p.slot)
        if before == after and sid not in origin:
            continue  # unchanged (a substitute always counts: the session itself changed)
        reason: Reason
        if sid in origin:
            reason = "discipline_frozen" if origin_disc(sid, origin, previous) in pain else "injury_remap"
        elif sid in missed:
            reason = "missed_session_rescheduled"
        elif before in gone:
            reason = "slot_unavailable"
        elif sid in flagged_set:
            reason = "athlete_flagged"
        else:
            reason = "better_slot"
        p.reason = reason
        moves.append(Move(session_id=sid, from_slot=before, to_slot=after, reason=reason))
    for s in new.dropped:
        moves.append(Move(session_id=s.id, from_slot=reference.get(s.id), to_slot=None, reason="no_room"))
    return ReplanResult(
        plan=new, moves=moves, notes=notes, ledger=ledger, frozen_disciplines=sorted(blocked)
    )


def origin_disc(sid: str, origin: dict[str, str], previous: Plan) -> str:
    p = previous.placement(origin[sid])
    return p.session.discipline if p else ""

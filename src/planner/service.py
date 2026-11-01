"""One place for "what the app does", shared by the CLI and the website.

A `Workspace` is your config file plus your `out/` folder. Every action (plan a
week, log a session, re-plan) goes through here, so both front ends behave
exactly the same and the tests cover both.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from planner.adherence import (
    LOW_RESPONSE,
    AdherenceModel,
    LogRow,
    WeeklySummary,
    read_log,
    sync_log,
    weekly_summaries,
    write_log,
)
from planner.config import AthleteConfig, Slot, calendar_for_week, load_config, week_start
from planner.export import export_week
from planner.friendly import resolve_slots
from planner.replan import DebtLedger, Injury, Move, frozen_by_pain, replan, substitute
from planner.report import week_type
from planner.sessions import build_week_sessions, how_to
from planner.solver import Placement, Plan, fit_to_slots, plan_week
from planner.store import InjuryStore, PlanStore
from planner.targets import DEFAULT_HOURS, Phase, phase_for, weekly_targets

Status = Literal["done", "skipped", "moved"]


class PlannerError(Exception):
    """Something the athlete can fix (no plan yet, week can't fit, unknown session)."""


class WeekResult(BaseModel):
    week: date
    phase: str
    week_type: str
    plan: Plan
    version: int
    targets: dict[str, int]
    available_min: int
    previous_min: int | None
    notes: list[str]
    files: dict[str, list[Path]]
    log_summary: str


class ReplanOutcome(BaseModel):
    week: date
    plan: Plan
    version: int
    moves: list[Move]
    notes: list[str]
    log_summary: str


def status_text(row: LogRow | None) -> str:
    if row is None or not row.logged:
        return ""
    mark = {"done": "✓", "moved": "✓", "skipped": "✗"}.get(row.status, "")
    extra = f" {row.actual_min}'" if row.status in ("done", "moved") else f" {row.reason}".rstrip()
    return f"{mark} {row.status}{extra}{' · pain' if row.pain else ''}"


def plan_markdown(plan: Plan, title: str, log: dict[str, LogRow] | None = None) -> str:
    status = log is not None
    head = "| Day | Time | Where | Session | Note |" + (" Logged |" if status else "")
    lines = [f"# {title}", "", head, "|---" * (6 if status else 5) + "|"]
    for p in plan.placements:
        note = p.reason.replace("_", " ") if p.reason else ""
        if not p.facility_ok:
            note = "⚠ no facility (time-only week)"
        row = (
            f"| {p.slot.on:%a %d %b} | {p.start:%H:%M}–{p.end:%H:%M} | {p.slot.location} "
            f"| {p.session.label} | {note} |"
        )
        if log is not None:
            row += f" {status_text(log.get(p.session.id))} |"
        lines.append(row)
    if plan.dropped:
        lines += ["", "Didn't fit this week: " + ", ".join(s.id for s in plan.dropped)]
    lines += ["", f"Planned: {plan.planned_minutes / 60:.1f}h", "", "## How to do each session", ""]
    for kind in dict.fromkeys(p.session.kind for p in plan.placements):
        s = next(p.session for p in plan.placements if p.session.kind == kind)
        lines.append(f"- **{kind.replace('_', ' ')}**: {how_to(s)}")
    lines += ["", "Effort is out of 5: 2 = chatty, 3 = short sentences, 4 = a few words."]
    return "\n".join(lines)


def slot_label(uid: str | None) -> str:
    """'2026-11-12|thu-16:15-18:15@School' -> 'Thu 16:15 School'."""
    if not uid:
        return "—"
    key = uid.split("|")[-1]
    when, _, place = key.partition("@")
    day, _, rest = when.partition("-")
    return f"{day.title()} {rest.split('-')[0]} {place}"


def _log_rows(plan: Plan, week: date, wtype: str) -> list[LogRow]:
    return [
        LogRow(
            on=p.slot.on, week=week, session_id=p.session.id, discipline=p.session.discipline,
            slot_key=p.slot.key, planned_min=p.session.duration_min, week_type=wtype,
        )
        for p in plan.placements
        if p.slot.on is not None
    ]


class Workspace:
    """Your config + your out/ folder."""

    def __init__(
        self, config_path: str | Path, out: str | Path = "out", prior: tuple[float, float] = (2, 2)
    ) -> None:
        self.config_path = Path(config_path)
        self.out = Path(out)
        self.prior = prior
        self._cfg: AthleteConfig | None = None

    # ---- reading -------------------------------------------------------------------
    @property
    def cfg(self) -> AthleteConfig:
        if self._cfg is None:
            self._cfg = load_config(self.config_path)
        return self._cfg

    def reload(self) -> None:
        self._cfg = None

    def now(self) -> datetime:
        """Wall-clock time where the athlete lives; plans are in local time."""
        return datetime.now(ZoneInfo(self.cfg.timezone)).replace(tzinfo=None)

    @property
    def log_path(self) -> Path:
        return self.out / "log.csv"

    def log(self) -> list[LogRow]:
        return read_log(self.log_path) if self.log_path.exists() else []

    def plans(self) -> PlanStore:
        return PlanStore(self.out / "plan_session_version.jsonl")

    def injuries(self) -> InjuryStore:
        return InjuryStore(self.out / "injuries.json")

    def plan(self, week: date) -> Plan | None:
        return self.plans().load(week)

    def require_plan(self, week: date) -> Plan:
        plan = self.plan(week)
        if plan is None:
            raise PlannerError(f"No plan for the week of {week:%d %b} yet. Plan it first.")
        return plan

    def log_index(self, week: date) -> dict[str, LogRow]:
        return {r.session_id: r for r in self.log() if r.week == week}

    def summary(self, week: date) -> WeeklySummary | None:
        return next((s for s in weekly_summaries(self.log()) if s.week == week), None)

    def planned_weeks(self) -> list[date]:
        return sorted({r.week for r in self.log()})

    def slots(self, week: date) -> list[Slot]:
        return calendar_for_week(self.cfg, week)

    # ---- actions -------------------------------------------------------------------
    def _previous_minutes(self, log: list[LogRow], week: date) -> int | None:
        """What you actually did last week, if you logged enough of it to trust."""
        last = [s for s in weekly_summaries(log) if s.week == week - timedelta(days=7)]
        if not last or last[0].completed_min <= 0 or last[0].response_rate < LOW_RESPONSE:
            return None
        return last[0].completed_min

    def _save(self, plan: Plan, week: date, note: str, title: str, wtype: str
              ) -> tuple[int, dict[str, list[Path]], str]:
        wk_dir = self.out / str(week)
        files = export_week(plan, wk_dir, self.cfg.timezone)
        version = self.plans().append(plan, week, note)
        (wk_dir / "plan.md").write_text(plan_markdown(plan, f"{title} (v{version})"), "utf-8")
        synced = sync_log(self.log(), _log_rows(plan, week, wtype), week)
        write_log(self.log_path, synced.rows)
        summary = f"log: {synced.added} added, {synced.updated} moved, {synced.removed} removed"
        return version, files, summary

    def plan_week(
        self,
        week: date,
        phase: Phase | None = None,
        *,
        ramp: float = 0.10,
        prev_minutes: int | None = None,
        experiment_start: date | None = None,
    ) -> WeekResult:
        cfg = self.cfg
        self.out.mkdir(parents=True, exist_ok=True)
        log = self.log()
        phase = phase or phase_for(week, cfg.race_date)
        slots = calendar_for_week(cfg, week)
        if not slots:
            raise PlannerError(f"No free time in the week of {week:%d %b}: add some slots.")
        available = sum(s.minutes for s in slots)
        prev = prev_minutes if prev_minutes is not None else self._previous_minutes(log, week)
        hours = cfg.weekly_hours or DEFAULT_HOURS[cfg.race]
        targets = weekly_targets(cfg.race, phase, available, prev, ramp, weekly_hours=hours)
        wtype = week_type(week, experiment_start)
        aware = wtype == "facility_aware"
        sessions, notes = fit_to_slots(build_week_sessions(targets, cfg.race, phase), slots, cfg,
                                       aware)
        istore = self.injuries()
        pain = frozen_by_pain(istore.pain_rows(log))
        injured = {i.discipline: i for i in istore.active(week)}
        if pain or injured:
            sessions, _ = substitute(sessions, set(pain) | set(injured), DebtLedger())
            notes += list(pain.values())
            notes += [f"{d} paused until {i.until:%a %d %b} (declared injury); its load moved to "
                      f"other sports. Clear the injury when you're back." for d, i in injured.items()]
        model = AdherenceModel(*self.prior).update(log)
        plan = plan_week(sessions, slots, cfg, model.probabilities(), facility_aware=aware,
                         default_p=model.p("unseen"))
        if plan.status == "infeasible":
            raise PlannerError(f"Can't build this week: {plan.reason}")
        title = f"Week of {week:%d %b %Y} — {phase}, {wtype.replace('_', '-')}"
        version, files, synced = self._save(plan, week, "week", title, wtype)
        return WeekResult(
            week=week, phase=phase, week_type=wtype, plan=plan, version=version, targets=targets,
            available_min=available, previous_min=prev, notes=notes, files=files,
            log_summary=synced,
        )

    def replan(
        self,
        now: datetime,
        week: date | None = None,
        *,
        unavailable: Sequence[str] = (),
        injuries: Sequence[Injury] = (),
        clear_injuries: Sequence[str] = (),
        flags: Sequence[str] = (),
    ) -> ReplanOutcome:
        week = week or week_start(now.date())
        previous = self.require_plan(week)
        ids = {p.session.id for p in previous.placements}
        unknown = [f for f in flags if f not in ids]
        if unknown:
            raise PlannerError(f"Unknown session {unknown}. This week's: {', '.join(sorted(ids))}")
        gone = resolve_slots(list(unavailable), self.slots(week))
        istore = self.injuries()
        active = istore.declare(list(injuries), list(clear_injuries), now.date())
        log = self.log()
        done = {r.session_id for r in log if r.week == week and r.status in ("done", "moved")}
        skipped = {r.session_id for r in log if r.week == week and r.status == "skipped"}
        model = AdherenceModel(*self.prior).update(log)
        res = replan(
            self.cfg, previous, now, p_complete=model.probabilities(), done_ids=done,
            skipped_ids=skipped, flagged=list(flags), unavailable_slots=gone, injuries=active,
            log=istore.pain_rows(log),
        )
        if res.plan.status == "infeasible":
            raise PlannerError(" ".join(res.notes) or f"Can't re-plan: {res.plan.reason}")
        wtype = next((r.week_type for r in log if r.week == week), "facility_aware")
        # The re-plan only covers what's left; keep the earlier sessions so the stored
        # week (and the log) still show what was planned before now.
        new_ids = {p.session.id for p in res.plan.placements}
        history = [p for p in previous.placements
                   if p.starts_at < now and p.session.id not in new_ids]
        full = res.plan.model_copy(
            update={"placements": sorted(history + res.plan.placements, key=lambda p: p.starts_at)}
        )
        version, _files, synced = self._save(full, week, "replan",
                                             f"Week of {week:%d %b %Y} — re-plan", wtype)
        return ReplanOutcome(week=week, plan=full, version=version, moves=res.moves,
                             notes=res.notes, log_summary=synced)

    def log_session(
        self,
        week: date,
        session_id: str,
        status: Status | None,
        *,
        minutes: int | None = None,
        reason: str | None = None,
        pain: bool = False,
    ) -> LogRow:
        """Record what happened. status=None clears the entry (back to unlogged)."""
        log = self.log()
        idx = next((i for i, r in enumerate(log)
                    if r.week == week and r.session_id == session_id), None)
        if idx is None:
            ids = ", ".join(r.session_id for r in log if r.week == week) or "none"
            raise PlannerError(f"No session '{session_id}' in the week of {week}. Sessions: {ids}")
        r = log[idx]
        if status is None:
            update: dict[str, object] = {"status": "", "reason": "", "actual_min": 0,
                                         "pain": False}
        elif status == "skipped":
            update = {"status": status, "reason": reason or "other", "actual_min": 0,
                      "pain": False}
        else:
            if minutes is not None and minutes < 0:
                raise PlannerError("minutes can't be negative")
            update = {"status": status, "reason": "", "pain": pain,
                      "actual_min": r.planned_min if minutes is None else minutes}
        log[idx] = LogRow.model_validate({**r.model_dump(), **update})
        write_log(self.log_path, log)
        return log[idx]


def placements_on(plan: Plan, day: date) -> list[Placement]:
    return [p for p in plan.placements if p.slot.on == day]

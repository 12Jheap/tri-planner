"""One place for "what the app does", shared by the CLI and the website.

A `Workspace` is your config file plus your `out/` folder. Every action (plan a
week, log a session, re-plan) goes through here, so both front ends behave
exactly the same and the tests cover both.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from planner.activities import (
    Activity,
    ImportResult,
    apply_matches,
    match_activities,
    read_activity_files,
    read_bytes,
)
from planner.adherence import (
    LOW_RESPONSE,
    AdherenceModel,
    LogRow,
    Source,
    WeeklySummary,
    read_log,
    sync_log,
    weekly_summaries,
    write_log,
)
from planner.config import AthleteConfig, Slot, calendar_for_week, load_config, week_start
from planner.export import export_week
from planner.friendly import resolve_slots
from planner.garmin import Fetcher, GarminError, Getter, fetch_activities, get_json
from planner.profile import Profile
from planner.replan import DebtLedger, Injury, Move, frozen_by_pain, replan, substitute
from planner.report import week_type
from planner.sessions import Session, build_week_sessions, how_to
from planner.solver import Placement, Plan, fill_slots, plan_week, slot_uid
from planner.store import InjuryStore, PlanStore
from planner.targets import DEFAULT_HOURS, Phase, is_recovery_week, phase_for, weekly_targets
from planner.wellness import (
    Wellness,
    heart_rates_from_garmin,
    parse_wellness,
    wellness_requests,
    zones_requests,
)
from planner.workouts import workout_for

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
    recovery: bool = False
    filled_min: int = 0


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


def plan_markdown(plan: Plan, title: str, log: dict[str, LogRow] | None = None,
                  profile: Profile | None = None) -> str:
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
    lines += ["", f"Planned: {plan.planned_minutes / 60:.1f}h", "", "## Sessions", ""]
    for p in plan.placements:
        w = workout_for(p.session, profile)
        head = f"**{p.slot.on:%a} {p.session.title}** ({p.session.duration_min} min)"
        lines += [f"{head}: {w.summary}", f"  _{how_to(p.session)}_", ""]
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
        """What you actually did recently: the bigger of the last two weeks you logged
        well enough to trust (so a recovery week doesn't reset your progress)."""
        recent = [s for s in weekly_summaries(log)
                  if week - timedelta(days=14) <= s.week < week
                  and s.completed_min > 0 and s.response_rate >= LOW_RESPONSE]
        return max((s.completed_min for s in recent), default=None)

    def _save(self, plan: Plan, week: date, note: str, title: str, wtype: str
              ) -> tuple[int, dict[str, list[Path]], str]:
        wk_dir = self.out / str(week)
        files = export_week(plan, wk_dir, self.cfg.timezone, self.cfg.profile)
        version = self.plans().append(plan, week, note)
        (wk_dir / "plan.md").write_text(
            plan_markdown(plan, f"{title} (v{version})", profile=self.cfg.profile), "utf-8")
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
        phase = phase or phase_for(week, cfg.race_date, cfg.race)
        slots = calendar_for_week(cfg, week)
        race_day = cfg.race_date if cfg.race_date and week <= cfg.race_date < week + timedelta(
            days=7) else None
        if race_day:  # race day itself is for racing
            slots = [k for k in slots if k.on is not None and k.on < race_day]
        if not slots:
            raise PlannerError(f"No free time in the week of {week:%d %b}: add some slots.")
        available = sum(s.minutes for s in slots)
        ahead = False
        if prev_minutes is not None:
            prev: int | None = prev_minutes
        else:  # same rule as the Season view, so the two always agree
            today = self.now().date()
            chain = {c.week: c for c in self.volume_chain(today, week)}
            prev = chain[week].prev if week in chain else self._previous_minutes(log, week)
            ahead = week > week_start(today) + timedelta(days=7)
        hours = cfg.profile.current_hours or DEFAULT_HOURS[cfg.race]
        recovery = phase != "taper" and is_recovery_week(week, cfg.race_date)
        targets = weekly_targets(cfg.race, phase, available, prev, ramp, weekly_hours=hours,
                                 recovery=recovery, strength=cfg.strength)
        wtype = week_type(week, experiment_start or cfg.experiment_start)
        aware = wtype == "facility_aware"
        sessions = build_week_sessions(targets, cfg.race, phase, recovery)
        notes: list[str] = []
        if ahead:
            notes.append("Planned ahead from your season projection, which assumes you "
                         "complete the weeks before. Re-plan it nearer the time to size it "
                         "from what you've actually done.")
        if recovery:
            notes.insert(0, "Recovery week: about 30% less and no hard sessions, so the last "
                            "three weeks' work turns into fitness.")
        istore = self.injuries()
        pain = frozen_by_pain(istore.pain_rows(log))
        injured = {i.discipline: i for i in istore.active(week)}
        if pain or injured:
            sessions, _ = substitute(sessions, set(pain) | set(injured), DebtLedger())
            notes += list(pain.values())
            notes += [f"{d} paused until {i.until:%a %d %b} (declared injury); its load moved to "
                      f"other sports. Clear the injury when you're back." for d, i in injured.items()]
        model = AdherenceModel(*self.prior).update(log)
        # Half distance needs more sessions than days, so two-session days are normal
        # (still never two of the same sport): the cost of stacking a day is lower.
        stacking = 0.1 if cfg.race == "half" else 0.25
        # A day's fair share: 1.6× the average training day. Beyond it each minute costs a
        # little, so the week spreads out instead of piling onto the weekend.
        train_days = len({k.on for k in slots}) or 1
        day_cap = max(60, round(1.6 * sum(targets.values()) / train_days))
        plan = plan_week(sessions, slots, cfg, model.probabilities(), facility_aware=aware,
                         default_p=model.p("unseen"), stacking_penalty=stacking,
                         day_cap=day_cap)
        if plan.status == "infeasible" and any(x.key for x in sessions):
            # A busy week (exams, travel): keep the sessions that fit rather than fail.
            relaxed = [x.model_copy(update={"key": False}) for x in sessions]
            plan = plan_week(relaxed, slots, cfg, model.probabilities(), facility_aware=aware,
                             default_p=model.p("unseen"), stacking_penalty=stacking,
                             day_cap=day_cap)
            if plan.status != "infeasible":
                kept = sum(1 for p in plan.placements if p.session.id in
                           {x.id for x in sessions if x.key})
                notes.append(f"Busy week: {kept} of {sum(x.key for x in sessions)} key "
                             "sessions fit, so the planner kept the most valuable ones.")
        if plan.status == "infeasible":
            raise PlannerError(f"Can't build this week: {plan.reason}")
        notes += plan.notes
        if race_day:
            notes.insert(0, f"Race week: race on {race_day:%A %d %b}. Short and sharp, "
                            "nothing on race day.")
        # Use spare slot time: lengthen aerobic sessions up to each sport's budget.
        budget = {d: max(targets.get(d, 0), sum(x.duration_min for x in sessions
                                                if x.discipline == d)) for d in targets}
        filled = 0
        if phase != "taper":  # a taper is meant to be short; don't pad it out
            plan, filled = fill_slots(plan, cfg, budget, aware)
        title = f"Week of {week:%d %b %Y} — {phase}, {wtype.replace('_', '-')}"
        version, files, synced = self._save(plan, week, "week", title, wtype)
        return WeekResult(
            week=week, phase=phase, week_type=wtype, plan=plan, version=version, targets=targets,
            available_min=available, previous_min=prev, notes=notes, files=files,
            log_summary=synced, recovery=recovery, filled_min=filled,
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


    def report_pain(self, week: date, session_id: str) -> LogRow:
        """Mark a logged session as painful (e.g. after a watch import, which can't know)."""
        log = self.log()
        for i, r in enumerate(log):
            if r.week == week and r.session_id == session_id and r.logged:
                log[i] = r.model_copy(update={"pain": True})
                write_log(self.log_path, log)
                return log[i]
        raise PlannerError("Log the session first, then say if something hurt.")

    # ---- watch / Garmin imports ------------------------------------------------------
    def import_activities(self, acts: list[Activity], source: Source = "file") -> ImportResult:
        """Tick off planned sessions from recorded activities (each imported once)."""
        log = self.log()
        weeks = {week_start(a.start.date()) for a in acts}
        plans = {w: p for w in weeks if (p := self.plan(w)) is not None}
        result = match_activities(acts, plans, log)
        if result.matched:
            write_log(self.log_path, apply_matches(log, result, source))
        return result

    def import_files(self, paths: Sequence[Path]) -> ImportResult:
        acts, bad = read_activity_files(list(paths), self.cfg.timezone)
        result = self.import_activities(acts, "file")
        result.unreadable = bad
        return result

    def import_uploads(self, files: Sequence[tuple[str, bytes]]) -> ImportResult:
        acts: list[Activity] = []
        bad: list[str] = []
        for name, data in files:
            try:
                acts += read_bytes(name, data, self.cfg.timezone)
            except Exception:  # noqa: BLE001 (report the file, keep going)
                bad.append(name)
        result = self.import_activities(acts, "file")
        result.unreadable = bad
        return result

    def sync_garmin(self, days: int = 14, fetch: Fetcher | None = None,
                    today: date | None = None) -> ImportResult:
        end = today or self.now().date()
        acts, bad = fetch_activities(end - timedelta(days=days), end, self.cfg.timezone, fetch)
        result = self.import_activities(acts, "garmin_personal")
        result.unreadable = bad
        return result

    # ---- Garmin: one refresh for activities + this morning's readiness ----------------
    @property
    def _status_path(self) -> Path:
        return self.out / "garmin_sync.json"

    def sync_status(self) -> SyncStatus | None:
        try:
            return SyncStatus.model_validate_json(self._status_path.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def sync_due(self, now: datetime, every: timedelta = timedelta(minutes=30)) -> bool:
        last = self.sync_status()
        return last is None or now - last.at >= every

    def wellness(self, day: date) -> Wellness | None:
        try:
            data = json.loads((self.out / "wellness.json").read_text("utf-8"))
        except (OSError, ValueError):
            return None
        raw = data.get(day.isoformat())
        return Wellness.model_validate(raw) if raw else None

    def _save_wellness(self, w: Wellness) -> None:
        path = self.out / "wellness.json"
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            data = {}
        data[w.day.isoformat()] = w.model_dump(mode="json")
        self.out.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1), encoding="utf-8")

    def refresh_garmin(self, *, fetch: Fetcher | None = None, getter: Getter | None = None,
                       days: int = 14, now: datetime | None = None) -> SyncStatus:
        """Pull recent activities and this morning's sleep/HRV/resting HR, and remember
        when, so opening the app doesn't hit Garmin more than every 30 minutes."""
        now = now or self.now()
        status = SyncStatus(at=now)
        try:
            res = self.sync_garmin(days=days, fetch=fetch, today=now.date())
            status.matched = len(res.matched)
            status.extras = [a.describe() for a in res.extras][:5]
            status.unreadable = res.unreadable
        except GarminError as err:
            status.error = str(err)
        if status.error is None:
            try:
                sleep, hrv, heart = get_json(wellness_requests(now.date()), getter)
                w = parse_wellness(now.date(), sleep, hrv, heart)
                w.fetched_at = now
                self._save_wellness(w)
                status.wellness = w.found
            except GarminError as err:  # recovery data is a bonus: never blocks logging
                status.wellness_error = str(err)
        self.out.mkdir(parents=True, exist_ok=True)
        self._status_path.write_text(status.model_dump_json(indent=1), encoding="utf-8")
        return status

    def garmin_heart_rates(self, getter: Getter | None = None) -> dict[str, int]:
        """Threshold / max / resting HR as Garmin has them. Shown for you to confirm."""
        return heart_rates_from_garmin(*get_json(list(zones_requests()), getter))

    def ease_session(self, week: date, session_id: str) -> Plan:
        """Swap a quality session for an easy one of the same sport, time and place."""
        plan = self.require_plan(week)
        p = plan.placement(session_id)
        if p is None:
            raise PlannerError(f"No session '{session_id}' in the week of {week:%d %b}.")
        row = self.log_index(week).get(session_id)
        if row is not None and row.logged:
            raise PlannerError("That session is already logged.")
        s = p.session
        if s.intensity < 3:
            raise PlannerError("That session is already easy.")
        kind = {"run": "easy", "bike": "endurance", "swim": "endurance"}.get(s.discipline)
        if kind is None:
            raise PlannerError("Only swim, bike and run sessions can be made easy.")
        easy = Session(**{**s.model_dump(exclude={"value", "kind", "intensity", "key"}),
                          "kind": kind, "intensity": 2 if s.discipline != "run" else 1,
                          "key": False})
        placements = [q.model_copy(update={"session": easy, "reason": "made_easy"})
                      if q.session.id == session_id else q for q in plan.placements]
        new = plan.model_copy(update={"placements": placements})
        wtype = next((r.week_type for r in self.log() if r.week == week), "facility_aware")
        self._save(new, week, "ease", f"Week of {week:%d %b %Y} — eased {session_id}", wtype)
        return new

    # ---- moving a session yourself ---------------------------------------------------
    def move_options(self, week: date, session_id: str, now: datetime) -> list[MoveOption]:
        """Every slot from now on where this session fits: kit open, room left."""
        plan = self.require_plan(week)
        p = plan.placement(session_id)
        if p is None:
            raise PlannerError(f"No session '{session_id}' in the week of {week:%d %b}.")
        row = self.log_index(week).get(session_id)
        if row is not None and row.logged:
            raise PlannerError("That session is already logged. Undo the log entry to move it.")
        s = p.session
        others = [q for q in plan.placements if q.session.id != session_id]
        out: list[MoveOption] = []
        for k in self.slots(week):
            if k.starts_at < now or slot_uid(k) == slot_uid(p.slot):
                continue
            busy = [(q.start, q.end) for q in others if slot_uid(q.slot) == slot_uid(k)]
            start = _first_gap(k, s, busy, self.cfg, plan.facility_aware)
            if start is None:
                continue
            moved = p.model_copy(update={"slot": k, "start": start})
            out.append(MoveOption(uid=slot_uid(k), slot=k, start=start,
                                  warnings=coaching_warnings([*others, moved], moved)))
        return out

    def move_session(self, week: date, session_id: str, uid: str, now: datetime
                     ) -> tuple[Plan, list[str]]:
        option = next((o for o in self.move_options(week, session_id, now) if o.uid == uid), None)
        if option is None:
            raise PlannerError("That slot can't take this session (kit, opening hours or room).")
        plan = self.require_plan(week)
        placements = [
            q.model_copy(update={"slot": option.slot, "start": option.start,
                                 "reason": "you_moved_it"})
            if q.session.id == session_id else q
            for q in plan.placements
        ]
        new = plan.model_copy(update={"placements": sorted(placements,
                                                            key=lambda q: q.starts_at)})
        wtype = next((r.week_type for r in self.log() if r.week == week), "facility_aware")
        self._save(new, week, "move", f"Week of {week:%d %b %Y} — moved {session_id}", wtype)
        return new, option.warnings

    # ---- the season ----------------------------------------------------------------
    def season(self, today: date) -> list[SeasonWeek]:
        """Every week from your first plan (or now) to race week: phase, recovery weeks,
        holidays, what was planned and done, and the volume the planner is heading for."""
        cfg = self.cfg
        log = self.log()
        summaries = {s.week: s for s in weekly_summaries(log)}
        last = week_start(cfg.race_date) if cfg.race_date and cfg.race_date > today \
            else week_start(today) + timedelta(weeks=12)
        out: list[SeasonWeek] = []
        for step in self.volume_chain(today, last):
            wk, phase, recovery, available, projected = (
                step.week, step.phase, step.recovery, step.available, step.projected)
            summ = summaries.get(wk)
            done = summ.completed_min if summ else None
            labels = sorted({o.name for o in cfg.overrides
                             if o.start <= wk + timedelta(days=6) and o.end >= wk})
            out.append(SeasonWeek(
                week=wk, phase=phase, recovery=recovery, available_min=available,
                projected_min=projected, planned_min=summ.planned_min if summ else None,
                done_min=done, logged=summ.logged if summ else 0,
                sessions=summ.sessions if summ else 0,
                week_type=week_type(wk, cfg.experiment_start), labels=labels,
                when="past" if wk < week_start(today) else
                ("now" if wk == week_start(today) else "future"),
                race=bool(cfg.race_date and wk <= cfg.race_date < wk + timedelta(days=7)),
            ))
        return out

    def volume_chain(self, today: date, last: date) -> list[ChainStep]:
        """Week-by-week volume from your first logged week (or now) to `last`.

        One rule for the Season view *and* for planning any week, so they always agree:
        each week grows ≤10% on the bigger of the two weeks before it. A past week you
        logged well counts as what you did; one you didn't log enough of holds volume
        flat (no evidence, no growth); weeks still to come assume you complete them.
        """
        cfg = self.cfg
        summaries = {s.week: s for s in weekly_summaries(self.log())}
        hours = cfg.profile.current_hours or DEFAULT_HOURS[cfg.race]
        this_week = week_start(today)
        history: list[int] = []
        out: list[ChainStep] = []
        wk = min([*summaries, this_week])
        while wk <= last:
            phase = phase_for(wk, cfg.race_date, cfg.race)
            recovery = phase != "taper" and is_recovery_week(wk, cfg.race_date)
            available = sum(k.minutes for k in calendar_for_week(cfg, wk))
            prev = max(history[-2:]) if history else None
            projected = sum(weekly_targets(cfg.race, phase, available, prev, 0.10,
                                           weekly_hours=hours, recovery=recovery,
                                           strength=cfg.strength).values())
            out.append(ChainStep(week=wk, phase=phase, recovery=recovery, available=available,
                                 prev=prev, projected=projected))
            summ = summaries.get(wk)
            if wk < this_week:
                reliable = summ is not None and summ.response_rate >= LOW_RESPONSE \
                    and summ.completed_min > 0
                if reliable:
                    assert summ is not None
                    history.append(summ.completed_min)
                else:
                    history.append(min(projected, prev) if prev else projected)
            else:
                history.append(projected)
            wk += timedelta(weeks=1)
        return out


class ChainStep(BaseModel):
    week: date
    phase: str
    recovery: bool
    available: int
    prev: int | None  # the volume this week ramps from
    projected: int


class SyncStatus(BaseModel):
    at: datetime
    matched: int = 0
    extras: list[str] = []
    unreadable: list[str] = []
    wellness: list[str] = []  # which readiness values Garmin had
    wellness_error: str | None = None
    error: str | None = None


EASY_KINDS = ("easy", "endurance", "long", "technique", "easy_strides", "substitute")


def effort_note(s: Session, row: LogRow | None, profile: Profile) -> str | None:
    """'Averaged 162 bpm, above your easy zone' when an easy session was run too hard."""
    if row is None or not row.avg_hr or s.kind not in EASY_KINDS or s.discipline == "swim":
        return None
    steady = profile.hr("steady")
    if steady is None or row.avg_hr <= steady[1]:
        return None
    return (f"Averaged {row.avg_hr} bpm, above easy (up to {steady[1]}). Easy days easy, so "
            "the hard days can be hard.")


class MoveOption(BaseModel):
    uid: str
    slot: Slot
    start: time
    warnings: list[str] = []


class SeasonWeek(BaseModel):
    week: date
    phase: str
    recovery: bool
    race: bool
    available_min: int
    projected_min: int
    planned_min: int | None
    done_min: int | None
    logged: int
    sessions: int
    week_type: str
    labels: list[str]
    when: Literal["past", "now", "future"]


def _first_gap(slot: Slot, s: Session, busy: list[tuple[time, time]], cfg: AthleteConfig,
               facility_aware: bool) -> time | None:
    """Earliest start in the slot that's free and has the kit open for the whole session."""
    loc = cfg.location(slot.location)
    t = datetime.combine(date(2000, 1, 1), slot.start)
    end = datetime.combine(date(2000, 1, 1), slot.end)
    step = timedelta(minutes=5)
    while t + timedelta(minutes=s.duration_min) <= end:
        a, b = t.time(), (t + timedelta(minutes=s.duration_min)).time()
        clash = any(a < q_end and q_start < b for q_start, q_end in busy)
        if not clash and (not facility_aware or s.fits(loc, slot.day, a, b)):
            return a
        t += step
    return None


def coaching_warnings(placements: list[Placement], moved: Placement) -> list[str]:
    """Plain warnings when a hand-made move breaks a coaching rule (it's still allowed)."""
    day = moved.slot.on
    if day is None:
        return []
    same = [q.session for q in placements if q.slot.on == day and q is not moved]
    s = moved.session
    out = []
    if any(q.discipline == s.discipline for q in same) and s.discipline != "strength":
        out.append(f"Two {s.discipline} sessions on {day:%A}.")
    if s.hard and any(q.hard for q in same):
        out.append(f"Two hard sessions on {day:%A}.")
    if (s.hard and any(q.kind == "long" for q in same)) or \
            (s.kind == "long" and any(q.hard for q in same)):
        out.append(f"A hard session and a long one on {day:%A}.")
    if s.kind == "long" and any(q.kind == "long" for q in same):
        out.append(f"Two long sessions on {day:%A}.")
    if s.hard:
        for d in (day - timedelta(days=1), day + timedelta(days=1)):
            if any(q.session.hard for q in placements if q.slot.on == d and q is not moved):
                out.append(f"Hard sessions on back-to-back days ({d:%A}).")
    return out


def placements_on(plan: Plan, day: date) -> list[Placement]:
    return [p for p in plan.placements if p.slot.on == day]

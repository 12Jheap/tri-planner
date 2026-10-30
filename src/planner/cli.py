"""Command line: plan a week, re-plan it, and report.

    tri-plan week   examples/joe.yaml --week 2026-11-02 --phase base
    tri-plan replan examples/joe.yaml --week 2026-11-02 --now 2026-11-04T12:00 --injury run:2026-11-10
    tri-plan report --log out/log.csv
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from planner.adherence import AdherenceModel, LogRow, read_log, weekly_summaries, write_log
from planner.config import ConfigError, calendar_for_week, load_config, week_start
from planner.export import export_week, to_ics
from planner.replan import Injury, replan
from planner.report import week_type, weekly_report
from planner.sessions import build_week_sessions
from planner.solver import Plan, plan_week
from planner.store import PlanStore
from planner.targets import weekly_targets


def _load_log(path: Path) -> list[LogRow]:
    return read_log(path) if path.exists() else []


def _markdown(plan: Plan, title: str) -> str:
    lines = [f"# {title}", "", "| Day | Time | Where | Session | Note |", "|---|---|---|---|---|"]
    for p in plan.placements:
        note = p.reason or ("⚠ no facility (time-only week)" if not p.facility_ok else "")
        lines.append(
            f"| {p.slot.on:%a %d %b} | {p.start:%H:%M}–{p.end:%H:%M} | {p.slot.location} "
            f"| {p.session.label} | {note} |"
        )
    if plan.dropped:
        lines += ["", "Dropped (no room): " + ", ".join(s.id for s in plan.dropped)]
    hours = plan.planned_minutes / 60
    return "\n".join([*lines, "", f"Planned: {hours:.1f}h"])


def _log_rows(plan: Plan, week: date, wtype: str) -> list[LogRow]:
    return [
        LogRow(
            on=p.slot.on, week=week, session_id=p.session.id, discipline=p.session.discipline,
            slot_key=p.slot.key, planned_min=p.session.duration_min, week_type=wtype,
        )
        for p in plan.placements
        if p.slot.on is not None
    ]


def cmd_week(a: argparse.Namespace) -> int:
    cfg = load_config(a.config)
    week = week_start(a.week)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "log.csv"
    log = _load_log(log_path)

    slots = calendar_for_week(cfg, week)
    available = sum(s.minutes for s in slots)
    prev = a.prev_minutes
    if prev is None:  # ramp from what you actually did last week, not what was planned
        last = [s for s in weekly_summaries(log) if s.week == week - timedelta(days=7)]
        prev = last[0].completed_min if last and last[0].completed_min > 0 else None
    targets = weekly_targets(cfg.race, a.phase, available, prev, a.ramp)
    sessions = build_week_sessions(targets, cfg.race, a.phase)
    model = AdherenceModel(a.prior_alpha, a.prior_beta).update(log)
    wtype = week_type(week, a.experiment_start)

    plan = plan_week(
        sessions, slots, cfg, model.probabilities(),
        facility_aware=wtype == "facility_aware", default_p=model.p("unseen"),
    )
    if plan.status == "infeasible":
        print(f"Can't build this week: {plan.reason}", file=sys.stderr)
        return 2

    wk_dir = out / str(week)
    files = export_week(plan, wk_dir)
    title = f"Week of {week:%d %b %Y} — {a.phase}, {wtype.replace('_', '-')}"
    (wk_dir / "plan.md").write_text(_markdown(plan, title), encoding="utf-8")
    version = PlanStore(out / "plan_session_version.jsonl").append(plan, week, "week")
    existing = {(r.week, r.session_id) for r in log}
    new_rows = [r for r in _log_rows(plan, week, wtype) if (r.week, r.session_id) not in existing]
    write_log(log_path, new_rows, append=True)

    print(_markdown(plan, title))
    print(f"\nTargets (min): {targets}  |  free time: {available / 60:.1f}h  |  plan v{version}")
    print(f"Wrote {files['ics'][0]}, {len(files['fit'])} .FIT workouts, and {len(new_rows)} rows to {log_path}")
    return 0


def _parse_injury(text: str) -> Injury:
    disc, _, until = text.partition(":")
    return Injury(discipline=disc, until=date.fromisoformat(until))


def cmd_replan(a: argparse.Namespace) -> int:
    cfg = load_config(a.config)
    week = week_start(a.week)
    out = Path(a.out)
    store = PlanStore(out / "plan_session_version.jsonl")
    previous = store.load(week)
    if previous is None:
        print(f"No plan stored for week {week}; run `tri-plan week` first.", file=sys.stderr)
        return 2
    log = _load_log(out / "log.csv")
    done = {r.session_id for r in log if r.week == week and r.status in ("done", "moved")}
    model = AdherenceModel(a.prior_alpha, a.prior_beta).update(log)
    res = replan(
        cfg, previous, a.now, p_complete=model.probabilities(), done_ids=done,
        flagged=a.flag, unavailable_slots=a.unavailable,
        injuries=[_parse_injury(i) for i in a.injury], log=log,
    )
    for n in res.notes:
        print(f"• {n}")
    if res.plan.status == "infeasible":
        return 2
    version = store.append(res.plan, week, "replan")
    wk_dir = out / str(week)
    wk_dir.mkdir(parents=True, exist_ok=True)
    to_ics(res.plan, wk_dir / "plan.ics")
    (wk_dir / "plan.md").write_text(_markdown(res.plan, f"Week of {week:%d %b %Y} — re-plan v{version}"))
    print("\nChanges:" if res.moves else "\nNo changes needed.")
    for m in res.moves:
        print(f"  {m.session_id}: {m.from_slot or '—'} → {m.to_slot or 'dropped'}  ({m.reason})")
    print()
    print(_markdown(res.plan, f"Re-plan v{version}"))
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    print(weekly_report(_load_log(Path(a.log))))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tri-plan", description="Facility-aware triathlon planner (v0)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("config", help="athlete YAML config")
        p.add_argument("--week", type=date.fromisoformat, default=date.today() + timedelta(days=7))
        p.add_argument("--out", default="out")
        p.add_argument("--prior-alpha", type=float, default=2.0)
        p.add_argument("--prior-beta", type=float, default=2.0)

    w = sub.add_parser("week", help="plan a week")
    common(w)
    w.add_argument("--phase", choices=["base", "build", "taper"], default="base")
    w.add_argument("--prev-minutes", type=int, default=None, help="last week's minutes (default: from log)")
    w.add_argument("--ramp", type=float, default=0.10)
    w.add_argument("--experiment-start", type=date.fromisoformat, default=None,
                   help="alternate facility-aware / time-only weeks from this date")
    w.set_defaults(fn=cmd_week)

    r = sub.add_parser("replan", help="re-plan the rest of a week")
    common(r)
    r.add_argument("--now", type=datetime.fromisoformat, default=datetime.now())
    r.add_argument("--injury", action="append", default=[], help="discipline:until, e.g. run:2026-11-10")
    r.add_argument("--unavailable", action="append", default=[], help="slot uid that's no longer possible")
    r.add_argument("--flag", action="append", default=[], help="session id you want moved")
    r.set_defaults(fn=cmd_replan)

    rep = sub.add_parser("report", help="completion report from your log")
    rep.add_argument("--log", default="out/log.csv")
    rep.set_defaults(fn=cmd_report)

    a = ap.parse_args(argv)
    try:
        return int(a.fn(a))
    except ConfigError as err:
        print(f"Config error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

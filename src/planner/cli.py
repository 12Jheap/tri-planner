"""Command line. The weekly loop:

    tri-plan init                      # answer a few questions -> athlete.yaml
    tri-plan week                      # plan next week (Sunday evening)
    tri-plan today                     # what's on today, and how to do it
    tri-plan log                       # tick off what you did (asks you, one by one)
    tri-plan replan --unavailable thu-pm --injury run:5
    tri-plan report

Every command uses ./athlete.yaml and ./out unless you pass a config path / --out.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from planner.adherence import (
    LOW_RESPONSE,
    REASONS,
    AdherenceModel,
    LogRow,
    read_log,
    sync_log,
    weekly_summaries,
    write_log,
)
from planner.config import AthleteConfig, ConfigError, calendar_for_week, load_config
from planner.export import export_week
from planner.friendly import parse_injury, parse_week, resolve_slots
from planner.replan import DebtLedger, frozen_by_pain, replan, substitute
from planner.report import week_type, weekly_report
from planner.sessions import build_week_sessions, how_to
from planner.solver import Placement, Plan, fit_to_slots, plan_week
from planner.store import InjuryStore, PlanStore
from planner.targets import DEFAULT_HOURS, describe_targets, phase_for, weekly_targets
from planner.wizard import run_wizard, to_yaml

DEFAULT_CONFIG = "athlete.yaml"
Ask = Callable[[str], str]


def _now(cfg: AthleteConfig) -> datetime:
    """Wall-clock time where the athlete lives; plans are in local time."""
    return datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)


def _load_log(path: Path) -> list[LogRow]:
    return read_log(path) if path.exists() else []


def _week(a: argparse.Namespace, cfg: AthleteConfig, default: str) -> date:
    return parse_week(a.week or default, _now(cfg).date())


def _status_cell(row: LogRow | None) -> str:
    if row is None or not row.logged:
        return ""
    mark = {"done": "✓", "moved": "✓", "skipped": "✗"}.get(row.status, "")
    extra = f" {row.actual_min}'" if row.status in ("done", "moved") else f" {row.reason}".rstrip()
    return f"{mark} {row.status}{extra}{' · pain' if row.pain else ''}"


def _markdown(plan: Plan, title: str, log: dict[str, LogRow] | None = None) -> str:
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
            row += f" {_status_cell(log.get(p.session.id))} |"
        lines.append(row)
    if plan.dropped:
        lines += ["", "Didn't fit this week: " + ", ".join(s.id for s in plan.dropped)]
    lines += ["", f"Planned: {plan.planned_minutes / 60:.1f}h", "", "## How to do each session", ""]
    for kind in dict.fromkeys(p.session.kind for p in plan.placements):
        s = next(p.session for p in plan.placements if p.session.kind == kind)
        lines.append(f"- **{kind.replace('_', ' ')}**: {how_to(s)}")
    lines += ["", "Effort is out of 5: 2 = chatty, 3 = short sentences, 4 = a few words."]
    return "\n".join(lines)


def _log_rows(plan: Plan, week: date, wtype: str) -> list[LogRow]:
    return [
        LogRow(
            on=p.slot.on, week=week, session_id=p.session.id, discipline=p.session.discipline,
            slot_key=p.slot.key, planned_min=p.session.duration_min, week_type=wtype,
        )
        for p in plan.placements
        if p.slot.on is not None
    ]


def _save(
    cfg: AthleteConfig, plan: Plan, week: date, out: Path, note: str, title: str, wtype: str
) -> tuple[int, dict[str, list[Path]], str]:
    """Write files, append the plan version and sync the log. Returns a log summary."""
    wk_dir = out / str(week)
    files = export_week(plan, wk_dir, cfg.timezone)
    version = PlanStore(out / "plan_session_version.jsonl").append(plan, week, note)
    (wk_dir / "plan.md").write_text(_markdown(plan, f"{title} (v{version})"), encoding="utf-8")
    log_path = out / "log.csv"
    synced = sync_log(_load_log(log_path), _log_rows(plan, week, wtype), week)
    write_log(log_path, synced.rows)
    summary = f"log: {synced.added} added, {synced.updated} moved, {synced.removed} removed"
    return version, files, summary


def _previous_minutes(log: list[LogRow], week: date) -> int | None:
    """What you actually did last week, if you logged enough of it to trust."""
    last = [s for s in weekly_summaries(log) if s.week == week - timedelta(days=7)]
    if not last or last[0].completed_min <= 0 or last[0].response_rate < LOW_RESPONSE:
        return None
    return last[0].completed_min


def cmd_init(a: argparse.Namespace, ask: Ask | None = None) -> int:
    ask = ask or input
    path = Path(a.config or DEFAULT_CONFIG)
    if path.exists() and not a.force:
        print(f"{path} already exists. Edit it, or use --force to start again.", file=sys.stderr)
        return 1
    data = run_wizard(ask, print)
    header = "# Made by `tri-plan init`. Edit freely: add templates/overrides for holidays.\n"
    path.write_text(header + to_yaml(data), encoding="utf-8")
    print(f"\nSaved {path}. Next: tri-plan week")
    return 0


def cmd_week(a: argparse.Namespace) -> int:
    cfg = load_config(a.config or DEFAULT_CONFIG)
    week = _week(a, cfg, "next")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = _load_log(out / "log.csv")
    phase = a.phase or phase_for(week, cfg.race_date)

    slots = calendar_for_week(cfg, week)
    if not slots:
        print(f"No free time in the week of {week}: add slots to your config.", file=sys.stderr)
        return 2
    available = sum(s.minutes for s in slots)
    prev = a.prev_minutes if a.prev_minutes is not None else _previous_minutes(log, week)
    hours = cfg.weekly_hours or DEFAULT_HOURS[cfg.race]
    targets = weekly_targets(cfg.race, phase, available, prev, a.ramp, weekly_hours=hours)
    wtype = week_type(week, a.experiment_start)
    aware = wtype == "facility_aware"
    sessions, notes = fit_to_slots(build_week_sessions(targets, cfg.race, phase), slots, cfg, aware)
    istore = InjuryStore(out / "injuries.json")
    pain = frozen_by_pain(istore.pain_rows(log))
    injured = {i.discipline: i for i in istore.active(week)}
    if pain or injured:
        ledger = DebtLedger()
        sessions, _ = substitute(sessions, set(pain) | set(injured), ledger)
        notes += list(pain.values())
        notes += [f"{d} paused until {i.until:%a %d %b} (declared injury); its load moved to "
                  f"other sports. Re-plan with --clear-injury {d} when you're back."
                  for d, i in injured.items()]
    model = AdherenceModel(a.prior_alpha, a.prior_beta).update(log)

    plan = plan_week(
        sessions, slots, cfg, model.probabilities(),
        facility_aware=aware, default_p=model.p("unseen"),
    )
    if plan.status == "infeasible":
        print(f"Can't build this week: {plan.reason}", file=sys.stderr)
        return 2

    title = f"Week of {week:%d %b %Y} — {phase}, {wtype.replace('_', '-')}"
    version, files, synced = _save(cfg, plan, week, out, "week", title, wtype)
    print(_markdown(plan, f"{title} (v{version})"))
    for n in notes:
        print(f"• {n}")
    print(f"\nTargets: {describe_targets(targets)}  |  free time: {available / 60:.1f}h")
    if prev is not None:
        print(f"Capped at +{a.ramp:.0%} on last week's {prev / 60:.1f}h done.")
    print(f"Saved {files['ics'][0]} (import into your calendar), {len(files['fit'])} .FIT "
          f"workouts for your watch; {synced}.")
    print("Next: tri-plan today  ·  tri-plan log")
    return 0


def _latest(a: argparse.Namespace, week: date) -> Plan | None:
    plan = PlanStore(Path(a.out) / "plan_session_version.jsonl").load(week)
    if plan is None:
        print(f"No plan for the week of {week} yet. Run: tri-plan week --week {week}",
              file=sys.stderr)
    return plan


def _log_index(out: Path, week: date) -> dict[str, LogRow]:
    return {r.session_id: r for r in _load_log(out / "log.csv") if r.week == week}


def cmd_show(a: argparse.Namespace) -> int:
    cfg = load_config(a.config or DEFAULT_CONFIG)
    week = _week(a, cfg, "this")
    plan = _latest(a, week)
    if plan is None:
        return 2
    print(_markdown(plan, f"Week of {week:%d %b %Y}", _log_index(Path(a.out), week)))
    return 0


def _today_line(p: Placement, row: LogRow | None) -> str:
    done = _status_cell(row)
    return (
        f"  {p.start:%H:%M}–{p.end:%H:%M}  {p.slot.location:<12} {p.session.label}"
        f"{'   ' + done if done else ''}\n      {how_to(p.session)}"
    )


def cmd_today(a: argparse.Namespace) -> int:
    cfg = load_config(a.config or DEFAULT_CONFIG)
    day = date.fromisoformat(a.date) if a.date else _now(cfg).date()
    week = parse_week(str(day), day)
    plan = _latest(a, week)
    if plan is None:
        return 2
    log = _log_index(Path(a.out), week)
    todays = [p for p in plan.placements if p.slot.on == day]
    print(f"{day:%A %d %B}")
    if not todays:
        print("  Rest day. Nothing planned.")
    for p in todays:
        print(_today_line(p, log.get(p.session.id)))
    nxt = next((p for p in plan.placements if p.slot.on and p.slot.on > day), None)
    if nxt:
        print(f"\nNext: {nxt.slot.on:%a} {nxt.start:%H:%M} {nxt.session.label} @ {nxt.slot.location}")
    if any(not (log.get(p.session.id) and log[p.session.id].logged) for p in todays):
        print("\nDone it? tri-plan log")
    return 0


def _ask_choice(ask: Ask, prompt: str, options: dict[str, str]) -> str:
    while True:
        ans = ask(prompt).strip().lower()
        if ans in options:
            return options[ans]
        print(f"  ✗ type one of: {', '.join(k for k in options if k)}")


def _ask_row(r: LogRow, label: str, ask: Ask) -> LogRow | None:
    """Ask about one session. None = leave it for later."""
    status = _ask_choice(
        ask, f"{r.on:%a %d %b}  {label}\n  [d]one, [s]kipped, [m]oved, Enter = later: ",
        {"d": "done", "done": "done", "s": "skipped", "skipped": "skipped",
         "m": "moved", "moved": "moved", "": ""},
    )
    if not status:
        return None
    update: dict[str, object] = {"status": status}
    if status in ("done", "moved"):
        while True:
            mins = ask(f"  Minutes [{r.planned_min}]: ").strip()
            if not mins or mins.isdigit():
                update["actual_min"] = int(mins) if mins else r.planned_min
                break
            print("  ✗ a number of minutes, please")
        update["pain"] = ask("  Anything hurt? [y/N]: ").strip().lower() in ("y", "yes")
    else:
        menu = {str(i): reason for i, reason in enumerate(REASONS, 1)}
        prompt = "  Why? " + "  ".join(f"{i}) {x.replace('_', ' ')}" for i, x in menu.items()) + ": "
        update["reason"] = _ask_choice(ask, prompt, menu)
    return r.model_copy(update=update)


def cmd_log(a: argparse.Namespace, ask: Ask | None = None) -> int:
    ask = ask or input
    cfg = load_config(a.config or DEFAULT_CONFIG)
    out = Path(a.out)
    log_path = out / "log.csv"
    log = _load_log(log_path)
    today = _now(cfg).date()
    week = _week(a, cfg, "this")
    plan = PlanStore(out / "plan_session_version.jsonl").load(week)
    labels = {p.session.id: p.session.label for p in plan.placements} if plan else {}

    if a.session:  # one-shot: tri-plan log --session bike-long --status done --min 100
        idx = next((i for i, r in enumerate(log) if r.week == week and r.session_id == a.session), None)
        if idx is None:
            ids = ", ".join(r.session_id for r in log if r.week == week) or "none"
            print(f"No session '{a.session}' in the week of {week}. Sessions: {ids}", file=sys.stderr)
            return 2
        if a.status is None:
            print("Say what happened: done, skipped or moved", file=sys.stderr)
            return 2
        r = log[idx]
        update: dict[str, object] = {"status": a.status, "pain": a.pain}
        if a.status == "skipped":
            update["reason"] = a.reason or "other"
        else:
            update["actual_min"] = a.minutes if a.minutes is not None else r.planned_min
        log[idx] = LogRow.model_validate({**r.model_dump(), **update})
        write_log(log_path, log)
        print(f"Logged {a.session}: {_status_cell(log[idx])}")
        return 0

    todo = [i for i, r in enumerate(log) if r.week == week and not r.logged and r.on <= today]
    if not todo:
        print("Nothing to log: everything up to today is ticked off.")
        return 0
    print(f"{len(todo)} session(s) to log. Enter skips one for now.\n")
    changed = 0
    for i in todo:
        new = _ask_row(log[i], labels.get(log[i].session_id, log[i].session_id), ask)
        if new is not None:
            log[i] = LogRow.model_validate(new.model_dump())
            write_log(log_path, log)  # save as we go, so Ctrl-C loses nothing answered
            changed += 1
    print(f"\nSaved {changed} session(s) to {log_path}.")
    summary = next((s for s in weekly_summaries(log) if s.week == week), None)
    if summary:
        print(summary.line())
    if any(r.pain for r in log if r.week == week):
        print("Something hurt: if it's the same thing twice, the planner pauses that sport.")
    return 0


def _when(uid: str | None) -> str:
    """'2026-11-12|thu-16:15-18:15@School' -> 'Thu 16:15 School'."""
    if not uid:
        return "—"
    key = uid.split("|")[-1]
    when, _, place = key.partition("@")
    day, _, rest = when.partition("-")
    return f"{day.title()} {rest.split('-')[0]} {place}"


def cmd_replan(a: argparse.Namespace) -> int:
    cfg = load_config(a.config or DEFAULT_CONFIG)
    now = datetime.fromisoformat(a.now) if a.now else _now(cfg)
    week = _week(a, cfg, str(now.date()))
    out = Path(a.out)
    previous = PlanStore(out / "plan_session_version.jsonl").load(week)
    if previous is None:
        print(f"No plan stored for week {week}; run `tri-plan week` first.", file=sys.stderr)
        return 2
    ids = {p.session.id for p in previous.placements}
    unknown = [f for f in a.flag if f not in ids]
    if unknown:
        print(f"Unknown session {unknown}. This week's: {', '.join(sorted(ids))}", file=sys.stderr)
        return 2
    gone = resolve_slots(a.unavailable, calendar_for_week(cfg, week))
    istore = InjuryStore(out / "injuries.json")
    injuries = istore.declare(
        [parse_injury(i, now.date()) for i in a.injury], a.clear_injury, now.date()
    )
    log = _load_log(out / "log.csv")
    done = {r.session_id for r in log if r.week == week and r.status in ("done", "moved")}
    skipped = {r.session_id for r in log if r.week == week and r.status == "skipped"}
    model = AdherenceModel(a.prior_alpha, a.prior_beta).update(log)
    res = replan(
        cfg, previous, now, p_complete=model.probabilities(), done_ids=done, skipped_ids=skipped,
        flagged=a.flag, unavailable_slots=gone, injuries=injuries, log=istore.pain_rows(log),
    )
    for n in res.notes:
        print(f"• {n}")
    if res.plan.status == "infeasible":
        return 2
    wtype = next((r.week_type for r in log if r.week == week), "facility_aware")
    title = f"Week of {week:%d %b %Y} — re-plan"
    # The re-plan only covers what's left; keep the earlier sessions so the stored
    # week (and the log) still show what was planned before now.
    new_ids = {p.session.id for p in res.plan.placements}
    history = [p for p in previous.placements if p.starts_at < now and p.session.id not in new_ids]
    full = res.plan.model_copy(
        update={"placements": sorted(history + res.plan.placements, key=lambda p: p.starts_at)}
    )
    version, _files, synced = _save(cfg, full, week, out, "replan", title, wtype)
    print("\nChanges:" if res.moves else "\nNo changes needed.")
    for m in res.moves:
        print(f"  {m.session_id}: {_when(m.from_slot)} → {_when(m.to_slot) if m.to_slot else 'dropped'}"
              f"  ({m.reason.replace('_', ' ')})")
    print(f"\n{_markdown(full, f'{title} (v{version})', _log_index(out, week))}\n\n{synced}")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    path = Path(a.log or Path(a.out) / "log.csv")
    if not path.exists():
        print(f"No log at {path} yet. Plan a week first: tri-plan week", file=sys.stderr)
        return 2
    print(weekly_report(read_log(path)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="tri-plan",
        description="Triathlon training that fits the week you actually have.",
        epilog="Start with: tri-plan init",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    def common(p: argparse.ArgumentParser, week_help: str) -> None:
        p.add_argument("config", nargs="?", help=f"your config file (default: {DEFAULT_CONFIG})")
        p.add_argument("--week", help=week_help)
        p.add_argument("--out", default="out", help="where plans and the log live (default: out)")
        p.add_argument("--prior-alpha", type=float, default=2.0, help=argparse.SUPPRESS)
        p.add_argument("--prior-beta", type=float, default=2.0, help=argparse.SUPPRESS)

    i = sub.add_parser("init", help="set up your config by answering questions")
    i.add_argument("config", nargs="?", help=f"file to create (default: {DEFAULT_CONFIG})")
    i.add_argument("--force", action="store_true", help="overwrite an existing file")
    i.set_defaults(fn=cmd_init)

    w = sub.add_parser("week", help="plan a week")
    common(w, "this, next (default) or a date in the week")
    w.add_argument("--phase", choices=["base", "build", "taper"], default=None,
                   help="default: worked out from your race date")
    w.add_argument("--prev-minutes", type=int, default=None, help=argparse.SUPPRESS)
    w.add_argument("--ramp", type=float, default=0.10, help="max weekly increase (default 0.10)")
    w.add_argument("--experiment-start", type=date.fromisoformat, default=None,
                   help="alternate facility-aware / time-only weeks from this date")
    w.set_defaults(fn=cmd_week)

    t = sub.add_parser("today", help="today's sessions and how to do them")
    common(t, argparse.SUPPRESS)
    t.add_argument("--date", help="another day, e.g. 2026-11-10")
    t.set_defaults(fn=cmd_today)

    s = sub.add_parser("show", help="the whole week, with what you've logged")
    common(s, "this (default), next or a date in the week")
    s.set_defaults(fn=cmd_show)

    lg = sub.add_parser("log", help="tick off sessions (asks one by one)")
    common(lg, "this (default), last, or a date in the week")
    lg.add_argument("--session", help="log one session without questions, e.g. bike-long")
    lg.add_argument("--status", choices=["done", "skipped", "moved"])
    lg.add_argument("--min", dest="minutes", type=int, help="minutes actually done")
    lg.add_argument("--reason", choices=list(REASONS), help="why it was skipped")
    lg.add_argument("--pain", action="store_true", help="something hurt")
    lg.set_defaults(fn=cmd_log)

    r = sub.add_parser("replan", help="re-plan the rest of the week when life happens")
    common(r, "default: the week of --now")
    r.add_argument("--now", help="pretend it's this time, e.g. 2026-11-11T19:00")
    r.add_argument("--injury", action="append", default=[], metavar="SPORT[:DAYS|:DATE]",
                   help="pause a sport: run (7 days), run:10, run:2026-11-20")
    r.add_argument("--clear-injury", action="append", default=[], metavar="SPORT",
                   help="you're back (or the physio's cleared you): stop pausing this sport")
    r.add_argument("--unavailable", action="append", default=[], metavar="WHEN",
                   help="a slot you've lost: thu, thu-pm, thu-am, 'thu 16:30', 2026-11-12")
    r.add_argument("--flag", action="append", default=[], metavar="SESSION",
                   help="move this session even if it's in the next 24h")
    r.set_defaults(fn=cmd_replan)

    rep = sub.add_parser("report", help="how much of the plan you actually did")
    rep.add_argument("--out", default="out")
    rep.add_argument("--log", default=None, help="log file (default: out/log.csv)")
    rep.set_defaults(fn=cmd_report)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return int(a.fn(a))
    except ConfigError as err:
        print(f"Config error: {err}", file=sys.stderr)
        return 1
    except ValueError as err:
        print(f"✗ {err}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

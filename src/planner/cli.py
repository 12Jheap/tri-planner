"""Command line. The weekly loop:

    tri-plan web                       # the same thing in your browser (and phone)
    tri-plan init                      # answer a few questions -> athlete.yaml
    tri-plan week                      # plan next week (Sunday evening)
    tri-plan today                     # what's on today, and how to do it
    tri-plan log                       # tick off what you did (asks you, one by one)
    tri-plan replan --unavailable thu-pm --injury run:5
    tri-plan report

Every command uses ./athlete.yaml and ./out unless you pass a config path / --out.
All the real work happens in planner.service, shared with the website.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from planner.activities import ImportResult
from planner.adherence import REASONS, LogRow, read_log
from planner.config import AthleteConfig, ConfigError
from planner.friendly import parse_injury, parse_week
from planner.garmin import GarminError
from planner.profile import Profile
from planner.report import weekly_report
from planner.service import (
    PlannerError,
    Workspace,
    placements_on,
    plan_markdown,
    slot_label,
    status_text,
)
from planner.sessions import how_to
from planner.solver import Placement
from planner.targets import describe_targets
from planner.wizard import run_wizard, to_yaml
from planner.workouts import workout_for

DEFAULT_CONFIG = "athlete.yaml"
Ask = Callable[[str], str]


def _now(cfg: AthleteConfig) -> datetime:
    """Wall-clock time where the athlete lives; plans are in local time."""
    return datetime.now(ZoneInfo(cfg.timezone)).replace(tzinfo=None)


def _ws(a: argparse.Namespace) -> Workspace:
    return Workspace(a.config or DEFAULT_CONFIG, a.out, (a.prior_alpha, a.prior_beta))


def _week(a: argparse.Namespace, ws: Workspace, default: str) -> date:
    return parse_week(a.week or default, _now(ws.cfg).date())


def cmd_init(a: argparse.Namespace, ask: Ask | None = None) -> int:
    ask = ask or input
    path = Path(a.config or DEFAULT_CONFIG)
    if path.exists() and not a.force:
        print(f"{path} already exists. Edit it, or use --force to start again.", file=sys.stderr)
        return 1
    data = run_wizard(ask, print)
    header = "# Made by `tri-plan init`. Edit freely: add templates/overrides for holidays.\n"
    path.write_text(header + to_yaml(data), encoding="utf-8")
    print(f"\nSaved {path}. Next: tri-plan week  (or tri-plan web)")
    return 0


def cmd_week(a: argparse.Namespace) -> int:
    ws = _ws(a)
    res = ws.plan_week(_week(a, ws, "next"), a.phase, ramp=a.ramp,
                       prev_minutes=a.prev_minutes, experiment_start=a.experiment_start)
    title = f"Week of {res.week:%d %b %Y} — {res.phase}, {res.week_type.replace('_', '-')}"
    print(plan_markdown(res.plan, f"{title} (v{res.version})", profile=ws.cfg.profile))
    for n in res.notes:
        print(f"• {n}")
    print(f"\nTargets: {describe_targets(res.targets)}  |  free time: {res.available_min / 60:.1f}h")
    if res.previous_min is not None:
        print(f"Capped at +{a.ramp:.0%} on last week's {res.previous_min / 60:.1f}h done.")
    print(f"Saved {res.files['ics'][0]} (import into your calendar), {len(res.files['fit'])} .FIT "
          f"workouts for your watch; {res.log_summary}.")
    print("Next: tri-plan today  ·  tri-plan log")
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    ws = _ws(a)
    week = _week(a, ws, "this")
    plan = ws.require_plan(week)
    print(plan_markdown(plan, f"Week of {week:%d %b %Y}", ws.log_index(week), ws.cfg.profile))
    return 0


def _today_line(p: Placement, row: LogRow | None, profile: Profile) -> str:
    done = status_text(row)
    steps = "\n".join(f"      · {b.summary()}" for b in workout_for(p.session, profile).blocks)
    return (
        f"  {p.start:%H:%M}–{p.end:%H:%M}  {p.slot.location:<12} {p.session.label}"
        f"{'   ' + done if done else ''}\n      {how_to(p.session)}\n{steps}"
    )


def cmd_today(a: argparse.Namespace) -> int:
    ws = _ws(a)
    day = date.fromisoformat(a.date) if a.date else _now(ws.cfg).date()
    week = parse_week(str(day), day)
    plan = ws.require_plan(week)
    log = ws.log_index(week)
    todays = placements_on(plan, day)
    print(f"{day:%A %d %B}")
    if not todays:
        print("  Rest day. Nothing planned.")
    for p in todays:
        print(_today_line(p, log.get(p.session.id), ws.cfg.profile))
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


def _ask_and_log(ws: Workspace, r: LogRow, label: str, ask: Ask) -> bool:
    """Ask about one session and save it. False = left for later."""
    status = _ask_choice(
        ask, f"{r.on:%a %d %b}  {label}\n  [d]one, [s]kipped, [m]oved, Enter = later: ",
        {"d": "done", "done": "done", "s": "skipped", "skipped": "skipped",
         "m": "moved", "moved": "moved", "": ""},
    )
    if not status:
        return False
    if status == "skipped":
        menu = {str(i): reason for i, reason in enumerate(REASONS, 1)}
        prompt = "  Why? " + "  ".join(f"{i}) {x.replace('_', ' ')}" for i, x in menu.items()) + ": "
        ws.log_session(r.week, r.session_id, "skipped", reason=_ask_choice(ask, prompt, menu))
        return True
    while True:
        mins = ask(f"  Minutes [{r.planned_min}]: ").strip()
        if not mins or mins.isdigit():
            break
        print("  ✗ a number of minutes, please")
    pain = ask("  Anything hurt? [y/N]: ").strip().lower() in ("y", "yes")
    ws.log_session(r.week, r.session_id, status,  # type: ignore[arg-type]
                   minutes=int(mins) if mins else None, pain=pain)
    return True


def cmd_log(a: argparse.Namespace, ask: Ask | None = None) -> int:
    ask = ask or input
    ws = _ws(a)
    week = _week(a, ws, "this")
    if a.session:  # one-shot: tri-plan log --session bike-long --status done --min 100
        if a.status is None:
            raise PlannerError("Say what happened: --status done, skipped or moved")
        row = ws.log_session(week, a.session, a.status, minutes=a.minutes, reason=a.reason,
                             pain=a.pain)
        print(f"Logged {a.session}: {status_text(row)}")
        return 0

    today = _now(ws.cfg).date()
    plan = ws.plan(week)
    labels = {p.session.id: p.session.label for p in plan.placements} if plan else {}
    todo = [r for r in ws.log() if r.week == week and not r.logged and r.on <= today]
    if not todo:
        print("Nothing to log: everything up to today is ticked off.")
        return 0
    print(f"{len(todo)} session(s) to log. Enter skips one for now.\n")
    changed = sum(_ask_and_log(ws, r, labels.get(r.session_id, r.session_id), ask) for r in todo)
    print(f"\nSaved {changed} session(s) to {ws.log_path}.")
    summary = ws.summary(week)
    if summary:
        print(summary.line())
    if any(r.pain for r in ws.log() if r.week == week):
        print("Something hurt: if it's the same thing twice, the planner pauses that sport.")
    return 0


def cmd_replan(a: argparse.Namespace) -> int:
    ws = _ws(a)
    now = datetime.fromisoformat(a.now) if a.now else _now(ws.cfg)
    week = _week(a, ws, str(now.date()))
    res = ws.replan(
        now, week, unavailable=a.unavailable, flags=a.flag, clear_injuries=a.clear_injury,
        injuries=[parse_injury(i, now.date()) for i in a.injury],
    )
    for n in res.notes:
        print(f"• {n}")
    print("\nChanges:" if res.moves else "\nNo changes needed.")
    for m in res.moves:
        to = slot_label(m.to_slot) if m.to_slot else "dropped"
        print(f"  {m.session_id}: {slot_label(m.from_slot)} → {to}  ({m.reason.replace('_', ' ')})")
    title = f"Week of {week:%d %b %Y} — re-plan (v{res.version})"
    md = plan_markdown(res.plan, title, ws.log_index(week), ws.cfg.profile)
    print(f"\n{md}\n\n{res.log_summary}")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    path = Path(a.log or Path(a.out) / "log.csv")
    if not path.exists():
        raise PlannerError(f"No log at {path} yet. Plan a week first: tri-plan week")
    print(weekly_report(read_log(path)))
    return 0


def _report_import(res: ImportResult) -> None:
    for m in res.matched:
        how = "another day" if m.moved else "done"
        print(f"✓ {m.activity.describe()} → {m.session_id} ({how})")
    for x in res.extras:
        print(f"· {x.describe()}: not in the plan, left alone")
    if res.duplicates:
        print(f"· {res.duplicates} already imported")
    for bad in res.unreadable:
        print(f"✗ couldn't read {bad}", file=sys.stderr)
    if not (res.matched or res.extras or res.duplicates):
        print("Nothing new to log.")


def cmd_import(a: argparse.Namespace) -> int:
    ws = _ws(a)
    paths = [Path(p).expanduser() for p in a.paths]
    if not paths and ws.cfg.watch_folder:
        paths = [Path(ws.cfg.watch_folder).expanduser()]
    if not paths:
        raise PlannerError("Give .fit/.zip files or a folder, or set watch_folder in your config.")
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise PlannerError(f"Not found: {', '.join(missing)}")
    _report_import(ws.import_files(paths))
    return 0


def cmd_sync(a: argparse.Namespace) -> int:
    ws = _ws(a)
    try:
        res = ws.sync_garmin(days=a.days)
    except GarminError as err:
        raise PlannerError(str(err)) from None
    _report_import(res)
    return 0


def cmd_web(a: argparse.Namespace) -> int:
    from planner.web import serve

    serve(Path(a.config or DEFAULT_CONFIG), Path(a.out), host=a.host, port=a.port,
          open_browser=not a.no_browser)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="tri-plan",
        description="Triathlon training that fits the week you actually have.",
        epilog="Start with: tri-plan web   (or tri-plan init for the terminal version)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")

    def common(p: argparse.ArgumentParser, week_help: str) -> None:
        p.add_argument("config", nargs="?", help=f"your config file (default: {DEFAULT_CONFIG})")
        p.add_argument("--week", help=week_help)
        p.add_argument("--out", default="out", help="where plans and the log live (default: out)")
        p.add_argument("--prior-alpha", type=float, default=2.0, help=argparse.SUPPRESS)
        p.add_argument("--prior-beta", type=float, default=2.0, help=argparse.SUPPRESS)

    wb = sub.add_parser("web", help="open the planner in your browser")
    wb.add_argument("config", nargs="?", help=f"your config file (default: {DEFAULT_CONFIG})")
    wb.add_argument("--out", default="out", help="where plans and the log live (default: out)")
    wb.add_argument("--port", type=int, default=8000)
    wb.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 to use it from your phone on the same wifi")
    wb.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    wb.set_defaults(fn=cmd_web)

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

    im = sub.add_parser("import", help="tick off sessions from watch files (.fit / .zip)")
    im.add_argument("paths", nargs="*", help="files or folders (default: watch_folder)")
    im.add_argument("--config", dest="config", default=None, help=argparse.SUPPRESS)
    im.add_argument("--out", default="out")
    im.add_argument("--prior-alpha", type=float, default=2.0, help=argparse.SUPPRESS)
    im.add_argument("--prior-beta", type=float, default=2.0, help=argparse.SUPPRESS)
    im.set_defaults(fn=cmd_import)

    sy = sub.add_parser("sync", help="tick off sessions from Garmin Connect (Personal API)")
    common(sy, argparse.SUPPRESS)
    sy.add_argument("--days", type=int, default=14, help="how far back to look (default 14)")
    sy.set_defaults(fn=cmd_sync)

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
    except PlannerError as err:
        print(f"✗ {err}", file=sys.stderr)
        return 2
    except ValueError as err:
        print(f"✗ {err}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

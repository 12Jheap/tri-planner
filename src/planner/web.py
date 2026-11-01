"""The planner as a website you run on your own computer: `tri-plan web`.

Single athlete, no accounts, no cloud. Everything is still the same files in
`out/` and your config, so the CLI and the website can be mixed freely.
Use `--host 0.0.0.0` to open it from your phone on the same wifi.
"""

from __future__ import annotations

import io
import secrets
import threading
import webbrowser
import zipfile
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.wrappers import Response

from planner.adherence import AdherenceModel, LogRow, weekly_summaries
from planner.config import DAYS, ConfigError, Facility, parse_config, week_start
from planner.friendly import parse_injury
from planner.report import completion_by
from planner.service import PlannerError, Workspace, placements_on, slot_label
from planner.sessions import how_to
from planner.solver import Placement, slot_uid
from planner.targets import DEFAULT_HOURS, describe_targets, phase_for
from planner.wizard import FACILITY_NAMES, parse_windows, to_yaml

HERE = Path(__file__).parent
SPORT_ICON = {"swim": "🏊", "bike": "🚴", "run": "🏃", "strength": "💪"}
REASON_TEXT = {
    "no_time": "No time", "facility_closed": "Facility closed", "body": "Body said no",
    "feeling_off": "Feeling off", "other": "Other",
}
WINDOWED = (Facility.POOL, Facility.OPEN_WATER, Facility.GYM)


def _nice(s: Any) -> str:
    """'Bike long · 1h25' instead of "Bike long 85' [KEY]"."""
    kind = "" if s.kind == s.discipline else " " + s.kind.replace("_", " ")
    return f"{s.discipline.title()}{kind} · {_fmt_min(s.duration_min)}"


def _fmt_min(m: int) -> str:
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _windows_text(windows: list[Any]) -> str:
    """Turn stored windows back into the 'mon-fri 16:00-19:00; sat,sun 08:00-12:00' text."""
    parts = []
    for w in windows:
        days = ",".join(w.days) if w.days else ""
        parts.append(f"{days} {w.start:%H:%M}-{w.end:%H:%M}".strip())
    return "; ".join(parts)


def create_app(ws: Workspace, now: Callable[[], datetime] | None = None) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"),
                static_folder=str(HERE / "static"))
    app.secret_key = secrets.token_hex(16)
    token = secrets.token_urlsafe(16)  # stops other websites posting to this one

    def clock() -> datetime:
        return now() if now else ws.now()

    def configured() -> bool:
        if not ws.config_path.exists():
            return False
        try:
            ws.reload()
            _ = ws.cfg
            return True
        except ConfigError:
            return False

    @app.context_processor
    def _globals() -> dict[str, Any]:
        return {
            "token": token, "icon": SPORT_ICON, "how_to": how_to, "fmt_min": _fmt_min, "nice": _nice,
            "reasons": REASON_TEXT, "nav": request.endpoint,
        }

    @app.before_request
    def _guard() -> Response | None:
        if request.method == "POST" and request.form.get("token") != token:
            abort(400, "This form is out of date. Reload the page and try again.")
        if request.endpoint not in ("setup", "setup_save", "static") and not configured():
            if ws.config_path.exists():
                flash(f"{ws.config_path} has a problem: fix it here.", "error")
                return redirect(url_for("setup", raw=1))
            return redirect(url_for("setup"))
        return None

    @app.errorhandler(PlannerError)
    @app.errorhandler(ValueError)
    def _planner_error(err: Exception) -> Response:
        flash(str(err), "error")
        return redirect(request.referrer or url_for("today"))

    # ---- helpers ----------------------------------------------------------------------
    def card(p: Placement, log: dict[str, LogRow], today: date) -> dict[str, Any]:
        row = log.get(p.session.id)
        return {
            "p": p, "row": row if row and row.logged else None,
            "loggable": p.slot.on is not None and p.slot.on <= today,
            "week": week_start(p.slot.on) if p.slot.on else None,
        }

    def banners(day: date) -> list[str]:
        out = [f"{SPORT_ICON.get(i.discipline, '')} {i.discipline.title()} paused until "
               f"{i.until:%a %d %b} (injury)." for i in ws.injuries().active(day)]
        return out

    # ---- pages ------------------------------------------------------------------------
    @app.get("/")
    def today() -> str:
        now_ = clock()
        day = date.fromisoformat(request.args["d"]) if request.args.get("d") else now_.date()
        week = week_start(day)
        plan = ws.plan(week)
        log = ws.log_index(week)
        cards = [card(p, log, now_.date()) for p in placements_on(plan, day)] if plan else []
        catch_up = []
        upcoming = []
        if plan:
            catch_up = [card(p, log, now_.date()) for p in plan.placements
                        if p.slot.on and p.slot.on < day and not (
                            log.get(p.session.id) and log[p.session.id].logged)]
            upcoming = [p for p in plan.placements if p.slot.on and p.slot.on > day][:3]
        return render_template(
            "today.html", day=day, week=week, plan=plan, cards=cards, catch_up=catch_up,
            upcoming=upcoming, summary=ws.summary(week), banners=banners(day),
            is_today=day == now_.date(), prev=day - timedelta(days=1),
            next=day + timedelta(days=1), athlete=ws.cfg.athlete,
        )

    @app.get("/week")
    def week_view() -> str:
        now_ = clock()
        week = week_start(date.fromisoformat(request.args["w"])) if request.args.get("w") \
            else week_start(now_.date())
        plan = ws.plan(week)
        log = ws.log_index(week)
        days = []
        for i, name in enumerate(DAYS):
            d = week + timedelta(days=i)
            items = [card(p, log, now_.date()) for p in placements_on(plan, d)] if plan else []
            days.append({"date": d, "name": name, "items": items, "today": d == now_.date()})
        wk_dir = ws.out / str(week)
        return render_template(
            "week.html", week=week, plan=plan, days=days, summary=ws.summary(week),
            prev=week - timedelta(days=7), next=week + timedelta(days=7),
            this_week=week_start(now_.date()), phase=phase_for(week, ws.cfg.race_date),
            has_files=(wk_dir / "plan.ics").exists(), banners=banners(week),
            fits=len(list(wk_dir.glob("*.fit"))) if wk_dir.exists() else 0,
            hours=ws.cfg.weekly_hours or DEFAULT_HOURS[ws.cfg.race],
        )

    @app.post("/week/plan")
    def plan_week() -> Response:
        week = week_start(date.fromisoformat(request.form["week"]))
        phase = request.form.get("phase") or None
        res = ws.plan_week(week, phase)  # type: ignore[arg-type]
        flash(f"Planned {res.plan.planned_minutes / 60:.1f}h for the week of {week:%d %b} "
              f"({res.phase}): {describe_targets(res.targets)}", "ok")
        for n in res.notes:
            flash(n, "info")
        if res.plan.dropped:
            flash("Didn't fit: " + ", ".join(s.id for s in res.plan.dropped), "info")
        return redirect(url_for("week_view", w=week))

    @app.post("/log")
    def log() -> Response:
        f = request.form
        week = date.fromisoformat(f["week"])
        action = f["action"]
        if action == "undo":
            ws.log_session(week, f["session"], None)
            flash("Cleared. Log it again when you're ready.", "info")
        elif action == "skipped":
            ws.log_session(week, f["session"], "skipped", reason=f.get("reason") or "other")
            flash("Logged as skipped. That's useful data too.", "ok")
        else:
            mins = f.get("minutes", "").strip()
            if mins and not mins.isdigit():
                raise PlannerError("Minutes should be a number.")
            status = "moved" if f.get("other_time") else "done"
            row = ws.log_session(week, f["session"], status,  # type: ignore[arg-type]
                                 minutes=int(mins) if mins else None, pain=bool(f.get("pain")))
            flash(f"Nice. {row.actual_min} min logged.", "ok")
            if row.pain:
                flash("Something hurt. If it happens twice in a row, that sport pauses "
                      "and you'll be told to see a physio.", "info")
        return redirect(f.get("next") or url_for("today"))

    @app.get("/replan")
    def replan_form() -> str:
        now_ = clock()
        week = week_start(now_.date())
        plan = ws.plan(week)
        slots = [k for k in ws.slots(week) if k.starts_at >= now_]
        by_day: dict[date, list[Any]] = defaultdict(list)
        planned_in: dict[str, list[str]] = defaultdict(list)
        if plan:
            for p in plan.placements:
                planned_in[slot_uid(p.slot)].append(_nice(p.session))
        for k in slots:
            assert k.on is not None
            by_day[k.on].append({"uid": slot_uid(k), "slot": k,
                                 "planned": planned_in.get(slot_uid(k), [])})
        soon = [p for p in plan.placements
                if now_ <= p.starts_at < now_ + timedelta(hours=24)] if plan else []
        return render_template(
            "replan.html", week=week, plan=plan, by_day=dict(sorted(by_day.items())), soon=soon,
            injuries=ws.injuries().active(now_.date()), now=now_,
        )

    @app.post("/replan")
    def replan_run() -> str | Response:
        now_ = clock()
        f = request.form
        injuries = []
        if f.get("injury_sport"):
            days = f.get("injury_days", "7").strip() or "7"
            injuries.append(parse_injury(f"{f['injury_sport']}:{days}", now_.date()))
        res = ws.replan(now_, unavailable=f.getlist("gone"), flags=f.getlist("flag"),
                        injuries=injuries, clear_injuries=f.getlist("clear"))
        moves = [{"id": m.session_id, "from": slot_label(m.from_slot),
                  "to": slot_label(m.to_slot) if m.to_slot else "dropped",
                  "why": m.reason.replace("_", " ")} for m in res.moves]
        labels = {p.session.id: _nice(p.session) for p in res.plan.placements}
        sports = {p.session.id: p.session.discipline for p in res.plan.placements}
        return render_template("replan_done.html", res=res, moves=moves, labels=labels,
                               sports=sports)

    @app.get("/progress")
    def progress() -> str:
        log = ws.log()
        weeks = list(reversed(weekly_summaries(log)))
        model = AdherenceModel(*ws.prior).update(log)
        slots = [{"key": k, "p": model.p(k), "n": sum(model.counts[k])}
                 for k in sorted(model.counts, key=lambda k: -model.p(k))]
        by_sport = completion_by(log, "discipline")
        by_type = completion_by(log, "week_type")
        return render_template("progress.html", weeks=weeks, slots=slots, by_sport=by_sport,
                               by_type=by_type, label=slot_label)

    @app.get("/files/<week>/<kind>")
    def files(week: str, kind: str) -> Response:
        wk = ws.out / str(week_start(date.fromisoformat(week)))
        if kind == "plan.ics" and (wk / "plan.ics").exists():
            return send_file((wk / "plan.ics").resolve(), as_attachment=True,
                             download_name=f"training-{week}.ics")
        if kind == "workouts.zip":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for fit in sorted(wk.glob("*.fit")):
                    z.write(fit, fit.name)
            buf.seek(0)
            return send_file(buf, as_attachment=True, download_name=f"workouts-{week}.zip",
                             mimetype="application/zip")
        abort(404)

    # ---- setup ------------------------------------------------------------------------
    def _raw() -> dict[str, Any]:
        if not ws.config_path.exists():
            return {}
        try:
            data = yaml.safe_load(ws.config_path.read_text("utf-8"))
        except yaml.YAMLError:
            return {}
        return data if isinstance(data, dict) else {}

    @app.get("/setup")
    def setup() -> str:
        cfg = ws.cfg if configured() else None
        raw_text = ws.config_path.read_text("utf-8") if ws.config_path.exists() else ""
        form: dict[str, Any] = {"athlete": "", "race": "sprint", "race_date": "",
                                "weekly_hours": "", "locations": [], "slots": {},
                                "overrides": [], "templates": []}
        if cfg:
            tmpl = cfg.templates[cfg.default_template]
            form = {
                "athlete": cfg.athlete, "race": cfg.race,
                "race_date": cfg.race_date.isoformat() if cfg.race_date else "",
                "weekly_hours": f"{cfg.weekly_hours:g}" if cfg.weekly_hours else "",
                "locations": [
                    {"name": loc.name, "kit": {f.name.value for f in loc.facilities},
                     "hours": {f.name.value: _windows_text(f.windows) for f in loc.facilities}}
                    for loc in cfg.locations
                ],
                "slots": {d: [s for s in tmpl.slots if s.day == d] for d in DAYS},
                "overrides": cfg.overrides,
                "templates": [t for t in cfg.templates if t != cfg.default_template],
            }
        return render_template(
            "setup.html", form=form, days=DAYS, facilities=FACILITY_NAMES, windowed=WINDOWED,
            raw_text=raw_text, show_raw=bool(request.args.get("raw")), first=cfg is None,
            default_hours=DEFAULT_HOURS,
        )

    def _form_to_config(f: Any) -> dict[str, Any]:
        data = _raw()
        data["athlete"] = f.get("athlete", "").strip() or "Athlete"
        data["race"] = f.get("race", "sprint")
        data.pop("race_date", None)
        if f.get("race_date"):
            data["race_date"] = date.fromisoformat(f["race_date"])
        data.pop("weekly_hours", None)
        if f.get("weekly_hours", "").strip():
            data["weekly_hours"] = float(f["weekly_hours"])
        data.setdefault("timezone", "Europe/London")

        locations = []
        for i in sorted({int(k.split("-")[1]) for k in f if k.startswith("loc-")}):
            name = f.get(f"loc-{i}-name", "").strip()
            if not name:
                continue
            facilities: list[Any] = []
            for fac in f.getlist(f"loc-{i}-kit"):
                hours = f.get(f"loc-{i}-hours-{fac}", "").strip()
                try:
                    windows = parse_windows(hours) if hours else []
                except ValueError as err:
                    raise ValueError(f"{name} {fac.replace('_', ' ')} hours: {err}") from None
                facilities.append({"name": fac, "windows": windows} if windows else fac)
            locations.append({"name": name, "facilities": facilities})
        if not locations:
            raise ValueError("add at least one place you train")
        data["locations"] = locations

        slots = []
        for d in DAYS:
            starts, ends, locs = (f.getlist(f"slot-{d}-{x}") for x in ("start", "end", "loc"))
            for s, e, loc in zip(starts, ends, locs, strict=False):
                if s and e:
                    slots.append({"day": d, "start": s, "end": e, "location": loc})
        default = data.get("default_template") or "normal"
        templates = data.get("templates") or {}
        templates[default] = {"slots": slots}
        data["templates"] = templates
        data["default_template"] = default

        overrides = []
        for name, s, e, t in zip(*(f.getlist(f"ov-{x}") for x in ("name", "start", "end",
                                                                     "template")), strict=False):
            if name.strip() and s and e:
                overrides.append({"name": name.strip(), "start": date.fromisoformat(s),
                                  "end": date.fromisoformat(e), "template": t})
        data["overrides"] = overrides
        return data

    @app.post("/setup")
    def setup_save() -> Response:
        f = request.form
        try:
            if f.get("raw") is not None and f.get("mode") == "raw":
                data = yaml.safe_load(f["raw"]) or {}
                if not isinstance(data, dict):
                    raise ConfigError("expected settings at the top level")
                parse_config(data)
                ws.config_path.write_text(f["raw"].replace("\r\n", "\n"), encoding="utf-8")
            else:
                data = _form_to_config(f)
                parse_config(data)
                header = "# Saved by tri-plan web. Edit here or in the app.\n"
                ws.config_path.write_text(header + to_yaml(data), encoding="utf-8")
        except (ConfigError, ValueError, yaml.YAMLError) as err:
            flash(f"Not saved: {err}", "error")
            return redirect(url_for("setup", raw=1 if f.get("mode") == "raw" else None))
        ws.reload()
        flash("Saved.", "ok")
        if ws.plan(week_start(clock().date())) is None:
            return redirect(url_for("week_view"))
        return redirect(url_for("setup"))

    return app


def serve(config: Path, out: Path, host: str = "127.0.0.1", port: int = 8000,
          open_browser: bool = True) -> None:
    app = create_app(Workspace(config, out))
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    print(f"tri-planner is running at {url}  (Ctrl-C to stop)")
    if host == "0.0.0.0":
        print("Open it on your phone at http://<this computer's IP>:" + str(port) +
              " — anyone on this wifi can reach it, so only do this on networks you trust.")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=port, debug=False)

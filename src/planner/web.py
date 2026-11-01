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

from planner import garmin
from planner.activities import ImportResult
from planner.adherence import AdherenceModel, LogRow, weekly_summaries
from planner.config import DAYS, ConfigError, Facility, parse_config, week_start
from planner.friendly import parse_injury
from planner.garmin import Fetcher, Getter
from planner.profile import ZONE_NAMES, mmss
from planner.report import completion_by, week_type
from planner.service import PlannerError, Workspace, effort_note, placements_on, slot_label
from planner.sessions import how_to
from planner.solver import Placement, slot_uid
from planner.targets import DEFAULT_HOURS, MAX_HOURS, is_recovery_week, phase_for
from planner.wellness import readiness
from planner.wizard import FACILITY_NAMES, parse_windows, to_yaml
from planner.workouts import workout_for

HERE = Path(__file__).parent
SPORTS = ("swim", "bike", "run", "strength")
REASON_TEXT = {
    "no_time": "No time", "facility_closed": "Facility closed", "body": "Body said no",
    "feeling_off": "Feeling off", "other": "Other",
}
WINDOWED = (Facility.POOL, Facility.OPEN_WATER, Facility.GYM)
PROFILE_TIMES = ("run_5k", "swim_css", "swim_400", "swim_200")
PROFILE_NUMBERS = ("current_hours", "ftp", "threshold_hr", "max_hr")


def _nice(s: Any) -> str:
    """'Threshold run · 45 min'."""
    return f"{s.title} · {_fmt_min(s.duration_min)}"


def _fmt_min(m: int) -> str:
    if m < 60:
        return f"{m} min"
    return f"{m // 60}h" if m % 60 == 0 else f"{m // 60}h{m % 60:02d}"


def _windows_text(windows: list[Any]) -> str:
    """Turn stored windows back into the 'mon-fri 16:00-19:00; sat,sun 08:00-12:00' text."""
    parts = []
    for w in windows:
        days = ",".join(w.days) if w.days else ""
        parts.append(f"{days} {w.start:%H:%M}-{w.end:%H:%M}".strip())
    return "; ".join(parts)


def _dur(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}:{seconds % 60:02d}" if seconds % 60 else f"{seconds // 60} min"


def create_app(ws: Workspace, now: Callable[[], datetime] | None = None,
               garmin_fetch: Fetcher | None = None, garmin_get: Getter | None = None,
               background: bool = True) -> Flask:
    app = Flask(__name__, template_folder=str(HERE / "templates"),
                static_folder=str(HERE / "static"))
    app.secret_key = secrets.token_hex(16)
    token = secrets.token_urlsafe(16)  # stops other websites posting to this one
    sync_lock = threading.Lock()

    def garmin_connected() -> bool:
        return garmin_fetch is not None or (garmin.library_installed() and garmin.key_available())

    def refresh() -> None:
        if not sync_lock.acquire(blocking=False):
            return  # one sync at a time
        try:
            ws.refresh_garmin(fetch=garmin_fetch, getter=garmin_get, now=clock())
        except Exception:
            app.logger.exception("Garmin sync failed")
        finally:
            sync_lock.release()

    def auto_sync() -> None:
        """Opening the app syncs with Garmin at most every 30 minutes, in the background."""
        if garmin_connected() and ws.sync_due(clock()):
            if background:
                threading.Thread(target=refresh, daemon=True).start()
            else:
                refresh()

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
            "token": token, "how_to": how_to, "fmt_min": _fmt_min, "nice": _nice,
            "reasons": REASON_TEXT, "nav": request.endpoint, "zone_names": ZONE_NAMES,
            "mmss": mmss, "dur": _dur, "garmin_ready": garmin_connected(),
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
        workout = workout_for(p.session, ws.cfg.profile)
        total = max(1, workout.seconds)
        return {
            "p": p, "s": p.session, "row": row if row and row.logged else None,
            "effort": effort_note(p.session, row, ws.cfg.profile) if row and row.logged else None,
            "loggable": p.slot.on is not None and p.slot.on <= today,
            "week": week_start(p.slot.on) if p.slot.on else None,
            "workout": workout,
            "segments": [(z, 100 * secs / total) for z, secs in workout.segments()],
        }

    def banners(day: date) -> list[str]:
        return [f"{i.discipline.title()} paused until {i.until:%a %d %b} (injury)."
                for i in ws.injuries().active(day)]

    # ---- pages ------------------------------------------------------------------------
    @app.get("/")
    def today() -> str:
        auto_sync()
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
            ready=readiness(ws.wellness(day)) if day == now_.date() else None,
            wellness=ws.wellness(day), sync=ws.sync_status(),
            can_ease=[c for c in cards if not c["row"] and c["s"].intensity >= 3
                      and c["s"].discipline != "strength"],
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
            days.append({"date": d, "name": name, "items": items, "today": d == now_.date(),
                         "past": d < now_.date()})
        wk_dir = ws.out / str(week)
        totals = {sp: sum(p.session.duration_min for p in plan.placements
                          if p.session.discipline == sp) for sp in SPORTS} if plan else {}
        race = ws.cfg.race_date
        return render_template(
            "week.html", week=week, plan=plan, days=days, summary=ws.summary(week),
            prev=week - timedelta(days=7), next=week + timedelta(days=7),
            this_week=week_start(now_.date()), phase=phase_for(week, race),
            recovery=is_recovery_week(week, race) and phase_for(week, race) != "taper",
            race_in_week=race if race and week <= race < week + timedelta(days=7) else None,
            has_files=(wk_dir / "plan.ics").exists(), banners=banners(week),
            fits=len(list(wk_dir.glob("*.fit"))) if wk_dir.exists() else 0,
            hours=ws.cfg.profile.current_hours or DEFAULT_HOURS[ws.cfg.race], totals=totals,
            weeks_to_race=(race - week).days // 7 if race and race >= week else None,
            test_week=(not plan.facility_aware) if plan
            else week_type(week, ws.cfg.experiment_start) == "time_only",
            experiment=ws.cfg.experiment_start,
        )

    @app.get("/s/<week>/<sid>")
    def session_detail(week: str, sid: str) -> str:
        wk = week_start(date.fromisoformat(week))
        plan = ws.require_plan(wk)
        p = plan.placement(sid)
        if p is None:
            abort(404)
        assert p is not None
        c = card(p, ws.log_index(wk), clock().date())
        moves = []
        if not c["row"]:
            try:
                moves = ws.move_options(wk, sid, clock())
            except PlannerError:
                moves = []
        by_day: dict[date, list[Any]] = defaultdict(list)
        for o in moves:
            assert o.slot.on is not None
            by_day[o.slot.on].append(o)
        return render_template("session.html", c=c, week=wk, known=ws.cfg.profile.known,
                               move_days=dict(sorted(by_day.items())))

    @app.post("/move")
    def move() -> Response:
        f = request.form
        week = week_start(date.fromisoformat(f["week"]))
        _plan, warnings = ws.move_session(week, f["session"], f["slot"], clock())
        flash("Moved. Calendar and watch files are updated.", "ok")
        for w in warnings:
            flash(f"Heads up: {w} You can keep it, but it's harder to recover from.", "info")
        return redirect(url_for("week_view", w=week))

    @app.get("/season")
    def season() -> str:
        today_ = clock().date()
        weeks = ws.season(today_)
        top = max([max(w.projected_min, w.planned_min or 0, w.done_min or 0) for w in weeks]
                  + [60])
        return render_template("season.html", weeks=weeks, top=top, race=ws.cfg.race_date,
                               experiment=ws.cfg.experiment_start,
                               ceiling=MAX_HOURS[ws.cfg.race])

    def _import_report(res: ImportResult, where: str) -> None:
        if res.matched:
            flash(f"{where}: ticked off {len(res.matched)} session"
                  f"{'s' if len(res.matched) != 1 else ''}. If anything hurt, open the "
                  "session and say so.", "ok")
        elif not res.extras:
            flash(f"{where}: nothing new to log.", "info")
        if res.extras:
            flash("Recorded but not in the plan: " + "; ".join(
                a.describe() for a in res.extras[:5]) + ".", "info")
        if res.unreadable:
            flash("Couldn't read: " + ", ".join(res.unreadable) + ".", "error")

    @app.post("/import")
    def import_files() -> Response:
        uploads = [(fs.filename or "upload", fs.read()) for fs in request.files.getlist("files")
                   if fs.filename]
        if not uploads:
            raise PlannerError("Choose one or more .fit or .zip files first.")
        _import_report(ws.import_uploads(uploads), "Imported")
        return redirect(request.form.get("next") or url_for("today"))

    @app.post("/import/watch")
    def import_watch() -> Response:
        folder = ws.cfg.watch_folder
        if not folder or not Path(folder).expanduser().is_dir():
            raise PlannerError("Plug the watch in (or check the watch folder on Profile).")
        _import_report(ws.import_files([Path(folder).expanduser()]), "From the watch")
        return redirect(request.form.get("next") or url_for("today"))

    @app.post("/sync")
    def sync() -> Response:
        with sync_lock:
            try:
                st = ws.refresh_garmin(fetch=garmin_fetch, getter=garmin_get, now=clock())
            except Exception as err:
                app.logger.exception("Garmin sync failed")
                raise PlannerError(f"Sync failed ({type(err).__name__}: {err}). Your plan and "
                                   "log are unchanged; the details are in the terminal.") from None
        if st.error:
            raise PlannerError(st.error)
        if st.matched:
            flash(f"Garmin: ticked off {st.matched} session{'s' if st.matched != 1 else ''}. "
                  "If anything hurt, open the session and say so.", "ok")
        else:
            flash("Garmin: nothing new to log.", "info")
        if st.extras:
            flash("Recorded but not in the plan: " + "; ".join(st.extras) + ".", "info")
        if st.unreadable:
            flash("Couldn't read: " + ", ".join(st.unreadable) + ".", "error")
        return redirect(request.form.get("next") or url_for("today"))

    @app.post("/ease")
    def ease() -> Response:
        f = request.form
        week = week_start(date.fromisoformat(f["week"]))
        ws.ease_session(week, f["session"])
        flash("Made easy: same time and place, easy effort. The hard work can wait a day.",
              "ok")
        return redirect(f.get("next") or url_for("today"))

    @app.get("/garmin/heart-rates")
    def garmin_hr() -> str | Response:
        try:
            found = ws.garmin_heart_rates(getter=garmin_get)
        except garmin.GarminError as err:
            raise PlannerError(str(err)) from None
        if not found:
            flash("Garmin didn't return heart-rate settings for your account.", "info")
            return redirect(url_for("setup") + "#garmin")
        current = ws.cfg.profile
        return render_template("garmin_hr.html", found=found, current=current)

    @app.post("/garmin/heart-rates")
    def garmin_hr_apply() -> Response:
        data = _raw()
        profile = dict(data.get("profile") or {})
        applied = []
        for k in ("threshold_hr", "max_hr"):
            v = request.form.get(k, "").strip()
            if v and request.form.get(f"use_{k}"):
                profile[k] = int(v)
                applied.append(k.replace("_", " "))
        if not applied:
            flash("Nothing changed.", "info")
            return redirect(url_for("setup") + "#fitness")
        data["profile"] = profile
        parse_config(data)
        ws.config_path.write_text("# Saved by tri-plan web. Edit here or in the app.\n"
                                  + to_yaml(data), encoding="utf-8")
        ws.reload()
        flash(f"Updated {' and '.join(applied)} from Garmin. Your zones are recalculated.",
              "ok")
        return redirect(url_for("setup") + "#fitness")

    @app.post("/garmin/key")
    def garmin_key() -> Response:
        try:
            path = garmin.save_key(request.form.get("key", ""))
        except garmin.GarminError as err:
            raise PlannerError(str(err)) from None
        flash(f"Garmin key saved to {path} (only your user can read it).", "ok")
        return redirect(url_for("setup") + "#garmin")

    @app.post("/week/plan")
    def plan_week() -> Response:
        week = week_start(date.fromisoformat(request.form["week"]))
        phase = request.form.get("phase") or None
        res = ws.plan_week(week, phase)  # type: ignore[arg-type]
        flash(f"Planned {len(res.plan.placements)} sessions, "
              f"{_fmt_min(res.plan.planned_minutes)} in total.", "ok")
        for n in res.notes:
            flash(n, "info")
        if res.plan.dropped:
            flash("Left out for lack of room: " + ", ".join(
                _nice(s) for s in res.plan.dropped) + ".", "info")
        return redirect(url_for("week_view", w=week))

    @app.post("/log")
    def log() -> Response:
        f = request.form
        week = date.fromisoformat(f["week"])
        action = f["action"]
        if action == "undo":
            ws.log_session(week, f["session"], None)
            flash("Entry cleared.", "info")
        elif action == "pain":
            ws.report_pain(week, f["session"])
            flash("Pain noted. Two sessions in a row with pain pauses that sport until "
                  "a physio clears you.", "info")
        elif action == "skipped":
            ws.log_session(week, f["session"], "skipped", reason=f.get("reason") or "other")
            flash("Logged as skipped.", "ok")
        else:
            mins = f.get("minutes", "").strip()
            if mins and not mins.isdigit():
                raise PlannerError("Minutes should be a number.")
            status = "moved" if f.get("other_time") else "done"
            row = ws.log_session(week, f["session"], status,  # type: ignore[arg-type]
                                 minutes=int(mins) if mins else None, pain=bool(f.get("pain")))
            flash(f"Logged {row.actual_min} min.", "ok")
            if row.pain:
                flash("Pain noted. Two sessions in a row with pain pauses that sport until "
                      "a physio clears you.", "info")
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
        sports: dict[str, str] = {p.session.id: p.session.discipline
                                  for p in res.plan.placements}
        for m in res.moves:  # dropped sessions aren't in the new plan
            sports.setdefault(m.session_id, m.session_id.split("-")[0])
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
                                "profile": {}, "locations": [], "slots": {},
                                "overrides": [], "templates": []}
        if cfg:
            tmpl = cfg.templates[cfg.default_template]
            prof = cfg.profile
            form = {
                "athlete": cfg.athlete, "race": cfg.race,
                "race_date": cfg.race_date.isoformat() if cfg.race_date else "",
                "profile": {
                    **{k: mmss(v) for k in PROFILE_TIMES if (v := getattr(prof, k))},
                    **{k: f"{v:g}" for k in PROFILE_NUMBERS if (v := getattr(prof, k))},
                },
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
            default_hours=DEFAULT_HOURS, zones=cfg.profile.table() if cfg else [],
            known=cfg.profile.known if cfg else [],
            experiment=cfg.experiment_start.isoformat() if cfg and cfg.experiment_start else "",
            watch_folder=cfg.watch_folder or "" if cfg else "",
            strength=cfg.strength if cfg else True,
            next_monday=week_start(clock().date()) + timedelta(days=7),
            garmin_lib=garmin.library_installed(), garmin_key=garmin.key_available(),
            key_file=garmin.KEY_FILE, sync=ws.sync_status() if cfg else None,
        )

    def _form_to_config(f: Any) -> dict[str, Any]:
        data = _raw()
        data["athlete"] = f.get("athlete", "").strip() or "Athlete"
        data["race"] = f.get("race", "sprint")
        data.pop("race_date", None)
        if f.get("race_date"):
            data["race_date"] = date.fromisoformat(f["race_date"])
        data.pop("weekly_hours", None)  # now profile.current_hours
        profile: dict[str, Any] = {}
        for k in PROFILE_TIMES:
            if v := f.get(f"p-{k}", "").strip():
                profile[k] = v
        for k in PROFILE_NUMBERS:
            if v := f.get(f"p-{k}", "").strip():
                try:
                    profile[k] = float(v) if k == "current_hours" else int(v)
                except ValueError:
                    raise ValueError(f"{k.replace('_', ' ')} should be a number") from None
        data["profile"] = profile
        data.setdefault("timezone", "Europe/London")
        data.pop("experiment_start", None)
        if f.get("experiment") and f.get("experiment_start"):
            data["experiment_start"] = date.fromisoformat(f["experiment_start"])
        data.pop("strength", None)
        if f.get("no_strength"):
            data["strength"] = False
        data.pop("watch_folder", None)
        if f.get("watch_folder", "").strip():
            data["watch_folder"] = f["watch_folder"].strip()

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

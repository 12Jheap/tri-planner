"""US-004: Logging and adherence model (v0)."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from planner.adherence import AdherenceModel, LogRow, read_log, weekly_summaries, write_log

WEEK = date(2026, 11, 2)
EARLY = "mon-06:30-07:30@School"
LATE = "mon-16:15-18:15@School"


def row(slot=EARLY, status="done", actual=60, planned=60, source="manual", **kw) -> LogRow:
    return LogRow(
        on=kw.pop("on", WEEK), week=kw.pop("week", WEEK), session_id=kw.pop("sid", "s"),
        discipline=kw.pop("discipline", "bike"), slot_key=slot, planned_min=planned,
        status=status, actual_min=actual, source=source, **kw,
    )


def test_ac_014_reads_a_google_sheet_or_csv_export_log_with_planned_session_(tmp_path: Path):
    """AC-014 [integration-test]: Reads a Google Sheet (or CSV export) log with planned session ID, status, reason code, actual minutes"""
    csv_text = (
        "on,week,session_id,discipline,slot_key,planned_min,status,reason,actual_min,pain,source,week_type\n"
        f"2026-11-02,2026-11-02,bike-long,bike,{LATE},75,done,,80,,manual,facility_aware\n"
        f"2026-11-03,2026-11-02,run-easy-1,run,{EARLY},45,skipped,No time,,,manual,facility_aware\n"
        f"2026-11-04,2026-11-02,swim-technique,swim,{LATE},40,,,,,,facility_aware\n"
    )
    path = tmp_path / "log.csv"
    path.write_text(csv_text)
    rows = read_log(path)
    assert [(r.session_id, r.status, r.reason, r.actual_min) for r in rows] == [
        ("bike-long", "done", "", 80),
        ("run-easy-1", "skipped", "no_time", 0),
        ("swim-technique", "no_response", "", 0),
    ]
    # Round-trips through our own writer (the template you paste into Google Sheets).
    again = read_log(write_log(tmp_path / "out.csv", rows))
    assert again == rows
    bad = tmp_path / "bad.csv"
    bad.write_text("session_id,status\nx,done\n")
    with pytest.raises(ValueError, match="missing columns"):
        read_log(bad)
    with pytest.raises(ValidationError, match="unknown reason"):
        row(status="skipped", reason="dog ate it")


def test_ac_015_maintains_a_beta_binomial_completion_estimate_per_slot_day_t():
    """AC-015 [unit-test]: Maintains a Beta-Binomial completion estimate per slot (day × time window × location), starting from a configurable prior"""
    m = AdherenceModel(prior_alpha=2, prior_beta=2)
    assert m.p(EARLY) == pytest.approx(0.5)
    m.update([row(EARLY, "skipped", 0)] * 4 + [row(EARLY, "done")] + [row(LATE, "done")] * 3)
    assert m.p(EARLY) == pytest.approx((2 + 1) / (4 + 5))
    assert m.p(LATE) == pytest.approx((2 + 3) / (4 + 3))
    assert m.p(LATE) > m.p(EARLY)
    lo, hi = m.interval(EARLY)
    assert 0 < lo < m.p(EARLY) < hi < 1
    optimistic = AdherenceModel(prior_alpha=8, prior_beta=2)
    assert optimistic.p("never-seen") == pytest.approx(0.8)
    # Pooled estimates never learn from Garmin API rows.
    pooled = AdherenceModel().update([row(LATE, "done", source="garmin_api")], pooled=True)
    assert pooled.p(LATE) == pytest.approx(0.5)


def test_ac_016_treats_unlogged_sessions_as_censored_not_skipped():
    """AC-016 [unit-test]: Treats unlogged sessions as censored, not skipped"""
    m = AdherenceModel().update([row(EARLY, "no_response", 0)] * 10)
    assert m.p(EARLY) == pytest.approx(0.5)
    blank = LogRow.model_validate(
        {"on": WEEK, "week": WEEK, "session_id": "x", "discipline": "run",
         "slot_key": EARLY, "planned_min": 30, "status": ""}
    )
    assert blank.status == "no_response" and not blank.logged


def test_ac_017_reports_weekly_completed_planned_hours_and_flags_if_logging_():
    """AC-017 [unit-test]: Reports weekly completed ÷ planned hours and flags if logging response rate is below 70%"""
    rows = [
        row(status="done", actual=60, planned=60),
        row(status="moved", actual=30, planned=60),
        row(status="skipped", actual=0, planned=60),
        row(status="no_response", actual=0, planned=60),
    ]
    (s,) = weekly_summaries(rows)
    assert s.planned_min == 240 and s.completed_min == 90
    assert s.ratio == pytest.approx(0.375)
    assert s.response_rate == pytest.approx(0.75) and not s.low_response
    (s2,) = weekly_summaries(rows + [row(status="no_response")] * 2)
    assert s2.low_response and "under 70% logged" in s2.line()
    assert "1.5h of 4.0h" in s.line()


def test_ac_018_stores_every_completion_row_with_a_source_field_manual_file_(tmp_path: Path):
    """AC-018 [unit-test]: Stores every completion row with a `source` field (manual / file / garmin_personal)"""
    rows = [row(source=src) for src in ("manual", "file", "garmin_personal")]
    back = read_log(write_log(tmp_path / "log.csv", rows))
    assert [r.source for r in back] == ["manual", "file", "garmin_personal"]
    assert "source" in (tmp_path / "log.csv").read_text().splitlines()[0]
    with pytest.raises(ValidationError):
        row(source="strava")

"""Logging and the adherence model (US-004).

You log each planned session as done / skipped / moved (+ a one-word reason) in a
Google Sheet; export it as CSV and the planner reads it. Blank status = you didn't
log it, which is treated as *censored* (unknown), never as skipped.

The adherence model is a Beta-Binomial per slot (weekday × time window × location):
P(you actually train in this slot) starts at a prior and updates with every logged
session. That's what moves key sessions out of slots you never really use.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator
from scipy.stats import beta as beta_dist

Status = Literal["done", "skipped", "moved", "no_response"]
Source = Literal["manual", "file", "garmin_personal", "garmin_api"]
REASONS = ("no_time", "facility_closed", "body", "feeling_off", "other")
LOW_RESPONSE = 0.70

LOG_COLUMNS = [
    "on", "week", "session_id", "discipline", "slot_key", "planned_min",
    "status", "reason", "actual_min", "pain", "source", "week_type",
    "avg_hr", "avg_power", "distance_m", "activity_id",
]


class LogRow(BaseModel):
    on: date
    week: date
    session_id: str
    discipline: str
    slot_key: str
    planned_min: int
    status: Status = "no_response"
    reason: str = ""
    actual_min: int = 0
    pain: bool = False
    source: Source = "manual"
    week_type: str = "facility_aware"
    # Filled in when the session came from a watch file (all optional).
    avg_hr: int | None = None
    avg_power: int | None = None
    distance_m: int | None = None
    activity_id: str = ""

    @field_validator("avg_hr", "avg_power", "distance_m", mode="before")
    @classmethod
    def _blank_metric(cls, v: object) -> object:
        return None if v in (None, "") else v

    @field_validator("activity_id", mode="before")
    @classmethod
    def _blank_id(cls, v: object) -> object:
        return "" if v is None else v

    @field_validator("status", mode="before")
    @classmethod
    def _blank_is_censored(cls, v: object) -> object:
        return "no_response" if v in (None, "") else str(v).strip().lower()

    @field_validator("reason", mode="before")
    @classmethod
    def _reason(cls, v: object) -> str:
        r = "" if v is None else str(v).strip().lower().replace(" ", "_")
        if r and r not in REASONS:
            raise ValueError(f"unknown reason '{v}' (use one of {', '.join(REASONS)})")
        return r

    @field_validator("pain", mode="before")
    @classmethod
    def _pain(cls, v: object) -> bool:
        return str(v).strip().lower() in ("1", "y", "yes", "true")

    @field_validator("actual_min", mode="before")
    @classmethod
    def _actual(cls, v: object) -> object:
        return 0 if v in (None, "") else v

    @field_validator("source", mode="before")
    @classmethod
    def _source(cls, v: object) -> object:
        return "manual" if v in (None, "") else v

    @property
    def logged(self) -> bool:
        return self.status != "no_response"

    @property
    def completed_min(self) -> int:
        return self.actual_min if self.status in ("done", "moved") else 0


def read_log(path: str | Path) -> list[LogRow]:
    """Read a log exported from Google Sheets (File → Download → CSV)."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"session_id", "status", "reason", "actual_min"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: log is missing columns {sorted(missing)}")
        return [LogRow.model_validate(r) for r in reader if r.get("session_id")]


def write_log(path: str | Path, rows: Iterable[LogRow], append: bool = False) -> Path:
    out = Path(path)
    new = not out.exists() or not append
    with open(out, "a" if append else "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        if new:
            w.writeheader()
        for r in rows:
            d = r.model_dump(mode="json")
            d["status"] = "" if r.status == "no_response" else r.status
            d["pain"] = "yes" if r.pain else ""
            w.writerow({k: "" if v is None else v for k, v in d.items()})
    return out


class LogSync(BaseModel):
    rows: list[LogRow]
    added: int = 0
    updated: int = 0
    removed: int = 0


def sync_log(log: list[LogRow], planned: list[LogRow], week: date) -> LogSync:
    """Bring the log in line with the latest plan for `week`.

    Anything you've already logged is never touched. Unlogged rows follow the
    plan: moved sessions get their new day/slot, sessions the plan dropped are
    removed, new sessions are added. Without this, a re-plan leaves stale rows
    behind and completed ÷ planned hours stops meaning anything.
    """
    new_by_id = {r.session_id: r for r in planned}
    out: list[LogRow] = []
    seen: set[str] = set()
    updated = removed = 0
    for r in log:
        if r.week != week:
            out.append(r)
            continue
        seen.add(r.session_id)
        if r.logged:
            out.append(r)
        elif r.session_id in new_by_id:
            fresh = new_by_id[r.session_id].model_copy(update={"source": r.source})
            updated += fresh.model_dump() != r.model_dump()
            out.append(fresh)
        else:
            removed += 1
    added = [r for r in planned if r.session_id not in seen]
    return LogSync(rows=out + added, added=len(added), updated=updated, removed=removed)


class AdherenceModel:
    """Beta-Binomial completion estimate per slot key."""

    def __init__(self, prior_alpha: float = 2.0, prior_beta: float = 2.0) -> None:
        if prior_alpha <= 0 or prior_beta <= 0:
            raise ValueError("prior parameters must be positive")
        self.prior = (prior_alpha, prior_beta)
        self.counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    def update(self, rows: Iterable[LogRow], pooled: bool = False) -> AdherenceModel:
        for r in rows:
            if not r.logged:
                continue  # censored: we don't know, so we learn nothing
            if pooled and r.source == "garmin_api":
                continue  # Garmin API data never feeds pooled estimates
            # The slot "worked" only if you trained in it as planned.
            self.counts[r.slot_key][0 if r.status == "done" else 1] += 1
        return self

    def p(self, slot_key: str) -> float:
        a, b = self.prior
        done, missed = self.counts.get(slot_key, [0, 0])
        return (a + done) / (a + b + done + missed)

    def interval(self, slot_key: str, mass: float = 0.8) -> tuple[float, float]:
        a, b = self.prior
        done, missed = self.counts.get(slot_key, [0, 0])
        lo, hi = beta_dist.interval(mass, a + done, b + missed)
        return float(lo), float(hi)

    def probabilities(self) -> dict[str, float]:
        return {k: self.p(k) for k in self.counts}


class WeeklySummary(BaseModel):
    week: date
    planned_min: int
    completed_min: int
    sessions: int
    logged: int

    @property
    def ratio(self) -> float:
        return self.completed_min / self.planned_min if self.planned_min else 0.0

    @property
    def response_rate(self) -> float:
        return self.logged / self.sessions if self.sessions else 0.0

    @property
    def low_response(self) -> bool:
        return self.response_rate < LOW_RESPONSE

    def line(self) -> str:
        flag = "  ⚠ under 70% logged — treat this week's numbers with caution" if self.low_response else ""
        return (
            f"Week of {self.week}: {self.completed_min / 60:.1f}h of {self.planned_min / 60:.1f}h "
            f"planned ({self.ratio:.0%}), {self.logged}/{self.sessions} sessions logged{flag}"
        )


def weekly_summaries(rows: Iterable[LogRow]) -> list[WeeklySummary]:
    weeks: dict[date, list[LogRow]] = defaultdict(list)
    for r in rows:
        weeks[r.week].append(r)
    return [
        WeeklySummary(
            week=w,
            planned_min=sum(r.planned_min for r in rs),
            completed_min=sum(r.completed_min for r in rs),
            sessions=len(rs),
            logged=sum(r.logged for r in rs),
        )
        for w, rs in sorted(weeks.items())
    ]

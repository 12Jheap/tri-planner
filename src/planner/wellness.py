"""How recovered you look this morning, from Garmin's sleep, HRV and resting heart rate.

Three plain rules, no black box:
- HRV: Garmin says LOW/POOR, or last night is below your own normal range.
- Sleep: under 6.5 hours, or a sleep score under 60.
- Resting HR: 5+ beats above your usual (7-day average).

0 flags = good, 1 = keep an eye on it, 2+ = low. On a low day the app *offers* to
make a hard session easy; you decide. These are your body's signals, not a
diagnosis, and nothing changes on its own.

Garmin's JSON is read defensively: if a value isn't there, it's "not available",
never a guess and never an alarm.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

SLEEP_HOURS_MIN = 6.5
SLEEP_SCORE_MIN = 60
RESTING_HR_RISE = 5
HRV_LOW_STATUS = ("LOW", "POOR")


def wellness_requests(day: date) -> list[tuple[str, dict[str, str] | None]]:
    """The Personal API calls behind one morning's readiness (paths from Garmin's client)."""
    d = day.isoformat()
    return [
        ("/sleep-service/sleep/dailySleep", {"date": d}),
        (f"/hrv-service/hrv/{d}", None),
        ("/wellness-service/wellness/dailyHeartRate", {"date": d}),
    ]


def find(obj: Any, *keys: str) -> Any:
    """First value found under any of `keys`, searching nested dicts/lists."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k) is not None:
                return obj[k]
        for v in obj.values():
            hit = find(v, *keys)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = find(v, *keys)
            if hit is not None:
                return hit
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, dict):  # e.g. {"value": 78, "qualifierKey": "GOOD"}
        return _num(v.get("value"))
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Wellness(BaseModel):
    day: date
    sleep_score: int | None = None
    sleep_hours: float | None = None
    hrv: int | None = None  # last night's average, ms
    hrv_status: str | None = None
    hrv_low: int | None = None  # bottom of your normal range
    resting_hr: int | None = None
    resting_hr_usual: int | None = None
    fetched_at: datetime | None = None

    @property
    def found(self) -> list[str]:
        names = {"sleep_score": "sleep score", "sleep_hours": "sleep time", "hrv": "HRV",
                 "resting_hr": "resting heart rate"}
        return [label for k, label in names.items() if getattr(self, k) is not None]


def parse_wellness(day: date, sleep: Any, hrv: Any, heart: Any) -> Wellness:
    overall = find(sleep, "overall")
    score = _num(overall) if overall is not None else _num(find(sleep, "sleepScore"))
    secs = _num(find(sleep, "sleepTimeSeconds"))
    summary = find(hrv, "hrvSummary") or hrv
    baseline = find(summary, "baseline") if summary else None
    status = find(summary, "status")
    hrv_now = _num(find(summary, "lastNightAvg"))
    low = _num(find(baseline, "balancedLow")) if baseline else None
    rest = _num(find(heart, "restingHeartRate"))
    usual = _num(find(heart, "lastSevenDaysAvgRestingHeartRate"))
    return Wellness(
        day=day,
        sleep_score=round(score) if score is not None else None,
        sleep_hours=round(secs / 3600, 1) if secs else None,
        hrv=round(hrv_now) if hrv_now else None,
        hrv_status=str(status).upper() if isinstance(status, str) else None,
        hrv_low=round(low) if low else None,
        resting_hr=round(rest) if rest else None,
        resting_hr_usual=round(usual) if usual else None,
    )


Level = Literal["good", "watch", "low", "unknown"]


class Readiness(BaseModel):
    level: Level
    flags: list[str] = []
    fine: list[str] = []

    @property
    def headline(self) -> str:
        return {
            "good": "You look recovered",
            "watch": "One thing to keep an eye on",
            "low": "You look under-recovered",
            "unknown": "No recovery data yet",
        }[self.level]


def readiness(w: Wellness | None) -> Readiness:
    if w is None or not w.found:
        return Readiness(level="unknown")
    flags: list[str] = []
    fine: list[str] = []
    if w.hrv is not None or w.hrv_status:
        below = w.hrv is not None and w.hrv_low is not None and w.hrv < w.hrv_low
        if (w.hrv_status in HRV_LOW_STATUS) or below:
            normal = f"; your normal starts at {w.hrv_low}" if w.hrv_low else ""
            flags.append(f"HRV is low ({w.hrv} ms{normal})" if w.hrv else "HRV is low")
        else:
            fine.append(f"HRV in your normal range ({w.hrv} ms)" if w.hrv else "HRV normal")
    if w.sleep_hours is not None or w.sleep_score is not None:
        short = w.sleep_hours is not None and w.sleep_hours < SLEEP_HOURS_MIN
        poor = w.sleep_score is not None and w.sleep_score < SLEEP_SCORE_MIN
        bits = ", ".join(x for x in (f"{w.sleep_hours}h" if w.sleep_hours else "",
                                     f"score {w.sleep_score}" if w.sleep_score else "") if x)
        (flags if short or poor else fine).append(
            f"{'Short or poor' if short or poor else 'Decent'} sleep ({bits})")
    if w.resting_hr is not None and w.resting_hr_usual is not None:
        if w.resting_hr >= w.resting_hr_usual + RESTING_HR_RISE:
            flags.append(f"Resting heart rate up ({w.resting_hr} vs usual {w.resting_hr_usual})")
        else:
            fine.append(f"Resting heart rate normal ({w.resting_hr})")
    level: Level = "low" if len(flags) >= 2 else ("watch" if flags else "good")
    return Readiness(level=level, flags=flags, fine=fine)


def heart_rates_from_garmin(*payloads: Any) -> dict[str, int]:
    """Threshold / max / resting HR from Garmin's HR-zone and profile data, if present."""
    keys = {
        "threshold_hr": ("lactateThresholdHeartRateUsed", "lactateThresholdHeartRate"),
        "max_hr": ("maxHeartRateUsed", "maxHeartRate"),
        "resting_hr": ("restingHeartRateUsed", "restingHeartRate"),
    }
    out: dict[str, int] = {}
    for name, names in keys.items():
        for payload in payloads:
            v = _num(find(payload, *names))
            if v and 30 <= v <= 230:
                out[name] = round(v)
                break
    return out


def zones_requests() -> Iterable[tuple[str, dict[str, str] | None]]:
    return [("/biometric-service/heartRateZones/v2", None),
            ("/userprofile-service/userprofile/settings", None)]

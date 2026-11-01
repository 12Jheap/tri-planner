"""Your current fitness, and the training zones that come from it.

You give whatever you know (all optional):
- `run_5k`: a recent 5k time, e.g. "21:30"
- `swim_css`: critical swim speed per 100m, e.g. "1:45" (or `swim_400` + `swim_200`
  time-trial times and it's worked out: CSS = (T400 − T200) / 2 per 100m)
- `ftp`: functional threshold power in watts (needs a power meter or smart trainer)
- `threshold_hr` (best) or `max_hr`: heart rate in bpm
- `current_hours`: roughly how much you train a week right now

Zones are standard, transparent rules (no black box): run paces scale from your
5k, bike power from FTP (Coggan), heart rate from threshold HR (Friel) or max HR,
swim paces from CSS. Without a number, the target falls back to how it should feel.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, field_validator, model_validator

Zone = Literal["recovery", "easy", "steady", "tempo", "threshold", "vo2", "sprint"]
ZONES: tuple[Zone, ...] = ("recovery", "easy", "steady", "tempo", "threshold", "vo2", "sprint")

ZONE_NAMES: dict[str, str] = {
    "recovery": "Recovery", "easy": "Easy", "steady": "Steady", "tempo": "Tempo",
    "threshold": "Threshold", "vo2": "VO2 max", "sprint": "Sprint",
}

# How each zone should feel, out of 10, when there's no number to aim at.
FEEL: dict[str, str] = {
    "recovery": "1–2/10, barely working",
    "easy": "3–4/10, full sentences",
    "steady": "5/10, chatty but focused",
    "tempo": "6–7/10, short sentences",
    "threshold": "7–8/10, comfortably hard, a few words",
    "vo2": "9/10, hard, no talking",
    "sprint": "fast but relaxed, not a flat-out sprint",
}

# Run: pace multipliers on threshold pace (bigger = slower). Threshold pace is roughly
# the pace you could race for an hour, ≈ 6% slower than 5k pace.
RUN_THRESHOLD_FROM_5K = 1.06
RUN: dict[str, tuple[float, float]] = {
    "recovery": (1.35, 1.50), "easy": (1.22, 1.35), "steady": (1.12, 1.22),
    "tempo": (1.05, 1.10), "threshold": (0.98, 1.03),
}
# VO2 and sprint are set from 5k pace instead.
RUN_FROM_5K: dict[str, tuple[float, float]] = {"vo2": (0.97, 1.01), "sprint": (0.88, 0.93)}

# Bike: % of FTP (Coggan levels; tempo here covers sweet spot 88–93%).
BIKE: dict[str, tuple[float, float]] = {
    "recovery": (0.40, 0.55), "easy": (0.56, 0.68), "steady": (0.69, 0.75),
    "tempo": (0.84, 0.93), "threshold": (0.95, 1.05), "vo2": (1.06, 1.20),
    "sprint": (1.30, 1.60),
}

# Heart rate as a fraction of threshold HR (Friel) or of max HR.
# Bands touch but never overlap, so every heart rate belongs to exactly one zone.
HR_THRESHOLD: dict[str, tuple[float, float]] = {
    "recovery": (0.70, 0.80), "easy": (0.81, 0.85), "steady": (0.86, 0.89),
    "tempo": (0.90, 0.94), "threshold": (0.95, 1.00), "vo2": (1.01, 1.05),
}
HR_MAX: dict[str, tuple[float, float]] = {
    "recovery": (0.55, 0.64), "easy": (0.65, 0.72), "steady": (0.73, 0.79),
    "tempo": (0.80, 0.86), "threshold": (0.87, 0.92), "vo2": (0.93, 0.97),
}

# Swim: seconds per 100m added to CSS (negative = faster).
SWIM: dict[str, tuple[int, int]] = {
    "recovery": (15, 20), "easy": (10, 15), "steady": (6, 10), "tempo": (3, 5),
    "threshold": (-1, 2), "vo2": (-6, -3), "sprint": (-12, -8),
}

DEFAULT_SWIM_PACE = 120  # s/100m, only used to turn swim time into metres when no CSS


def parse_duration(v: Any) -> int | None:
    """'21:30', '1:45', '1:02:10' or seconds -> seconds.

    Unquoted YAML like 21:30 arrives as the base-60 number 1290, which is already
    the right number of seconds.
    """
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ValueError(f"'{v}' isn't a time")  # noqa: TRY004 (pydantic wants ValueError)
    if isinstance(v, int | float):
        return int(v)
    parts = str(v).strip().split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"'{v}' isn't a time (try 21:30)") from None
    if not 1 <= len(nums) <= 3 or any(n < 0 for n in nums):
        raise ValueError(f"'{v}' isn't a time (try 21:30)")
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return round(total)


def mmss(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


class Profile(BaseModel):
    current_hours: float | None = None
    run_5k: int | None = None  # seconds
    swim_css: int | None = None  # seconds per 100m
    swim_400: int | None = None
    swim_200: int | None = None
    ftp: int | None = None  # watts
    threshold_hr: int | None = None
    max_hr: int | None = None

    @field_validator("run_5k", "swim_css", "swim_400", "swim_200", mode="before")
    @classmethod
    def _times(cls, v: Any) -> int | None:
        return parse_duration(v)

    @field_validator("current_hours")
    @classmethod
    def _hours(cls, v: float | None) -> float | None:
        if v is not None and not 0 <= v <= 30:
            raise ValueError(f"current_hours {v} looks wrong (expected 0–30)")
        return v

    @model_validator(mode="after")
    def _sane(self) -> Profile:
        if self.run_5k is not None and not 12 * 60 <= self.run_5k <= 60 * 60:
            raise ValueError(f"5k time {mmss(self.run_5k)} looks wrong (expected 12:00–60:00)")
        if self.swim_css is None and self.swim_400 and self.swim_200:
            if self.swim_400 <= self.swim_200:
                raise ValueError("400m time must be slower than 200m time")
            self.swim_css = round((self.swim_400 - self.swim_200) / 2)
        if self.swim_css is not None and not 55 <= self.swim_css <= 240:
            raise ValueError(f"swim CSS {mmss(self.swim_css)}/100m looks wrong")
        if self.ftp is not None and not 50 <= self.ftp <= 600:
            raise ValueError(f"FTP {self.ftp} W looks wrong")
        for name in ("threshold_hr", "max_hr"):
            hr = getattr(self, name)
            if hr is not None and not 100 <= hr <= 230:
                raise ValueError(f"{name.replace('_', ' ')} {hr} looks wrong")
        return self

    # ---- zones ------------------------------------------------------------------------
    @property
    def run_threshold_pace(self) -> float | None:
        """Seconds per km."""
        return self.run_5k / 5 * RUN_THRESHOLD_FROM_5K if self.run_5k else None

    def run_pace(self, zone: str) -> tuple[float, float] | None:
        """(fast, slow) seconds per km."""
        if not self.run_5k:
            return None
        p5 = self.run_5k / 5
        if zone in RUN_FROM_5K:
            lo, hi = RUN_FROM_5K[zone]
            return p5 * lo, p5 * hi
        t = self.run_threshold_pace
        assert t is not None
        lo, hi = RUN[zone]
        return t * lo, t * hi

    def bike_power(self, zone: str) -> tuple[int, int] | None:
        if not self.ftp:
            return None
        lo, hi = BIKE[zone]
        return round(self.ftp * lo), round(self.ftp * hi)

    def hr(self, zone: str) -> tuple[int, int] | None:
        if zone == "sprint":
            return None
        if self.threshold_hr:
            lo, hi = HR_THRESHOLD[zone]
            return round(self.threshold_hr * lo), round(self.threshold_hr * hi)
        if self.max_hr:
            lo, hi = HR_MAX[zone]
            return round(self.max_hr * lo), round(self.max_hr * hi)
        return None

    def swim_pace(self, zone: str) -> tuple[int, int] | None:
        """(fast, slow) seconds per 100m."""
        if not self.swim_css:
            return None
        lo, hi = SWIM[zone]
        return self.swim_css + lo, self.swim_css + hi

    def swim_speed(self, zone: str) -> float:
        """Seconds per 100m used to size sets (middle of the zone, or a default)."""
        pace = self.swim_pace(zone)
        if pace:
            return sum(pace) / 2
        return DEFAULT_SWIM_PACE + SWIM[zone][0]

    def target(self, discipline: str, zone: str) -> str:
        """Plain target for one zone, e.g. '4:09–4:22/km · HR 168–177'."""
        parts: list[str] = []
        if discipline == "run" and (pace := self.run_pace(zone)):
            parts.append(f"{mmss(pace[0])}–{mmss(pace[1])}/km")
        if discipline == "bike" and (watts := self.bike_power(zone)):
            parts.append(f"{watts[0]}–{watts[1]} W")
        if discipline == "swim" and (sp := self.swim_pace(zone)):
            parts.append(f"{mmss(sp[0])}–{mmss(sp[1])}/100m")
        if discipline in ("run", "bike") and (hr := self.hr(zone)):
            parts.append(f"HR {hr[0]}–{hr[1]}")
        return " · ".join(parts) if parts else f"effort {FEEL[zone]}"

    def table(self) -> list[dict[str, str]]:
        """One row per zone with every target you have numbers for."""
        rows = []
        for z in ZONES:
            run = self.run_pace(z)
            bike = self.bike_power(z)
            swim = self.swim_pace(z)
            hr = self.hr(z)
            rows.append({
                "zone": ZONE_NAMES[z], "key": z, "feel": FEEL[z],
                "run": f"{mmss(run[0])}–{mmss(run[1])}" if run else "",
                "bike": f"{bike[0]}–{bike[1]}" if bike else "",
                "swim": f"{mmss(swim[0])}–{mmss(swim[1])}" if swim else "",
                "hr": f"{hr[0]}–{hr[1]}" if hr else "",
            })
        return rows

    @property
    def known(self) -> list[str]:
        out = []
        if self.run_5k:
            out.append("run")
        if self.ftp:
            out.append("bike")
        if self.swim_css:
            out.append("swim")
        if self.threshold_hr or self.max_hr:
            out.append("hr")
        return out

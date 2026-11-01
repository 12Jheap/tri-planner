"""Append-only plan history: the `plan_session_version` table (US-005).

Every plan or re-plan is appended as a new version. Nothing is ever overwritten,
so you can always see what the plan said at any point and why it changed.
Stored as JSON Lines: one row per planned session per version.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from planner.adherence import LogRow
from planner.config import Slot
from planner.replan import Injury
from planner.sessions import Session
from planner.solver import Placement, Plan, slot_uid


class InjuryStore:
    """Declared injuries, remembered between commands (out/injuries.json).

    You say it once (`--injury run:10`); every plan and re-plan respects it until
    it runs out or you clear it. The athlete declares; the planner never diagnoses.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _data(self) -> dict:
        if not self.path.exists():
            return {"injuries": [], "cleared": {}}
        return json.loads(self.path.read_text("utf-8"))

    def load(self) -> list[Injury]:
        return [Injury.model_validate(d) for d in self._data()["injuries"]]

    def active(self, on: date) -> list[Injury]:
        return [i for i in self.load() if i.active(on)]

    def cleared(self) -> dict[str, date]:
        """Sport -> date you said you were back; pain reports before it no longer count."""
        return {d: date.fromisoformat(v) for d, v in self._data()["cleared"].items()}

    def declare(self, new: list[Injury], clear: list[str], today: date) -> list[Injury]:
        """Add/replace by discipline, drop cleared and expired ones; returns active list."""
        data = self._data()
        keep = {i.discipline: i for i in self.load() if i.active(today)}
        for d in clear:
            keep.pop(d, None)
            data["cleared"][d] = today.isoformat()
        for i in new:
            keep[i.discipline] = i
        data["injuries"] = [i.model_dump(mode="json") for i in keep.values()]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return list(keep.values())

    def pain_rows(self, rows: list[LogRow]) -> list[LogRow]:
        """Log rows that still count towards a pain freeze (after any clearance)."""
        cleared = self.cleared()
        return [r for r in rows if r.on > cleared.get(r.discipline, date.min)]


class PlanStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def last_version(self) -> int:
        return max((r["version"] for r in self._rows()), default=0)

    def append(self, plan: Plan, week: date, note: str = "") -> int:
        version = self.last_version() + 1
        created = datetime.now(tz=UTC).isoformat(timespec="seconds")
        with open(self.path, "a", encoding="utf-8") as fh:  # append-only, by design
            for p in plan.placements:
                row = {
                    "version": version,
                    "created_at": created,
                    "week": week.isoformat(),
                    "note": note,
                    "facility_aware": plan.facility_aware,
                    "session_id": p.session.id,
                    "slot_uid": slot_uid(p.slot),
                    "slot_key": p.slot.key,
                    "start": p.start.isoformat(timespec="minutes"),
                    "reason": p.reason,
                    "session": p.session.model_dump(mode="json"),
                    "slot": p.slot.model_dump(mode="json"),
                }
                fh.write(json.dumps(row) + "\n")
        return version

    def load(self, week: date, version: int | None = None) -> Plan | None:
        """Rebuild the plan for `week` (latest version unless given)."""
        rows = [r for r in self._rows() if r["week"] == week.isoformat()]
        if not rows:
            return None
        v = version or max(r["version"] for r in rows)
        chosen = [r for r in rows if r["version"] == v]
        placements = [
            Placement(
                session=Session.model_validate(r["session"]),
                slot=Slot.model_validate(r["slot"]),
                start=time.fromisoformat(r["start"]),
                reason=r["reason"],
            )
            for r in chosen
        ]
        placements.sort(key=lambda p: p.starts_at)
        return Plan(
            status="feasible", placements=placements, facility_aware=chosen[0]["facility_aware"]
        )

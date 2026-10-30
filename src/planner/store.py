"""Append-only plan history: the `plan_session_version` table (US-005).

Every plan or re-plan is appended as a new version. Nothing is ever overwritten,
so you can always see what the plan said at any point and why it changed.
Stored as JSON Lines: one row per planned session per version.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from planner.config import Slot
from planner.sessions import Session
from planner.solver import Placement, Plan, slot_uid


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

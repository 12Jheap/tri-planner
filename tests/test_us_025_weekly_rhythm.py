"""US-025: A weekly rhythm: review the week, plan the next (v0)."""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from pathlib import Path

from planner.service import Workspace
from planner.web import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "short_weekday_slots.yaml"
W1, W2 = date(2026, 11, 9), date(2026, 11, 16)


def _ws(tmp_path: Path) -> Workspace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, tmp_path / "athlete.yaml")
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def _site(ws: Workspace):
    clock = {"now": datetime(2026, 11, 12, 18)}
    client = create_app(ws, now=lambda: clock["now"], background=False).test_client()
    html = client.get("/setup").get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)  # type: ignore[union-attr]
    return client, token, clock


def test_ac_107_from_friday_today_offers_to_plan_next_week(tmp_path):
    """AC-107 [e2e-test]: From Friday, Today offers to plan next week if it isn't planned yet (one tap); not earlier in the week, not once it's planned, and not when you're looking at another day"""
    ws = _ws(tmp_path)
    client, token, clock = _site(ws)
    nudge = "Next week isn't planned yet"
    clock["now"] = datetime(2026, 11, 13, 18)  # Friday, but this week has no plan either
    assert nudge not in client.get("/").get_data(as_text=True)
    ws.plan_week(W1)
    clock["now"] = datetime(2026, 11, 12, 18)  # Thursday: too early to nag
    assert nudge not in client.get("/").get_data(as_text=True)
    for day in (13, 14, 15):  # Friday to Sunday
        clock["now"] = datetime(2026, 11, day, 18)
        home = client.get("/").get_data(as_text=True)
        assert nudge in home and "Plan the week of 16 Nov" in home
        assert f'name="week" value="{W2}"' in home
    assert nudge not in client.get("/?d=2026-11-14").get_data(as_text=True)  # another day
    res = client.post("/week/plan", data={"token": token, "week": str(W2)}, follow_redirects=True)
    assert res.status_code == 200 and ws.plan(W2) is not None
    assert nudge not in client.get("/").get_data(as_text=True)


def test_ac_108_a_finished_week_gets_an_honest_review(tmp_path):
    """AC-108 [e2e-test]: Once a week is over (or on its Sunday) the Week page reviews it: share of planned time done, key sessions done, each sport, average effort, what was skipped and why, one plain verdict, and a button to plan next week; if too little is logged it says it can't judge"""
    ws = _ws(tmp_path)
    client, _, clock = _site(ws)
    ws.plan_week(W1)
    plan = ws.plan(W1)
    assert plan is not None
    clock["now"] = datetime(2026, 11, 14, 20)  # Saturday: the week isn't over
    assert "Week review" not in client.get(f"/week?w={W1}").get_data(as_text=True)
    assert ws.week_review(date(2026, 11, 2)) is None  # never planned: nothing to review

    clock["now"] = datetime(2026, 11, 15, 20)  # Sunday
    guess = client.get(f"/week?w={W1}").get_data(as_text=True)
    assert "Week review" in guess and "so this is a guess" in guess  # nothing logged yet
    assert f"{len(plan.placements)} of {len(plan.placements)} sessions aren" in guess

    keys = [p for p in plan.placements if p.session.key]
    easy = [p for p in plan.placements if not p.session.key]
    assert len(keys) >= 2 and len(easy) >= 2
    for p in plan.placements:
        if p in easy[:2]:
            ws.log_session(W1, p.session.id, "skipped", reason="no_time")
        else:
            ws.log_session(W1, p.session.id, "done", rpe=6)
    review = ws.week_review(W1)
    assert review is not None
    skipped_min = sum(p.session.duration_min for p in easy[:2])
    assert review.planned_min == plan.planned_minutes
    assert review.done_min == plan.planned_minutes - skipped_min
    assert (review.key_done, review.key_total) == (len(keys), len(keys))
    assert review.unlogged == 0 and review.mean_rpe == 6 and review.top_reason == "no_time"
    assert sum(done for done, _ in review.by_sport.values()) == review.done_min
    assert sorted(t for t, _ in review.skipped) == sorted(p.session.title for p in easy[:2])
    page = client.get(f"/week?w={W1}").get_data(as_text=True)
    section = page.split('aria-label="Week review"', 1)[1].split("</section>", 1)[0]
    assert review.verdict in section.replace("&#39;", "'")
    assert f"{round(review.ratio * 100)}%" in section
    assert f"{len(keys)}/{len(keys)}" in section and "key sessions" in section
    assert "average effort /10" in section and "Most common reason: no time" in section
    for sport in review.by_sport:
        assert sport.capitalize() in section
    assert "Plan the week of 16 Nov" in section  # next week isn't planned: one tap from here
    ws.plan_week(W2)
    clock["now"] = datetime(2026, 11, 18, 8)  # a past week keeps its review
    later = client.get(f"/week?w={W1}").get_data(as_text=True)
    assert "Week review" in later
    assert "Plan the week of" not in later.split('aria-label="Week review"', 1)[1].split(
        "</section>", 1)[0]
    assert "Week review" not in client.get(f"/week?w={W2}").get_data(as_text=True)

    # The verdict follows what was done, and key sessions count for more than minutes.
    def verdict(done_ids: set[str]) -> str:
        w = _ws(tmp_path / f"v{len(done_ids)}")
        w.plan_week(W1)
        for p in w.plan(W1).placements:  # type: ignore[union-attr]
            if p.session.id in done_ids:
                w.log_session(W1, p.session.id, "done")
            else:
                w.log_session(W1, p.session.id, "skipped", reason="feeling_off")
        return w.week_review(W1).verdict  # type: ignore[union-attr]

    assert verdict({p.session.id for p in plan.placements}).startswith("Strong week")
    assert verdict(set()).startswith("A light week (0%)")

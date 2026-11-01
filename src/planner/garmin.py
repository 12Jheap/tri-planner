"""Pull your recent activities from Garmin Connect with the Personal API.

Uses Garmin's own client (garmin-connect-personal-api-python, Python 3.12+):
your Personal API key is exchanged for a bearer token (cached by that library in
~/.config/garmin/), then recent activities are listed and each original .FIT is
downloaded and read by activities.py, exactly like an uploaded file.

The key is read from, in order: the GARMIN_PERSONAL_API_KEY environment variable,
then ~/.config/garmin/connect-personal-api-key. It is never stored in this
project's files. Create a key at https://connect.garmin.com/app/settings/personalApiToken
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from planner.activities import Activity, read_bytes

KEY_FILE = Path("~/.config/garmin/connect-personal-api-key").expanduser()
KEY_ENV = "GARMIN_PERSONAL_API_KEY"
INSTALL_HINT = 'pip install -e ".[garmin]"  (needs Python 3.12+)'


class GarminError(Exception):
    """Something to fix on the Garmin side: no key, library missing, request refused."""


def library_installed() -> bool:
    try:
        import garmin_personal_api  # noqa: F401
    except ImportError:
        return False
    return True


def key_available() -> bool:
    if os.environ.get(KEY_ENV, "").strip():
        return True
    try:
        return bool(KEY_FILE.read_text("utf-8").strip())
    except OSError:
        return False


def save_key(key: str, path: Path | None = None) -> Path:
    """Store the key where Garmin's client looks for it, readable only by you."""
    path = path or KEY_FILE
    key = key.strip()
    if len(key) < 20 or any(c.isspace() for c in key):
        raise GarminError("That doesn't look like a Personal API key.")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key + "\n")
    os.chmod(path, 0o600)
    return path


Fetcher = Callable[[date, date], list[tuple[str, bytes]]]


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [r for r in value if isinstance(r, dict)]
    if isinstance(value, dict):
        for k in ("activities", "activityList"):
            if isinstance(value.get(k), list):
                return [r for r in value[k] if isinstance(r, dict)]
    return []


def download_recent(start: date, end: date, limit: int = 50) -> list[tuple[str, bytes]]:
    """(activity id, original-file zip bytes) for activities between two dates."""
    if not library_installed():
        raise GarminError(f"Garmin's client isn't installed: {INSTALL_HINT}")
    from garmin_personal_api import (
        GarminPersonalApiClient,
        GarminPersonalApiError,
        PersonalApiAuthenticator,
        resolve_api_key,
    )

    try:
        with PersonalApiAuthenticator() as auth:
            token = auth.obtain_token(resolve_api_key())
        out = []
        with GarminPersonalApiClient(token.access_token) as client:
            listing = client.search_activities(start=0, limit=limit, start_date=start,
                                               end_date=end)
            for rec in _records(listing):
                aid = rec.get("activityId")
                if aid is None:
                    continue
                out.append((str(aid), client.download_activity(aid)))
        return out
    except GarminPersonalApiError as err:
        status = getattr(err, "status_code", None)
        if status == 401:
            raise GarminError("Garmin refused the key. Make a new Personal API key and save "
                              "it again.") from None
        raise GarminError(f"Garmin: {err}") from None
    except OSError as err:
        raise GarminError(f"Couldn't reach Garmin: {err}") from None


def fetch_activities(start: date, end: date, tz: str, fetch: Fetcher | None = None
                     ) -> list[Activity]:
    """Activities from Garmin Connect between two dates (inclusive)."""
    if fetch is None and not key_available():
        raise GarminError(f"No Garmin key yet. Save it on the Profile page, or put it in "
                          f"{KEY_FILE} or the {KEY_ENV} environment variable.")
    files = (fetch or download_recent)(start, end)
    acts: list[Activity] = []
    for aid, data in files:
        acts += read_bytes(f"{aid}.zip", data, tz, activity_id=f"garmin:{aid}")
    return acts

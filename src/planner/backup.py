"""Backups: your settings and training history in one zip.

When the planner lives on one old laptop, a dead disk would take every plan, log
entry and test result with it. So:

- once a day (when the site is opened, and when the server starts) a zip is written
  to out/backups/, and the newest 14 are kept;
- Profile has a "Download backup" button, to keep a copy somewhere else (cloud drive,
  another computer). A backup on the same disk doesn't survive that disk.

A backup holds your settings file and everything in out/ except old backups and the
server log. It never contains your Garmin key (that lives in your user folder).
To restore: unzip it into the tri-planner folder.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

KEEP = 14
SKIP_DIRS = ("backups",)
SKIP_FILES = ("server.log",)
PREFIX = "tri-planner-"


def backup_bytes(config_path: Path, out: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if config_path.exists():
            z.write(config_path, config_path.name)
        if out.is_dir():
            for f in sorted(out.rglob("*")):
                rel = f.relative_to(out)
                if not f.is_file() or rel.parts[0] in SKIP_DIRS or f.name in SKIP_FILES:
                    continue
                z.write(f, Path("out") / rel)
    return buf.getvalue()


def backup_dir(out: Path) -> Path:
    return out / "backups"


def backups(out: Path) -> list[Path]:
    """Existing automatic backups, newest first."""
    return sorted(backup_dir(out).glob(f"{PREFIX}*.zip"), reverse=True)


def make_backup(config_path: Path, out: Path, today: date, dest: Path | None = None) -> Path:
    folder = dest or backup_dir(out)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{PREFIX}{today.isoformat()}.zip"
    path.write_bytes(backup_bytes(config_path, out))
    return path


def auto_backup(config_path: Path, out: Path, today: date) -> Path | None:
    """Today's backup, written once; older ones beyond the newest 14 are removed.
    Returns the new file, or None if today's already exists or there's nothing to save."""
    if not config_path.exists() or not out.is_dir():
        return None
    path = backup_dir(out) / f"{PREFIX}{today.isoformat()}.zip"
    if path.exists():
        return None
    made = make_backup(config_path, out, today)
    for old in backups(out)[KEEP:]:
        old.unlink()
    return made


def last_backup(out: Path) -> date | None:
    for path in backups(out):
        try:
            return date.fromisoformat(path.stem.removeprefix(PREFIX))
        except ValueError:
            continue
    return None

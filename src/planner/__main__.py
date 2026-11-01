"""Lets `python -m planner web` work even when the tri-plan command isn't on PATH."""

from planner.cli import main

raise SystemExit(main())

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class TemporalResult:
    triggered: bool
    type: str
    detail: str


def out_of_hours(ts_iso: str, start_hour: int = 6, end_hour: int = 22) -> TemporalResult:
    ts = datetime.fromisoformat(ts_iso)
    hour = ts.astimezone(timezone.utc).hour
    if hour < start_hour or hour > end_hour:
        return TemporalResult(triggered=True, type="out_of_hours", detail=f"hour={hour} outside {start_hour}-{end_hour} UTC")
    return TemporalResult(triggered=False, type="out_of_hours", detail="ok")


from __future__ import annotations

import math
from dataclasses import dataclass

from .baseline import Baseline, BaselineStore, utc_now_iso


@dataclass
class DriftResult:
    triggered: bool
    z: float
    detail: str


def update_and_score(
    *,
    store: BaselineStore,
    agent_id: str,
    tool_name: str,
    current_hourly_count: int,
) -> tuple[Baseline, DriftResult]:
    b = store.get(agent_id, tool_name)
    if b is None:
        b = Baseline(agent_id=agent_id, tool_name=tool_name, mean_hourly=float(current_hourly_count), stddev_hourly=1.0, sample_count=1, updated_at=utc_now_iso())
        store.upsert(b)
        return b, DriftResult(triggered=False, z=0.0, detail="Baseline initialized")

    mean = b.mean_hourly
    std = max(b.stddev_hourly, 1e-6)
    z = (current_hourly_count - mean) / std
    triggered = abs(z) > 3.0 and b.sample_count >= 10

    # online update with simple EWMA-ish approach
    alpha = 0.05
    new_mean = (1 - alpha) * mean + alpha * current_hourly_count
    new_var = (1 - alpha) * (std * std) + alpha * ((current_hourly_count - new_mean) ** 2)
    new_std = math.sqrt(max(new_var, 1e-6))
    b2 = Baseline(agent_id=agent_id, tool_name=tool_name, mean_hourly=float(new_mean), stddev_hourly=float(new_std), sample_count=b.sample_count + 1, updated_at=utc_now_iso())
    store.upsert(b2)

    detail = f"hourly={current_hourly_count} z={z:.2f} baseline_mean={mean:.2f} baseline_std={std:.2f}"
    return b2, DriftResult(triggered=triggered, z=float(z), detail=detail)


"""Deterministic sensor-consensus logic (no LLM involved)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConsensusResult:
    status: str               # "consensus" | "majority" | "ambiguous"
    value: float | None       # conservative (lowest) value of the agreeing cluster
    median: float | None
    agreeing: list[int]
    outliers: list[int]
    spread: float


def tolerance(value: float, rel: float = 0.03, abs_min: float = 5.0) -> float:
    return max(abs_min, abs(value) * rel)


def sensor_consensus(readings: list[float], rel: float = 0.03, abs_min: float = 5.0) -> ConsensusResult:
    n = len(readings)
    best: list[int] = []
    for i, ref in enumerate(readings):
        cluster = [j for j, r in enumerate(readings) if abs(r - ref) <= tolerance(ref, rel, abs_min)]
        if len(cluster) > len(best) or (len(cluster) == len(best) and cluster and
                                        min(readings[k] for k in cluster) > min(readings[k] for k in best)):
            best = cluster
    spread = (max(readings) - min(readings)) if readings else 0.0
    if n == 0 or len(best) < 2:
        return ConsensusResult("ambiguous", None, None, [], list(range(n)), spread)
    vals = sorted(readings[k] for k in best)
    median = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    status = "consensus" if len(best) == n else "majority"
    return ConsensusResult(status, min(vals), round(median, 3),
                           best, [k for k in range(n) if k not in best], round(spread, 3))

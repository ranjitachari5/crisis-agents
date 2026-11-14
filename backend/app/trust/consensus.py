"""Deterministic, robust sensor-consensus logic (F5). No LLM involved.

Plain 2-of-3 majority voting assumes independent failures: two spoofed or
co-located faulty sensors defeat it. This estimator instead

1. drops physically implausible readings (non-finite, outside bounds),
2. takes the median and rejects outliers with a MAD-based threshold, clamped
   to the sensors' measurement tolerance so that a 3-way split never passes,
3. averages the kept readings weighted by per-sensor reputation, and
4. refuses (``INSUFFICIENT_CONSENSUS`` / ``UNCORROBORATED_STEP``) rather than
   guessing: when a large step change is supported only by a majority while
   the dissenting sensor still reads the last accepted value, that is
   indistinguishable from a correlated fault and is escalated to the commander.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MAD_SCALE = 1.4826  # MAD -> standard deviation for normal noise


@dataclass
class ConsensusResult:
    status: str               # "consensus" | "majority" | "ambiguous"
    value: float | None       # conservative (lowest) kept reading
    median: float | None      # reputation-weighted robust estimate of the kept readings
    agreeing: list[int]
    outliers: list[int]
    spread: float
    reason: str = "OK"        # OK | INSUFFICIENT_PLAUSIBLE | INSUFFICIENT_CONSENSUS | UNCORROBORATED_STEP
    implausible: list[int] = field(default_factory=list)


def tolerance(value: float, rel: float = 0.03, abs_min: float = 5.0) -> float:
    return max(abs_min, abs(value) * rel)


def _ambiguous(n: int, spread: float, reason: str, implausible: list[int]) -> ConsensusResult:
    return ConsensusResult("ambiguous", None, None, [], list(range(n)), round(spread, 3), reason, implausible)


def sensor_consensus(readings: list[float], weights: list[float] | None = None, *, rel: float = 0.03,
                     abs_min: float = 5.0, k: float = 3.0, bounds: tuple[float, float] | None = None,
                     previous: float | None = None, max_step: float | None = None) -> ConsensusResult:
    n = len(readings)
    if n == 0:
        return _ambiguous(0, 0.0, "INSUFFICIENT_PLAUSIBLE", [])
    x = np.asarray(readings, dtype=float)
    w = np.ones(n) if weights is None else np.clip(np.asarray(weights, dtype=float), 1e-3, None)
    finite = np.isfinite(x)
    spread = float(np.ptp(x[finite])) if finite.any() else 0.0

    plausible = finite.copy()
    if bounds is not None:
        lo, hi = bounds
        plausible &= (x >= lo) & (x <= hi)
    implausible = [int(i) for i in np.flatnonzero(~plausible)]
    idx = np.flatnonzero(plausible)
    if len(idx) < 2:
        return _ambiguous(n, spread, "INSUFFICIENT_PLAUSIBLE", implausible)

    xs = x[idx]
    med = float(np.median(xs))
    mad = float(np.median(np.abs(xs - med))) * MAD_SCALE
    floor = tolerance(med, rel, abs_min)
    # MAD alone is unstable for n=3 (it can collapse to ~0 or blow up on a split);
    # clamp it between one and two measurement tolerances.
    threshold = min(max(k * mad, floor), 2 * floor)
    keep = [int(i) for i in idx[np.abs(xs - med) <= threshold]]
    if len(keep) < 2:
        return _ambiguous(n, spread, "INSUFFICIENT_CONSENSUS", implausible)

    kept = x[keep]
    estimate = float(np.average(kept, weights=w[keep]))
    outliers = [i for i in range(n) if i not in keep]
    status = "consensus" if len(keep) == n else "majority"

    if previous is not None and max_step is not None and status == "majority" and abs(estimate - previous) > max_step:
        # A big jump that only a majority supports while a dissenter still reads the last accepted
        # value: indistinguishable from two correlated faulty/spoofed sensors. Escalate, never guess.
        prev_tol = tolerance(previous, rel, abs_min)
        if any(plausible[i] and abs(x[i] - previous) <= prev_tol for i in outliers):
            return _ambiguous(n, spread, "UNCORROBORATED_STEP", implausible)

    return ConsensusResult(status, round(float(kept.min()), 3), round(estimate, 3), keep, outliers,
                           round(spread, 3), "OK", implausible)

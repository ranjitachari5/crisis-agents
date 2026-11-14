"""Multi-seed benchmark / ablation sweep from the command line (F16).

    python -m scripts.crisis_benchmark --scenario flood_cascade --seeds 1 2 3 4 5 --ticks 32 \
        --modes negotiation no_trust fallback_only negotiation_only centralized --adversarial --out results.json

Prints mean ± 95% CI per metric and writes the full result (with config hash) as JSON.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.evaluation.runner import DEFAULT_MODES, VARIANTS, run_evaluation  # noqa: E402

METRICS = ("weighted_damage", "critical_service_uptime_pct", "unmet_demand_mwh", "constraint_violations",
           "convergence_rate", "fallback_rate")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="flood_cascade")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    ap.add_argument("--ticks", type=int, default=32)
    ap.add_argument("--fairness", type=float, default=0.5)
    ap.add_argument("--modes", nargs="+", default=DEFAULT_MODES, choices=list(VARIANTS))
    ap.add_argument("--adversarial", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()

    settings = dataclasses.replace(get_settings(), llm_enabled=False)
    res = run_evaluation(settings, a.scenario, a.seeds, a.ticks, a.fairness, a.modes, a.adversarial)
    print(f"config {res['config_hash'][:12]}  scenario={a.scenario} seeds={a.seeds} ticks={a.ticks} "
          f"adversarial={a.adversarial}  ({res['duration_s']} s)")
    print(f"{'mode':20s}" + "".join(f"{m:>30s}" for m in METRICS))
    for mode, r in res["results"].items():
        cells = []
        for m in METRICS:
            st = r["stats"].get(m) if "stats" in r else None
            if st and st["mean"] is not None:
                ci = st["ci95"]
                cells.append(f"{st['mean']:.3f} ± {(ci[1] - ci[0]) / 2:.3f}" if ci else f"{st['mean']:.3f}")
            else:
                cells.append("-" if r.get(m) is None else str(r.get(m)))
        print(f"{mode:20s}" + "".join(f"{c:>30s}" for c in cells))
    if a.out:
        a.out.write_text(json.dumps(res, indent=2, default=str))
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

from app.optimization.allocator import AllocationProblem, solve

IDS = ["hospital_agent", "water_agent", "telecom_agent", "emergency_agent"]


def problem(supply, fairness=0.5):
    return AllocationProblem(
        IDS, dict(zip(IDS, [100, 70, 50, 60])), dict(zip(IDS, [85, 55, 30, 35])), dict(zip(IDS, [130, 90, 60, 80])),
        dict(zip(IDS, [10, 8.95, 9.15, 8])), dict(zip(IDS, [100, 89.5, 91.5, 80])), supply, fairness)


def test_respects_supply_and_minimums():
    for f in (0, 0.3, 0.5, 0.8, 1):
        s = solve(problem(230, f))
        assert sum(s.allocation.values()) <= 230 + 1e-6
        assert not s.degradation
        for i, m in zip(IDS, [85, 55, 30, 35]):
            assert s.allocation[i] >= m - 1e-6
        for i, d in zip(IDS, [100, 70, 50, 60]):
            assert s.allocation[i] <= d + 1e-6


def test_fairness_slider_changes_allocation():
    pri, bal, eq = (solve(problem(230, f)).allocation for f in (0.0, 0.5, 1.0))
    assert pri["hospital_agent"] > bal["hospital_agent"] > eq["hospital_agent"]
    assert pri["emergency_agent"] < eq["emergency_agent"]
    assert solve(problem(230, 1.0)).objective["fairness_penalty"] < solve(problem(230, 0.0)).objective["fairness_penalty"]


def test_no_deficit_gives_full_demand():
    s = solve(problem(400))
    assert s.allocation == dict(zip(IDS, [100.0, 70.0, 50.0, 60.0]))


def test_degradation_mode_reports_shortages_and_uses_all_supply():
    s = solve(problem(180))
    assert s.degradation
    assert abs(sum(s.allocation.values()) - 180) < 1e-3
    assert s.shortages
    assert s.allocation["hospital_agent"] >= 85 - 1e-6  # highest critical weight protected first


def test_zero_supply():
    s = solve(problem(0))
    assert sum(s.allocation.values()) == 0


def test_rounded_allocation_stays_within_supply():
    p = AllocationProblem(
        ["a1", "a2", "a3", "a4", "a5"],
        {"a1": 33.9346924030449, "a2": 43.37150230634484, "a3": 46.16311358516383,
         "a4": 34.818740318659835, "a5": 40.36482089507599},
        {"a1": 16.419125472944696, "a2": 31.75598245043277, "a3": 19.98525090511609,
         "a4": 19.307829835233488, "a5": 10.310801368986827},
        {"a1": 35.55049552211767, "a2": 83.50292434905009, "a3": 44.960006636975805,
         "a4": 44.066549346218636, "a5": 62.887456875567345},
        {"a1": 1.0, "a2": 1.0, "a3": 1.0, "a4": 1.0, "a5": 1.0},
        {"a1": 1.0, "a2": 1.0, "a3": 1.0, "a4": 1.0, "a5": 1.0},
        189.3439730034437,
        0.21765530162737312,
    )
    s = solve(p)
    assert sum(s.allocation.values()) <= p.supply + 1e-6

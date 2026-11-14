from app.validation.validator import AllocationConstraints, validate_allocation

IDS = ["hospital_agent", "water_agent", "telecom_agent", "emergency_agent"]


def cons(grid=200, battery=30, version=3):
    return AllocationConstraints(version, grid, battery, dict(zip(IDS, [85, 55, 30, 35])),
                                 dict(zip(IDS, [130, 90, 60, 80])), dict(zip(IDS, [100, 70, 50, 60])), IDS)


GOOD = dict(zip(IDS, [90, 60, 40, 40]))


def codes(r):
    return {v.code for v in r.violations}


def test_valid_allocation():
    r = validate_allocation(GOOD, cons(), 3, "p1", set())
    assert r.valid and not r.degradation_mode and r.battery_discharge == 30


def test_over_capacity_rejected():
    r = validate_allocation({**GOOD, "water_agent": 70}, cons(), 3, "p1", set())
    assert "OVER_CAPACITY" in codes(r)


def test_below_minimum_rejected_when_avoidable():
    r = validate_allocation({**GOOD, "hospital_agent": 80, "water_agent": 70}, cons(), 3, "p1", set())
    assert "BELOW_MIN_SAFE" in codes(r)


def test_above_max_rejected():
    r = validate_allocation({**GOOD, "telecom_agent": 61}, cons(grid=400), 3, "p1", set())
    assert "ABOVE_MAX" in codes(r)


def test_stale_and_duplicate():
    assert "STALE_PROPOSAL" in codes(validate_allocation(GOOD, cons(), 2, "p1", set()))
    assert "DUPLICATE_PROPOSAL" in codes(validate_allocation(GOOD, cons(), 3, "p1", {"p1"}))


def test_degradation_allows_shortage_but_not_withholding():
    c = cons(grid=170, battery=0)  # mins 205 > 170
    ok = validate_allocation(dict(zip(IDS, [85, 30, 30, 25])), c, 3, "p", set())
    assert ok.valid and ok.degradation_mode and ok.unavoidable_shortages
    bad = validate_allocation(dict(zip(IDS, [85, 20, 30, 25])), c, 3, "p", set())
    assert "SUPPLY_WITHHELD_IN_DEGRADATION" in codes(bad)


def test_battery_limit_and_missing_agent():
    r = validate_allocation(GOOD, cons(battery=10), 3, "p", set())
    assert "BATTERY_LIMIT" in codes(r) or "OVER_CAPACITY" in codes(r)
    r = validate_allocation({k: v for k, v in GOOD.items() if k != "water_agent"}, cons(), 3, "p", set())
    assert "AGENT_SET_MISMATCH" in codes(r)


def test_non_finite_rejected():
    r = validate_allocation({**GOOD, "water_agent": float("nan")}, cons(), 3, "p", set())
    assert not r.valid

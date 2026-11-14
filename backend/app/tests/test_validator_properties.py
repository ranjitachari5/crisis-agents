"""F6/F9/F17: validator soundness (hypothesis), new violation codes, optimizer output always validates."""
import math

from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from app.optimization.allocator import AllocationProblem, solve
from app.validation.validator import TOL, AllocationConstraints, validate_allocation

IDS = ["hospital_agent", "water_agent", "telecom_agent", "emergency_agent"]
MINS = dict(zip(IDS, [85, 55, 30, 35]))
MAXS = dict(zip(IDS, [130, 90, 60, 80]))
DEMAND = dict(zip(IDS, [100, 70, 50, 60]))
RAMP = dict(zip(IDS, [45, 30, 30, 37.5]))
FEEDERS = {"north": (["hospital_agent", "emergency_agent"], 180.0), "south": (["water_agent", "telecom_agent"], 120.0)}


def cons(grid, battery, prev=None, usable=None):
    return AllocationConstraints(3, grid, battery, MINS, MAXS, DEMAND, IDS, previous=prev, ramp_up=RAMP,
                                 feeders=FEEDERS, battery_usable_mwh=usable, dt_hours=0.25)


def independent_violations(a, c):
    """Re-derive every constraint independently of the validator."""
    out = set()
    total = sum(a.values())
    if total > c.total_supply + TOL:
        out.add("OVER_CAPACITY")
    degr = sum(min(MINS[i], DEMAND[i]) for i in IDS) > c.total_supply + TOL
    for i in IDS:
        if a[i] > MAXS[i] + TOL:
            out.add("ABOVE_MAX")
        if not degr and a[i] < min(MINS[i], DEMAND[i]) - TOL:
            out.add("BELOW_MIN_SAFE")
        if c.previous and a[i] > max(c.previous[i] + RAMP[i], min(MINS[i], DEMAND[i])) + TOL:
            out.add("RAMP_LIMIT")
    for members, cap in FEEDERS.values():
        if sum(a[m] for m in members) > cap + TOL:
            out.add("FEEDER_CAP")
    need = max(0.0, total - c.grid_supply)
    if need > c.battery_offer + TOL:
        out.add("BATTERY_LIMIT")
    if c.battery_usable_mwh is not None and need * c.dt_hours > c.battery_usable_mwh + TOL:
        out.add("BATTERY_SOC")
    if degr:
        absorbable = sum(min(c.upper_cap(i), DEMAND[i]) for i in IDS)
        if total < min(c.total_supply, absorbable) - 0.05:
            out.add("SUPPLY_WITHHELD_IN_DEGRADATION")
    return out


alloc_st = st.fixed_dictionaries({i: st.floats(0, 140, allow_nan=False) for i in IDS})


@hsettings(max_examples=400, deadline=None)
@given(alloc_st, st.floats(100, 320), st.floats(0, 30), st.booleans(), st.floats(0, 40))
def test_validator_sound_and_complete(a, grid, battery, use_prev, usable):
    prev = {i: DEMAND[i] * 0.6 for i in IDS} if use_prev else None
    c = cons(grid, battery, prev, usable)
    r = validate_allocation(a, c, 3, "p", set())
    expected = independent_violations(a, c)
    assert r.valid == (not expected)
    if not r.valid:
        assert expected & {v.code for v in r.violations}


def test_malformed_values_rejected_before_arithmetic():
    c = cons(200, 30)
    for bad, code in ((float("nan"), "NON_FINITE_OR_NEGATIVE"), (float("inf"), "NON_FINITE_OR_NEGATIVE"),
                      (-1.0, "NON_FINITE_OR_NEGATIVE"), ("90", "NON_NUMERIC"), (True, "NON_NUMERIC"),
                      (None, "NON_NUMERIC")):
        r = validate_allocation({**DEMAND, "water_agent": bad}, c, 3, "p", set())
        assert not r.valid and code in {v.code for v in r.violations}


def test_ramp_feeder_and_soc_codes():
    prev = dict(zip(IDS, [85, 21, 30, 35]))
    r = validate_allocation({**MINS, "telecom_agent": 50, "water_agent": 55}, cons(400, 0, prev), 3, "p", set())
    assert r.valid  # water restored to its safe minimum despite +34 MW > 30 MW ramp
    r = validate_allocation({**MINS, "telecom_agent": 61.0 + 5}, cons(400, 0, prev), 3, "p", set())
    assert "RAMP_LIMIT" in {v.code for v in r.violations}
    r = validate_allocation({**DEMAND, "hospital_agent": 125, "emergency_agent": 60}, cons(400, 0), 3, "p", set())
    assert "FEEDER_CAP" in {v.code for v in r.violations}
    r = validate_allocation(DEMAND, cons(260, 30, usable=2.0), 3, "p", set())
    assert "BATTERY_SOC" in {v.code for v in r.violations}


@hsettings(max_examples=150, deadline=None)
@given(st.floats(120, 300), st.floats(0, 1), st.lists(st.floats(0.7, 1.3), min_size=4, max_size=4))
def test_optimizer_output_always_validates(supply, fairness, scale):
    demand = {i: DEMAND[i] * s for i, s in zip(IDS, scale)}
    p = AllocationProblem(IDS, demand, MINS, MAXS, dict(zip(IDS, [10, 9, 9, 8])), dict(zip(IDS, [100, 90, 91, 80])),
                          supply, fairness)
    sol = solve(p)
    c = AllocationConstraints(0, supply, 0.0, MINS, MAXS, demand, IDS)
    r = validate_allocation(sol.allocation, c, 0, "p", set())
    assert r.valid, (sol.solver, [v.code for v in r.violations])
    assert all(math.isfinite(x) for x in sol.allocation.values())

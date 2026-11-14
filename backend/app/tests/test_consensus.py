"""F5: robust consensus under independent and correlated sensor faults."""
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from app.trust.consensus import sensor_consensus

NOMINAL = 320.0
BOUNDS = (0.0, NOMINAL * 1.1)
noise = st.floats(-0.8, 0.8)


@given(st.floats(50, 320), noise, noise, noise)
def test_agreeing_sensors_reach_consensus(v, a, b, c):
    r = sensor_consensus([v + a, v + b, v + c], bounds=BOUNDS, previous=v, max_step=48)
    assert r.status == "consensus" and abs(r.median - v) < 1.0


@given(st.floats(80, 320), st.floats(0.05, 0.6), noise, noise)
def test_single_faulty_sensor_is_excluded(v, frac, a, b):
    r = sensor_consensus([v + a, v + b, v * frac], bounds=BOUNDS, previous=v, max_step=48)
    assert r.status == "majority" and r.outliers == [2] and abs(r.median - v) < 1.0


@hsettings(max_examples=200)
@given(st.floats(120, 320), st.floats(0.05, 0.55), noise, noise)
def test_two_correlated_bad_sensors_escalate_not_accept(v, frac, a, b):
    # a cut larger than the per-step limit (15 % of nominal = 48 MW) asserted by only two sensors
    bad = v * frac
    r = sensor_consensus([bad + a, bad + b, v], bounds=BOUNDS, previous=v, max_step=48)
    assert r.status == "ambiguous" and r.reason == "UNCORROBORATED_STEP" and r.median is None


@given(st.floats(150, 320))
def test_unanimous_large_change_is_accepted(v):
    # a real event moves every sensor type together; that is corroborated, not a correlated fault
    r = sensor_consensus([v * 0.5, v * 0.5 + 0.3, v * 0.5 - 0.2], bounds=BOUNDS, previous=v, max_step=48)
    assert r.status == "consensus"


def test_three_way_split_and_implausible_readings():
    assert sensor_consensus([200, 120, 40], bounds=BOUNDS).reason == "INSUFFICIENT_CONSENSUS"
    r = sensor_consensus([200, 200.4, 9999], bounds=BOUNDS)
    assert r.status == "majority" and r.implausible == [2]
    assert sensor_consensus([float("nan"), 200, -5], bounds=BOUNDS).reason == "INSUFFICIENT_PLAUSIBLE"


def test_reputation_weights_the_estimate():
    r = sensor_consensus([200, 202, 201], weights=[1.0, 0.1, 1.0])
    assert abs(r.median - 200.55) < 0.1


def test_engine_escalates_correlated_fault_and_freezes(engine):
    v = engine.agreements.version
    inc = engine.inject_fake("contradictory_sensors", {"mode": "correlated"})
    assert inc["decision"] == "escalated" and engine.frozen
    engine.step()
    assert engine.agreements.version == v

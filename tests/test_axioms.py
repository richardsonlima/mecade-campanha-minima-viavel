from mecade.axioms import AxiomEvaluator, AxiomParams, deviation


def P(**kw):
    base = dict(k=2, d_on=0.5, d_off=0.3, tau_dwell=15, aggregation="max", deadband=0.3, budget_B=60)
    base.update(kw)
    return AxiomParams(**base)


def test_deviation_floor_avoids_division_by_zero():
    assert deviation(0.02, 0.0, floor=0.01) == 2.0
    assert deviation(None, 1.0, 0.01) is None


def test_transient_spike_does_not_alert_dwell():
    ev = AxiomEvaluator(P())
    out = ev.step({"a": 2.0, "b": 2.0, "c": 0.0}, 5) + ev.step({"a": 0.0, "b": 0.0, "c": 0.0}, 5)
    assert "ALERT" not in out


def test_single_signal_does_not_alert_k_of_n():
    ev = AxiomEvaluator(P())
    out = []
    for _ in range(10):
        out += ev.step({"a": 3.0, "b": 0.0, "c": 0.0}, 5)
    assert "ALERT" not in out


def test_sustained_correlated_deviation_alerts_after_dwell():
    ev = AxiomEvaluator(P())
    seq = [ev.step({"a": 0.8, "b": 0.8, "c": 0.0}, 5) for _ in range(3)]
    assert "ALERT" not in seq[0] + seq[1] and "ALERT" in seq[2]  # 15 s


def test_hysteresis_keeps_alert_between_thresholds():
    ev = AxiomEvaluator(P())
    for _ in range(3):
        ev.step({"a": 0.8, "b": 0.8, "c": 0.0}, 5)
    assert ev.alert
    out = ev.step({"a": 0.4, "b": 0.4, "c": 0.0}, 5)  # entre d_off e d_on
    assert ev.alert and "ALERT_CLEAR" not in out
    out = ev.step({"a": 0.1, "b": 0.1, "c": 0.0}, 5)
    assert not ev.alert and "ALERT_CLEAR" in out


def test_noise_below_deadband_never_violates_budget():
    ev = AxiomEvaluator(P())
    for _ in range(10_000):
        assert "BLOCK" not in ev.step({"a": 0.25, "b": 0.2, "c": 0.1}, 5)
    assert ev.I == 0.0


def test_gray_failure_accumulates_and_blocks_once():
    ev = AxiomEvaluator(P())
    events = []
    for _ in range(100):  # D_agr = 0.9 -> excesso 0.6/s; B = 60 -> ~100 s
        events += ev.step({"a": 0.9, "b": 0.2, "c": 0.2}, 5)
    assert events.count("BLOCK") == 1 and events.count("LIMIT") == 1
    assert "ALERT" not in events  # só um sinal acima de d_on: o LIMIT pega o que escapa do ALERT


def test_no_data():
    ev = AxiomEvaluator(P())
    assert ev.step({"a": None}, 5) == ["NO_DATA"]

from mecade.reactive import ReactiveRule


def rule():
    return ReactiveRule(rules=[{"signal": "p99", "op": ">", "factor_of_baseline": 2.0}],
                        for_s=300, response_delay=120, baseline={"p99": 0.25})


def test_fires_only_after_continuous_for():
    r = rule()
    t = 0
    for _ in range(59):
        assert r.step(t, {"p99": 0.6}, 5) == []
        t += 5
    assert r.step(t, {"p99": 0.6}, 5) == ["REACTIVE_FIRE"]
    assert not r.mitigation_due(t + 119) and r.mitigation_due(t + 120)


def test_interruption_resets_pending():
    r = rule()
    for i in range(50):
        r.step(i * 5, {"p99": 0.6}, 5)
    r.step(250, {"p99": 0.3}, 5)
    assert r.t_true == 0 and r.fired_at is None

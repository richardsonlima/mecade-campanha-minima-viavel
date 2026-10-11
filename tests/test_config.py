from mecade.config import load_campaign, load_scenario, render_chaos


def test_all_scenarios_load_and_render():
    camp = load_campaign()
    for sc_id in camp["scenarios"] + [camp["control_scenario"]]:
        sc = load_scenario(sc_id)
        m = render_chaos(sc["chaos"], name="x", ns="boutique", pods=["p-1"], fault_s=600)
        if m is None:
            continue
        assert m["metadata"] == {"name": "x", "namespace": "boutique"}
        text = str(m)
        assert "{" not in text.replace("{'", "").replace("{\"", "") or "'{" not in text


def test_pods_placeholder_becomes_list():
    sc = load_scenario("s1_latencia_productcatalog")
    m = render_chaos(sc["chaos"], name="x", ns="boutique", pods=["a", "b"], fault_s=600)
    assert m["spec"]["selector"]["pods"] == {"boutique": ["a", "b"]}
    assert m["spec"]["duration"] == "600s"

"""Teste de ponta a ponta do pipeline usando o backend de simulação, sem cluster."""
import copy

from analysis.metrics import metrics_table, load_runs, paired_comparison
from mecade.config import load_campaign, load_scenario
from mecade.runner import run_one
from mecade.sim import SimWorld, VirtualClock


def test_sim_campaign_end_to_end(tmp_path):
    camp = copy.deepcopy(load_campaign())
    out = tmp_path / "runs"
    k = 0
    for sc in camp["scenarios"]:
        for rep in (1, 2):
            for arm in ("baseline", "mecade"):
                k += 1
                clock = VirtualClock(); world = SimWorld(clock, seed=k)
                meta = run_one(run_id=f"{k:03d}_{sc}_{arm}_r{rep:02d}", scenario=load_scenario(sc), arm=arm,
                               campaign=camp, prom=world, kube=world, clock=clock, out_root=out,
                               sim_world=world, log=lambda *_: None)
                assert meta["status"] == "complete"
    clock = VirtualClock(); world = SimWorld(clock, seed=999)
    ctrl = run_one(run_id="900_c0_controle_mecade_r01", scenario=load_scenario("c0_controle"), arm="mecade",
                   campaign=camp, prom=world, kube=world, clock=clock, out_root=out, sim_world=world, log=lambda *_: None)
    assert not any(e["event"] == "BLOCK" for e in ctrl["events"]), "falso bloqueio no controle simulado"

    import json
    for p in out.glob("*/meta.json"):  # quem acrescenta `pair` é o orquestrador; aqui faço o mesmo à mão
        m = json.loads(p.read_text()); rid = m["run_id"]
        if "c0_controle" not in rid:
            m["pair"] = f"{m['scenario']}#{rid.split('_r')[-1]}"
        p.write_text(json.dumps(m))
    runs = load_runs(out, include_sim=True)
    m = metrics_table(runs)
    assert len(m) == 13
    mec = m[(m.arm == "mecade") & (m.pair != "")]
    assert mec["detected"].all()
    cmp = paired_comparison(m, "TTR_capped")
    assert set(cmp["scenario"]) == set(camp["scenarios"])

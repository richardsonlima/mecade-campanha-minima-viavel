"""Tipo de máquina dos nós no meta.json (PROTOCOLO_C3, 8.1 item 5)."""
import json


def test_tipo_de_maquina_dos_nos_vem_do_rotulo(monkeypatch):
    from mecade.backends import Kubectl
    nos = {"items": [{"metadata": {"labels": {"node.kubernetes.io/instance-type": "e2-standard-2"}}}] * 3
           + [{"metadata": {"labels": {}}}]}
    k = Kubectl("boutique")
    monkeypatch.setattr(k, "_run", lambda *a, **kw: json.dumps(nos))
    assert k.node_machine_types() == {"desconhecido": 1, "e2-standard-2": 3}
    monkeypatch.setattr(k, "_run", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("sem kubectl")))
    assert k.node_machine_types() == {}


def test_meta_da_replica_registra_o_tipo_de_maquina(tmp_path):
    from mecade.config import load_campaign, load_scenario
    from mecade.runner import run_one
    from mecade.sim import SimWorld, VirtualClock
    camp = load_campaign()
    clock = VirtualClock()
    w = SimWorld(clock, seed=1)
    meta = run_one(run_id="900_c0_controle_mecade_r01", scenario=load_scenario("c0_controle"), arm="mecade",
                   campaign=camp, prom=w, kube=w, clock=clock, out_root=tmp_path, audit_enabled=False,
                   sim_world=w, log=lambda *_: None)
    assert meta["machine_types"] == {"sim": 3}
    assert not list((tmp_path / "900_c0_controle_mecade_r01").glob("k8s_*"))   # sim não coleta

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


def _roda_com_coletor(monkeypatch, tmp_path, coletor_cls, quebra_no_loop=False):
    import mecade.runner as rn
    from mecade.config import load_campaign, load_scenario
    from mecade.sim import SimWorld, VirtualClock
    clock = VirtualClock()
    w = SimWorld(clock, seed=1)
    monkeypatch.setattr(rn, "Kubectl", SimWorld)        # o sim passa por backend real para o isinstance
    monkeypatch.setattr(rn, "ColetorK8s", coletor_cls)
    if quebra_no_loop:
        def q(*a, **k):
            raise RuntimeError("prometheus caiu")
        monkeypatch.setattr(w, "instant", q)
    return rn.run_one(run_id="901_c0_controle_mecade_r01", scenario=load_scenario("c0_controle"), arm="mecade",
                      campaign=load_campaign(), prom=w, kube=w, clock=clock, out_root=tmp_path, audit_enabled=False,
                      sim_world=w, log=lambda *_: None)


class _ColetorFalso:
    vivo = []

    def __init__(self, *a, **k):
        self.parou = False
        _ColetorFalso.vivo.append(self)

    def iniciar(self):
        pass

    def parar(self):
        self.parou = True


def test_falha_ao_criar_o_coletor_nao_derruba_a_replica(monkeypatch, tmp_path):
    class Quebra:
        def __init__(self, *a, **k):
            raise RuntimeError("sem permissão em out")
    meta = _roda_com_coletor(monkeypatch, tmp_path, Quebra)
    assert meta["status"] == "complete"


def test_falha_ao_iniciar_o_coletor_nao_derruba_a_replica(monkeypatch, tmp_path):
    class Quebra(_ColetorFalso):
        def iniciar(self):
            raise RuntimeError("thread não subiu")
    assert _roda_com_coletor(monkeypatch, tmp_path, Quebra)["status"] == "complete"


def test_coletor_para_mesmo_quando_o_laco_levanta_excecao(monkeypatch, tmp_path):
    import pytest
    _ColetorFalso.vivo.clear()
    with pytest.raises(RuntimeError):
        _roda_com_coletor(monkeypatch, tmp_path, _ColetorFalso, quebra_no_loop=True)
    assert _ColetorFalso.vivo and all(c.parou for c in _ColetorFalso.vivo)


def test_kubectl_tem_timeout_nas_chamadas(monkeypatch):
    import subprocess
    from mecade.backends import Kubectl
    vistos = []

    def falso(cmd, **kw):
        vistos.append((cmd, kw.get("timeout")))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"items": []}', stderr="")
    monkeypatch.setattr(subprocess, "run", falso)
    k = Kubectl("boutique")
    k.node_machine_types()
    k.restart("frontend")
    k.wait_rollout("frontend", timeout="300s")
    assert all(t for _, t in vistos) and vistos[0][1] <= 20 and vistos[-1][1] == 330.0

    def trava(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(subprocess, "run", trava)
    assert k.node_machine_types() == {}                 # metadado: não derruba a réplica

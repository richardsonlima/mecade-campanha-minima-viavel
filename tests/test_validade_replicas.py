"""meta.json com rastreabilidade e filtro das réplicas da análise oficial."""
import copy
import json
import subprocess
import warnings

import pytest

from analysis.metrics import execution_failures, load_official_runs, load_runs, paired_comparison
from mecade import runner
from mecade.config import load_campaign, load_scenario
from mecade.runner import run_one
from mecade.sim import SimWorld, VirtualClock

CID = "mvc-teste"


def _roda(out, run_id, **kw):
    camp = copy.deepcopy(load_campaign())
    clock = VirtualClock()
    w = SimWorld(clock, seed=1)
    return run_one(run_id=run_id, scenario=load_scenario("s3_podkill_cart"), arm="mecade", campaign=camp,
                   prom=w, kube=w, clock=clock, out_root=out, sim_world=w, log=lambda *_: None, **kw)


def test_meta_traz_campaign_id_hash_dirty_e_plano(tmp_path):
    meta = _roda(tmp_path, "001_x")
    lido = json.loads((tmp_path / "001_x" / "meta.json").read_text())
    assert lido["campaign_id"] == load_campaign()["campaign_id"]
    assert len(lido["config_sha256"]) == 64
    assert lido["git_dirty"] in (True, False)
    assert lido["plano"] == "sim"
    assert lido["git_commit"] == meta["git_commit"]  # campos antigos continuam


def test_hash_do_config_e_estavel_e_tolera_arquivo_ausente():
    assert runner._config_sha256().isalnum()
    assert runner._config_sha256("/nao/existe") == "sem-config"


def test_git_dirty_ignora_data_e_ve_mudanca_local(tmp_path, monkeypatch):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    (tmp_path / "data").mkdir()
    (tmp_path / "a.txt").write_text("1")
    git("add", ".")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    assert runner._git_dirty() is False
    (tmp_path / "data" / "runs.txt").write_text("novo")
    assert runner._git_dirty() is False
    (tmp_path / "a.txt").write_text("2")
    assert runner._git_dirty() is True


def test_git_dirty_sem_git_devolve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path / "inexistente")
    assert runner._git_dirty() is None


def _fake(root, run_id, **meta):
    d = root / run_id
    d.mkdir(parents=True)
    (d / "steps.csv").write_text("t,D_agr\n0,0\n")
    base = {"run_id": run_id, "status": "complete", "backend": "k8s"}
    (d / "meta.json").write_text(json.dumps({**base, **meta}))


def test_load_official_runs_filtra_e_lista_excluidas(tmp_path):
    _fake(tmp_path, "ok", campaign_id=CID, plano="oficial")
    _fake(tmp_path, "outra", campaign_id="outra", plano="oficial")
    _fake(tmp_path, "sim", campaign_id=CID, plano="sim", backend="sim")
    _fake(tmp_path, "cal", campaign_id=CID, plano="calibracao")
    _fake(tmp_path, "cal_antiga", campaign_id=CID, etapa="calibracao")
    _fake(tmp_path, "velha")
    _fake(tmp_path, "falha", status="falha_execucao")
    with pytest.warns(UserWarning, match="velha"):
        runs, excl = load_official_runs(tmp_path, campaign_id=CID)
    assert [m["run_id"] for m, _ in runs] == ["ok"]
    assert {e["run_id"] for e in excl} == {"outra", "sim", "cal", "cal_antiga", "velha", "falha"}
    assert all(e["motivo"] for e in excl)
    assert "campaign_id" in next(e for e in excl if e["run_id"] == "velha")["motivo"]


def test_load_official_runs_le_o_campaign_id_do_config(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f"campaign_id: {CID}\n")
    _fake(tmp_path / "r", "ok", campaign_id=CID)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        runs, excl = load_official_runs(tmp_path / "r", config_path=cfg)
    assert len(runs) == 1 and excl == []


def test_load_runs_nao_mudou_e_inclui_sim(tmp_path):
    _fake(tmp_path, "sim", backend="sim")
    _fake(tmp_path, "k8s")
    assert len(load_runs(tmp_path, include_sim=True)) == 2
    assert len(load_runs(tmp_path)) == 1


def test_rotulo_de_sim_e_calibracao_vale_mesmo_sem_campaign_id(tmp_path):
    _fake(tmp_path, "sim_velha", backend="sim")
    _fake(tmp_path, "cal_velha", etapa="calibracao")
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # o aviso de campaign_id só sai quando é o motivo
        _, excl = load_official_runs(tmp_path, campaign_id=CID)
    motivos = {e["run_id"]: e["motivo"] for e in excl}
    assert motivos == {"sim_velha": "simulação", "cal_velha": "calibração"}


def test_execution_failures_filtra_pelo_campaign_id_oficial(tmp_path):
    _fake(tmp_path, "falha_ok", status="falha_execucao", campaign_id=CID)
    _fake(tmp_path, "falha_outra", status="falha_execucao", campaign_id="outra")
    _fake(tmp_path, "falha_sem_id", status="falha_execucao")
    _fake(tmp_path, "cal1_falha", status="falha_execucao", campaign_id=CID)
    _fake(tmp_path, "falha_sim", status="falha_execucao", campaign_id=CID, backend="sim")
    _fake(tmp_path, "completa", campaign_id=CID)
    with pytest.warns(UserWarning, match="falha_sem_id.*sem campaign_id"):
        assert [f["run_id"] for f in execution_failures(tmp_path, campaign_id=CID)] == ["falha_ok"]


def test_paired_comparison_tolera_braco_orfao_de_par_excluido():
    import pandas as pd
    linhas = []
    for pair in range(1, 6):
        linhas.append({"scenario": "s1", "arm": "baseline", "pair": f"p{pair}", "x": 100.0 + pair})
        if pair != 3:                                   # o par p3 perdeu o braço MECADE (falha_execucao)
            linhas.append({"scenario": "s1", "arm": "mecade", "pair": f"p{pair}", "x": 50.0 + pair})
    linhas.append({"scenario": "s1", "arm": "mecade", "pair": "p9", "x": 1.0})   # órfão do outro lado
    out = paired_comparison(pd.DataFrame(linhas), "x")
    assert len(out) == 1 and out.iloc[0]["n_pairs"] == 4
    assert out.iloc[0]["median_diff"] == -50.0

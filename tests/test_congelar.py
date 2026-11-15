"""Congelamento da calibração da campanha 3 e a trava do plano oficial (PROTOCOLO_C3, 8.1 item 6)."""
import json
import shutil

import pytest
import yaml

from analysis import congelar as cg
from mecade.config import ROOT
from tests.test_calibrate import _c3_runs


@pytest.fixture
def resultado():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs()
    r = calibrate_c3(ctrl + pil, piso_erro=0.01)
    assert r["viavel"]
    return r


@pytest.fixture
def config(tmp_path):
    p = tmp_path / "campaign.yaml"
    shutil.copy(ROOT / "config" / "campaign.yaml", p)
    return p


def test_gravar_copia_o_resultado_e_so_essas_linhas(config, resultado):
    antes = config.read_text(encoding="utf-8")
    cg.gravar(config, resultado)
    depois = config.read_text(encoding="utf-8")
    cfg = yaml.safe_load(depois)
    assert cfg["signals"]["p95"]["floor"] == pytest.approx(resultado["pisos"]["p95"])
    assert cfg["signals"]["p99"]["floor"] == pytest.approx(resultado["pisos"]["p99"])
    assert cfg["signals"]["error_rate"]["floor"] == 0.01
    ax = cfg["axioms"]
    assert (ax["d_on"], ax["d_off"], ax["deadband"]) == (resultado["d_on"], resultado["d_off"], resultado["deadband"])
    assert ax["tau_dwell"] == resultado["tau_dwell"] and ax["budget_B"] == resultado["budget_B"]
    mudadas = [(a, b) for a, b in zip(antes.split("\n"), depois.split("\n")) if a != b]
    assert len(antes.split("\n")) == len(depois.split("\n"))
    assert len(mudadas) <= 8
    for a, b in mudadas:   # comentário da linha preservado
        if "#" in a:
            assert a[a.index("#"):] == b[b.index("#"):]
    assert cg.conferir(cfg, resultado) == []


def test_conferir_acusa_cada_diferenca(config, resultado):
    cg.gravar(config, resultado)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["axioms"]["budget_B"] += 10
    cfg["signals"]["p99"]["floor"] = 0.123
    difs = cg.conferir(cfg, resultado)
    assert len(difs) == 2 and any("budget_B" in d for d in difs) and any("p99" in d for d in difs)


def test_resultado_inviavel_nao_vira_config(config, resultado):
    antes = config.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        cg.gravar(config, {**resultado, "viavel": False})
    assert config.read_text(encoding="utf-8") == antes
    assert cg.conferir(yaml.safe_load(antes), {**resultado, "viavel": False})


def test_editar_valor_sem_comentario_e_chave_ausente():
    t = "a:\n  b: 1\n  c:\n    d: 2.5\ne:\n  d: 9\n"
    assert cg.editar_valor(t, ("a", "c", "d"), 7.0) == "a:\n  b: 1\n  c:\n    d: 7.0\ne:\n  d: 9\n"
    with pytest.raises(KeyError):
        cg.editar_valor(t, ("a", "x"), 1)
    with pytest.raises(KeyError):
        cg.editar_valor(t, ("e", "c", "d"), 1)


def _cfg_da_campanha_2():
    cfg = yaml.safe_load((ROOT / "config" / "campaign.yaml").read_text(encoding="utf-8"))
    cfg["axioms"]["budget_B"] = 47.0
    cfg["signals"]["p95"]["floor"] = cfg["signals"]["p99"]["floor"] = 0.05
    return cfg


def test_trava_recusa_config_com_valores_da_campanha_2():
    cfg = _cfg_da_campanha_2()
    motivos = cg.verificar_trava(cfg)
    assert any("budget_B" in m for m in motivos) and any("p95" in m for m in motivos) and any("p99" in m for m in motivos)


def test_trava_libera_depois_do_congelamento_e_recusa_se_divergir(config, resultado):
    cg.gravar(config, resultado)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert cg.verificar_trava(cfg, resultado) == []
    cfg["axioms"]["budget_B"] = 47.0
    assert cg.verificar_trava(cfg, resultado)            # B da campanha 2
    cfg["axioms"]["budget_B"] = resultado["budget_B"] + 10
    assert any("não confere" in m for m in cg.verificar_trava(cfg, resultado))
    assert cg.verificar_trava(cfg) == []                 # sem resultado guardado, só a regra da campanha 2


def test_cli_gravar_e_conferir_com_resultado_em_arquivo(config, resultado, tmp_path):
    arq = tmp_path / "r.json"
    arq.write_text(json.dumps(resultado), encoding="utf-8")
    assert cg.main(["--conferir", "--config", str(config), "--resultado", str(arq)]) == 1
    assert cg.main(["--gravar", "--config", str(config), "--resultado", str(arq)]) == 0
    assert cg.main(["--conferir", "--config", str(config), "--resultado", str(arq)]) == 0


def test_run_campaign_recusa_o_plano_oficial_com_valores_da_campanha_2(monkeypatch, capsys):
    from orchestrator import run_campaign as rc
    monkeypatch.setattr("sys.argv", ["run_campaign"])
    monkeypatch.setattr(rc, "load_campaign", _cfg_da_campanha_2)
    monkeypatch.setattr(rc, "carregar_resultado", lambda: None)
    with pytest.raises(SystemExit) as e:
        rc.main()
    assert "recusado" in str(e.value) and "budget_B" in str(e.value)

"""Análise de sensibilidade da H2: envelope no limiar do ALERT e RTO contado da injeção."""
import pandas as pd

from analysis.metrics import metrics_table
from analysis.sensibilidade import config_sensibilidade, tabela_sensibilidade
from mecade.config import load_campaign


def _run(run_id, d_agr, eventos=(), mitigacao="none"):
    camp = load_campaign()
    n = len(d_agr)
    df = pd.DataFrame({"t": [5.0 * i for i in range(n)], "D_agr": d_agr, "D_p95": d_agr, "D_p99": d_agr,
                       "D_error_rate": [0.0] * n, "p95": [0.1] * n, "p99": [0.1] * n, "error_rate": [0.0] * n})
    meta = {"run_id": run_id, "scenario": "s", "arm": "mecade", "timing": {**camp["timing"], "fault": 10},
            "axioms": {**camp["axioms"], "d_on": 2.9, "d_off": 2.7, "deadband": 2.7, "tau_dwell": 15,
                       "budget_B": 1e9, "envelope_delta": 1.0},
            "recovery": {**camp["recovery"], "hold": 10}, "events": list(eventos), "rto_s": 30,
            "mitigation": {"acao": mitigacao}}
    return meta, df


def test_pico_curto_acima_do_envelope_antigo_e_aceitavel():
    # D chega a 2,0 por um passo: com envelope_delta = 1,0 saía degradado; abaixo de d_on segue aceitável
    runs = [_run("c", [0.1, 2.0, 0.1, 0.1, 0.1, 0.1])]
    x = tabela_sensibilidade(metrics_table(runs), runs)
    assert x.loc[0, "classe"] == "degradado"
    assert x.loc[0, "classe_env"] == "aceitavel"


def test_degradado_exige_d_on_por_tau_dwell():
    curto = _run("a", [3.0, 3.0, 0.1, 0.1, 0.1, 0.1, 0.1])  # 10 s acima de d_on, menos que 15 s
    longo = _run("b", [3.0, 3.0, 3.0, 0.1, 0.1, 0.1, 0.1])  # 15 s acima
    x = tabela_sensibilidade(metrics_table([curto, longo]), [curto, longo]).set_index("run_id")
    assert x.loc["a", "classe_env"] == "aceitavel"
    assert x.loc["b", "classe_env"] == "degradado"


def test_rto_conta_da_injecao_e_nao_da_deteccao():
    # detecção em 25 s, restauração em 35 s: MTTR = 10 s cabe no RTO de 30 s, o TTR de 35 s não
    run = _run("r", [5.0] * 7 + [0.1] * 6, eventos=[{"t": 25.0, "event": "ALERT"}, {"t": 30.0, "event": "MITIGATION"}],
               mitigacao="restart")
    x = tabela_sensibilidade(metrics_table([run]), [run])
    assert x.loc[0, "TTR"] == 35.0 and x.loc[0, "MTTR"] == 10.0
    assert bool(x.loc[0, "rto_ok"]) is True
    assert x.loc[0, "rto_ok_ttr"] == 0.0


def test_config_troca_so_recuperacao_e_classificacao():
    import yaml
    from pathlib import Path
    cfg = Path(__file__).resolve().parent.parent / "config" / "campaign.yaml"
    orig = yaml.safe_load(cfg.read_text(encoding="utf-8"))["analysis"]["veredito"]
    s = config_sensibilidade(orig)
    assert [c["metrica"] for c in s["criterios"]["recuperacao"]["componentes"]] == ["TTR_capped", "rto_ok_ttr"]
    assert [c["metrica"] for c in s["criterios"]["classificacao"]["componentes"]] == ["classe_pior_env"]
    assert s["criterios"]["convergencia"] == orig["criterios"]["convergencia"]
    assert orig["criterios"]["recuperacao"]["componentes"][0]["metrica"] == "MTTR_capped"  # original intocado

import numpy as np
import pandas as pd

from analysis.calibrate import calibrate

TIMING = {"step": 5}
AX = {"k": 2, "aggregation": "max"}


def _df(D):
    t = np.arange(len(D)) * 5.0
    return pd.DataFrame({"t": t, "D_agr": D, "D_p95": D, "D_p99": D, "D_error_rate": 0.0})


def _m(pair="", scenario="c0_controle", arm="mecade"):
    return {"pair": pair, "scenario": scenario, "arm": arm, "timing": TIMING, "axioms": AX}


def test_regra_da_fase_1():
    ctrl = _df(np.full(240, 0.12))
    s1 = _df(np.r_[np.full(60, 1.5), np.full(180, 0.1)])  # 60 passos antes de 300 s
    r = calibrate([(_m(), ctrl), (_m("s1#01", "s1_x", "baseline"), s1), (_m("s1#01", "s1_x", "mecade"), s1)])
    assert r["d_off"] == r["deadband"] == 0.2  # P99 = 0,12 sobe para 0,2
    assert r["d_on"] == 0.4
    assert r["budget_B"] == 390.0  # (1,5 - 0,2) * 5 * 60; controle não pesa
    assert r["tau_dwell"] == 15 and r["viavel"]


def test_budget_respeita_50_por_cento_nos_controles():
    ctrl = _df(np.r_[np.full(239, 0.1), 3.0])
    s1 = _df(np.full(240, 0.1))
    r = calibrate([(_m(), ctrl), (_m("s1#01", "s1_x", "baseline"), s1)])
    assert r["medido"]["I_max_controles"] * 2 <= r["budget_B"]


def test_alerta_espurio_sobe_o_tau():
    # um trecho de 20 s acima de d_on num controle, raro demais para pesar no P99
    D = np.full(2000, 0.1)
    D[100:104] = 2.0
    s1 = _df(np.full(240, 2.0))
    r = calibrate([(_m(), _df(D)), (_m("s1#01", "s1_x", "baseline"), s1)])
    assert r["medido"]["alertas_espurios_por_tau"][15] == 1
    assert r["tau_dwell"] == 25


def test_sem_solucao_quando_nem_30s_resolve():
    D = np.full(2000, 0.1)
    D[100:120] = 2.0
    r = calibrate([(_m(), _df(D)), (_m("s1#01", "s1_x", "baseline"), _df(np.full(240, 2.0)))])
    assert r["tau_dwell"] is None and not r["viavel"]

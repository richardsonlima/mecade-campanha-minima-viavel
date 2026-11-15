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


def test_modo_protecao_b_so_pela_margem_de_ruido():
    # campanha 2: o piloto de s1 não entra; B = 2 x maior I dos controles
    ctrl = _df(np.r_[np.full(239, 0.1), 3.0])
    s1 = _df(np.r_[np.full(60, 1.5), np.full(180, 0.1)])
    pilotos = [(_m("s1#01", "s1_x", "baseline"), s1), (_m("s1#01", "s1_x", "mecade"), s1)]
    antiga = calibrate([(_m(), ctrl), *pilotos])
    nova = calibrate([(_m(), ctrl), *pilotos], regra_B="margem_ruido")
    I_ctrl = nova["medido"]["I_max_controles"]
    assert nova["budget_B"] == np.ceil(round(2 * I_ctrl * 10, 9)) / 10
    assert nova["budget_B"] < antiga["budget_B"]
    assert nova["regra_B"] == "margem_ruido" and nova["viavel"]


def test_modo_protecao_dispensa_piloto_de_s1():
    ctrl = _df(np.r_[np.full(239, 0.1), 3.0])
    r = calibrate([(_m(), ctrl)], regra_B="margem_ruido")
    assert r["viavel"] and r["budget_B"] > 0


def test_tau_sem_solucao_fica_no_valor_declarado():
    D = np.full(2000, 0.1)
    D[100:110] = 2.0  # 50 s acima de d_on: nenhum tau até 30 s zera o ALERT
    r = calibrate([(_m(), _df(D))], regra_B="margem_ruido", tau_sem_solucao=30)
    assert r["medido"]["alertas_espurios_por_tau"][30] >= 1
    assert r["tau_dwell"] == 30 and r["viavel"]


# campanha 3: pisos da mediana de M_base, LIMIT condicionado ao ALERT e B dos pilotos do braço baseline
def _bruto(p95, p99, err=0.0):
    p95 = np.asarray(p95, dtype=float)
    t = np.arange(len(p95)) * 5.0
    return pd.DataFrame({"t": t, "p95": p95, "p99": np.broadcast_to(p99, p95.shape), "error_rate": err})


def _m3(base, pair="", scenario="c0_controle", arm="mecade", run_id="x"):
    return {"pair": pair, "scenario": scenario, "arm": arm, "timing": TIMING, "axioms": AX, "run_id": run_id,
            "M_base": {"p95": base[0], "p99": base[1], "error_rate": 0.0},
            "reactive": {"for": 300, "response_delay": 120}}


def _c3_runs(pilot_p95=2.0, n_pilotos=2):
    from analysis.calibrate import calibrate_c3  # noqa: F401
    ctrl = [(_m3((b, 2 * b), run_id=f"c{i}"), _bruto(np.full(240, b), 2 * b)) for i, b in enumerate((0.1, 0.2, 0.3))]
    pil = []
    for i in range(n_pilotos):
        p95 = np.r_[np.full(4, 0.2), np.full(236, pilot_p95 + i)]
        pil.append((_m3((0.2, 0.4), f"s1#{i}", "s1_x", "baseline", f"p{i}"), _bruto(p95, p95 * 2)))
    pil.append((_m3((0.2, 0.4), "s1#0", "s1_x", "mecade", "m0"), _bruto(np.full(240, 0.2), 0.4)))
    return ctrl, pil


def test_c3_pisos_e_zona_morta():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs()
    r = calibrate_c3(ctrl + pil, piso_erro=0.01)
    assert r["pisos"] == {"p95": 0.2, "p99": 0.4, "error_rate": 0.01}  # mediana de M_base dos controles
    assert r["deadband"] == r["d_off"] == 0.0 and r["d_on"] == 0.2      # controles sem desvio nenhum
    assert r["limit_gate"] == "alert" and r["medido"]["I_max_controles"] == 0.0


def test_c3_b_vem_do_piloto_mais_brando_30s_depois_do_alert():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs(pilot_p95=2.0)
    r = calibrate_c3(ctrl + pil, piso_erro=0.01)
    p = {x["run_id"]: x for x in r["medido"]["pilotos"]}
    assert set(p) == {"p0", "p1"}                 # o braço MECADE não entra na regra
    assert p["p0"]["t_alert"] == 30.0              # desvio a partir de t = 20 s, 15 s de dwell em passos de 5 s
    # D_agr = (4 - 0,4)/0,4 = 9 no piloto p0; 7 passos de 5 s integrados até t_alert + 30 s
    assert abs(p["p0"]["I"] - 9 * 5 * 7) < 1e-6
    assert r["budget_B"] == 310 and r["viavel"]    # arredondado para baixo na dezena


def test_c3_inviavel_sem_margem_de_ruido():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs()
    # 8 passos (40 s) com p95 e p99 altos: raro demais para o P99, longo demais para o dwell de 30 s
    ruido = _bruto(np.r_[np.full(232, 0.2), np.full(8, 6.0)], 0.4)
    ruido["p99"] = np.r_[np.full(232, 0.4), np.full(8, 12.0)]
    ctrl.append((_m3((0.2, 0.4), run_id="ruidoso"), ruido))
    r = calibrate_c3(ctrl + pil, piso_erro=0.01, tau_sem_solucao=30)
    assert r["tau_dwell"] == 30
    assert r["medido"]["I_max_controles"] > 0
    assert r["budget_B"] < 2 * r["medido"]["I_max_controles"] and not r["viavel"]


def test_c3_inviavel_com_piloto_sem_alert():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs()
    pil.append((_m3((0.2, 0.4), "s2#0", "s2_x", "baseline", "calmo"), _bruto(np.full(240, 0.2), 0.4)))
    r = calibrate_c3(ctrl + pil, piso_erro=0.01)
    assert r["medido"]["pilotos_sem_alert"] == ["calmo"] and not r["viavel"]


def test_c3_inviavel_abaixo_do_minimo_de_controles_ou_pilotos():
    from analysis.calibrate import calibrate_c3
    ctrl, pil = _c3_runs()  # 3 controles e 2 pilotos do braço baseline, viável sem mínimo
    assert calibrate_c3(ctrl + pil, piso_erro=0.01)["viavel"]
    ok = calibrate_c3(ctrl + pil, piso_erro=0.01, min_controles=3, min_pilotos=2)
    assert ok["viavel"] and ok["medido"]["abaixo_do_minimo"] == []
    r = calibrate_c3(ctrl + pil, piso_erro=0.01, min_controles=4, min_pilotos=2)
    assert not r["viavel"] and r["medido"]["abaixo_do_minimo"] == ["3 controles, mínimo 4"]
    r = calibrate_c3(ctrl + pil, piso_erro=0.01, min_controles=3, min_pilotos=3)
    assert not r["viavel"] and r["medido"]["n_pilotos"] == 2  # o piloto do braço MECADE não conta

"""Regra de veredito (D1, 2026-11-12) com dados sintéticos. Nada aqui é evidência da campanha."""
import warnings

import numpy as np
import pandas as pd
import pytest

from analysis.veredito import (adicionar_holm, avaliar_componente, holm, mcnemar_comparison, mcnemar_exato,
                               resolver_limiares, veredito_criterios, veredito_hipoteses)
from mecade.config import ROOT as ROOT_REPO, load_campaign

MENOR = {"metrica": "x", "favoravel": "menor"}
MAIOR = {"metrica": "x", "favoravel": "maior"}


def linha(med, lo, hi, p=0.01):
    return {"median_diff": med, "ci95_low": lo, "ci95_high": hi, "wilcoxon_p": p}


def test_atende_menor_e_maior():
    assert avaliar_componente(linha(-5, -8, -2), MENOR)[0]
    assert avaliar_componente(linha(0.1, 0.05, 0.2), MAIOR)[0]


def test_ic_cruzando_zero_nao_atende():
    ok, motivo = avaliar_componente(linha(-5, -9, 1), MENOR)
    assert not ok and "cruza zero" in motivo
    assert not avaliar_componente(linha(0.1, -0.05, 0.3), MAIOR)[0]


def test_lado_errado_nao_atende():
    assert not avaliar_componente(linha(5, 2, 8), MENOR)[0]
    assert not avaliar_componente(linha(-0.1, -0.2, -0.05), MAIOR)[0]
    assert not avaliar_componente(linha(0, -1, 1), MENOR)[0]


def test_ic_indisponivel_nao_atende():
    assert not avaliar_componente(linha(-5, np.nan, np.nan), MENOR)[0]


def test_limiar_da_mediana():
    comp = {**MENOR, "limiar": -10, "op": "<="}
    assert avaliar_componente(linha(-12, -15, -8), comp)[0]
    ok, motivo = avaliar_componente(linha(-5, -8, -2), comp)
    assert not ok and "limiar" in motivo


def test_componente_limiar_sem_pareamento():
    comp = {"metrica": "taxa", "tipo": "limiar", "op": "<=", "limiar": 0.1}
    assert avaliar_componente({"valor": 0.1}, comp)[0]
    assert not avaliar_componente({"valor": 0.2}, comp)[0]
    assert not avaliar_componente({"valor": np.nan}, comp)[0]


MAPA = {
    "a": {"hipotese": "H1", "componentes": [{"metrica": "ma", "favoravel": "menor"}, {"metrica": "mb", "favoravel": "menor"}]},
    "b": {"hipotese": "H1", "componentes": [{"metrica": "taxa", "tipo": "limiar", "op": "<=", "limiar": 0.1}]},
    "c": {"hipotese": "H2", "componentes": [{"metrica": "mc", "favoravel": "maior"},
                                              {"metrica": "mp", "favoravel": "maior", "pendente": "motivo"}]},
    "d": {"hipotese": "H3", "componentes": [{"metrica": "mc2", "favoravel": "maior"}]},
}


def tab(*rows):
    return pd.DataFrame(rows, columns=["scenario", "metric", "median_diff", "ci95_low", "ci95_high", "wilcoxon_p", "valor"])


BOM_M = (-5, -8, -2, 0.01, np.nan)
RUIM_M = (5, 2, 8, 0.01, np.nan)


def test_hipotese_aceita_com_todos_os_cenarios():
    t = tab(*[(s, k, *BOM_M) for s in ("s1", "s2") for k in ("ma", "mb")], ("controle", "taxa", *[np.nan] * 4, 0.1))
    c = veredito_criterios(t, MAPA)
    assert set(c["status"]) == {"ATENDE"}
    h = veredito_hipoteses(c).set_index("hipotese")
    assert h.loc["H1", "veredito"] == "ACEITA"


def test_hipotese_parcial_relata_por_cenario():
    t = tab(("s1", "ma", *BOM_M), ("s1", "mb", *BOM_M), ("s2", "ma", *BOM_M), ("s2", "mb", *RUIM_M),
            ("controle", "taxa", *[np.nan] * 4, 0.0))
    c = veredito_criterios(t, MAPA)
    por = c[c["criterio"] == "a"].set_index("scenario")["status"].to_dict()
    assert por == {"s1": "ATENDE", "s2": "NAO_ATENDE"}
    assert "mb" in c[(c["criterio"] == "a") & (c["scenario"] == "s2")].iloc[0]["falhas"]
    assert veredito_hipoteses(c).set_index("hipotese").loc["H1", "veredito"] == "PARCIAL"


def test_hipotese_nao_aceita_quando_nenhum_atende():
    t = tab(("s1", "ma", *RUIM_M), ("s1", "mb", *RUIM_M), ("controle", "taxa", *[np.nan] * 4, 0.5))
    h = veredito_hipoteses(veredito_criterios(t, MAPA)).set_index("hipotese")
    assert h.loc["H1", "veredito"] == "NAO_ACEITA"


def test_limiar_nao_cumprido_derruba_criterio_sem_pareamento():
    t = tab(("s1", "ma", *BOM_M), ("s1", "mb", *BOM_M), ("controle", "taxa", *[np.nan] * 4, 0.2))
    c = veredito_criterios(t, MAPA).set_index("criterio")
    assert c.loc["a", "status"] == "ATENDE" and c.loc["b", "status"] == "NAO_ATENDE"
    assert veredito_hipoteses(veredito_criterios(t, MAPA)).set_index("hipotese").loc["H1", "veredito"] == "PARCIAL"


def test_componente_pendente_nao_decide_e_deixa_hipotese_pendente():
    t = tab(("s1", "mc", *[0.2, 0.1, 0.3, 0.01, np.nan]))
    c = veredito_criterios(t, MAPA).set_index("criterio")
    assert c.loc["c", "status"] == "PENDENTE" and c.loc["c", "pendentes"] == "mp"
    assert veredito_hipoteses(c.reset_index()).set_index("hipotese").loc["H2", "veredito"] == "PENDENTE"
    # componente decisiva que falha vence a pendência
    t2 = tab(("s1", "mc", 0.2, -0.1, 0.3, 0.5, np.nan))
    assert veredito_criterios(t2, MAPA).iloc[0]["status"] == "NAO_ATENDE"


def test_hipotese_sem_dados():
    h = veredito_hipoteses(veredito_criterios(tab(("s1", "ma", *BOM_M), ("s1", "mb", *BOM_M)), MAPA)).set_index("hipotese")
    assert h.loc["H3", "veredito"] == "SEM_DADOS"


def test_holm_valores_conhecidos():
    # Exemplo clássico: p = .01, .04, .03, .005 com m = 4
    assert np.allclose(holm([0.01, 0.04, 0.03, 0.005]), [0.03, 0.06, 0.06, 0.02])
    # monótono, trunca em 1 e ignora NaN
    r = holm([0.5, np.nan, 0.6])
    assert np.allclose(r[[0, 2]], [1.0, 1.0]) and np.isnan(r[1])
    assert holm([]).size == 0
    assert holm([0.2])[0] == 0.2


def test_holm_como_analise_secundaria():
    # p = 0.03 e 0.01: sem correção os dois passam em 0.05; Holm com m = 2 dá 0.02 e 0.03, e 0.03 não passa em 0.025
    t = tab(("s1", "ma", *BOM_M[:3], 0.03, np.nan), ("s1", "mb", *BOM_M[:3], 0.01, np.nan),
            ("controle", "taxa", *[np.nan] * 4, 0.0))
    t = adicionar_holm(t, MAPA)
    principal = veredito_criterios(t, MAPA).set_index("criterio")
    assert principal.loc["a", "status"] == "ATENDE"
    sec = veredito_criterios(t, MAPA, alpha_holm=0.025).set_index("criterio")
    assert sec.loc["a", "status"] == "NAO_ATENDE" and "Holm" in sec.loc["a", "falhas"]
    assert veredito_criterios(t, MAPA, alpha_holm=0.05).set_index("criterio").loc["a", "status"] == "ATENDE"


def test_mapa_da_config_cobre_tabela_4_7():
    # campanha 2: a classificação é descritiva e sai do mapa (Tabela 4.7 da v0.9, docs/PROTOCOLO_C2.md)
    cfg = load_campaign()["analysis"]
    mapa = resolver_limiares(cfg["veredito"], cfg)
    assert {s["hipotese"] for s in mapa.values()} == {"H1", "H2", "H3"}
    assert set(mapa) == {"recuperacao", "deteccao_estabilidade", "convergencia", "falsos_bloqueios",
                         "overhead_auditoria"}
    fb = mapa["falsos_bloqueios"]["componentes"][0]
    assert fb["limiar"] == cfg["false_block_max_rate"] == 0.1
    ov = {c["metrica"]: c["limiar"] for c in mapa["overhead_auditoria"]["componentes"]}
    assert ov == {"delta_audit_p95_ms": 5, "delta_cpu_pct": 8}
    for s in mapa.values():
        for c in s["componentes"]:
            assert c.get("tipo") == "limiar" or c["favoravel"] in ("menor", "maior")


def test_cenario_planejado_sem_pares_vira_sem_dados_e_impede_aceita():
    # S1, S2 e S3 planejados; S3 não tem nenhum par válido, então não há linha dele na tabela
    t = tab(*[(s, k, *BOM_M) for s in ("s1", "s2") for k in ("ma", "mb")], ("controle", "taxa", *[np.nan] * 4, 0.0))
    sem = veredito_hipoteses(veredito_criterios(t, MAPA)).set_index("hipotese")
    assert sem.loc["H1", "veredito"] == "ACEITA"                       # sem a lista, o S3 some
    c = veredito_criterios(t, MAPA, cenarios=["s1", "s2", "s3"])
    s3 = c[(c["criterio"] == "a") & (c["scenario"] == "s3")].iloc[0]
    assert s3["status"] == "SEM_DADOS"
    h = veredito_hipoteses(c).set_index("hipotese")
    assert h.loc["H1", "veredito"] == "PARCIAL" and h.loc["H1", "sem_dados"] == 1
    assert "controle" in set(c[c["criterio"] == "b"]["scenario"])      # critério de controle não ganha s1..s3


def test_todos_os_cenarios_sem_dados_nao_vira_aceita():
    t = tab(("controle", "taxa", *[np.nan] * 4, 0.0))
    h = veredito_hipoteses(veredito_criterios(t, MAPA, cenarios=["s1", "s2"])).set_index("hipotese")
    assert h.loc["H1", "veredito"] == "PARCIAL"                         # o controle atende, os cenários faltam
    h2 = veredito_hipoteses(veredito_criterios(tab(), MAPA, cenarios=["s1"])).set_index("hipotese")
    assert h2.loc["H1", "veredito"] == "SEM_DADOS"


def test_hipotese_com_nao_atende_e_pendente_sai_pendente():
    mapa = {"x": {"hipotese": "H2", "componentes": [{"metrica": "ma", "favoravel": "menor"}]},
            "y": {"hipotese": "H2", "componentes": [{"metrica": "mp", "favoravel": "maior", "pendente": "motivo"}]}}
    t = tab(("s1", "ma", *RUIM_M), ("s1", "mp", 0.2, 0.1, 0.3, 0.01, np.nan))
    c = veredito_criterios(t, mapa)
    assert set(c["status"]) == {"NAO_ATENDE", "PENDENTE"}
    assert veredito_hipoteses(c).set_index("hipotese").loc["H2", "veredito"] == "PENDENTE"


def test_cenarios_planejados_do_plano_ou_do_config(tmp_path):
    from analysis.veredito import cenarios_planejados
    plano = tmp_path / "plan.csv"
    plano.write_text("order,run_id,scenario,arm,rep,pair,audit\n1,a,c0_controle,mecade,1,,0\n2,b,s2,baseline,1,s2#1,1\n3,c,s3,mecade,1,s3#1,1\n")
    assert cenarios_planejados(plano, ["s1", "s2", "s3"]) == ["s2", "s3"]      # contingência
    with pytest.warns(UserWarning, match="plano oficial ausente"):
        assert cenarios_planejados(tmp_path / "nao_existe.csv", ["s3", "s1"]) == ["s1", "s3"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # com plano, nenhum aviso
        cenarios_planejados(plano, ["s1"])


def test_estrito_so_liga_com_estrito_igual_a_1():
    import shutil
    import subprocess
    if shutil.which("make") is None:
        pytest.skip("sem make")
    def cmd(valor):
        args = ["make", "-n", "evidencias"] + ([f"ESTRITO={valor}"] if valor is not None else [])
        return subprocess.run(args, capture_output=True, text=True, check=True, cwd=ROOT_REPO).stdout
    assert "--estrito" in cmd("1")
    assert "--estrito" not in cmd("0")
    assert "--estrito" not in cmd(None)


# D5: proporções da H2 por McNemar exato
PROP_MAIOR = {"metrica": "rto_ok", "tipo": "proporcao", "favoravel": "maior"}
PROP_MENOR = {"metrica": "classe_pior", "tipo": "proporcao", "favoravel": "menor"}


def test_mcnemar_exato_valores_conhecidos():
    assert mcnemar_exato(0, 0) == 1.0
    assert mcnemar_exato(3, 3) == pytest.approx(1.0)
    assert mcnemar_exato(5, 0) == pytest.approx(2 * 0.5 ** 5)
    assert mcnemar_exato(0, 5) == pytest.approx(0.0625)
    assert mcnemar_exato(8, 1) == pytest.approx(2 * (1 + 9) / 512)


def _pares(scenario, metric, pares):
    """pares: lista de (mecade, baseline) com indicador 0/1."""
    linhas = []
    for i, (mec, base) in enumerate(pares):
        for arm, v in (("mecade", mec), ("baseline", base)):
            linhas.append({"scenario": scenario, "pair": f"{scenario}#{i}", "arm": arm, metric: float(v)})
    return pd.DataFrame(linhas)


def test_mcnemar_comparison_conta_discordantes():
    m = _pares("s1", "rto_ok", [(1, 0)] * 6 + [(1, 1)] * 2 + [(0, 0)])
    r = mcnemar_comparison(m, "rto_ok").iloc[0]
    assert (r["discordantes_mecade"], r["discordantes_baseline"], r["n_pairs"]) == (6, 0, 9)
    assert r["diff_prop"] == pytest.approx(8 / 9 - 2 / 9)
    assert r["mcnemar_p"] == pytest.approx(2 * 0.5 ** 6)


def test_proporcao_atende_com_diferenca_favoravel_e_p_menor_que_alfa():
    ok = {"diff_prop": 0.5, "mcnemar_p": 0.03}
    assert avaliar_componente(ok, PROP_MAIOR)[0]
    assert avaliar_componente({"diff_prop": -0.5, "mcnemar_p": 0.03}, PROP_MENOR)[0]
    assert not avaliar_componente({"diff_prop": 0.5, "mcnemar_p": 0.05}, PROP_MAIOR)[0]       # p = alfa não passa
    assert not avaliar_componente({"diff_prop": 0.5, "mcnemar_p": 0.2}, PROP_MAIOR)[0]
    assert not avaliar_componente({"diff_prop": -0.5, "mcnemar_p": 0.01}, PROP_MAIOR)[0]      # lado contrário
    assert not avaliar_componente({"diff_prop": 0.0, "mcnemar_p": 1.0}, PROP_MAIOR)[0]
    assert not avaliar_componente({"diff_prop": 0.5, "mcnemar_p": np.nan}, PROP_MAIOR)[0]
    assert not avaliar_componente({"diff_prop": 0.5, "mcnemar_p": 0.03}, PROP_MENOR)[0]       # menor é o favorável


def test_proporcao_entra_na_familia_h2_do_holm():
    mapa = {"r": {"hipotese": "H2", "componentes": [{"metrica": "mc", "favoravel": "maior"}, PROP_MAIOR]}}
    t = pd.DataFrame([{"scenario": "s1", "metric": "mc", "wilcoxon_p": 0.02, "mcnemar_p": np.nan},
                      {"scenario": "s1", "metric": "rto_ok", "wilcoxon_p": np.nan, "mcnemar_p": 0.03}])
    h = adicionar_holm(t, mapa)
    assert h["p_holm"].tolist() == pytest.approx([0.04, 0.04])
    linha_ = {"diff_prop": 0.5, "mcnemar_p": 0.03, "p_holm": 0.04}
    assert avaliar_componente(linha_, PROP_MAIOR, alpha=0.05)[0]
    assert not avaliar_componente({**linha_, "p_holm": 0.06}, PROP_MAIOR, alpha=0.05)[0]


# D6: uma família de Holm por hipótese
def test_holm_uma_familia_por_hipotese():
    mapa = {"a": {"hipotese": "H1", "componentes": [{"metrica": "h1a", "favoravel": "menor"}, {"metrica": "h1b", "favoravel": "menor"}]},
            "b": {"hipotese": "H2", "componentes": [{"metrica": "h2a", "favoravel": "menor"}]}}
    t = pd.DataFrame([{"scenario": "s1", "metric": "h1a", "wilcoxon_p": 0.01},
                      {"scenario": "s1", "metric": "h1b", "wilcoxon_p": 0.04},
                      {"scenario": "s1", "metric": "h2a", "wilcoxon_p": 0.03}])
    h = adicionar_holm(t, mapa).set_index("metric")["p_holm"]
    assert h["h1a"] == pytest.approx(0.02) and h["h1b"] == pytest.approx(0.04)   # m = 2 só dentro da H1
    assert h["h2a"] == pytest.approx(0.03)                                         # família da H2 tem m = 1
    # com família única o h2a sairia 0.06 (m = 3 no passo de p = 0.03 vira 2 * 0.03, monótono com 0.04: 0.06)


# D7: valor igual ao limiar atende (<=)
def test_limiar_igual_atende_nos_tres_limiares_da_config():
    cfg = load_campaign()["analysis"]
    mapa = resolver_limiares(cfg["veredito"], cfg)
    for crit in ("falsos_bloqueios", "overhead_auditoria"):
        for c in mapa[crit]["componentes"]:
            assert c["op"] == "<="
            assert avaliar_componente({"valor": c["limiar"]}, c)[0]
            assert not avaliar_componente({"valor": c["limiar"] * 1.01 + 1e-6}, c)[0]


def test_proporcoes_da_h2_nao_estao_mais_pendentes_na_config():
    cfg = load_campaign()["analysis"]
    mapa = resolver_limiares(cfg["veredito"], cfg)
    comps = {c["metrica"]: c for s in mapa.values() for c in s["componentes"]}
    assert comps["rto_ok_ttr"]["tipo"] == "proporcao" and comps["rto_ok_ttr"]["favoravel"] == "maior"
    assert [c["metrica"] for c in mapa["recuperacao"]["componentes"]] == ["TTR_capped", "rto_ok_ttr"]
    assert "MTTR_capped" not in comps and "classe_pior" not in comps
    assert not any(c.get("pendente") for c in comps.values())

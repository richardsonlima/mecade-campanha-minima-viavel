"""Análise de sensibilidade da H2, exploratória e post hoc (13/11/2026). Não altera a análise principal.

Durante as execuções oficiais encontrei três problemas de medida na H2 e só fechei esta análise depois das
70 réplicas. Por isso ela não é emenda do pré-registro: é exploratória, reportada ao lado da principal, sobre
os mesmos dados brutos (steps.csv e eventos). As mesmas definições são o critério primário da campanha 2:

  rto_ok_ttr   TTR <= RTO, com TTR contado da injeção. O RTO é o prazo para retomar o serviço depois do
               incidente (ISO 22301), então se compara com o tempo desde o início da falha, e não com o MTTR,
               que começa na detecção e premia quem detecta tarde.
  classe_env   classe tripartite com o envelope igual ao limiar calibrado do ALERT: degradado quando D_agr
               fica acima de d_on por tau_dwell segundos seguidos. Com envelope_delta = 1,0, as réplicas de
               controle (sem falha) saíam degradadas. Crítico continua sendo o desvio acumulado acima de B.
  I_rel        desvio acumulado com zona morta dividido por B (gravidade contínua, só descritiva).
  log10_V      log10 de V médio, a mesma grandeza do RRIndex numa escala legível (só descritiva). O RRIndex
               fica como está: é monotônico em V, então o sinal de cada par não muda com a escala.

O critério de recuperação da sensibilidade decide por TTR_capped e rto_ok_ttr; o MTTR segue reportado.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from analysis.metrics import DECISION


def _sustentado(acima: np.ndarray, n: int) -> bool:
    run = 0
    for a in acima:
        run = run + 1 if a else 0
        if run >= n:
            return True
    return False


def metricas_extra(runs) -> pd.DataFrame:
    linhas = []
    for meta, df in runs:
        tm, ax = meta["timing"], meta["axioms"]
        step = float(tm["step"])
        d = df[df["t"] >= 0]
        dag = d["D_agr"].fillna(0).to_numpy()
        n_dwell = max(1, int(round(float(ax.get("tau_dwell", 15)) / step)))
        I_max = float(np.cumsum(np.clip(dag - ax["deadband"], 0, None) * step).max()) if len(dag) else 0.0
        if I_max > ax["budget_B"]:
            classe = "critico"
        elif _sustentado(dag > ax["d_on"], n_dwell):
            classe = "degradado"
        else:
            classe = "aceitavel"
        Dm = d[[f"D_{s}" for s in DECISION if f"D_{s}" in d]].fillna(0)
        V = float((Dm ** 2).mean(axis=1).mean()) if len(Dm) else np.nan
        linhas.append({"run_id": meta["run_id"], "classe_env": classe, "I_rel": I_max / ax["budget_B"],
                       "log10_V": float(np.log10(V)) if V and V > 0 else np.nan})
    return pd.DataFrame(linhas)


def tabela_sensibilidade(m: pd.DataFrame, runs, rto_por_run: dict | None = None) -> pd.DataFrame:
    """`m` é a saída de metrics_table. Devolve `m` com as colunas da sensibilidade."""
    x = m.merge(metricas_extra(runs), on="run_id", how="left")
    rto = rto_por_run or {meta["run_id"]: meta.get("rto_s", np.inf) for meta, _ in runs}
    x["rto_ok_ttr"] = [bool(not pd.isna(t) and t <= rto.get(r, np.inf)) for r, t in zip(x["run_id"], x["TTR"])]
    x["rto_ok_ttr"] = x["rto_ok_ttr"].astype(float)
    x["classe_pior_env"] = (x["classe_env"] != "aceitavel").astype(float)
    return x


def config_sensibilidade(veredito_cfg: dict) -> dict:
    """Mapa de critérios da sensibilidade: troca só recuperação e classificação."""
    c = copy.deepcopy(veredito_cfg)
    c["criterios"]["recuperacao"]["componentes"] = [
        {"metrica": "TTR_capped", "favoravel": "menor"},
        {"metrica": "rto_ok_ttr", "tipo": "proporcao", "favoravel": "maior"},
    ]
    c["criterios"]["classificacao"]["componentes"] = [
        {"metrica": "classe_pior_env", "tipo": "proporcao", "favoravel": "menor"},
    ]
    return c

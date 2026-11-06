"""Regra da Fase 1, já decidida antes dos dados (prompt da campanha, Fase 1, passo 3).

  d_off = deadband = P99 de D_agr nos controles, arredondado para cima com uma casa decimal
  d_on  = d_off + 0,2
  B     = menor valor em que (a) nenhum controle passa de 50% de B e (b) no piloto de s1 o desvio
          acumulado não esgota B antes de 300 s de falha
  tau_dwell = 15 s; sobe de 5 em 5 até 30 s se os controles tiverem ALERT espúrio

Os D_m não dependem dos parâmetros calibrados, então refaço I(t) e o ALERT offline, com o próprio
AxiomEvaluator. Só calcula e mostra: quem grava em config/campaign.yaml é o congelamento.

  python -m analysis.calibrate [data/calibracao/runs]
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

from analysis.metrics import DECISION, load_runs
from mecade.axioms import AxiomEvaluator, AxiomParams
from mecade.config import ROOT

JANELA_B_S = 300.0
TAUS = (15, 20, 25, 30)


def _ceil1(x: float) -> float:
    return math.ceil(round(x * 10, 9)) / 10


def _I(df, deadband: float, step: float, until: float | None = None) -> float:
    d = df[df["t"] >= 0]
    if until is not None:
        d = d[d["t"] < until]
    return float((np.clip(d["D_agr"].fillna(0).to_numpy() - deadband, 0, None) * step).sum())


def _alertas(df, params: AxiomParams, step: float) -> int:
    ev = AxiomEvaluator(params)
    n = 0
    for _, r in df[df["t"] >= 0].iterrows():
        D = {s: (None if np.isnan(r[f"D_{s}"]) else float(r[f"D_{s}"])) for s in DECISION}
        n += ev.step(D, step).count("ALERT")
    return n


def calibrate(runs: list) -> dict:
    ctrl = [(m, df) for m, df in runs if not m.get("pair")]
    s1 = [(m, df) for m, df in runs if m.get("pair") and m["scenario"].startswith("s1_")]
    if not ctrl or not s1:
        raise ValueError(f"Faltam dados: {len(ctrl)} controles e {len(s1)} pilotos de s1.")
    step = float(ctrl[0][0]["timing"]["step"])
    dagr = np.concatenate([df[df["t"] >= 0]["D_agr"].dropna().to_numpy() for _, df in ctrl])
    p99 = float(np.percentile(dagr, 99))
    d_off = deadband = _ceil1(p99)
    d_on = round(d_off + 0.2, 1)

    I_ctrl = max(_I(df, deadband, step) for _, df in ctrl)
    I_s1: dict[str, float] = {}
    for m, df in s1:  # com duas rodadas há mais de um piloto por braço, e vale o maior
        I_s1[m["arm"]] = max(I_s1.get(m["arm"], 0.0), _I(df, deadband, step, JANELA_B_S))
    budget = _ceil1(max(2 * I_ctrl, max(I_s1.values())))

    tau = None
    espurios = {}
    for t in TAUS:
        params = AxiomParams(d_on=d_on, d_off=d_off, tau_dwell=float(t), deadband=deadband, budget_B=budget or 1.0,
                             k=int(ctrl[0][0]["axioms"]["k"]), aggregation=ctrl[0][0]["axioms"]["aggregation"])
        espurios[t] = sum(_alertas(df, params, step) for _, df in ctrl)
        if espurios[t] == 0:
            tau = t
            break

    # B positivo é o que torna a regra satisfazível; sem desvio em s1 ou sem tau válido, paro e pergunto
    viavel = budget > 0 and tau is not None
    return {"viavel": viavel, "d_off": d_off, "deadband": deadband, "d_on": d_on, "budget_B": budget, "tau_dwell": tau,
            "medido": {"p50_D_agr": float(np.percentile(dagr, 50)), "p95_D_agr": float(np.percentile(dagr, 95)),
                       "p99_D_agr": p99, "max_D_agr": float(dagr.max()), "n_amostras": int(len(dagr)),
                       "n_controles": len(ctrl), "I_max_controles": I_ctrl, "I_s1_antes_300s": I_s1,
                       "alertas_espurios_por_tau": espurios}}


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "calibracao" / "runs"
    r = calibrate(load_runs(root, include_sim=True))
    print(json.dumps(r, indent=2, ensure_ascii=False))
    if not r["viavel"]:
        print("A regra não tem solução com estes dados. Paro e registro os números e decido.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

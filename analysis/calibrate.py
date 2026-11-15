"""Regra da Fase 1, já decidida antes dos dados (prompt da campanha, Fase 1, passo 3).

  d_off = deadband = P99 de D_agr nos controles, arredondado para cima com uma casa decimal
  d_on  = d_off + 0,2
  B     = menor valor em que (a) nenhum controle passa de 50% de B e (b) no piloto de s1 o desvio
          acumulado não esgota B antes de 300 s de falha
  tau_dwell = 15 s; sobe de 5 em 5 até 30 s se os controles tiverem ALERT espúrio

Campanha 2 (`calibracao.regra_B: margem_ruido` no config, pré-registro em docs/PROTOCOLO_C2.md): B só pela
condição (a), B = 2 x maior I dos controles; sem a condição (b). Se nenhum tau até 30 s zerar o ALERT
espúrio, tau_dwell = 30 s e a contagem fica registrada (`calibracao.tau_sem_solucao: 30`).

Campanha 3 (`calibracao.regra_B: alerta_piloto`, pré-registro em docs/PROTOCOLO_C3.md, Seção 4): ver
calibrate_c3(). Os pisos de latência saem da mediana de M_base dos controles, o LIMIT só integra com ALERT
ativo (D3 em mecade/axioms.py) e B sai dos pilotos de falha do braço baseline, com a margem de ruído como
condição de viabilidade.

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
from mecade.config import ROOT, load_campaign

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


def calibrate(runs: list, regra_B: str = "margem_ruido_e_piloto", tau_sem_solucao: float | None = None) -> dict:
    ctrl = [(m, df) for m, df in runs if not m.get("pair")]
    s1 = [(m, df) for m, df in runs if m.get("pair") and m["scenario"].startswith("s1_")]
    if regra_B not in ("margem_ruido_e_piloto", "margem_ruido"):
        raise ValueError(f"regra_B desconhecida: {regra_B}")
    if not ctrl or (regra_B == "margem_ruido_e_piloto" and not s1):
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
    if regra_B == "margem_ruido":  # campanha 2: o piloto de s1 não entra na regra
        budget = _ceil1(2 * I_ctrl)
    else:
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
    if tau is None and tau_sem_solucao is not None:
        tau = int(tau_sem_solucao)

    # B positivo é o que torna a regra satisfazível; sem desvio em s1 ou sem tau válido, paro e pergunto
    viavel = budget > 0 and tau is not None
    return {"viavel": viavel, "regra_B": regra_B, "d_off": d_off, "deadband": deadband, "d_on": d_on, "budget_B": budget, "tau_dwell": tau,
            "medido": {"p50_D_agr": float(np.percentile(dagr, 50)), "p95_D_agr": float(np.percentile(dagr, 95)),
                       "p99_D_agr": p99, "max_D_agr": float(dagr.max()), "n_amostras": int(len(dagr)),
                       "n_controles": len(ctrl), "I_max_controles": I_ctrl, "I_s1_antes_300s": I_s1,
                       "alertas_espurios_por_tau": espurios}}


SINAIS_LATENCIA = ("p95", "p99")
POS_ALERT_S = 30.0       # campanha 3: B é o desvio acumulado até 30 s depois do ALERT no piloto mais brando
MARGEM_RUIDO = 2.0       # campanha 3: B precisa ser pelo menos 2 x o maior I condicionado dos controles


def _floor10(x: float) -> float:
    return math.floor(x / 10) * 10


def _recalcula_D(meta: dict, df, pisos: dict[str, float]):
    """D_m com os pisos novos, a partir das medidas brutas e do M_base gravados na réplica."""
    base = meta["M_base"]
    d = df[df["t"] >= 0].copy()
    for s in DECISION:
        b = base.get(s)
        d[f"D_{s}"] = (d[s] - b).abs() / max(b, pisos[s]) if b is not None else np.nan
    d["D_agr"] = d[[f"D_{s}" for s in DECISION]].max(axis=1, skipna=True)
    return d


def _trilha(d, params: AxiomParams, step: float):
    """I(t) condicionado ao ALERT e o instante do primeiro ALERT, com o próprio AxiomEvaluator."""
    ev = AxiomEvaluator(params)
    t_alert, I = None, []
    for _, r in d.iterrows():
        D = {s: (None if np.isnan(r[f"D_{s}"]) else float(r[f"D_{s}"])) for s in DECISION}
        if "ALERT" in ev.step(D, step) and t_alert is None:
            t_alert = float(r["t"])
        I.append((float(r["t"]), ev.I))
    return t_alert, I


def calibrate_c3(runs: list, piso_erro: float, tau_sem_solucao: float | None = None,
                 limite_piloto_s: float | None = None) -> dict:
    """Regra da Fase 1 da campanha 3 (docs/PROTOCOLO_C3.md, Seção 4), fixada antes dos dados.

      pisos   p95 e p99: mediana de M_base nos controles; error_rate: o piso do config
      d_off = deadband = P99 de D_agr nos controles (com os pisos novos), para cima na primeira casa
      d_on  = d_off + 0,2; tau_dwell como nas campanhas 1 e 2
      B     = menor I condicionado ao ALERT, 30 s depois do primeiro ALERT, entre os pilotos do braço
              baseline, arredondado para baixo na dezena
      viável se B >= 2 x maior I condicionado dos controles e todo piloto tem ALERT antes de limite_piloto_s
    """
    ctrl = [(m, df) for m, df in runs if not m.get("pair")]
    pil = [(m, df) for m, df in runs if m.get("pair") and m["arm"] == "baseline"]
    if not ctrl or not pil:
        raise ValueError(f"Faltam dados: {len(ctrl)} controles e {len(pil)} pilotos do braço baseline.")
    step = float(ctrl[0][0]["timing"]["step"])
    k, agg = int(ctrl[0][0]["axioms"]["k"]), ctrl[0][0]["axioms"]["aggregation"]
    pisos = {s: float(np.median([m["M_base"][s] for m, _ in ctrl])) for s in SINAIS_LATENCIA}
    pisos["error_rate"] = float(piso_erro)
    if limite_piloto_s is None:
        rc = ctrl[0][0].get("reactive") or {}
        limite_piloto_s = float(rc.get("for", 300)) + float(rc.get("response_delay", 120)) - step

    dc = [_recalcula_D(m, df, pisos) for m, df in ctrl]
    dagr = np.concatenate([d["D_agr"].dropna().to_numpy() for d in dc])
    p99 = float(np.percentile(dagr, 99))
    d_off = deadband = _ceil1(p99)
    d_on = round(d_off + 0.2, 1)

    def par(tau):
        return AxiomParams(k=k, aggregation=agg, d_on=d_on, d_off=d_off, deadband=deadband, tau_dwell=float(tau),
                           budget_B=1e18, limit_gate="alert")

    tau, espurios = None, {}
    for t in TAUS:
        espurios[t] = sum(_alertas(d, par(t), step) for d in dc)
        if espurios[t] == 0:
            tau = t
            break
    if tau is None and tau_sem_solucao is not None:
        tau = int(tau_sem_solucao)

    I_ctrl = [(_trilha(d, par(tau or TAUS[-1]), step)[1] or [(0, 0.0)])[-1][1] for d in dc]
    por_piloto, sem_alert = [], []
    for m, df in pil:
        d = _recalcula_D(m, df, pisos)
        t_alert, I = _trilha(d[d["t"] < limite_piloto_s], par(tau or TAUS[-1]), step)
        if t_alert is None:
            sem_alert.append(m.get("run_id", m["scenario"]))
            continue
        I_alvo = max((i for t, i in I if t <= t_alert + POS_ALERT_S), default=0.0)
        por_piloto.append({"run_id": m.get("run_id"), "scenario": m["scenario"], "t_alert": t_alert, "I": I_alvo})
    budget = _floor10(min(p["I"] for p in por_piloto)) if por_piloto else 0.0

    viavel = (tau is not None and budget > 0 and not sem_alert and budget >= MARGEM_RUIDO * max(I_ctrl))
    return {"viavel": viavel, "regra_B": "alerta_piloto", "pisos": pisos, "d_off": d_off, "deadband": deadband,
            "d_on": d_on, "budget_B": budget, "tau_dwell": tau, "limit_gate": "alert",
            "medido": {"p50_D_agr": float(np.percentile(dagr, 50)), "p99_D_agr": p99, "max_D_agr": float(dagr.max()),
                       "n_amostras": int(len(dagr)), "n_controles": len(ctrl), "I_controles": I_ctrl,
                       "I_max_controles": max(I_ctrl), "pilotos": por_piloto, "pilotos_sem_alert": sem_alert,
                       "limite_piloto_s": limite_piloto_s, "alertas_espurios_por_tau": espurios}}


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "calibracao" / "runs"
    camp = load_campaign()
    cal = camp.get("calibracao") or {}
    if cal.get("regra_B") == "alerta_piloto":
        r = calibrate_c3(load_runs(root, include_sim=True), piso_erro=float(camp["signals"]["error_rate"]["floor"]),
                         tau_sem_solucao=cal.get("tau_sem_solucao"))
    else:
        r = calibrate(load_runs(root, include_sim=True), regra_B=cal.get("regra_B", "margem_ruido_e_piloto"),
                      tau_sem_solucao=cal.get("tau_sem_solucao"))
    print(json.dumps(r, indent=2, ensure_ascii=False))
    if not r["viavel"]:
        print("A regra não tem solução com estes dados. Paro e registro os números e decido.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

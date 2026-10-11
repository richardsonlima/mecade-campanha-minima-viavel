"""Métricas por réplica e comparações pareadas da Campanha Mínima Viável.

As definições batem com a Seção 4 de docs/PROTOCOLO.md. Todos os tempos contam a partir da injeção (t = 0).

  TTD          tempo até a detecção: primeiro ALERT (mecade) ou disparo da regra reativa (baseline)
  TTM          tempo até a mitigação (BLOCK ou runbook)
  TTR          tempo até o estado estacionário voltar, contado da injeção: primeiro instante em
               que D_agr <= d_off por `hold` segundos, procurado depois da mitigação (ou depois do
               fim do incidente, quando não houve mitigação)
  MTTR         TTR - TTD, só quando houve detecção (da detecção até a restauração)
  area         degradação acumulada, soma de D_agr * dt de t = 0 até o fim da janela
  TSR_fault    1 menos a taxa média de erro durante o incidente
  classe       crítico (desvio acumulado com zona morta > B), degradado (max D_agr > envelope) ou aceitável
  RRIndex_run  1 / (1 + V̄), com V(t) igual à média dos D_m(t)^2 no incidente e na recuperação (Seção 3.4.2)
  eta_t_proxy  P99 do baseline dividido pelo P99 médio no incidente (aproximação, ver PROTOCOLO D6)
  eta_I_proxy  (vazão/CPU) no incidente dividido por (vazão/CPU) no baseline (aproximação, ver PROTOCOLO D6)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

DECISION = ["p95", "p99", "error_rate"]


def load_runs(root: str | Path, include_sim: bool = False) -> list[tuple[dict, pd.DataFrame]]:
    runs = []
    for meta_path in sorted(Path(root).glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("status") != "complete" or (meta.get("backend") == "sim" and not include_sim):
            continue
        df = pd.read_csv(meta_path.parent / "steps.csv")
        runs.append((meta, df))
    return runs


def _first(events: list[dict], *names: str) -> float | None:
    ts = [e["t"] for e in events if e["event"] in names]
    return min(ts) if ts else None


def run_metrics(meta: dict, df: pd.DataFrame) -> dict:
    tm, ax, rec = meta["timing"], meta["axioms"], meta["recovery"]
    step, fault, hold = float(tm["step"]), float(tm["fault"]), float(rec["hold"])
    d = df[df["t"] >= 0].copy()
    ev = meta["events"]
    t_det = _first(ev, "ALERT") if meta["arm"] == "mecade" else _first(ev, "REACTIVE_FIRE")
    t_mit = _first(ev, "MITIGATION")
    t_block = _first(ev, "BLOCK")

    # quando o estado estacionário volta
    search_from = t_mit if t_mit is not None else fault
    ok = (d["D_agr"] <= ax["d_off"]).to_numpy()
    tt = d["t"].to_numpy()
    need = int(round(hold / step))
    t_rec = None
    run = 0
    for i in range(len(tt)):
        if tt[i] < search_from:
            run = 0
            continue
        run = run + 1 if ok[i] else 0
        if run >= need:
            t_rec = float(tt[i - need + 1])
            break
    window_end = float(tt[-1]) if len(tt) else fault

    # classificação offline, com a mesma regra nos dois braços
    excess = np.clip(d["D_agr"].fillna(0).to_numpy() - ax["deadband"], 0, None) * step
    I_max = float(np.cumsum(excess).max()) if len(excess) else 0.0
    max_D = float(d["D_agr"].max()) if len(d) else 0.0
    if I_max > ax["budget_B"]:
        classe = "critico"
    elif max_D > ax.get("envelope_delta", 1.0):
        classe = "degradado"
    else:
        classe = "aceitavel"

    fw = d[d["t"] < fault]
    Dm = d[[f"D_{s}" for s in DECISION if f"D_{s}" in d]].fillna(0)
    V = (Dm ** 2).mean(axis=1)
    base = meta.get("M_base") or {}
    base_df = df[df["t"] < 0]

    def ratio(a, b):
        return float(a) / float(b) if a is not None and b not in (None, 0) and not pd.isna(b) else np.nan

    thr_cpu_fault = ratio(fw.get("aux_throughput", pd.Series(dtype=float)).mean(), fw.get("aux_cpu_boutique", pd.Series(dtype=float)).mean())
    thr_cpu_base = ratio(base_df.get("aux_throughput", pd.Series(dtype=float)).mean(), base_df.get("aux_cpu_boutique", pd.Series(dtype=float)).mean())
    mttr = (t_rec - t_det) if (t_rec is not None and t_det is not None) else np.nan
    return {
        "run_id": meta["run_id"], "scenario": meta["scenario"], "arm": meta["arm"], "pair": meta.get("pair", ""),
        "backend": meta.get("backend"), "audit": meta.get("audit_planned", 1),
        "detected": t_det is not None, "TTD": t_det if t_det is not None else np.nan,
        "TTM": t_mit if t_mit is not None else np.nan,
        "TTR": t_rec if t_rec is not None else np.nan, "TTR_censored": t_rec is None,
        "TTR_capped": t_rec if t_rec is not None else window_end,
        "MTTR": mttr, "rto_ok": bool(not pd.isna(mttr) and mttr <= meta.get("rto_s", np.inf)),
        "area": float((d["D_agr"].fillna(0) * step).sum()),
        "TSR_fault": float(1 - fw["error_rate"].mean()) if len(fw) else np.nan,
        "p99_fault": float(fw["p99"].mean()) if len(fw) else np.nan,
        "classe": classe, "block": t_block is not None, "I_max": I_max, "max_D": max_D,
        "RRIndex_run": float(1 / (1 + V.mean())) if len(V) else np.nan,
        "eta_t_proxy": ratio(base.get("p99"), fw["p99"].mean() if len(fw) else None),
        "eta_I_proxy": ratio(thr_cpu_fault, thr_cpu_base),
        "audit_p95_ms": (meta.get("audit") or {}).get("enqueue_p95_ms"),
        "controller_cpu_s": meta.get("controller_cpu_s"),
    }


def metrics_table(runs) -> pd.DataFrame:
    return pd.DataFrame([run_metrics(m, df) for m, df in runs])


def cliffs_delta(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) == 0 or len(y) == 0:
        return np.nan
    gt = sum((xi > y).sum() for xi in x)
    lt = sum((xi < y).sum() for xi in x)
    return float((gt - lt) / (len(x) * len(y)))


def bootstrap_ci(diffs, n_boot: int = 5000, seed: int = 20261011, alpha: float = 0.05):
    diffs = np.asarray(diffs, float)
    diffs = diffs[~np.isnan(diffs)]
    if len(diffs) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(diffs, size=(n_boot, len(diffs)), replace=True), axis=1)
    return (float(np.quantile(meds, alpha / 2)), float(np.quantile(meds, 1 - alpha / 2)))


def paired_comparison(m: pd.DataFrame, metric: str) -> pd.DataFrame:
    """MECADE contra baseline, pareado por (cenário, réplica). A diferença é mecade menos baseline."""
    out = []
    main = m[m["pair"].astype(str) != ""]
    for sc, g in main.groupby("scenario"):
        w = g.pivot_table(index="pair", columns="arm", values=metric, aggfunc="first").dropna()
        if not {"baseline", "mecade"} <= set(w.columns) or len(w) == 0:
            continue
        diff = w["mecade"] - w["baseline"]
        try:
            p = stats.wilcoxon(w["mecade"], w["baseline"], zero_method="zsplit").pvalue if len(w) >= 2 else np.nan
        except ValueError:
            p = np.nan
        lo, hi = bootstrap_ci(diff)
        out.append({"scenario": sc, "metric": metric, "n_pairs": len(w),
                    "median_baseline": float(w["baseline"].median()), "median_mecade": float(w["mecade"].median()),
                    "median_diff": float(diff.median()), "ci95_low": lo, "ci95_high": hi,
                    "wilcoxon_p": float(p), "cliffs_delta": cliffs_delta(w["mecade"], w["baseline"])})
    return pd.DataFrame(out)

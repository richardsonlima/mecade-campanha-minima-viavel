"""Métricas por réplica e comparações pareadas da Campanha Mínima Viável.

As definições batem com a Seção 4 de docs/PROTOCOLO.md. Todos os tempos contam a partir da injeção (t = 0).

  TTD          tempo até a detecção: primeiro ALERT (mecade) ou disparo da regra reativa (baseline)
  TTM          tempo até a mitigação (BLOCK ou runbook)
  TTR          tempo até o estado estacionário voltar, contado da injeção: primeiro instante em
               que D_agr <= d_off por `hold` segundos, procurado depois da mitigação (ou depois do
               fim do incidente, quando não houve mitigação)
  MTTR         TTR - TTD, só quando houve detecção (da detecção até a restauração)
  area_incidente  desvio acumulado durante o incidente, soma de D_agr * dt em 0 <= t < fault (v0.8, Seção 4.4.1)
  area         o mesmo até o fim da janela, incluindo a recuperação (só descritiva)
  p95_std, p99_std  desvio-padrão de P95 e P99 durante o incidente (variabilidade da Tabela 4.6)
  censurada    réplica com falha injetada sem detecção ou sem restauração; entra na comparação com o fim
               da janela como valor conservador (TTD_capped, TTR_capped, MTTR_capped)
  TSR_fault    1 menos a taxa média de erro durante o incidente
  classe       crítico (desvio acumulado com zona morta > B), degradado (max D_agr > envelope) ou aceitável
  RRIndex_run  1 / (1 + V̄), com V(t) igual à média dos D_m(t)^2 no incidente e na recuperação (Seção 3.4.2)

η_I e η_t ficam fora da campanha (decisão D6 da v0.8): exigem demanda escalonada, e a carga aqui é fixa.
"""
from __future__ import annotations

import json
import warnings
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


def _motivo_exclusao(meta: dict, campaign_id: str) -> str | None:
    if meta.get("status") != "complete":
        return f"status={meta.get('status')!r}"
    if meta.get("backend") == "sim" or meta.get("plano") == "sim":
        return "simulação"
    if meta.get("plano") == "calibracao" or meta.get("etapa") == "calibracao":
        return "calibração"
    if "campaign_id" not in meta:
        return "sem campaign_id (réplica antiga)"
    if meta["campaign_id"] != campaign_id:
        return f"campaign_id={meta['campaign_id']!r}, esperado {campaign_id!r}"
    if meta.get("plano") not in (None, "oficial"):
        return f"plano={meta.get('plano')!r}"
    return None


def _campaign_id_oficial(campaign_id: str | None, config_path: str | Path | None) -> str:
    if campaign_id is None:
        import yaml
        cfg = Path(config_path) if config_path else Path(__file__).resolve().parent.parent / "config" / "campaign.yaml"
        campaign_id = yaml.safe_load(cfg.read_text(encoding="utf-8"))["campaign_id"]
    return campaign_id


def load_official_runs(root: str | Path, campaign_id: str | None = None,
                       config_path: str | Path | None = None) -> tuple[list[tuple[dict, pd.DataFrame]], list[dict]]:
    """Réplicas aceitas na análise oficial e a lista das excluídas, cada uma com o motivo. Aceito só `complete`
    com `campaign_id` igual ao do config, fora de simulação e calibração. Réplica sem `campaign_id` sai com aviso.
    Não mexo em `load_runs`, que o orquestrador usa com include_sim=True."""
    campaign_id = _campaign_id_oficial(campaign_id, config_path)
    runs, excluidas = [], []
    for meta_path in sorted(Path(root).glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        motivo = _motivo_exclusao(meta, campaign_id)
        if motivo:
            excluidas.append({"run_id": meta.get("run_id", meta_path.parent.name), "motivo": motivo})
            if motivo.startswith("sem campaign_id"):
                warnings.warn(f"{meta_path.parent.name}: sem campaign_id, excluída da análise oficial", stacklevel=2)
            continue
        runs.append((meta, pd.read_csv(meta_path.parent / "steps.csv")))
    return runs, excluidas


def execution_failures(root: str | Path, campaign_id: str | None = None, config_path: str | Path | None = None) -> list[dict]:
    """Réplicas oficiais que falharam 3 vezes na execução. Não têm dados; o par delas sai da comparação pareada.
    Filtra pelo `campaign_id` oficial como `load_official_runs`: falha de outra campanha, de calibração ou de
    simulação não entra. O meta de falha traz `campaign_id` desde 2026-11-12; sem ele, a falha fica de fora."""
    campaign_id = _campaign_id_oficial(campaign_id, config_path)
    out = []
    for meta_path in sorted(Path(root).glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("status") != "falha_execucao":
            continue
        if meta.get("campaign_id") != campaign_id or meta.get("backend") == "sim" or meta.get("plano") in ("sim", "calibracao") \
                or str(meta.get("run_id", "")).startswith("cal"):
            continue
        out.append(meta)
    return out


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
    mttr = (t_rec - t_det) if (t_rec is not None and t_det is not None) else np.nan
    com_falha = (meta.get("mitigation") or {}).get("acao", "none") != "none"
    ttr_capped = t_rec if t_rec is not None else window_end
    ttd_capped = t_det if t_det is not None else window_end
    return {
        "run_id": meta["run_id"], "scenario": meta["scenario"], "arm": meta["arm"], "pair": meta.get("pair", ""),
        "backend": meta.get("backend"), "audit": meta.get("audit_planned", 1),
        "detected": t_det is not None, "TTD": t_det if t_det is not None else np.nan,
        "TTM": t_mit if t_mit is not None else np.nan,
        "TTR": t_rec if t_rec is not None else np.nan, "TTR_censored": t_rec is None,
        "TTR_capped": ttr_capped,
        "TTD_capped": ttd_capped, "MTTR_capped": ttr_capped - ttd_capped if t_det is not None else window_end,
        "censurada": bool(com_falha and (t_det is None or t_rec is None)),
        "MTTR": mttr, "rto_ok": bool(not pd.isna(mttr) and mttr <= meta.get("rto_s", np.inf)),
        "area": float((d["D_agr"].fillna(0) * step).sum()),
        "area_incidente": float((fw["D_agr"].fillna(0) * step).sum()),
        "p95_std": float(fw["p95"].std()) if len(fw) else np.nan,
        "p99_std": float(fw["p99"].std()) if len(fw) else np.nan,
        "TSR_fault": float(1 - fw["error_rate"].mean()) if len(fw) else np.nan,
        "p99_fault": float(fw["p99"].mean()) if len(fw) else np.nan,
        "classe": classe, "block": t_block is not None, "I_max": I_max, "max_D": max_D,
        "RRIndex_run": float(1 / (1 + V.mean())) if len(V) else np.nan,
        "audit_p95_ms": (meta.get("audit") or {}).get("enqueue_p95_ms"),
        "controller_cpu_s": meta.get("controller_cpu_s"),
    }


def false_block_verdict(m: pd.DataFrame, max_rate: float) -> dict:
    """H1, falsos bloqueios: BLOCK nos controles contra o limiar `analysis.false_block_max_rate` de config/campaign.yaml
    (1/10, decisão de 2026-11-11). Passa quando a taxa não excede o limiar."""
    ctrl = m[m["pair"].astype(str) == ""]
    n, blocks = len(ctrl), int(ctrl["block"].sum()) if len(ctrl) else 0
    return {"controles": n, "blocks": blocks, "taxa": blocks / n if n else float("nan"),
            "limiar": max_rate, "aceito": bool(n and blocks <= max_rate * n + 1e-9)}


def audit_overhead(m: pd.DataFrame) -> dict:
    """Tabela 4.6, H3: Δ_audit,p95 e Δcpu nos controles, com a auditoria ligada contra desligada."""
    ctrl = m[m["pair"].astype(str) == ""]
    on, off = ctrl[ctrl["audit"] == 1], ctrl[ctrl["audit"] == 0]
    p95 = on["audit_p95_ms"].dropna()
    cpu_on, cpu_off = on["controller_cpu_s"].median(), off["controller_cpu_s"].median()
    dcpu = float((cpu_on - cpu_off) / cpu_off * 100) if cpu_off and not pd.isna(cpu_off) else np.nan
    return {"n_on": len(on), "n_off": len(off), "delta_audit_p95_ms": float(p95.max()) if len(p95) else np.nan,
            "delta_cpu_pct": dcpu}


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

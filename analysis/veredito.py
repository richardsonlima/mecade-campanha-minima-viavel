"""Veredito da Campanha Mínima Viável (minha decisão D1, 2026-11-12; docs/PROTOCOLO.md Seção 4).

Entrada: tabela longa de diferenças pareadas, uma linha por (cenário, métrica), com as colunas de
`analysis.metrics.paired_comparison` (`median_diff`, `ci95_low`, `ci95_high`, `wilcoxon_p`). Critério sem
diferença pareada entra como linha com `valor` (e sem `median_diff`), e o cenário é `controle`.

Regras:
  componente   ATENDE quando a mediana está do lado favorável, o IC 95% não cruza zero e o limiar (se houver)
               é cumprido pela mediana. Componente `tipo: limiar` compara `valor` com o limiar.
  critério     por cenário: ATENDE se todas as componentes decisivas atendem; NAO_ATENDE se alguma falha;
               PENDENTE se nenhuma falha mas há componente marcada `pendente` no mapa.
  hipótese     ACEITA (tudo atende), PARCIAL (algumas atendem, outras não), NAO_ACEITA (nenhuma atende) e
               PENDENTE (há PENDENTE e o resultado ainda poderia mudar). SEM_DADOS se não há linha nenhuma.
  Holm         análise secundária: exige também p ajustado < alpha nas componentes pareadas.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.metrics import audit_overhead, false_block_verdict, paired_comparison

CONTROLE = "controle"
_OPS = {"<=": lambda a, b: a <= b + 1e-9, "<": lambda a, b: a < b, ">=": lambda a, b: a >= b - 1e-9, ">": lambda a, b: a > b}


def holm(pvalues) -> np.ndarray:
    """p-valores ajustados por Holm-Bonferroni (step-down, monótonos, truncados em 1). NaN fica NaN e não conta em m."""
    p = np.asarray(pvalues, float)
    out = np.full(p.shape, np.nan)
    idx = np.flatnonzero(~np.isnan(p))
    m = len(idx)
    if m == 0:
        return out
    ordem = idx[np.argsort(p[idx], kind="stable")]
    corrente = 0.0
    for rank, i in enumerate(ordem):
        corrente = max(corrente, (m - rank) * p[i])
        out[i] = min(1.0, corrente)
    return out


def _ausente(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def avaliar_componente(linha: dict, comp: dict, alpha: float | None = None) -> tuple[bool, str]:
    """(atende, motivo) de uma componente numa linha da tabela. `alpha` liga o Holm: exige `p_holm` < alpha."""
    if comp.get("tipo") == "limiar":
        v = linha.get("valor")
        if _ausente(v):
            return False, "sem dado"
        ok = _OPS[comp["op"]](float(v), float(comp["limiar"]))
        return ok, f"valor {float(v):.4g} {comp['op']} {comp['limiar']}" if ok else f"valor {float(v):.4g} não cumpre {comp['op']} {comp['limiar']}"
    med, lo, hi = linha.get("median_diff"), linha.get("ci95_low"), linha.get("ci95_high")
    if any(_ausente(x) for x in (med, lo, hi)):
        return False, "sem diferença pareada ou IC indisponível"
    sinal = -1 if comp["favoravel"] == "menor" else 1
    if sinal * med <= 0:
        return False, "mediana do lado contrário ou nula"
    if (lo <= 0 <= hi):
        return False, "IC 95% cruza zero"
    if sinal * (hi if sinal < 0 else lo) <= 0:  # defesa: IC inteiro tem de estar do lado favorável
        return False, "IC 95% fora do lado favorável"
    if "limiar" in comp and not _OPS[comp.get("op", "<=")](float(med), float(comp["limiar"])):
        return False, f"limiar {comp['limiar']} não cumprido pela mediana"
    if alpha is not None:
        p = linha.get("p_holm")
        if _ausente(p) or p >= alpha:
            return False, "p ajustado por Holm não passa"
    return True, "atende"


def veredito_criterios(tabela: pd.DataFrame, mapa: dict, alpha_holm: float | None = None) -> pd.DataFrame:
    """Uma linha por (critério, cenário): `status` ATENDE, NAO_ATENDE ou PENDENTE e o motivo por componente.
    `mapa` é `analysis.veredito.criterios`. Só entram os cenários que aparecem na tabela para alguma componente do critério."""
    linhas = []
    for crit, spec in mapa.items():
        comps = spec["componentes"]
        sub = tabela[tabela["metric"].isin([c["metrica"] for c in comps])]
        for sc in sorted(sub["scenario"].unique()):
            falhas, pend, ok_n = [], [], 0
            for c in comps:
                if c.get("pendente"):
                    pend.append(c["metrica"])
                    continue
                rows = sub[(sub["scenario"] == sc) & (sub["metric"] == c["metrica"])]
                if rows.empty:
                    falhas.append(f"{c['metrica']}: sem linha")
                    continue
                ok, motivo = avaliar_componente(rows.iloc[0].to_dict(), c, alpha_holm)
                if ok:
                    ok_n += 1
                else:
                    falhas.append(f"{c['metrica']}: {motivo}")
            if falhas:
                status = "NAO_ATENDE"
            elif pend or ok_n == 0:
                status = "PENDENTE"
            else:
                status = "ATENDE"
            linhas.append({"hipotese": spec["hipotese"], "criterio": crit, "scenario": sc, "status": status,
                           "falhas": "; ".join(falhas), "pendentes": ", ".join(pend)})
    return pd.DataFrame(linhas, columns=["hipotese", "criterio", "scenario", "status", "falhas", "pendentes"])


def veredito_hipoteses(crit: pd.DataFrame, hipoteses=("H1", "H2", "H3")) -> pd.DataFrame:
    """H1 a H3 a partir do veredito por critério e cenário."""
    out = []
    for h in hipoteses:
        g = crit[crit["hipotese"] == h] if len(crit) else crit
        n_ok, n_no, n_pe = (int((g["status"] == s).sum()) for s in ("ATENDE", "NAO_ATENDE", "PENDENTE")) if len(g) else (0, 0, 0)
        if len(g) == 0:
            v = "SEM_DADOS"
        elif n_no == 0 and n_pe == 0:
            v = "ACEITA"
        elif n_ok > 0 and n_no > 0:
            v = "PARCIAL"
        elif n_pe > 0:
            v = "PENDENTE"
        elif n_ok == 0:
            v = "NAO_ACEITA"
        else:  # pragma: no cover
            v = "PARCIAL"
        det = "; ".join(f"{r.criterio}/{r.scenario}={r.status}" for r in g.itertuples())
        out.append({"hipotese": h, "veredito": v, "atende": n_ok, "nao_atende": n_no, "pendente": n_pe, "detalhe": det})
    return pd.DataFrame(out)


def adicionar_holm(tabela: pd.DataFrame, mapa: dict) -> pd.DataFrame:
    """Coluna `p_holm`: Holm sobre todos os p de Wilcoxon das componentes pareadas decisivas do mapa (família única)."""
    t = tabela.copy()
    decisivas = {c["metrica"] for s in mapa.values() for c in s["componentes"] if c.get("tipo") != "limiar" and not c.get("pendente")}
    mask = t["metric"].isin(decisivas) & t["wilcoxon_p"].notna() if "wilcoxon_p" in t else pd.Series(False, index=t.index)
    t["p_holm"] = np.nan
    if mask.any():
        t.loc[mask, "p_holm"] = holm(t.loc[mask, "wilcoxon_p"].to_numpy())
    return t


def resolver_limiares(veredito_cfg: dict, analysis_cfg: dict) -> dict:
    """Troca `limiar_ref` pelo valor da chave correspondente em `analysis` e devolve uma cópia do mapa."""
    mapa = {}
    for crit, spec in veredito_cfg["criterios"].items():
        comps = []
        for c in spec["componentes"]:
            c = dict(c)
            if "limiar_ref" in c:
                c["limiar"] = analysis_cfg[c.pop("limiar_ref")]
            comps.append(c)
        mapa[crit] = {**spec, "componentes": comps}
    return mapa


def montar_tabela(m: pd.DataFrame, mapa: dict, false_block_max_rate: float) -> pd.DataFrame:
    """Tabela de entrada a partir da tabela de métricas por réplica: diferenças pareadas das componentes pareadas
    e, para o cenário `controle`, as linhas de limiar (taxa de falsos bloqueios e overhead da auditoria)."""
    d = m.copy()
    d["rto_ok"] = d["rto_ok"].astype(float)
    d["classe_pior"] = (d["classe"] != "aceitavel").astype(float)
    metricas = [c["metrica"] for s in mapa.values() for c in s["componentes"] if c.get("tipo") != "limiar"]
    partes = [paired_comparison(d, k) for k in metricas]
    tab = pd.concat([p for p in partes if len(p)] or [pd.DataFrame()], ignore_index=True)
    fb = false_block_verdict(m, false_block_max_rate)
    ov = audit_overhead(m)
    extra = pd.DataFrame([
        {"scenario": CONTROLE, "metric": "taxa_falsos_bloqueios", "valor": fb["taxa"]},
        {"scenario": CONTROLE, "metric": "delta_audit_p95_ms", "valor": ov["delta_audit_p95_ms"]},
        {"scenario": CONTROLE, "metric": "delta_cpu_pct", "valor": ov["delta_cpu_pct"]},
    ])
    return pd.concat([tab, extra], ignore_index=True)


def resumo(m: pd.DataFrame, veredito_cfg: dict, analysis_cfg: dict):
    """Tudo de uma vez: (tabela com Holm, critérios, hipóteses, critérios Holm, hipóteses Holm)."""
    mapa = resolver_limiares(veredito_cfg, analysis_cfg)
    tab = adicionar_holm(montar_tabela(m, mapa, analysis_cfg["false_block_max_rate"]), mapa)
    c1 = veredito_criterios(tab, mapa)
    c2 = veredito_criterios(tab, mapa, alpha_holm=veredito_cfg["alpha"])
    return tab, c1, veredito_hipoteses(c1), c2, veredito_hipoteses(c2)

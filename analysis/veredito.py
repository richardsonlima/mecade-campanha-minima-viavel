"""Veredito da Campanha Mínima Viável (minha decisão D1, 2026-11-12; docs/PROTOCOLO.md Seção 4).

Entrada: tabela longa de diferenças pareadas, uma linha por (cenário, métrica), com as colunas de
`analysis.metrics.paired_comparison` (`median_diff`, `ci95_low`, `ci95_high`, `wilcoxon_p`). Critério sem
diferença pareada entra como linha com `valor` (e sem `median_diff`), e o cenário é `controle`.

Regras:
  componente   ATENDE quando a mediana está do lado favorável, o IC 95% não cruza zero e o limiar (se houver)
               é cumprido pela mediana. Componente `tipo: limiar` compara `valor` com o limiar.
  critério     por cenário: ATENDE se todas as componentes decisivas atendem; NAO_ATENDE se alguma falha;
               PENDENTE se nenhuma falha mas há componente marcada `pendente` no mapa; SEM_DADOS se o cenário
               planejado não tem linha nenhuma (por exemplo, sem par válido). SEM_DADOS vale como não atendido.
  hipótese     ACEITA (tudo atende), PARCIAL (algumas atendem, outras não ou sem dados), NAO_ACEITA (nenhuma
               atende) e PENDENTE (há PENDENTE e nenhum ATENDE junto de falha, então o resultado ainda poderia
               mudar; NAO_ATENDE misturado com PENDENTE, sem ATENDE, sai PENDENTE). SEM_DADOS se não há dado.
  proporção    `tipo: proporcao` (decisão D5, 2026-11-12): indicador 0/1 comparado por McNemar exato sobre os pares
               (MECADE, baseline). ATENDE quando a diferença de proporções (MECADE menos baseline) está do lado
               favorável e p < alpha (0,05), já na análise principal.
  limiar       "abaixo de" é <=: valor igual ao limiar atende (decisão D7).
  Holm         análise secundária: exige também p ajustado < alpha nas componentes pareadas e nas proporções, com uma
               família por hipótese (H1, H2, H3; decisão D6). Os p de McNemar entram na família da H2.
"""
from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

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


def mcnemar_exato(b: int, c: int) -> float:
    """p bilateral do McNemar exato: binomial(b + c, 1/2) sobre os pares discordantes. Sem discordantes, p = 1."""
    n = int(b) + int(c)
    if n == 0:
        return 1.0
    return float(stats.binomtest(int(min(b, c)), n, 0.5, alternative="two-sided").pvalue)


def mcnemar_comparison(m: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Indicador 0/1 `metric`, MECADE contra baseline, pareado por (cenário, réplica). `diff_prop` é a proporção do
    MECADE menos a do baseline; `mcnemar_p` é o McNemar exato (D5). Mesmas colunas-chave de `paired_comparison`."""
    out = []
    main = m[m["pair"].astype(str) != ""]
    for sc, g in main.groupby("scenario"):
        w = g.pivot_table(index="pair", columns="arm", values=metric, aggfunc="first").dropna()
        if not {"baseline", "mecade"} <= set(w.columns) or len(w) == 0:
            continue
        mec, base = w["mecade"] > 0.5, w["baseline"] > 0.5
        b, c = int((mec & ~base).sum()), int((~mec & base).sum())
        out.append({"scenario": sc, "metric": metric, "n_pairs": len(w),
                    "prop_baseline": float(base.mean()), "prop_mecade": float(mec.mean()),
                    "diff_prop": float(mec.mean() - base.mean()), "discordantes_mecade": b, "discordantes_baseline": c,
                    "mcnemar_p": mcnemar_exato(b, c)})
    return pd.DataFrame(out)


def avaliar_componente(linha: dict, comp: dict, alpha: float | None = None, alpha_prop: float = 0.05) -> tuple[bool, str]:
    """(atende, motivo) de uma componente numa linha da tabela. `alpha` liga o Holm: exige `p_holm` < alpha.
    `alpha_prop` é o nível do McNemar das componentes `tipo: proporcao`, que vale também na análise principal."""
    if comp.get("tipo") == "proporcao":
        d, p = linha.get("diff_prop"), linha.get("mcnemar_p")
        if _ausente(d) or _ausente(p):
            return False, "sem pares ou McNemar indisponível"
        if (-1 if comp["favoravel"] == "menor" else 1) * d <= 0:
            return False, "diferença de proporções do lado contrário ou nula"
        if p >= alpha_prop:
            return False, f"McNemar exato p = {p:.3g} não passa em {alpha_prop}"
        if alpha is not None:
            ph = linha.get("p_holm")
            if _ausente(ph) or ph >= alpha:
                return False, "p ajustado por Holm não passa"
        return True, "atende"
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


def cenarios_planejados(plano_csv: str | Path | None, cenarios_config: list[str], controle: str = "c0_controle") -> list[str]:
    """Cenários com injeção que a campanha planejou: os do plano oficial (cobre o plano de contingência) ou, sem
    plano, os de `scenarios` em config/campaign.yaml."""
    if plano_csv and Path(plano_csv).is_file():
        import csv
        with open(plano_csv, encoding="utf-8") as fh:
            return sorted({r["scenario"] for r in csv.DictReader(fh) if r["scenario"] != controle})
    warnings.warn(f"plano oficial ausente ({plano_csv}); uso os cenários de `scenarios` do config como planejados", stacklevel=2)
    return sorted(cenarios_config)


def veredito_criterios(tabela: pd.DataFrame, mapa: dict, alpha_holm: float | None = None,
                       cenarios: list[str] | None = None, alpha_prop: float = 0.05) -> pd.DataFrame:
    """Uma linha por (critério, cenário): `status` ATENDE, NAO_ATENDE, PENDENTE ou SEM_DADOS e o motivo por componente.
    `mapa` é `analysis.veredito.criterios`. Entram os cenários que aparecem na tabela para alguma componente do
    critério e, quando `cenarios` (os planejados) é dado, também os que faltam, como SEM_DADOS: a D1 exige todos os
    cenários aplicáveis. Critério só de limiar (controles) usa o cenário `controle`."""
    linhas = []
    for crit, spec in mapa.items():
        comps = spec["componentes"]
        sub = tabela[tabela["metric"].isin([c["metrica"] for c in comps])]
        de_controle = all(c.get("tipo") == "limiar" for c in comps)
        esperados = set(sub["scenario"].unique())
        if cenarios is not None:
            esperados |= {CONTROLE} if de_controle else set(cenarios)
        for sc in sorted(esperados):
            if sub[sub["scenario"] == sc].empty:
                linhas.append({"hipotese": spec["hipotese"], "criterio": crit, "scenario": sc, "status": "SEM_DADOS",
                               "falhas": "cenário planejado sem linha na tabela (sem par válido)", "pendentes": ""})
                continue
            falhas, pend, ok_n = [], [], 0
            for c in comps:
                if c.get("pendente"):
                    pend.append(c["metrica"])
                    continue
                rows = sub[(sub["scenario"] == sc) & (sub["metric"] == c["metrica"])]
                if rows.empty:
                    falhas.append(f"{c['metrica']}: sem linha")
                    continue
                ok, motivo = avaliar_componente(rows.iloc[0].to_dict(), c, alpha_holm, alpha_prop)
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
        n_ok, n_no, n_pe, n_sd = (int((g["status"] == s).sum()) for s in ("ATENDE", "NAO_ATENDE", "PENDENTE", "SEM_DADOS")) \
            if len(g) else (0, 0, 0, 0)
        falta = n_no + n_sd  # sem dados vale como não atendido
        if n_ok == 0 and n_no == 0 and n_pe == 0:
            v = "SEM_DADOS"
        elif falta == 0 and n_pe == 0:
            v = "ACEITA"
        elif n_ok > 0 and falta > 0:
            v = "PARCIAL"
        elif n_pe > 0:
            v = "PENDENTE"
        else:
            v = "NAO_ACEITA"
        det = "; ".join(f"{r.criterio}/{r.scenario}={r.status}" for r in g.itertuples())
        out.append({"hipotese": h, "veredito": v, "atende": n_ok, "nao_atende": n_no, "pendente": n_pe,
                    "sem_dados": n_sd, "detalhe": det})
    return pd.DataFrame(out)


def adicionar_holm(tabela: pd.DataFrame, mapa: dict) -> pd.DataFrame:
    """Coluna `p_holm`: Holm com uma família por hipótese (D6), sobre os p das componentes pareadas decisivas
    (Wilcoxon, ou McNemar nas `tipo: proporcao`) de todos os cenários da hipótese."""
    t = tabela.copy()
    t["p_holm"] = np.nan
    for h in sorted({s["hipotese"] for s in mapa.values()}):
        mets = {c["metrica"]: ("mcnemar_p" if c.get("tipo") == "proporcao" else "wilcoxon_p")
                for s in mapa.values() if s["hipotese"] == h for c in s["componentes"]
                if c.get("tipo") != "limiar" and not c.get("pendente")}
        p = pd.Series(np.nan, index=t.index)
        for met, col in mets.items():
            if col in t:
                sel = t["metric"] == met
                p[sel] = t.loc[sel, col]
        mask = p.notna()
        if mask.any():
            t.loc[mask, "p_holm"] = holm(p[mask].to_numpy())
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
    comps = [c for s in mapa.values() for c in s["componentes"] if c.get("tipo") != "limiar"]
    partes = [mcnemar_comparison(d, c["metrica"]) if c.get("tipo") == "proporcao" else paired_comparison(d, c["metrica"])
              for c in comps]
    tab = pd.concat([p for p in partes if len(p)] or [pd.DataFrame()], ignore_index=True)
    fb = false_block_verdict(m, false_block_max_rate)
    ov = audit_overhead(m)
    extra = pd.DataFrame([
        {"scenario": CONTROLE, "metric": "taxa_falsos_bloqueios", "valor": fb["taxa"]},
        {"scenario": CONTROLE, "metric": "delta_audit_p95_ms", "valor": ov["delta_audit_p95_ms"]},
        {"scenario": CONTROLE, "metric": "delta_cpu_pct", "valor": ov["delta_cpu_pct"]},
    ])
    return pd.concat([tab, extra], ignore_index=True)


def resumo(m: pd.DataFrame, veredito_cfg: dict, analysis_cfg: dict, cenarios: list[str] | None = None):
    """Tudo de uma vez: (tabela com Holm, critérios, hipóteses, critérios Holm, hipóteses Holm). `cenarios` são os
    planejados (`cenarios_planejados`); o que faltar na tabela vira SEM_DADOS."""
    mapa = resolver_limiares(veredito_cfg, analysis_cfg)
    tab = adicionar_holm(montar_tabela(m, mapa, analysis_cfg["false_block_max_rate"]), mapa)
    alfa = veredito_cfg["alpha"]
    c1 = veredito_criterios(tab, mapa, cenarios=cenarios, alpha_prop=alfa)
    c2 = veredito_criterios(tab, mapa, alpha_holm=alfa, cenarios=cenarios, alpha_prop=alfa)
    return tab, c1, veredito_hipoteses(c1), c2, veredito_hipoteses(c2)

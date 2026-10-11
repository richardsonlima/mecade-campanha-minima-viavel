"""Gera o analysis/analysis.ipynb. Mantenho o notebook como código para conseguir revisar em diff.

  python analysis/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
nb.cells = [
    md("# Análise da Campanha Mínima Viável\n\n"
       "Métricas por réplica, critérios de aceitação (Tabela 4.2) e comparações pareadas entre MECADE e baseline.\n\n"
       "Para a campanha real, `DATA_ROOT` aponta para `data/runs`. Uso `data/sim/runs` (com `INCLUDE_SIM=True`) "
       "só para testar o pipeline, e esses dados simulados não entram em nenhum resultado."),
    code("import sys, pathlib\n"
         "ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == 'analysis' else pathlib.Path.cwd()\n"
         "sys.path.insert(0, str(ROOT))\n"
         "import pandas as pd, numpy as np, matplotlib.pyplot as plt\n"
         "from analysis.metrics import load_runs, metrics_table, paired_comparison\n"
         "DATA_ROOT = ROOT / 'data' / 'runs'\n"
         "INCLUDE_SIM = False\n"
         "FIG = ROOT / 'analysis' / 'figures'; FIG.mkdir(parents=True, exist_ok=True)\n"
         "runs = load_runs(DATA_ROOT, include_sim=INCLUDE_SIM)\n"
         "m = metrics_table(runs)\n"
         "print(len(runs), 'réplicas carregadas'); m.head()"),
    md("## 1. Visão geral por cenário e braço"),
    code("cols = ['detected','TTD','TTM','TTR_capped','MTTR','area','TSR_fault','p99_fault','RRIndex_run']\n"
         "main = m[m['pair'].astype(str) != '']\n"
         "main.groupby(['scenario','arm'])[cols].median().round(3)"),
    md("## 2. Classificação tripartite (Tabela 3.5) e detecção"),
    code("pd.crosstab([main['scenario'], main['arm']], main['classe'])"),
    code("main.groupby(['scenario','arm']).agg(n=('run_id','count'), detectadas=('detected','sum'), "
         "ttr_censuradas=('TTR_censored','sum'), rto_ok=('rto_ok','sum'))"),
    md("## 3. Comparações pareadas (MECADE menos baseline)\n\n"
       "Wilcoxon pareado, delta de Cliff e IC de 95% por *bootstrap* da mediana das diferenças. "
       "Nas réplicas sem restauração, `TTR_capped` usa o fim da janela, o que é conservador."),
    code("pd.concat([paired_comparison(m, k) for k in ['TTR_capped','area','TSR_fault','p99_fault','RRIndex_run']], "
         "ignore_index=True).round(4)"),
    md("## 4. Taxa de falsos bloqueios (réplicas de controle)"),
    code("ctrl = m[m['pair'].astype(str) == '']\n"
         "print(f\"Controles: {len(ctrl)} | BLOCK acionado em {int(ctrl['block'].sum())} \"\n"
         "      f\"=> taxa de falsos bloqueios = {ctrl['block'].mean() if len(ctrl) else float('nan'):.2%}\")"),
    md("## 5. Overhead da auditoria (Camada 6, perfil mínimo)\n\n"
       "Δ_audit no caminho de decisão é o p95 do custo de enfileirar o evento. Comparo também a CPU do controlador com auditoria ligada e desligada."),
    code("aud = m[m['arm']=='mecade'].groupby('audit')[['audit_p95_ms','controller_cpu_s']].median()\n"
         "print(aud)\n"
         "print('Critério: Δ_audit,p95 <= 5 ms ->', bool((m['audit_p95_ms'].dropna() <= 5).all()))"),
    md("## 6. Figuras"),
    code("def fig_series(scenario):\n"
         "    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)\n"
         "    for meta, df in runs:\n"
         "        if meta['scenario'] != scenario or not meta.get('pair'):\n"
         "            continue\n"
         "        d = df[df['t'] >= 0]\n"
         "        ax.plot(d['t'], d['D_agr'], lw=0.8, alpha=0.6, color='tab:red' if meta['arm']=='mecade' else 'tab:gray')\n"
         "    ax.axvline(0, ls=':', c='k'); ax.set_xlabel('t desde a injeção (s)'); ax.set_ylabel('D_agr')\n"
         "    ax.set_title(f'{scenario}: MECADE (vermelho) × baseline (cinza)')\n"
         "    fig.tight_layout(); fig.savefig(FIG / f'Dagr_{scenario}.png', dpi=300)\n"
         "for sc in sorted(main['scenario'].unique()):\n"
         "    fig_series(sc)"),
    code("fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)\n"
         "main.boxplot(column='TTR_capped', by=['scenario','arm'], ax=ax, rot=30)\n"
         "ax.set_ylabel('TTR (s)'); plt.suptitle(''); fig.tight_layout(); fig.savefig(FIG / 'TTR_box.png', dpi=300)"),
    md("## 7. Exportação para a dissertação"),
    code("m.to_csv(ROOT / 'analysis' / 'metricas_por_replica.csv', index=False)\n"
         "print('analysis/metricas_por_replica.csv gravado')"),
]
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
Path(__file__).with_name("analysis.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
print("analysis/analysis.ipynb gerado")

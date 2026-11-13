"""Gera o analysis/analysis.ipynb. Mantenho o notebook como código para conseguir revisar em diff.

  python analysis/build_notebook.py
"""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
nb.cells = [
    md("# Análise da Campanha Mínima Viável\n\n"
       "Métricas por réplica, critérios de aceitação (Tabela 4.6 da v0.8) e comparações pareadas entre MECADE e baseline.\n\n"
       "Para a campanha real, `DATA_ROOT` aponta para `data/runs`. Uso `data/sim/runs` (com `INCLUDE_SIM=True`) "
       "só para testar o pipeline, e esses dados simulados não entram em nenhum resultado."),
    code("import sys, pathlib\n"
         "ROOT = pathlib.Path.cwd().parent if pathlib.Path.cwd().name == 'analysis' else pathlib.Path.cwd()\n"
         "sys.path.insert(0, str(ROOT))\n"
         "import pandas as pd, numpy as np, matplotlib.pyplot as plt\n"
         "from analysis.metrics import audit_overhead, execution_failures, false_block_verdict, load_official_runs, load_runs, metrics_table, paired_comparison\n"
         "DATA_ROOT = ROOT / 'data' / 'runs'\n"
         "INCLUDE_SIM = False\n"
         "FIG = ROOT / 'analysis' / 'figures'; FIG.mkdir(parents=True, exist_ok=True)\n"
         "if INCLUDE_SIM:\n"
         "    runs, excluidas = load_runs(DATA_ROOT, include_sim=True), []\n"
         "else:  # análise oficial: só campaign_id do config, sem sim nem calibração\n"
         "    runs, excluidas = load_official_runs(DATA_ROOT)\n"
         "print(len(excluidas), 'réplicas excluídas:', excluidas)\n"
         "m = metrics_table(runs)\n"
         "print(len(runs), 'réplicas carregadas'); m.head()"),
    md("## 1. Visão geral por cenário e braço"),
    code("cols = ['detected','TTD','TTM','TTR_capped','MTTR','area_incidente','p95_std','p99_std','TSR_fault','p99_fault','RRIndex_run']\n"
         "main = m[m['pair'].astype(str) != '']\n"
         "main.groupby(['scenario','arm'])[cols].median().round(3)"),
    md("## 2. Classificação tripartite (Tabela 3.5) e detecção"),
    code("pd.crosstab([main['scenario'], main['arm']], main['classe'])"),
    code("main.groupby(['scenario','arm']).agg(n=('run_id','count'), detectadas=('detected','sum'), "
         "censuradas=('censurada','sum'), rto_ok=('rto_ok','sum'), rto_ok_ttr=('rto_ok_ttr','sum'))"),
    code("falhas = execution_failures(DATA_ROOT)\n"
         "print('falha_execucao (o par sai da comparação):', [(f['run_id'], f['pair']) for f in falhas])\n"
         "print('censuradas:', list(main[main['censurada']]['run_id']))"),
    md("## 3. Comparações pareadas (MECADE menos baseline)\n\n"
       "Wilcoxon pareado, delta de Cliff e IC de 95% por *bootstrap* da mediana das diferenças. "
       "Réplicas censuradas entram com o fim da janela (`_capped`), como manda a Seção 4.4.1 da v0.8."),
    code("pd.concat([paired_comparison(m, k) for k in ['TTD_capped','TTR_capped','MTTR_capped','area_incidente','p95_std','p99_std','RRIndex_run','log10_V','I_rel','TSR_fault','p99_fault']], "
         "ignore_index=True).round(4)"),
    md("## 4. Taxa de falsos bloqueios (réplicas de controle)"),
    code("from mecade.config import load_campaign\n"
         "v = false_block_verdict(m, load_campaign()['analysis']['false_block_max_rate'])\n"
         "print(f\"Controles: {v['controles']} | BLOCK acionado em {v['blocks']} => taxa de falsos bloqueios = {v['taxa']:.2%}\")\n"
         "print(f\"Critério: taxa <= {v['limiar']:.0%} (no máximo 1 em 10) ->\", v['aceito'])"),
    md("## 5. Overhead da auditoria (Camada 6, perfil mínimo)\n\n"
       "Δ_audit no caminho de decisão é o p95 do custo de enfileirar o evento. Δcpu compara a CPU do controlador nos controles com auditoria ligada e desligada."),
    code("aud = m[m['arm']=='mecade'].groupby('audit')[['audit_p95_ms','controller_cpu_s']].median()\n"
         "print(aud)\n"
         "o = audit_overhead(m); print(o)\n"
         "print('Critério: Δ_audit,p95 <= 5 ms ->', o['delta_audit_p95_ms'] <= 5, '| Δcpu <= 8% ->', o['delta_cpu_pct'] <= 8)"),
    md("## 6. Vereditos (decisão D1, 2026-11-12)\n\n"
       "Critério por cenário: mediana da diferença pareada do lado favorável ao MECADE, IC 95% *bootstrap* sem cruzar zero "
       "e limiar da Tabela 4.6 cumprido. Hipótese: ACEITA (todos os critérios em todos os cenários), PARCIAL ou NÃO ACEITA. "
       "O mapa de critério para hipótese está em `analysis.veredito` de `config/campaign.yaml`. "
       "Componente marcada como pendente não decide, e a hipótese afetada sai PENDENTE. "
       "As proporções da H2 usam McNemar exato sobre os pares e exigem p < 0,05 (D5). Na campanha 2 a proporção que decide é `rto_ok_ttr` "
       "(TTR <= RTO, contado da injeção), e a classe tripartite é só descritiva (docs/PROTOCOLO_C2.md). "
       "Cenário planejado sem par válido sai SEM_DADOS e impede a hipótese de ser ACEITA. "
       "A análise principal não tem correção; Holm é a secundária, com uma família por hipótese (D6)."),
    code("from analysis.veredito import cenarios_planejados, resumo\n"
         "camp = load_campaign(); cfg = camp['analysis']\n"
         "plano = ROOT / 'data' / f\"plan_{camp['campaign_id']}.csv\"  # o plano oficial cobre o de contingência\n"
         "plan_sc = cenarios_planejados(plano, camp['scenarios'], camp['control_scenario'])\n"
         "print('Cenários planejados:', plan_sc)\n"
         "tab_v, crit, hip, crit_holm, hip_holm = resumo(m, cfg['veredito'], cfg, cenarios=plan_sc)\n"
         "print('Análise principal, sem correção')\n"
         "crit"),
    code("hip"),
    code("print('Análise secundária, com Holm (uma família por hipótese: H1, H2, H3)')\n"
         "crit_holm"),
    code("hip_holm"),
    code("tab_v.round(4)"),
    md("## 7. Figuras"),
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
    md("## 8. Exportação para a dissertação"),
    code("m.to_csv(ROOT / 'analysis' / 'metricas_por_replica.csv', index=False)\n"
         "print('analysis/metricas_por_replica.csv gravado')"),
]
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
Path(__file__).with_name("analysis.ipynb").write_text(nbf.writes(nb), encoding="utf-8")
print("analysis/analysis.ipynb gerado")

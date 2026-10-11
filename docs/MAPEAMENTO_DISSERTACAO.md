# Onde cada parte da dissertação está no código (v0.6 do texto)

| Elemento da dissertação | Implementação |
|---|---|
| Camada 1, registro de cenário (Tabela 3.3) | `scenarios/*.yaml` |
| Camada 1, Cenário Base e estado estacionário | `load/k8s/loadgen.py` (carga fixa, semente fixa) e a fase `baseline` de `mecade/runner.py`, onde M_base é a mediana |
| Camada 2, catálogo de métricas (Tabela 3.4) | `config/campaign.yaml` (`signals` e `aux_signals`) e `analysis/metrics.py` |
| Camada 2, classificação tripartite (Tabela 3.5) | campo `classe` em `analysis/metrics.py::run_metrics` |
| Camada 3, desvio D(t) (Eq. 3.1) | `mecade/axioms.py::deviation`, com piso (decisão D2 do protocolo) |
| Camada 3, ALERT, LIMIT e BLOCK (Listagem 3.1) | `mecade/axioms.py::AxiomEvaluator`, com zona morta (decisão D1) |
| Camada 4, operadores de injeção (Tabela 3.6) | `scenarios/*.yaml`, que viram CRDs do Chaos Mesh (NetworkChaos, PodChaos, Schedule) |
| Camada 4, BLOCK e Safe State | `mecade/runner.py::mitigate`, que executa a ação do runbook quando o BLOCK dispara |
| Camada 5, orquestração | `orchestrator/` (plano randomizado e execução retomável) |
| Camada 6, perfil mínimo (Tabelas 3.7 e 3.8) | `mecade/audit.py` (JSONL com hash encadeado, escrita assíncrona) |
| Camada 6, envelope de overhead | `audit_p95_ms` e `controller_cpu_s` em `analysis/metrics.py`, com controles alternando auditoria ligada e desligada |
| Seção 3.4, RRIndex limitado | `RRIndex_run` em `analysis/metrics.py` (decisão D7) |
| Seção 3.3, trilha de adoção | a campanha cobre o E1 (controles e calibração) e o E2 (ambiente de referência) |
| Tabela 4.2, critérios de aceitação | `analysis/analysis.ipynb`, Seções 2 a 5 |
| Seção 4.6, reprodutibilidade | `versions.env`, `CHANGELOG.md`, `data/README.md` e os metadados de cada réplica (commit, versões, parâmetros) |

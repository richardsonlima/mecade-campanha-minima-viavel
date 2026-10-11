# data/

| Caminho | Conteúdo | Vai para o git? |
|---|---|---|
| `plan_<campanha>.csv` | plano randomizado (ordem, braço, par, auditoria) | sim, e congelo antes da primeira réplica oficial |
| `runs/<run_id>/meta.json` | parâmetros, versões, commit, eventos, M_base, auditoria | sim (ou num arquivo compactado no final) |
| `runs/<run_id>/steps.csv` | série amostrada pelo controlador: sinais, D, D_agr, I, alerta | sim |
| `runs/<run_id>/prom_range.csv` | exportação bruta do Prometheus, como evidência independente | sim |
| `audit/<run_id>.jsonl` | trilha da Camada 6 com hash encadeado | sim |
| `runs/campaign.log` | log de execução | sim |
| `sim/` | dados da simulação, só para testar o pipeline | não |

No fim da campanha gero um `.tar.gz` com `runs/`, `audit/` e o plano, e coloco o SHA-256 dele na
dissertação, na seção de reprodutibilidade (4.6).

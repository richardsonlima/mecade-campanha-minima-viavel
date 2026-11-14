# CHANGELOG da campanha

Qualquer mudança de versão, parâmetro ou cenário depois que as réplicas oficiais começarem vai
anotada aqui. Réplicas rodadas antes e depois de uma mudança não são comparáveis entre si.

## 14/11 - calibração da campanha 2 congelada

Regra da Seção 3 do `docs/PROTOCOLO_C2.md` aplicada à rodada 1 da campanha 2 (`data/calibracao/resultado_r1.json`), sem mudança na regra.

- d_off e deadband: 0,3 → 2,9 (P99 de `D_agr` nos controles = 2,83, arredondado para cima; P50 = 0,58, P95 = 2,19, máximo 3,65, 2400 amostras de 10 controles).
- d_on: 0,5 → 3,1 (d_off + 0,2).
- budget_B: 60,0 → 47,0, só pela condição (a): 2 × o maior I dos controles (23,47), arredondado para cima.
- tau_dwell: fica em 15 s, sem ALERT espúrio nos controles com os valores novos.
- Plano oficial `data/plan_mvc-2026-11-c2.csv`, gerado com a semente 20261113: 70 execuções, SHA-256 `cf4eb65d…`.
- `make test`: 113 passam.

## 13/11 - pré-registro da campanha 2 (`mvc-2026-11-c2`)

Branch `campanha-2`, a partir do `main` depois da tag `mvc-2026-11-final`. Protocolo em `docs/PROTOCOLO_C2.md`.

- `campaign_id`: `mvc-2026-11` → `mvc-2026-11-c2`; semente `20261011` → `20261113`.
- Axiomas de volta aos valores iniciais (d_on 0,5; d_off e deadband 0,3; B 60; tau 15 s), para a calibração da campanha 2.
- `axioms.envelope: d_on_tau`: classe degradada quando D_agr fica acima de d_on por tau_dwell seguidos (`analysis/metrics.py`). Com `delta` (padrão), vale a regra da campanha 1.
- `analysis/metrics.py` passa a calcular `rto_ok_ttr` (TTR ≤ RTO, contado da injeção), `log10_V` e `I_rel`. As colunas da campanha 1 não mudam.
- Mapa de critérios: a recuperação decide por `TTR_capped` e `rto_ok_ttr`; MTTR e classificação saem do mapa e ficam descritivos.
- Calibração (`calibracao` no config): 10 controles e 1 par por cenário; `regra_B: margem_ruido` (B = 2 × maior I dos controles, sem a condição do piloto de s1); `tau_sem_solucao: 30`.
- Os dados, o notebook e as figuras da campanha 1 saem do branch (ficam no `main` e na tag). `RESULTADOS_CAMPANHA.md` vira `docs/RESULTADOS_CAMPANHA_1.md`.
- RTO, cenários, versões, braço baseline, linha do tempo e número de execuções não mudam.

## 13/11 - análise de sensibilidade da H2 (exploratória)

- `analysis/sensibilidade.py` e `tests/test_sensibilidade.py`: análise exploratória post hoc da H2 (TTR e RTO
  contado da injeção na recuperação; envelope igual a d_on por tau_dwell na classificação; I_max/B e log10 V̄
  descritivos). Não muda a análise principal nem o veredito. Resultado na Seção 10 de `RESULTADOS_CAMPANHA.md`.

## 13/11 - execuções oficiais e análise final

Nenhuma mudança de versão, parâmetro, cenário ou código entre a tag `mvc-2026-11-calibracao` e as 70 execuções (`git_commit` `6ebcd97` em todas).

- 70 de 70 `complete`, 0 `falha_execucao`, nenhuma refeita nem fora da ordem.
- Desvio de execução: `censuradas_baseline_fora_do_limite`, total 10, todas do baseline em s2 sem detecção na janela. Pela regra do limite de 10%, não contam; ficam relatadas em `data/desvios_execucao.jsonl` e `RESULTADOS_CAMPANHA.md`. Perdidas no limite: 0.
- Desvio de procedimento: os dados brutos entram no mesmo commit da análise, e não num commit separado antes dela (Seção 9 de `docs/EVIDENCIAS.md`, passos 4 a 7). O manifesto e a conferência das três cópias vêm depois, antes da tag final. Os dados são os mesmos da VM e do bucket.
- Resultados em `RESULTADOS_CAMPANHA.md`: H1 PARCIAL, H2 PARCIAL, H3 ACEITA.

## 12/11 - calibração congelada

Regra da Seção 6 do `docs/PROTOCOLO.md` aplicada à rodada 1 (`data/calibracao/resultado_r1.json`), sem mudança na regra.

- `campaign_id`: `mvc-2026-10` → `mvc-2026-11`.
- d_off e deadband: 0,3 → 2,7 (P99 de `D_agr` nos controles = 2,67, arredondado para cima; P50 = 0,67, P95 = 2,31, máximo 3,69, 720 amostras de 3 controles).
- d_on: 0,5 → 2,9 (d_off + 0,2).
- budget_B: 60,0 → 26837,7, o menor B em que o maior I dos controles (19,8) fica abaixo de 50% de B e o piloto de s1 não esgota B antes de 300 s de falha (I = 26837,7 no braço MECADE).
- tau_dwell: fica em 15 s, sem ALERT espúrio nos controles com os valores novos.
- Os `meta.json` da calibração registram `git_commit = 67fbcac`, equivalente a `ff7a20f` (docs/EQUIVALENCIA_COMMITS.md).
- `tests/test_pipeline_sim.py` fixa os valores iniciais dos axiomas: o mundo simulado não chega a D = 2,9 em s1, e o teste confere o pipeline, não a calibração.
- O plano oficial `data/plan_mvc-2026-11.csv` não mudou (SHA-256 `cfb49339…`, 70 réplicas).

## 12/11 - repositório e pré-registro

- Reescrevi o histórico do repositório e migrei para mecade-campanha-minima-viavel; a tag de pré-registro foi recriada (equivalência de commits em docs/EQUIVALENCIA_COMMITS.md).
- Os `meta.json` da calibração registram `git_commit = 67fbcac`, equivalente a `ff7a20f`, o commit da tag de pré-registro.
- Desvio: a data externa do pré-registro passou a ser a do novo push. A tag original saiu por volta de 01:00 UTC e a rodada 1 da calibração começou às 01:07 UTC, antes da nova data. As duas datas antecedem qualquer análise da calibração e qualquer réplica oficial.
- No commit da tag (`ff7a20f`), `config/campaign.yaml`, `analysis/metrics.py`, `orchestrator/plan_campaign.py` e `mecade/axioms.py` têm o mesmo conteúdo da tag original. Em `docs/PROTOCOLO.md`, `analysis/veredito.py` e `orchestrator/run_campaign.py` mudou só a redação de trechos para a primeira pessoa. Regras, critérios e lógica continuam iguais. O plano oficial segue com SHA-256 `cfb49339…`.

## 12/11 - D5 a D7

- D5: McNemar exato nas proporções da H2. D6: Holm com uma família por hipótese. D7: valor igual ao limiar atende. Implementado em `analysis/veredito.py`. Motivo: fechar a regra de veredito antes de qualquer dado oficial.

## 12/11 - correções (398a548..c2aa304)

Não muda o núcleo rígido nem o plano oficial.

- `make evidencias ESTRITO=1`: sai com código 3 se houver arquivo de evidência fora do git, árvore suja ou HEAD sem tag. Só `ESTRITO=1` liga o modo; `ESTRITO=0` não liga mais.
- `execution_failures` filtra pelo `campaign_id` oficial. O meta de `falha_execucao` ganhou `campaign_id`. Emite aviso quando falta o campo.
- `_motivo_exclusao` testa simulação e calibração antes do `campaign_id`.
- `info_git` usa `core.quotepath=off` e `-z`, para nomes com acento ou espaço.
- `verificar-evidencias` confere também as trilhas em subpastas de `data/audit` e `data/calibracao/audit`.
- `git_dirty` conta também arquivo não rastreado fora de `data/`.
- `cenarios_planejados` avisa quando cai no `scenarios` do config. `_mark_execution_failure` recebe o `campaign_id` já carregado.

## 12/11 - D1 e D4

Não muda o núcleo rígido nem o plano oficial.

- D1: regra de veredito (aceita, parcial, não aceita) por critério e cenário, com IC 95% bootstrap. Holm sobre Wilcoxon é análise secundária. Implementada em `analysis/veredito.py`, registrada em `docs/PROTOCOLO.md` (Seção 4 e Seção 8).
- D4: variabilidade de P95/P99 é o desvio-padrão durante o incidente (`p95_std`, `p99_std`).
- D3: MIT para o código e CC BY 4.0 para os dados. `CITATION.cff` sem DOI por enquanto.

## 11/11 - rastreabilidade do `meta.json`

- `meta.json` ganha `campaign_id`, `git_dirty`, `config_sha256` e `plano` (`oficial`, `calibracao` ou `sim`).
- `analysis.metrics.load_official_runs` aceita só réplica `complete` com `campaign_id` do config, fora de simulação e calibração, e devolve as excluídas com o motivo. `load_runs` e `count_lost` não mudaram.

## 11/11 - Portão B e limite de 10%

Não muda o núcleo rígido nem o plano oficial.

- Limite de 10%: conta `falha_execucao` de qualquer braço e `censurada` do braço MECADE. A censurada do baseline é relatada, porque o baseline reativo pode ficar sem detecção por construção. `count_lost` deixou de somar as censuradas do baseline; os códigos de saída 3 e 4 não mudaram.
- Falsos bloqueios (H1): no máximo 1 BLOCK em 10 controles, em `analysis.false_block_max_rate` (0.1). A análise passa a dar o veredito.
- TTD é critério de aceitação, como na Tabela 4.6 da v0.8.
- Cadeia de evidências em `docs/EVIDENCIAS.md`: `make evidencias` e `make verificar-evidencias`.
- `make verify-audit` agora sai com erro se qualquer trilha falhar. Antes, uma trilha quebrada no meio passava.

## 05/11 - v0.1.2

Não muda o núcleo rígido (axiomas, D(t), I(T), RRIndex_run, critérios, cenários, `timing`, baseline reativo, `block.stop_injection`).

- `create-cluster.sh`: vCPUs pelo tipo de máquina, mais a VM, e checagem da cota do projeto. Antes pedia 12 fixos.
- VM em `debian-13`, porque numpy e scipy fixados exigem Python 3.12 ou mais novo. Startup-script em `controller-startup.sh`, testado em contêiner `debian:13`.
- `.gitignore` criado.
- Calibração fora do plano oficial: `run_id` `cal<rodada>_`, semente própria, saída em `data/calibracao/`. `make calibrar` aplica a regra da Fase 1. `make pilot` não consome mais o plano oficial.
- Regra das 3 falhas: `tentativas.jsonl`, `falha_execucao`, parada acima de 10% de perdidas e em 3 falhas seguidas. Trilha parcial vai para `audit/tentativas/`. `--sem-limite-perdidas` desliga a parada em 10%.
- `analysis/metrics.py` cobre a Tabela 4.6: `area_incidente`, `p95_std`, `p99_std`, `censurada`, `TTD_capped`, `MTTR_capped`, `audit_overhead`. Saíram `eta_t_proxy` e `eta_I_proxy` (D6). Censuradas entram na análise principal com o fim da janela (Seção 4.4.1).
- `make sim` limpa `data/sim/` antes. `docs/PROTOCOLO.md`, `docs/MAPEAMENTO_DISSERTACAO.md` e `docs/RUNBOOK.md` alinhados à v0.8.
- `data/ENVIRONMENT.md` não traz mais o ID do projeto.

## 18/10 - v0.1.1

- `create-cluster.sh`: sem `--no-enable-autoupgrade`, que o GKE recusa com release channel. Uso exclusão de manutenção `no_minor_or_node_upgrades` até 15/12/2026. Confere a cota de CPUs e grava `data/ENVIRONMENT.md`.
- VM do controlador (`make controller-vm`) na zona do cluster, para os lotes longos não dependerem do notebook.
- `make port-forward-loop` reabre o port-forward do Prometheus. `make gke-down` limpa as injeções antes de zerar os nós; `make gke-up` espera tudo ficar pronto.
- O `.gitignore` não tinha entrado neste commit; entrou só na v0.1.2.
- Nenhuma mudança de parâmetro, cenário ou versão da pilha.

## 11/10 - v0.1.0

- Estrutura inicial com Online Boutique v0.10.5, Chaos Mesh 2.8.4, kube-prometheus-stack 90.0.0 e kind v0.33.0.
- Cenários s1, s2 e s3 (versão 1) e controle c0.
- Parâmetros dos axiomas nos valores iniciais. A calibração acontece na Fase 1.

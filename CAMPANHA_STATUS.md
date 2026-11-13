# Diário da campanha MECADE (2026)

Fase atual: campanha mvc-2026-11 fechada (tag `mvc-2026-11-final`). Nós do GKE em 0; a VM `mecade-ctl` e o cluster ficam para a campanha 2.
Custo estimado: cerca de R$ 11 até 12/11 07:30 UTC, com taxa de R$ 1,5 a 2,2/h. O faturamento confirma com atraso.
Próximo passo: pré-registro da campanha 2 (modo proteção), com push antes da calibração. Depósito no Zenodo só por ordem minha.

## 05/11 - pré-voo e preparação

- `make venv && make test`: 15 testes passaram, Python 3.14.4. O `.venv` antigo estava em Python 3.11, sem dependências, e foi recriado.
- Commit de partida: `b198a7b`.
- Instalei no notebook: Google Cloud SDK 592.0.0 com `gke-gcloud-auth-plugin` 0.5.21, `kubectl` v1.37.2 e `helm` v3.22.1 (SHA-256 conferido).
- Commits locais `cb19b09..faad656`:
  1. `.gitignore` criado, sem ignorar os dados versionados.
  2. `create-cluster.sh`: vCPUs pelo tipo de máquina, mais a VM. `e2-standard-2` pede 8; `e2-standard-4` pede 14 e é recusada em cota 8.
  3. VM em `debian-13`, Python 3.13.5. O startup-script passou em contêiner `debian:13`, com `make venv` e `make test`. Não testei em VM real.
  4. Calibração separada: `run_id` `cal<rodada>_`, semente própria, saída em `data/calibracao/`.
  5. Regra das 3 falhas com `tentativas.jsonl`, `falha_execucao`, desvio de ordem, parada em mais de 10% de perdidas (código 3) e em 3 falhas seguidas (código 4).
- Defeitos que achei além da lista do pré-voo:
  - a tentativa refeita anexava outra cadeia à mesma trilha e o `make verify-audit` falharia; a trilha parcial agora vai para `audit/tentativas/`;
  - `make sim` pulava réplicas concluídas; agora limpa `data/sim/`;
  - `make pilot` consumia o plano oficial; agora usa o plano de calibração;
  - a análise não cobria toda a Tabela 4.6; acrescentei área no incidente, variabilidade de P95/P99, censura com fim da janela e Δcpu, e tirei os proxies de η (D6).
- `make test`: 49 testes passando. `make sim` em `faad656`: 70 réplicas. A simulação não é evidência. O plano oficial é idêntico byte a byte ao de `b198a7b`.
- Sem credencial nos arquivos; o ID do projeto saiu de `data/ENVIRONMENT.md`.

## 11/11 - Fase 0 em espera e limite de 10%

- Habilitei as APIs compute e container. Cota medida: CPUS_ALL_REGIONS = 12 e CPUS em us-central1 = 200, uso 0. A campanha usa 8 e cabe.
- Implementei o limite de 10% e registrei o Portão B: commits `26a1b5c`, `031e7d0`. Runbook em `def8d2d`.
- Correções em `35c45f4`: desvio do baseline repetido a cada retomada, rótulo de braço desconhecido (agora conta como MECADE, com aviso), aritmética inteira no limite e limiar documentado como taxa.
- `make test`: 56 testes passam.
- Teste gratuito confirmado no console: R$ 1.830,55 de crédito, 90 dias, fim em 10/02/2027. Limites convertidos à taxa implícita (R$ 1.831 ≈ US$ 300, cerca de R$ 6,10 por US$ 1): parar se a taxa passar de R$ 6,10/h ou o gasto acumulado passar de R$ 610. Fase 0 liberada.

## 11/11 - parada e recomeço

- Parei tudo durante a Fase 0. Ficaram no ar o cluster `mecade-mvc` (3 nós `e2-standard-2`), a VM `mecade-ctl` e o bucket. Apaguei os três e conferi: 0 instâncias e 0 clusters. Nenhum dado de réplica existia.
- Portão A refeito: a campanha roda no projeto "My First Project", dentro da minha organização e ligado à mesma conta de faturamento do teste gratuito. O projeto `mecade-mvc`, criado antes, ficou sem recursos.
- A organização aplica `iam.automaticIamGrantsForDefaultServiceAccounts`. A conta de serviço padrão do Compute não ganha Editor, então dei à mão os papéis mínimos de nós e VM.
- Fase 0 recomeçada.

## 12/11 - Fase 0

Concluída por volta de 00:55 UTC.

- Criação (UTC): cluster `mecade-mvc` 00:34:09; nós 00:35:38; `data/ENVIRONMENT.md` 00:40:51; `kps` 00:41 e `chaos-mesh` 00:43 (helm); VM `mecade-ctl` 00:46:27; bucket 00:46:46 em US-CENTRAL1.
- Servidor Kubernetes (plano de controle e nós): v1.36.4-gke.2377000, containerd 2.2.7.
- VM: Debian 13.7, Python 3.13.5, kubectl v1.36.6, Helm 3.22.1. O kubectl do notebook (v1.37.2) está uma versão acima, dentro do skew com o servidor 1.36.
- Charts: `CHAOS_MESH_CHART_VERSION=2.8.4` e `KUBE_PROMETHEUS_STACK_CHART_VERSION=90.0.0` (app v0.93.1). Online Boutique v0.10.5, loadgen `python:3.12-slim`.
- Máquinas: 3 nós `e2-standard-2` (6 vCPUs) em us-central1-a, todos Ready, mais a VM `e2-small` (2 vCPUs). Total de 8 vCPUs.
- No smoke, CPU de 16% a 35% e memória de 33% a 40% por nó. Nenhum pod fora de Running.
- Na VM, o repositório estava em `47dc71b` (via `git bundle`). `make test`: 70 testes. Bucket: escrita, leitura e remoção testadas.
- `make smoke`: p95 = 0,180 s, p99 = 0,242 s, error_rate = 0,0, throughput = 24,2 req/s, cpu_boutique = 0,637, cpu_target = 0,163. Todos os sinais de decisão respondendo.
- `~/.mecade-projeto` tem o formato `PROJECT=<id>`; carrego com `. ~/.mecade-projeto`.
- Sem bloqueio, sem pods Pending, sem falta de permissão IAM.

## 12/11 - decisões D1 a D7

- D1 a D4, antes de qualquer dado oficial. Registradas em `docs/PROTOCOLO.md` e implementadas em `analysis/veredito.py`.
- D3: conta no Zenodo criada. MIT para o código e CC BY 4.0 para os dados (`LICENSE`, `data/LICENSE`, `CITATION.cff`).
- D5 a D7, antes de qualquer dado oficial. Implementadas na análise (`0ea957f`).
- Escolhi seguir adiante e só registrar. Dependem de mim: a release final (DOI) e o e-mail final.

## 12/11 - pré-registro

- Achados baixos corrigidos antes das réplicas oficiais: aviso em `execution_failures` sem `campaign_id`, `ESTRITO=0` ligando o modo estrito, aviso no fallback de `cenarios_planejados` e `campaign_id` relido em `_mark_execution_failure`. Detalhes no CHANGELOG.
- `make test`: 96 testes passam. Veredito com SEM_DADOS e caso misto PENDENTE em `cb5e2ab`.
- O plano oficial é idêntico ao de `b198a7b`, SHA-256 `cfb49339…`, 70 réplicas, núcleo rígido intacto.
- Tag `mvc-2026-11-prereg` publicada por volta de 01:00 UTC.
- Ativei o repositório em Zenodo > GitHub. Toda release publicada no GitHub vira depósito com DOI. Tags de pré-registro e de calibração vão só como tag, nunca como release. A única release será a final, depois da tag `mvc-2026-11-final` e da conferência de segurança do pacote, por ordem minha na hora.

## 12/11 - calibração rodada 1

Comecei às 01:07 UTC na VM, em `67fbcac`, com 96 testes passando.

- 9 réplicas, `cal1_001..009`: 3 controles c0 (um com a auditoria desligada) e 1 par por cenário.
- Gravam só em `data/calibracao/`. Saída em `~/calib_r1.out` na VM.
- Fim estimado: cerca de 05:20 UTC. Custo estimado de R$ 1,6 a 2,2/h, abaixo do limite de R$ 6,10/h. A rodada deve ficar perto de R$ 9.
- O plano oficial `data/plan_mvc-2026-11.csv` entra no commit do congelamento, como manda `docs/EVIDENCIAS.md`.
- O `git_commit` dos `meta.json` fica `67fbcac`, mesmo com o HEAD local mais novo. Só a análise mudou depois, então a calibração não muda.
- Antes das réplicas oficiais, a VM recebe um bundle novo.

## 12/11 - migração de repositório

- Campanha migrada para `mecade-campanha-minima-viavel`, com o histórico de `main` e a tag de pré-registro. O repositório `mecade-mvc-01` fica como estava; o registro oficial passa a ser o novo.
- Atualizei `repository-code` em `CITATION.cff`, `docs/RUNBOOK.md` e `infra/gke/controller-vm.sh`.
- A rodada 1 continua na VM, no clone `~/mecade-mvc-01` criado a partir do bundle de `67fbcac`.
- Falta ativar o repositório novo em Zenodo > GitHub antes da release final.

## 12/11 - calibração congelada

Rodada 1 de 01:07 a 05:11 UTC: 9 réplicas `complete`, sem falha e sem desvio de execução. Copiei `data/calibracao/` para o bucket e para a máquina local; as três cópias têm 43 arquivos.

- `D_agr` nos controles (3 réplicas, 720 amostras): P50 = 0,67, P95 = 2,31, P99 = 2,67, máximo 3,69. O ruído vem da latência (p95 e p99); `error_rate` ficou em 0 nos controles.
- d_off = deadband = 2,7; d_on = 2,9.
- budget_B = 26837,7: o maior I(t) antes de 300 s de falha no piloto de s1 (MECADE 26837,7; baseline 22917,4). O maior I dos controles foi 19,8, bem abaixo de 50% de B.
- tau_dwell = 15 s: com os valores novos, os controles não têm ALERT espúrio. Os ALERTs ao vivo nos controles vinham do d_on inicial de 0,5.
- Axiomas refeitos offline com os valores novos: s1 (MECADE) dá ALERT em 20 s e BLOCK em 300 s; s2 dá ALERT em 80 s, sem BLOCK; s3 dá ALERT em 75 s, sem BLOCK; controles sem evento.
- `make sim` com os valores novos: 70 réplicas concluídas. O teste de ponta a ponta da simulação passou a fixar os valores iniciais dos axiomas, porque as amplitudes do mundo simulado ficam abaixo de d_on = 2,9. `make test`: 104 passam.
- Plano oficial `data/plan_mvc-2026-11.csv`: 70 réplicas, SHA-256 `cfb49339…`, igual ao pré-registrado.
- Os `meta.json` da calibração registram `67fbcac`, que corresponde a `ff7a20f` neste repositório.
- Custo estimado de R$ 1,6 a 2,2/h, perto de R$ 10 desde a criação do cluster.

## 13/11 - execuções oficiais e análise final

- 70 de 70 execuções `complete`, de 12/11 05:24 a 13/11 13:05 UTC, todas em `6ebcd97`, na primeira tentativa e na ordem sorteada. 0 `falha_execucao`.
- 10 execuções sem detecção na janela (`censurada`), todas do baseline em s2. Não contam no limite de 10%; o orquestrador registrou `censuradas_baseline_fora_do_limite` com total 10. Perdidas no limite: 0 de 70.
- Copiei `data/runs` (70 execuções), `data/audit` (35 trilhas), `campaign.log` e `desvios_execucao.jsonl`. Os SHA-256 batem com a cópia da nuvem e, numa amostra de 14 arquivos, com a VM.
- `make verify-audit`: 35 trilhas, 0 com falha.
- `make analyze`: figuras em `analysis/figures/`, métricas em `analysis/metricas_por_replica.csv`.
- H1 PARCIAL: TTD menor nos três cenários (mediana da diferença de -285 s em s1, -1115 s em s2, -255 s em s3), área menor em s1 e s3, P95/P99 sem diferença; 0 BLOCK em 10 controles.
- H2 PARCIAL: RRIndex_run atende em s1 e s3; recuperação e classificação não atendem. O MTTR do MECADE sai maior em s1 (+230 s) e s3 (+177,5 s), porque detecta antes; nenhuma execução do MECADE dentro do RTO de 180 s.
- H3 ACEITA: Δ_audit,p95 = 0,0435 ms e Δcpu = -2,26%, com 5 controles por estado de auditoria.
- No Holm por família, H1 e H2 seguem PARCIAL e H3 ACEITA.
- 5 de 10 controles tiveram ALERT, sem BLOCK. Em s2 o MECADE não chega a BLOCK e nenhum braço aplica o runbook.
- Números completos e origem de cada um em `RESULTADOS_CAMPANHA.md`.

## 13/11 - fechamento

- Decidi tratar as correções da H2 como análise exploratória post hoc, e não como emenda: a análise principal fica como foi pré-registrada. `analysis/sensibilidade.py` no commit `6e5b690`; o veredito não muda (Seção 10 de `RESULTADOS_CAMPANHA.md`).
- Tag `mvc-2026-11-final` em `6e5b690`. `make evidencias ESTRITO=1`: 362 arquivos, 35/35 trilhas, SHA-256 do manifesto `5d24630b37a99867070b1d151c2e4ff06712e4fff459e551b61ec30c0aed391b`.
- Três cópias conferidas contra esse manifesto: local, bucket e VM, as três com `CONFERE` em 362 arquivos.
- Não desmontei a infraestrutura: decidi rodar a campanha 2, confirmatória, com o Chaos Budget em modo proteção.

## Decisões

- Portão A (11/11): projeto novo para a campanha, depois refeito no "My First Project" (ver 11/11). `MACHINE=e2-standard-2`.
- Portão B (11/11): falsos bloqueios no máximo 1 em 10 controles; TTD é critério de aceitação.
- Limite de 10% (11/11): conta `falha_execucao` e censuradas do braço MECADE; censuradas do baseline são relatadas. Ajuste em `count_lost`, com teste, antes da primeira réplica oficial.
- D1: critério atende num cenário quando a mediana da diferença pareada favorece o MECADE, o IC 95% bootstrap não cruza zero e o limiar da Tabela 4.6, quando houver, é cumprido pela mediana. Hipótese aceita se todos os critérios atendem em todos os cenários, parcial se só alguns (por cenário). Holm é análise secundária.
- D2: push dos commits e da tag `mvc-2026-11-prereg` antes da calibração, e da tag `mvc-2026-11-calibracao` antes das réplicas oficiais, depois de conferir que não vão credenciais nem o ID do projeto.
- D3: MIT (código) e CC BY 4.0 (dados). Depósito no Zenodo só no fim.
- D4: variabilidade de P95/P99 é o desvio-padrão durante o incidente.
- D5 = A: proporções da H2 (réplicas dentro do RTO; degradadas ou críticas) por McNemar exato sobre os pares (MECADE, baseline) do indicador 0/1. Atende se a diferença favorece o MECADE e p < 0,05.
- D6 = A: no Holm da análise secundária, uma família por hipótese (H1, H2, H3).
- D7 = A: nos limiares "abaixo de" (falsos bloqueios, Δ_audit, Δcpu), valor igual ao limiar atende (≤).

## Limitações conhecidas

- Na simulação, 20 de 70 réplicas saem censuradas (todas de s2 e s3 no baseline). Só as 10 de s2 dariam 14%. O piloto da calibração mostra o comportamento real.
- H3: um controle sem ALERT registra só `CONTROL_START`. O Δ_audit,p95 sai de poucas amostras e a auditoria quase não pesa no Δcpu. Vai para o Cap. 5 se os dados confirmarem.
- `meta.json` truncado em queda faz a réplica ser refeita e conta uma falha a mais. É raro e conservador.
- MTTR pode sair negativo se a detecção vier depois da restauração. Conferi nos dados oficiais: nenhum negativo. MTTR é TTR menos TTD, então detectar antes aumenta o MTTR.
- Área do desvio: segui a v0.8 (`area_incidente`, durante o incidente) e mantive `area` como descritiva.
- Nós do GKE em 0 desde o fim das execuções; cluster e VM ainda existem até o desmonte.
- Alerta de orçamento: não consegui confirmar.
- Execuções oficiais sem desvio de protocolo além do registro das 10 sem detecção do baseline em s2.
- Com `envelope_delta` = 1,0 abaixo do P99 do ruído (2,67), todas as execuções saem pelo menos `degradado`, inclusive os controles, e o critério de classificação não separa os braços.

# Diário da campanha MECADE (2026)

Fase atual: calibração, rodada 1 rodando na VM desde 12/11 01:07 UTC.
Custo estimado: menos de R$ 5 até 01:15 UTC, com taxa de R$ 1,6 a 2,2/h. O faturamento confirma com atraso.
Próximo passo: terminar a rodada 1, aplicar a regra de calibração, congelar e criar a tag `mvc-2026-11-calibracao`.

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
- MTTR pode sair negativo se a detecção vier depois da restauração. Confiro nos dados.
- Área do desvio: segui a v0.8 (`area_incidente`, durante o incidente) e mantive `area` como descritiva.
- Cluster e VM ligados, gastando crédito. Ao fim do lote, `make gke-down`.
- Alerta de orçamento: não consegui confirmar.
- Nenhum desvio de protocolo em réplica, porque nenhuma oficial rodou.

# Cadeia de evidências da campanha

Este documento diz como uma banca confere que os números do Cap. 5 saem de dados brutos íntegros, de
protocolo e calibração congelados antes dos dados e de código identificável. Cada elo aponta para um
commit, uma tag, um arquivo ou um comando. O checklist da Seção 9 é o roteiro do fim da campanha.

## 1. Pré-registro (antes de qualquer dado)

| Elemento | Onde está | Commit e data (BRT) |
|---|---|---|
| Protocolo inicial | `docs/PROTOCOLO.md` | `b041bf3`, 2026-10-11 |
| Protocolo alinhado à v0.8 (desfechos, censura, regra de calibração da Seção 6) | `docs/PROTOCOLO.md`, `analysis/metrics.py` | `1ce44d3` e `f50e8d3`, 2026-11-05 |
| Regra de calibração em código | `analysis/calibrate.py`, `tests/test_calibrate.py` | `d4e8d76`, 2026-11-05 |
| Portão A: projeto dedicado e tipo de máquina (`e2-standard-2`) | `CAMPANHA_STATUS.md` (sem o ID, que não vai ao repositório) | `1c95992`, 2026-11-11 |
| Portão B: falsos bloqueios no máximo 1 em 10 (taxa 0,1); TTD como critério | `docs/PROTOCOLO.md` Seção 8, `config/campaign.yaml` (`analysis.false_block_max_rate`) | `031e7d0`, 2026-11-11 |
| Limite de 10% de perdidas (`falha_execucao` de qualquer braço e `censurada` do MECADE) | `docs/PROTOCOLO.md` Seção 4, `orchestrator/run_campaign.py` | `26a1b5c` e `35c45f4`, 2026-11-11 |
| Variabilidade de P95/P99 como desvio-padrão no incidente | `docs/PROTOCOLO.md` Seções 4 e 8 | `1ce44d3`; confirmada na D4 em 2026-11-12 |

**Limite desta prova.** As datas de commit são locais e podem ser escritas por quem faz o commit. Até
2026-11-11 o GitHub tem só até `b198a7b`; os 15 commits seguintes não foram enviados. Para a data
anterior aos dados valer diante de terceiros, a tag de pré-registro precisa sair do computador antes da
primeira réplica (Seção 9, passo 1): push da tag para o GitHub, depósito no Zenodo ou OSF, ou um carimbo
de tempo (OpenTimestamps) do hash do commit. Qualquer uma das três serve; sem nenhuma, a ordem
"protocolo antes dos dados" depende só da minha palavra.

## 2. Congelamento da calibração

A Fase 1 roda fora do plano oficial (`run_id` `cal<rodada>_`, saída em `data/calibracao/`). Depois de
aplicar a regra (`make calibrar`), congelo num único commit:

- `config/campaign.yaml` com os valores calibrados e `campaign_id: mvc-2026-11`;
- `data/calibracao/` inteiro (planos, réplicas, trilhas) e a saída da regra, que hoje só vai para a
  tela: `make -s calibrar > data/calibracao/resultado_r<rodada>.json`;
- o plano oficial `data/plan_mvc-2026-11.csv`;
- a entrada no `CHANGELOG.md` com valores, percentis e justificativa.

Esse commit recebe a tag anotada `mvc-2026-11-calibracao`, enviada para fora (Seção 1) antes da primeira
réplica oficial. A banca confere a ordem assim:

- todo `meta.json` oficial traz `git_commit`; o manifesto lista os commits distintos em
  `replicas_oficiais.git_commits`, e cada um deve descender da tag
  (`git merge-base --is-ancestor mvc-2026-11-calibracao <commit>`);
- `replicas_oficiais.primeira_wall_start_utc` deve ser posterior à data da tag no servidor externo;
- `replicas_oficiais.axiomas_sha256` deve ter uma única entrada: todas as réplicas usaram os mesmos
  parâmetros dos axiomas, iguais aos de `config/campaign.yaml` na tag;
- `git diff mvc-2026-11-calibracao mvc-2026-11-final -- config/ scenarios/ mecade/axioms.py data/plan_mvc-2026-11.csv`
  deve sair vazio. Qualquer diferença é desvio e precisa estar no `CHANGELOG.md`.

## 3. Integridade dos dados brutos

- **Trilhas da Camada 6.** `make verify-audit` recalcula a cadeia de hash de cada `data/audit/*.jsonl`
  e sai com erro se qualquer uma falhar. As trilhas parciais de `audit/tentativas/` ficam fora do
  `make verify-audit` e do `gerar`, mas entram no manifesto com hash, e o `make verificar-evidencias`
  também confere a cadeia delas (e de qualquer trilha em subpasta de `data/audit`). A cadeia pega alteração e troca de ordem, mas não pega
  o corte das últimas linhas; por isso o manifesto compara a contagem com `audit.records` do `meta.json`.
- **Manifesto.** `make evidencias` grava `data/EVIDENCIAS_MANIFESTO.json`:
  - commit, tags, data do commit e se a árvore estava limpa;
  - `campaign_id` e SHA-256 de `config/campaign.yaml`;
  - SHA-256 e número de réplicas do plano oficial;
  - SHA-256 e tamanho de cada arquivo de `data/runs`, `data/audit`, `data/calibracao`, mais
    `data/campaign.log` e `data/desvios_execucao.jsonl`, e a contagem por diretório;
  - resultado do verify-audit (oficial e calibração);
  - `versions.env`, versão do Python e das bibliotecas da análise e SHA-256 do `requirements.txt`;
  - resumo das réplicas (por status, backend, commit e parâmetros) e uma lista de alertas;
  - data de geração em UTC.

  O comando imprime o SHA-256 do próprio manifesto. Esse hash vai para a Seção 4.6 da dissertação.
- **Três cópias.** Cada cópia é conferida contra o manifesto do commit da tag final, nunca contra o que
  veio junto com ela:
  1. VM: `make verificar-evidencias MANIFESTO=/caminho/do/manifesto/da/tag`;
  2. bucket: baixo para um diretório vazio (`gcloud storage rsync -r gs://<bucket>/data <dir>/data`) e
     rodo `make verificar-evidencias RAIZ=<dir> MANIFESTO=...`. O bucket só guarda MD5 e CRC32C, por
     isso baixo em vez de confiar nos hashes dele;
  3. local: `make verificar-evidencias`.

  As três precisam imprimir `CONFERE` com o mesmo número de arquivos. Registro as três saídas no
  `RESULTADOS_CAMPANHA.md`.

## 4. Reprodutibilidade

- **Código:** a tag `mvc-2026-11-final` e o commit dela.
- **Ambiente:** `versions.env` (Online Boutique v0.10.5, Chaos Mesh 2.8.4, kube-prometheus-stack
  90.0.0, imagens), `requirements.txt` com versões fixas, `data/ENVIRONMENT.md` (cluster, tipo de
  máquina, versão do Kubernetes) e o campo `ambiente_analise` do manifesto.
- **Um comando:** num clone da tag com os dados, `make venv && make analyze` executa
  `analysis/analysis.ipynb` sobre `data/runs` e regenera `analysis/figures/*.png` e
  `analysis/metricas_por_replica.csv`. O bootstrap usa semente fixa (20261011, 5000 reamostras),
  então as tabelas saem iguais. Os PNG podem mudar byte a byte com outra versão do matplotlib, sem
  mudar o conteúdo.
- **Reexecução do experimento:** README, `docs/RUNBOOK.md` e `infra/`. Não se espera o mesmo número
  em outro cluster; espera-se o mesmo procedimento.

## 5. De cada número do Cap. 5 até a origem

Todo valor sai de `data/runs/*/meta.json` e `steps.csv`, lidos por `analysis/metrics.py::load_runs`.

| Valor no Cap. 5 | Função | Onde aparece |
|---|---|---|
| TTD, TTR, MTTR, `_capped`, censura | `metrics.py::run_metrics` | notebook Seções 1 a 3; `metricas_por_replica.csv` |
| Área do desvio (`area_incidente`), variabilidade (`p95_std`, `p99_std`) | `run_metrics` | Seções 1 e 3 |
| RRIndex_run | `run_metrics` | Seções 1 e 3 |
| Proporção dentro do RTO (`rto_ok`) | `run_metrics` | Seção 2 |
| Classe (crítico, degradado, aceitável) | `run_metrics` | Seção 2 (`crosstab`) |
| Mediana da diferença pareada, IC 95%, Wilcoxon, δ de Cliff | `paired_comparison`, `bootstrap_ci`, `cliffs_delta` | Seção 3 |
| Falsos bloqueios e veredito | `false_block_verdict`, limiar de `config/campaign.yaml` | Seção 4 |
| Δ_audit,p95 e Δcpu | `audit_overhead` | Seção 5 |
| `falha_execucao` e pares retirados | `execution_failures`; `data/desvios_execucao.jsonl` | Seção 2 |
| Valores calibrados e percentis de ruído (Cap. 4) | `analysis/calibrate.py` | `data/calibracao/resultado_r<rodada>.json` |
| Figuras D_agr por cenário e boxplot de TTR | notebook Seção 6 | `analysis/figures/Dagr_<cenario>.png`, `TTR_box.png` |
| Integridade da trilha, contagem de arquivos, hashes | `analysis/evidencias.py`, `mecade/audit.py::verify` | `data/EVIDENCIAS_MANIFESTO.json` |

No `RESULTADOS_CAMPANHA.md`, cada valor leva entre parênteses a função e a seção do notebook, ou o
campo do manifesto. Um número que não sai dessa tabela não entra no Cap. 5.

## 6. Desvios e censura

- `censurada`: réplica com falha que rodou até o fim sem detecção ou sem restauração. Entra na
  comparação com o fim da janela (`_capped`) e é listada por cenário e braço.
- `falha_execucao`: 3 tentativas perdidas, sem dados. O par sai da comparação pareada e é listado.
- Réplica refeita fora da ordem sorteada: desvio, em `data/desvios_execucao.jsonl`.
- Todo desvio vai para `CHANGELOG.md` e `CAMPANHA_STATUS.md` com data, motivo e impacto. O
  `RESULTADOS_CAMPANHA.md` repete a lista inteira, inclusive a contagem do limite de 10%.

## 7. Limitações já conhecidas

- **n pequeno.** 10 pares por cenário (contingência: s2 e s3). O IC por bootstrap percentil da mediana
  com 10 pontos tem cobertura abaixo da nominal e extremos presos às estatísticas de ordem. O Wilcoxon
  com n = 10 tem poder baixo. Relato tamanho de efeito e IC, e não leio p > 0,05 como ausência de efeito.
- **Falsos bloqueios.** 0 em 10 controles ainda é compatível com taxa real de até cerca de 26%
  (Clopper-Pearson unilateral 95%: 1 − 0,05^(1/10) ≈ 0,26). O critério "no máximo 1 em 10" é atendido
  ou não, mas a taxa fica mal estimada; o Cap. 5 relata o IC junto.
- **H3 com poucos eventos.** Um controle sem ALERT grava só `CONTROL_START`; o Δ_audit,p95 vem de
  poucas amostras e a auditoria quase não pesa no Δcpu. Com 5 controles por estado de auditoria, o
  Δcpu é uma razão de medianas de 5 valores.
- **Múltiplas comparações.** São cerca de 9 métricas × 3 cenários na Seção 3 do notebook, sem correção.
  Os p-valores ficam descritivos; o veredito segue a regra declarada na Seção 9, passo 1.
- **Variabilidade de P95/P99.** A v0.8 não define a medida; uso o desvio-padrão no incidente,
  declarado no protocolo.
- **Simulação.** `data/sim/` testa o pipeline e não é evidência. O manifesto acusa réplica simulada em
  `data/runs`.
- As do protocolo (Seção 7) e da Seção 4.5 da v0.8 valem também: D3, D5, D6, Online Boutique como
  único sistema-alvo.

## 8. Citar e arquivar

Recomendo depositar o pacote final num repositório com DOI. O Zenodo serve e é gratuito. O pacote leva:

- o código no commit da tag `mvc-2026-11-final` (a integração GitHub do Zenodo arquiva uma release);
- `data/` com `runs/`, `audit/`, `calibracao/`, o plano, `campaign.log`, `desvios_execucao.jsonl` e o
  manifesto;
- `analysis/analysis.ipynb` executado, `analysis/figures/` e `metricas_por_replica.csv`;
- `RESULTADOS_CAMPANHA.md`, `docs/PROTOCOLO.md`, `docs/EVIDENCIAS.md`, `CHANGELOG.md`.

A dissertação cita o DOI da versão e, na Seção 4.6, o SHA-256 do manifesto e o da tag.

O que isso exige de mim, e só de mim:

1. Conta no Zenodo (login com ORCID ou GitHub) e, se usar a integração, ligar o repositório.
2. Licença: o repositório não tem `LICENSE`. Sugestão: MIT ou Apache-2.0 para o código e CC BY 4.0
   para os dados. Sem licença, o depósito público não autoriza reuso.
3. Metadados: título, autores e afiliação (ITA), orientador, palavras-chave, versão.
4. Acesso: aberto já ou embargado até a defesa. O Zenodo permite reservar o DOI antes de publicar,
   para citar no texto.
5. Autorizar o push das tags para o GitHub (hoje a regra é sem push) e a publicação.
6. Fazer uma revisão de segurança do pacote antes do depósito: nenhum ID de projeto, IP,
   e-mail ou credencial em `campaign.log`, `meta.json` ou `ENVIRONMENT.md`.

Nada foi depositado.

## 9. Checklist da Fase 4

**Antes das réplicas oficiais**

1. Decidir e registrar no `docs/PROTOCOLO.md` a regra de veredito: o que é "atende" para cada linha da
   Tabela 4.6 (por exemplo, mediana da diferença na direção certa e IC 95% sem cruzar zero) e como os
   cenários se combinam em H1, H2 e H3. Commit, tag anotada `mvc-2026-11-prereg` e envio para fora
   (Seção 1). Sem esse passo, o veredito é escolhido depois de ver os dados.
2. Congelar a calibração (Seção 2): commit com `config/campaign.yaml`, `data/calibracao/`,
   `resultado_r<rodada>.json`, plano oficial e CHANGELOG; tag anotada `mvc-2026-11-calibracao`; envio
   para fora; `make evidencias` e guardar o SHA-256 impresso (manifesto parcial, só calibração).

**Depois da última réplica**

3. Na VM: `make verify-audit` (precisa terminar com "0 com falha"). Copiar `data/` para o bucket.
4. Trazer `data/` para a máquina local. Commit dos dados brutos, sem análise:
   "Registrei os dados brutos da campanha mvc-2026-11".
5. `make evidencias`. Ler os alertas: só podem sobrar "HEAD sem tag" e nada de trilha, commit misturado,
   simulação ou dado fora do git. Commit do manifesto.
6. `make verificar-evidencias` nas três cópias (Seção 3), com o manifesto do passo 5.
7. `make analyze`. Commit do notebook executado, das figuras e do `metricas_por_replica.csv`.
8. Escrever `RESULTADOS_CAMPANHA.md` (abaixo). Commit.
9. `git tag -a mvc-2026-11-final` no commit do passo 8 e, só então, `make evidencias ESTRITO=1`: o manifesto
   final aponta para esse commit. O fechamento da Fase 4 usa o modo estrito, que sai com código 3 se
   houver arquivo de evidência fora do git, árvore suja ou HEAD sem tag (sem ele esses casos são só
   alertas). O manifesto em si não conta como sujeira. Commit do manifesto. Conferir que
   `git diff mvc-2026-11-calibracao mvc-2026-11-final -- config/ scenarios/ mecade/axioms.py data/plan_mvc-2026-11.csv`
   sai vazio.
10. Cópia final de `data/` e `analysis/figures/` para o bucket, `make verificar-evidencias` na cópia do
    bucket, e só então o desmonte.
11. Depósito com DOI (Seção 8), se eu autorizar.

**O que entra no `RESULTADOS_CAMPANHA.md`, cada valor com a origem entre parênteses**

- Identificação: tag, commit, `campaign_id`, SHA-256 do manifesto e do plano (manifesto).
- Cap. 4: valores calibrados e percentis de ruído (`data/calibracao/resultado_r<rodada>.json`).
- Por critério da Tabela 4.6 e por cenário: n de pares, mediana de cada braço, mediana da diferença,
  IC 95%, δ de Cliff, Wilcoxon (descritivo) e veredito pela regra do passo 1 (`paired_comparison`,
  notebook Seção 3). Proporção dentro do RTO e de réplicas degradadas ou críticas por braço (Seção 2).
- Veredito de H1, H2 e H3, com os critérios que o sustentam.
- Falsos bloqueios: k/n, taxa e IC de Clopper-Pearson (`false_block_verdict`, Seção 4).
- Overhead: Δ_audit,p95, Δcpu, n com e sem auditoria (`audit_overhead`, Seção 5).
- Censuradas e `falha_execucao` por cenário e braço, contagem do limite de 10%, todos os desvios
  (`desvios_execucao.jsonl`, `CHANGELOG.md`).
- Integridade: saída do verify-audit e das três conferências do manifesto.
- Lista das figuras e tabelas, com caminho.
- Limitações (Seção 7).

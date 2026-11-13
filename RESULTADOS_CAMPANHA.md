# Resultados da campanha mvc-2026-11

Notas da análise final das 70 execuções oficiais. Sigo o roteiro da Seção 9 de `docs/EVIDENCIAS.md`.
Cada número traz a origem entre parênteses: função de `analysis/`, seção do notebook
`analysis/analysis.ipynb` ou arquivo de `data/`. As seções do notebook citadas são as do próprio notebook
executado (1 visão geral, 2 classificação e detecção, 3 comparações pareadas, 4 falsos bloqueios,
5 overhead, 6 vereditos, 7 figuras, 8 exportação).

## 1. Identificação

- `campaign_id`: `mvc-2026-11` (`config/campaign.yaml`; campo `campaign_id` dos 70 `data/runs/*/meta.json`).
- Código das execuções: `git_commit` = `6ebcd97` em todos os 70 `meta.json`, que é o commit da tag
  `mvc-2026-11-calibracao`. Todos com `git_dirty = false`, `tentativa = 1`, `fora_da_ordem = false`.
- `config/campaign.yaml`: SHA-256 `b43291c4…7c67ac3317`, igual ao `config_sha256` dos 70 `meta.json`.
  Parâmetros dos axiomas idênticos nas 70 execuções.
- Plano oficial `data/plan_mvc-2026-11.csv`: 70 execuções, SHA-256 `cfb49339…f2826731fc`.
- `git diff mvc-2026-11-calibracao HEAD -- config/ scenarios/ mecade/axioms.py data/plan_mvc-2026-11.csv`: vazio.
- Ordem no tempo: tag de calibração em 12/11 05:17 UTC; primeira execução oficial em 12/11 05:24 UTC,
  última iniciada em 13/11 12:40 UTC (`wall_start` dos `meta.json`); fim em 13/11 13:05 UTC
  (`data/campaign.log`).
- Tag `mvc-2026-11-final` e SHA-256 do manifesto: ainda não existem. Entram depois do `make evidencias ESTRITO=1`.

## 2. Calibração (Cap. 4)

Rodada 1, 3 controles e 1 par por cenário (`data/calibracao/resultado_r1.json`, `analysis/calibrate.py`).

| Medida | Valor |
|---|---|
| P50 de `D_agr` nos controles | 0,670 |
| P95 de `D_agr` nos controles | 2,305 |
| P99 de `D_agr` nos controles | 2,670 |
| Máximo de `D_agr` nos controles | 3,689 |
| Amostras / controles | 720 / 3 |
| Maior I nos controles | 19,75 |
| I antes de 300 s de falha no piloto de s1 | MECADE 26837,66; baseline 22917,38 |
| ALERT espúrio nos controles com tau = 15 s | 0 |

Valores congelados: `d_off` = `deadband` = 2,7; `d_on` = 2,9; `budget_B` = 26837,7; `tau_dwell` = 15 s.
Ficaram como estavam: `k` = 2 de 3, `aggregation` = max, `envelope_delta` = 1,0 (`config/campaign.yaml`).

## 3. Execuções, integridade e cópias

- 70 de 70 com status `complete`, 0 `falha_execucao` (`execution_failures`, notebook Seção 2).
  `load_official_runs` não excluiu nenhuma (notebook, primeira célula).
- Dados copiados para `data/runs/` (70 execuções, 280 arquivos), `data/audit/` (35 trilhas),
  `data/campaign.log` e `data/desvios_execucao.jsonl`: 317 arquivos de dados, mais os 2 `.gitkeep`.
  Os SHA-256 dos 319 arquivos batem com a cópia local da nuvem; numa amostra de 14 arquivos, também batem
  com a VM do controlador.
- `make verify-audit`: 35 trilhas verificadas, 0 com falha. São 30 do braço MECADE e 5 dos controles
  com auditoria ligada.
- Pendente: `make evidencias` e `make verificar-evidencias` nas três cópias (VM, bucket e local).
  Registro as três saídas aqui quando rodar.

## 4. Desfechos por cenário e braço

Medianas das 10 execuções de cada célula (notebook Seção 1; `run_metrics`). Tempos em segundos desde a injeção.
TTM é o tempo até a mitigação, contado a partir da injeção: o primeiro evento `MITIGATION` da execução
(`_first(ev, "MITIGATION")` em `analysis/metrics.py::run_metrics`; o evento é emitido em `mecade/runner.py`).

| Cenário | Braço | TTD | TTM | TTR_capped | MTTR | area_incidente | BLOCK |
|---|---|---|---|---|---|---|---|
| s1 | baseline | 305 | 427,5 | 540 | 235 | 42630,5 | 0/10 |
| s1 | MECADE | 20 | 330 | 475 | 455 | 33785,5 | 10/10 |
| s2 | baseline | sem detecção | sem mitigação | 600 | - | 19339,7 | 0/10 |
| s2 | MECADE | 80 | sem mitigação | 622,5 | 545 | 19708,2 | 0/10 |
| s3 | baseline | 345 | 465 | 540 | 192,5 | 34991,1 | 0/10 |
| s3 | MECADE | 92,5 | 427,5 | 482,5 | 380 | 31439,3 | 10/10 |

O que importa para ler as tabelas seguintes:

- Em s2 o MECADE dá ALERT em 75 a 80 s, mas I não chega a B e não há BLOCK. Nenhum dos braços aplica o
  runbook, e a recuperação só começa depois de FAULT_END (600 s).
- MTTR é TTR menos TTD (`docs/PROTOCOLO.md`, Seção 4). O MECADE detecta 285 s antes em s1 e 255 s antes em s3 (mediana da
  diferença de TTD), então o MTTR
  dele sai maior mesmo quando o TTR é menor. Nenhum MTTR negativo.
- Classe: as 60 execuções com falha saem `critico` em s1 e s3 e `degradado` em s2, nos dois braços
  (`crosstab`, notebook Seção 2).

## 5. Critérios da Tabela 4.6 por cenário

Diferença pareada é MECADE menos baseline; 10 pares por cenário. IC 95% por bootstrap percentil da mediana
das diferenças (semente 20261011, 5000 reamostras). Wilcoxon pareado bilateral; com n = 10, o menor p
possível é 0,0020. Holm com uma família por hipótese (D6). Origem: `paired_comparison`,
`mcnemar_comparison`, `adicionar_holm` e `resumo` de `analysis/veredito.py`, notebook Seções 3 e 6.

### H1, detecção e estabilidade da latência (Tabela 4.6, linha 3)

Favorável ao MECADE: valor menor nas quatro componentes.

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| TTD_capped | s1 | 305 | 20 | -285 | [-285; -282,5] | -1,00 | 0,0020 | 0,0234 |
| TTD_capped | s2 | 1195 (fim da janela) | 80 | -1115 | [-1115; -1115] | -1,00 | 0,0020 | 0,0234 |
| TTD_capped | s3 | 345 | 92,5 | -255 | [-275; -205] | -1,00 | 0,0020 | 0,0234 |
| area_incidente | s1 | 42630,5 | 33785,5 | -8379,9 | [-12458,5; -326,3] | -0,80 | 0,0098 | 0,0781 |
| area_incidente | s2 | 19339,7 | 19708,2 | 433,0 | [-1409,8; 1474,6] | 0,14 | 0,8457 | 1,0000 |
| area_incidente | s3 | 34991,1 | 31439,3 | -3816,5 | [-4928,5; -2442,1] | -0,90 | 0,0020 | 0,0234 |
| p95_std | s1 | 1,2789 | 1,2757 | 0,0261 | [-0,0746; 0,2070] | 0,14 | 0,7695 | 1,0000 |
| p95_std | s2 | 2,0240 | 2,0256 | 0,0021 | [-0,0329; 0,0482] | 0,04 | 0,8457 | 1,0000 |
| p95_std | s3 | 0,5499 | 0,5360 | -0,0417 | [-0,1159; 0,0692] | -0,18 | 0,6250 | 1,0000 |
| p99_std | s1 | 1,5137 | 1,4863 | 0,0015 | [-0,0923; 0,1609] | 0,08 | 0,9219 | 1,0000 |
| p99_std | s2 | 1,9373 | 1,9952 | 0,0184 | [-0,0665; 0,1193] | 0,10 | 0,4922 | 1,0000 |
| p99_std | s3 | 1,3847 | 1,3086 | 0,0539 | [-0,2014; 0,1226] | 0,08 | 0,8457 | 1,0000 |

Veredito do critério (regra D1): NÃO ATENDE em s1, s2 e s3. O TTD atende nos três cenários e a área
atende em s1 e s3, mas a variabilidade de P95/P99 não muda entre os braços (mediana da diferença do lado
contrário, ou IC cruzando zero em p95_std de s3). No Holm, a área de s1 também deixa de passar.

### H1, falsos bloqueios (Tabela 4.6, linha 5)

0 BLOCK em 10 controles, taxa 0,0 contra o limiar de 0,1 (`false_block_verdict`, notebook Seção 4): ATENDE.
IC de Clopper-Pearson para 0/10: limite superior unilateral de 95% de 0,259 (`docs/EVIDENCIAS.md`, Seção 7);
bilateral de 95% [0; 0,308] (`scipy.stats.beta.ppf(0.975, 1, 10)`).

Os controles tiveram ALERT, mas nenhum BLOCK: 5 de 10 com ALERT, em t = 45, 110, 305, 540 e 1150 s, e
I máximo de 514,1, abaixo de 2% de B (`detected`, `TTD` e `I_max` dos controles em
`analysis/metricas_por_replica.csv`). Na reprodução offline da calibração com os valores calibrados, os 3
controles não tiveram ALERT; ao vivo, com d_on = 0,5, tiveram.

### H2, recuperação (Tabela 4.6, linha 1)

Favorável: MTTR_capped e TTR_capped menores; `rto_ok` maior. RTO de 180 s nos três cenários (`scenarios/*.yaml`).

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| MTTR_capped | s1 | 235 | 455 | 230 | [185; 250] | 1,00 | 0,0020 | 0,0293 |
| MTTR_capped | s2 | 1195 (fim da janela) | 545 | -650 | [-675; -640] | -1,00 | 0,0020 | 0,0293 |
| MTTR_capped | s3 | 192,5 | 380 | 177,5 | [150; 215] | 0,96 | 0,0020 | 0,0293 |
| TTR_capped | s1 | 540 | 475 | -52,5 | [-102,5; -35] | -0,67 | 0,0059 | 0,0586 |
| TTR_capped | s2 | 600 | 622,5 | 7,5 | [-10; 30] | 0,24 | 0,4297 | 1,0000 |
| TTR_capped | s3 | 540 | 482,5 | -57,5 | [-80; -35] | -0,72 | 0,0039 | 0,0430 |

`rto_ok` por McNemar exato (D5):

| Cenário | Baseline | MECADE | Dif. de proporções | Discordantes (só MECADE / só baseline) | p McNemar | p Holm |
|---|---|---|---|---|---|---|
| s1 | 0/10 | 0/10 | 0,0 | 0 / 0 | 1,0000 | 1,0000 |
| s2 | 0/10 | 0/10 | 0,0 | 0 / 0 | 1,0000 | 1,0000 |
| s3 | 5/10 | 0/10 | -0,5 | 0 / 5 | 0,0625 | 0,5000 |

Veredito do critério: NÃO ATENDE em s1, s2 e s3. O TTR atende em s1 e s3, mas o MTTR fica do lado
contrário em s1 e s3 e nenhuma execução do MECADE fica dentro do RTO. Em s2 o MTTR favorável vem só do
baseline sem detecção na janela, e o TTR fica do lado contrário.

### H2, classificação (Tabela 4.6, linha 2)

`classe_pior` (degradada ou crítica), favorável menor, McNemar exato (D5): 10/10 nos dois braços nos três
cenários, diferença 0,0, sem discordantes, p = 1,0000 (Holm 1,0000). NÃO ATENDE em s1, s2 e s3.

### H2, convergência (Tabela 4.6, linha 4)

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| RRIndex_run | s1 | 9,23e-4 | 1,16e-3 | 2,31e-4 | [2,80e-5; 3,34e-4] | 0,76 | 0,0098 | 0,0879 |
| RRIndex_run | s2 | 2,82e-3 | 2,69e-3 | -1,31e-4 | [-5,04e-4; 2,19e-4] | -0,16 | 0,6250 | 1,0000 |
| RRIndex_run | s3 | 1,27e-3 | 1,43e-3 | 1,66e-4 | [7,57e-5; 2,11e-4] | 0,86 | 0,0020 | 0,0293 |

Veredito do critério: ATENDE em s1 e s3, NÃO ATENDE em s2. No Holm, só s3 atende.

Escala: RRIndex_run = 1/(1 + V̄), e nas medianas por célula V̄ vai de cerca de 350 (s2) a cerca de 1080
(baseline de s1) (`1/RRIndex_run - 1`, `analysis/metricas_por_replica.csv`). Por isso o índice fica perto de
zero e as diferenças são da ordem de 1e-4. A Tabela 4.6 não fixa limiar para a convergência, então o veredito
vale pelo sinal da mediana da diferença e pelo IC que não cruza zero, e não pelo tamanho absoluto.

### H3, overhead da auditoria (Tabela 4.6, linha 6)

Controles com auditoria ligada (n = 5) contra desligada (n = 5) (`audit_overhead`, notebook Seção 5).

- Δ_audit,p95 = 0,0435 ms, o maior p95 de enfileiramento entre os 5 controles com auditoria (valores de
  0,029 a 0,044 ms). Limiar ≤ 5 ms: ATENDE.
- Δcpu = -2,26%: mediana da CPU do controlador de 4,375 s com auditoria contra 4,476 s sem. Limiar ≤ 8%: ATENDE.

## 6. Vereditos das hipóteses

Regra D1 (`veredito_hipoteses`, notebook Seção 6).

| Hipótese | Análise principal | Holm por família (D6) | O que sustenta |
|---|---|---|---|
| H1 | PARCIAL | PARCIAL | falsos bloqueios atende; detecção e estabilidade não atende em nenhum cenário (TTD e área favoráveis, P95/P99 sem diferença) |
| H2 | PARCIAL | PARCIAL | convergência atende em s1 e s3 (só s3 no Holm); recuperação e classificação não atendem em nenhum cenário |
| H3 | ACEITA | ACEITA | Δ_audit,p95 = 0,0435 ms e Δcpu = -2,26%, os dois abaixo do limiar |

Na H2, a análise principal tem 2 de 9 combinações de critério e cenário atendendo; no Holm, 1 de 9.

## 7. Execuções sem detecção ou sem recuperação na janela, e desvios

- Execuções sem detecção ou sem recuperação na janela (`censurada`): 10, todas do baseline em s2, todas
  sem detecção (`censurada` em `run_metrics`, notebook Seção 2): `005_s2_gray_currency_baseline_r06`,
  `007_..._r03`, `025_..._r04`, `028_..._r09`, `030_..._r07`, `035_..._r08`, `051_..._r02`, `061_..._r01`,
  `067_..._r05` e `070_..._r10`. Entram na análise principal com o fim da janela (`TTD_capped` e
  `MTTR_capped` = 1195 s). No MECADE e nos outros cenários, 0.
- `falha_execucao`: 0. Nenhum par saiu da comparação.
- Limite de 10%: contam `falha_execucao` de qualquer braço e `censurada` do MECADE. Total 0 de 70 (0%).
  As 10 do baseline não contam e estão relatadas aqui.
- Desvio de execução registrado pelo orquestrador: `censuradas_baseline_fora_do_limite`, 10 linhas em
  `data/desvios_execucao.jsonl` e `data/campaign.log`, de 12/11 07:37 a 13/11 13:05 UTC, com o total
  acumulado de 1 a 10. É o registro das 10 execuções acima, não uma parada.
- Nenhuma execução refeita e nenhuma fora da ordem sorteada (`tentativa` e `fora_da_ordem` nos `meta.json`).
- Desvio de procedimento: os dados brutos entram no mesmo commit da análise, e não num commit separado antes
  dela (Seção 9 de `docs/EVIDENCIAS.md`, passos 4 a 7). Registrado no `CHANGELOG.md` (13/11).
- Desvios anteriores às execuções oficiais, já no `CHANGELOG.md`: data externa do pré-registro passou a ser
  a do novo push, depois da migração de repositório (12/11).

## 8. Figuras e tabelas

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `analysis/figures/Dagr_s1_latencia_productcatalog.png` | D_agr desde a injeção, MECADE e baseline, s1 | notebook Seção 7 |
| `analysis/figures/Dagr_s2_gray_currency.png` | idem, s2 | notebook Seção 7 |
| `analysis/figures/Dagr_s3_podkill_cart.png` | idem, s3 | notebook Seção 7 |
| `analysis/figures/TTR_box.png` | boxplot de TTR_capped por cenário e braço | notebook Seção 7 |
| `analysis/metricas_por_replica.csv` | métricas das 70 execuções (`run_metrics`) | notebook Seção 8 |
| `analysis/analysis.ipynb` | notebook executado, com as tabelas das Seções 1 a 6 | `make analyze` |

## 9. Limitações

- **MTTR.** Como MTTR é TTR menos TTD, detectar mais cedo aumenta o MTTR. O critério de recuperação
  penaliza o braço que detecta antes; o TTR mostra o outro lado.
- **Classificação.** Com `envelope_delta` = 1,0 abaixo do P99 do ruído (2,67), toda execução, inclusive os
  10 controles, sai pelo menos `degradado`. O critério de classificação não discrimina os braços neste
  ambiente.
- **s2.** I não chega a B e o MECADE não aciona o runbook. A comparação de recuperação em s2 mede só a
  volta depois do fim da falha.
- **n = 10 por cenário.** O Wilcoxon tem poder baixo e o menor p possível é 0,0020. Não leio p > 0,05 como
  ausência de efeito.
- **Bootstrap.** O IC percentil da mediana com 10 pontos tem cobertura abaixo da nominal e extremos presos
  às estatísticas de ordem; em TTD sai quase degenerado, porque o TTD do MECADE em s1 é 20 s nas 10 execuções.
- **Falsos bloqueios.** 0 em 10 é compatível com taxa real de até 0,259 (unilateral) ou 0,308 (bilateral).
- **Camada 6 em perfil mínimo.** JSONL com hash encadeado, sem blockchain. Δ_audit,p95 vem de poucos eventos
  por controle e Δcpu é razão de medianas de 5 valores. A vazão de 1000 eventos/s não é exercida.
- **Ruído subestimado na calibração.** Os 3 controles da calibração tiveram max D de 3,69 e I máximo de
  19,75 (`data/calibracao/resultado_r1.json`); os 10 controles oficiais chegaram a max D de 10,50 e I máximo
  de 514,1 (`max_D` e `I_max` em `analysis/metricas_por_replica.csv`). Isso explica o ALERT em 5 de 10
  controles, sem BLOCK, porque I ficou abaixo de 2% de B.
- **Múltiplas comparações.** A análise principal não tem correção; o Holm por família é secundário.
- Valem também as limitações da Seção 7 do protocolo e de `docs/EVIDENCIAS.md` (D3, D5 e D6 da Seção 5 do
  protocolo, Online Boutique como único sistema-alvo).

# Resultados da campanha mvc-2026-11-c2

Notas da análise final das 70 execuções oficiais da campanha 2, confirmatória, com o Chaos Budget em modo
proteção (`docs/PROTOCOLO_C2.md`). Sigo o roteiro da Seção 9 de `docs/EVIDENCIAS.md` e o formato de
`docs/RESULTADOS_CAMPANHA_1.md`. Cada número traz a origem entre parênteses: função de `analysis/`, seção do
notebook `analysis/analysis.ipynb` ou arquivo de `data/`. As seções do notebook são as do próprio notebook
executado (1 visão geral, 2 classificação e detecção, 3 comparações pareadas, 4 falsos bloqueios,
5 overhead, 6 vereditos, 7 figuras, 8 exportação).

A análise é a pré-registrada, sem mudança de critério: veredito por cenário pela regra D1, McNemar exato
para `rto_ok_ttr`, Holm por família como análise secundária e "≤" nos limiares
(`docs/PROTOCOLO_C2.md`, Seções 2 e 4; mapa de critérios em `analysis.veredito` de `config/campaign.yaml`).

## 1. Identificação

- `campaign_id`: `mvc-2026-11-c2` (`config/campaign.yaml`; campo `campaign_id` dos 70 `data/runs/*/meta.json`).
- Código das execuções: `git_commit` = `f947e60` em todos os 70 `meta.json`, que é o commit da tag
  `mvc-2026-11-c2-calibracao`. Todos com `git_dirty = false`, `tentativa = 1`, `fora_da_ordem = false`,
  `status = complete`.
- `config/campaign.yaml`: SHA-256 `10f9ce90…a1976dee5b`, igual ao `config_sha256` dos 70 `meta.json`.
  Parâmetros dos axiomas idênticos nas 70 execuções.
- Plano oficial `data/plan_mvc-2026-11-c2.csv`: 70 execuções, semente 20261113, SHA-256 `cf4eb65d…e6ce9aca66`.
- `git diff mvc-2026-11-c2-calibracao HEAD -- config/ scenarios/ mecade/ analysis/*.py data/plan_mvc-2026-11-c2.csv data/calibracao`: vazio.
- Ordem no tempo: tag de calibração em 14/11 02:36 UTC; primeira execução oficial em 14/11 02:39 UTC,
  última iniciada em 15/11 09:55 UTC (`wall_start` dos `meta.json`); fim em 15/11 10:20 UTC
  (`data/campaign.log`).
- Dados brutos no commit `9040444`. Manifesto `data/EVIDENCIAS_MANIFESTO.json` gerado com `make evidencias`
  sobre esse commit: 393 arquivos, trilhas íntegras 35/35, SHA-256
  `6423eb84c851dfbb4ae95920530fbb908c4d507a50e9286ede8fd69698f7a2b2`. Único alerta: "HEAD sem tag".
- Fechamento: tag `mvc-2026-11-c2-final` em `333dbf5`. `make evidencias ESTRITO=1`: 393 arquivos, trilhas
  35/35, sem alertas, SHA-256 do manifesto final
  `b1effa76c7e18201440cc06aa01b682a0b39571e4e39403c4484f313b2867967`. Este é o hash que cito na dissertação.
  `git diff mvc-2026-11-c2-calibracao mvc-2026-11-c2-final -- config/ scenarios/ mecade/axioms.py data/plan_mvc-2026-11-c2.csv`
  sai vazio.

## 2. Calibração (Cap. 4)

Rodada 1, 10 controles e 1 par por cenário (`data/calibracao/resultado_r1.json`, `analysis/calibrate.py`).

| Medida | Valor |
|---|---|
| P50 de `D_agr` nos controles | 0,582 |
| P95 de `D_agr` nos controles | 2,191 |
| P99 de `D_agr` nos controles | 2,831 |
| Máximo de `D_agr` nos controles | 3,653 |
| Amostras / controles | 2400 / 10 |
| Maior I nos controles | 23,47 |
| ALERT espúrio nos controles com tau = 15 s | 0 |

Valores congelados: `d_off` = `deadband` = 2,9; `d_on` = 3,1; `budget_B` = 47,0 (só a condição (a),
2 × 23,47 arredondado para cima); `tau_dwell` = 15 s. Ficaram como estavam: `k` = 2 de 3,
`aggregation` = max, `envelope` = `d_on_tau` (`config/campaign.yaml`).

## 3. Execuções, integridade e cópias

- 70 de 70 com status `complete`, 0 `falha_execucao` (`execution_failures`, notebook Seção 2).
  `load_official_runs` não excluiu nenhuma (notebook, primeira célula).
- Dados copiados da VM do controlador para `data/runs/` (70 execuções, 280 arquivos), `data/audit/`
  (35 trilhas), `data/campaign.log` e `data/desvios_execucao.jsonl`: 317 arquivos de dados.
  `data/calibracao/` e o plano vieram junto e são idênticos aos já versionados.
- Conferência das três cópias contra o manifesto final da tag, em 15/11 (`make verificar-evidencias`):
  - VM do controlador (`~/mecade-c2`): `CONFERE: 393 arquivos no manifesto, 0 alterados, 0 faltando, 0 sobrando`;
  - bucket, baixado para um diretório vazio: o plano oficial não estava lá, porque o backup periódico não o
    copiava. Copiei o plano, o manifesto e `analysis/figures/` para `oficial-c2/` e conferi de novo:
    `CONFERE: 393 arquivos no manifesto, 0 alterados, 0 faltando, 0 sobrando`;
  - local: `CONFERE: 393 arquivos no manifesto, 0 alterados, 0 faltando, 0 sobrando`.
  - `make verify-audit` na VM: 35 trilhas verificadas, 0 com falha.
- Conferência preliminar das cópias, antes da tag, em 15/11:
  - VM do controlador: SHA-256 dos 395 arquivos de `data/runs`, `data/audit`, `data/calibracao`, plano,
    log e desvios, calculado na VM, igual ao da cópia local;
  - bucket (`oficial-c2/`): MD5 dos 317 arquivos de dados, lido dos metadados dos objetos, igual ao da cópia
    local. Não baixei a cópia do bucket nem rodei `make verificar-evidencias` sobre ela;
  - local: `make verificar-evidencias` com o manifesto acima:
    `CONFERE: 393 arquivos no manifesto, 0 alterados, 0 faltando, 0 sobrando`.
- `make verify-audit`: 35 trilhas verificadas, 0 com falha. São 30 do braço MECADE e 5 dos controles
  com auditoria ligada.
- `make test`: 113 passam.

## 4. Desfechos por cenário e braço

Medianas das 10 execuções de cada célula (notebook Seção 1; `run_metrics`). Tempos em segundos desde a
injeção. TTD é o primeiro ALERT; TTM é o primeiro `MITIGATION`; TTR é a volta ao estado estacionário
(`D_agr` ≤ d_off por 60 s).

| Cenário | Braço | TTD | TTM | TTR_capped | MTTR | area_incidente | BLOCK | I_max/B |
|---|---|---|---|---|---|---|---|---|
| s1 | baseline | 302,5 | 425 | 525 | 222,5 | 41285,6 | 0/10 | 851,9 |
| s1 | MECADE | 20 | 12,5 | 1042,5 | 1022,5 | 54575,4 | 10/10 | 1281,5 |
| s2 | baseline | sem detecção | sem mitigação | 607,5 | - | 20155,9 | 0/10 | 401,3 |
| s2 | MECADE | 80 | 70 | 135 | 55 | 2887,4 | 10/10 | 47,4 |
| s3 | baseline | 345 | 465 | 550 | 207,5 | 35416,1 | 0/10 | 723,1 |
| s3 | MECADE | 105 | 55 | 175 | 85 | 4846,3 | 10/10 | 85,0 |

O que importa para ler as tabelas seguintes:

- Com B = 47, o BLOCK sai cedo nos três cenários: 10 a 20 s em s1, 65 a 70 s em s2 e 50 a 55 s em s3
  (`events` dos `meta.json`). Em s2 e s3 o BLOCK vem antes do ALERT, porque o LIMIT integra
  `D_agr` acima da zona morta sem esperar a correlação de 2 de 3 sinais.
- s2 e s3: a mitigação logo depois do BLOCK funciona. O TTR do MECADE vai de 115 a 300 s (s2) e de 110 a
  310 s (s3), contra 600 a 635 s (s2) e 515 a 690 s (s3) do baseline.
- s1: o restart sai 10 a 20 s depois da injeção e não tira a latência. O ALERT_CLEAR do MECADE vem entre
  745 e 1090 s, de 145 a 490 s depois do FAULT_END (600 s); o TTR vai de 745 a 1090 s, contra 475 a 585 s
  do baseline, cujo restart sai em 425 s. Na campanha 1 o mesmo restart, em 330 s, funcionou. Os dados não
  mostram a causa; o que posso dizer é que o restart precoce em s1 piorou e alongou o incidente.
- s2: o baseline não detecta em nenhuma das 10 execuções (a regra reativa não dispara na janela); o MECADE
  detecta nas 10.
- Classe (descritiva, `envelope: d_on_tau`): as 60 execuções com falha saem `critico` nos dois braços,
  porque I passa de B = 47 em todas. Nos controles: 5 `critico`, 1 `degradado` e 4 `aceitavel`
  (`crosstab`, notebook Seção 2).

## 5. Critérios da Tabela 4.7 por cenário

Diferença pareada é MECADE menos baseline; 10 pares por cenário. IC 95% por bootstrap percentil da mediana
das diferenças (semente 20261011, 5000 reamostras, `bootstrap_ci`). Wilcoxon pareado bilateral; com n = 10, o
menor p possível é 0,0020. Holm com uma família por hipótese (D6). Origem: `paired_comparison`,
`mcnemar_comparison`, `adicionar_holm` e `resumo` de `analysis/veredito.py`, notebook Seções 3 e 6.

### H2, recuperação

Favorável ao MECADE: `TTR_capped` menor e `rto_ok_ttr` maior (TTR ≤ 180 s, contado da injeção).

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| TTR_capped | s1 | 525 | 1042,5 | 505 | [460; 560] | 1,00 | 0,0020 | 0,0176 |
| TTR_capped | s2 | 607,5 | 135 | -480 | [-495; -462,5] | -1,00 | 0,0020 | 0,0176 |
| TTR_capped | s3 | 550 | 175 | -372,5 | [-450; -345] | -1,00 | 0,0020 | 0,0176 |

`rto_ok_ttr` por McNemar exato (D5):

| Cenário | Baseline | MECADE | Dif. de proporções | Discordantes (só MECADE / só baseline) | p McNemar | p Holm |
|---|---|---|---|---|---|---|
| s1 | 0/10 | 0/10 | 0,0 | 0 / 0 | 1,0000 | 1,0000 |
| s2 | 0/10 | 9/10 | 0,9 | 9 / 0 | 0,0039 | 0,0176 |
| s3 | 0/10 | 7/10 | 0,7 | 7 / 0 | 0,0156 | 0,0469 |

Veredito do critério: ATENDE em s2 e s3, NÃO ATENDE em s1 (TTR do lado contrário e nenhuma execução
dentro do RTO). Igual no Holm.

### H2, convergência

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| RRIndex_run | s1 | 9,47e-4 | 6,08e-4 | -2,88e-4 | [-4,03e-4; -1,98e-4] | -0,80 | 0,0840 | 0,1680 |
| RRIndex_run | s2 | 2,50e-3 | 2,14e-2 | 1,86e-2 | [1,19e-2; 2,13e-2] | 1,00 | 0,0020 | 0,0176 |
| RRIndex_run | s3 | 1,24e-3 | 1,22e-2 | 1,10e-2 | [8,68e-3; 1,13e-2] | 1,00 | 0,0020 | 0,0176 |

Veredito do critério: ATENDE em s2 e s3, NÃO ATENDE em s1 (mediana do lado contrário). Igual no Holm.
`log10_V` ao lado, descritivo (mediana da diferença): s1 +0,19, s2 -0,92, s3 -1,00.

### H2, classificação (descritiva)

Sem critério na campanha 2. 10/10 `critico` nos dois braços dos três cenários (Seção 4).

### H1, detecção e estabilidade da latência

Favorável ao MECADE: valor menor nas quatro componentes.

| Componente | Cenário | Mediana baseline | Mediana MECADE | Mediana dif. | IC 95% | δ de Cliff | p Wilcoxon | p Holm |
|---|---|---|---|---|---|---|---|---|
| TTD_capped | s1 | 302,5 | 20 | -282,5 | [-285; -277,5] | -1,00 | 0,0020 | 0,0234 |
| TTD_capped | s2 | 1195 (fim da janela) | 80 | -1115 | [-1115; -1115] | -1,00 | 0,0020 | 0,0234 |
| TTD_capped | s3 | 345 | 107,5 | -240 | [-260; -145] | -0,80 | 0,0801 | 0,3203 |
| area_incidente | s1 | 41285,6 | 54575,4 | 8275,2 | [5596,2; 17033,0] | 0,74 | 0,0840 | 0,3203 |
| area_incidente | s2 | 20155,9 | 2887,4 | -16759,5 | [-18489,6; -16132,3] | -1,00 | 0,0020 | 0,0234 |
| area_incidente | s3 | 35416,1 | 4846,3 | -30733,3 | [-34201,8; -28582,9] | -1,00 | 0,0020 | 0,0234 |
| p95_std | s1 | 0,6950 | 0,6952 | -0,0152 | [-0,5676; 0,2554] | 0,08 | 0,5566 | 0,5566 |
| p95_std | s2 | 2,0663 | 1,1591 | -0,9092 | [-0,9203; -0,8399] | -1,00 | 0,0020 | 0,0234 |
| p95_std | s3 | 0,4984 | 0,4015 | -0,1022 | [-0,1884; 0,0121] | -0,52 | 0,1055 | 0,3203 |
| p99_std | s1 | 1,1960 | 0,6074 | -0,6470 | [-0,7627; -0,3607] | -1,00 | 0,0020 | 0,0234 |
| p99_std | s2 | 2,0430 | 1,2817 | -0,7654 | [-0,8704; -0,6327] | -1,00 | 0,0020 | 0,0234 |
| p99_std | s3 | 1,4040 | 0,8666 | -0,6177 | [-0,7681; -0,2317] | -1,00 | 0,0020 | 0,0234 |

Veredito do critério: ATENDE em s2; NÃO ATENDE em s1 (área do lado contrário e IC de p95_std cruzando zero)
e em s3 (IC de p95_std cruzando zero). No Holm, s3 perde também o TTD (p ajustado 0,3203).

### H1, falsos bloqueios

5 BLOCK em 10 controles, taxa 0,5 contra o limiar de 0,1 (`false_block_verdict`, notebook Seção 4):
NÃO ATENDE. IC de Clopper-Pearson bilateral de 95% para 5/10: [0,187; 0,813]
(`scipy.stats.beta.ppf`). O protocolo já previa esse desfecho como resultado possível da regra nova de B
(`docs/PROTOCOLO_C2.md`, Seção 4), e por isso ele não entra como desvio.

| Controle | Auditoria | ALERT (t) | BLOCK | I_max | max D |
|---|---|---|---|---|---|
| `050_c0_controle_mecade_r05` | ligada | 755 | sim | 172,2 | 5,51 |
| `053_c0_controle_mecade_r08` | desligada | 145 | sim | 713,4 | 10,13 |
| `062_c0_controle_mecade_r04` | desligada | 130 | sim | 352,1 | 7,27 |
| `065_c0_controle_mecade_r09` | ligada | 510 | sim | 379,6 | 8,96 |
| `070_c0_controle_mecade_r01` | ligada | sem ALERT | sim | 82,1 | 5,02 |
| os outros 5 | 2 ligadas, 3 desligadas | sem ALERT | não | 0 a 6,5 | 1,95 a 3,33 |

Origem: `detected`, `TTD`, `block`, `I_max` e `max_D` em `analysis/metricas_por_replica.csv`. ALERT em 4 de
10 controles. Os BLOCK aparecem com auditoria ligada e desligada.

### H3, overhead da auditoria

Controles com auditoria ligada (n = 5) contra desligada (n = 5) (`audit_overhead`, notebook Seção 5).

- Δ_audit,p95 = 0,0704 ms, o maior p95 de enfileiramento entre os 5 controles com auditoria (valores de
  0,030 a 0,070 ms). Limiar ≤ 5 ms: ATENDE.
- Δcpu = +1,18%: mediana da CPU do controlador de 4,399 s com auditoria contra 4,348 s sem. Limiar ≤ 8%: ATENDE.

## 6. Vereditos das hipóteses

Regra D1 (`veredito_hipoteses`, notebook Seção 6).

| Hipótese | Análise principal | Holm por família (D6) | O que sustenta |
|---|---|---|---|
| H1 | PARCIAL | PARCIAL | detecção e estabilidade atende em s2 e não atende em s1 e s3; falsos bloqueios não atende (5/10) |
| H2 | PARCIAL | PARCIAL | recuperação e convergência atendem em s2 e s3 e não atendem em s1 |
| H3 | ACEITA | ACEITA | Δ_audit,p95 = 0,0704 ms e Δcpu = +1,18%, os dois abaixo do limiar |

Na H2, 4 de 6 combinações de critério e cenário atendem, nas duas análises. Na H1, 1 de 4.

Comparação com a campanha 1 (`docs/RESULTADOS_CAMPANHA_1.md`, Seção 6): os vereditos de hipótese são os
mesmos (PARCIAL, PARCIAL, ACEITA), mas o conteúdo muda. Na H2, o MECADE em modo proteção passa a cumprir o
RTO em s2 (9/10) e s3 (7/10), onde na campanha 1 nenhuma execução cumpria. Na H1, a especificidade cai de
0/10 para 5/10 falsos bloqueios.

## 7. Execuções sem detecção ou sem recuperação na janela, e desvios

- Execuções sem detecção ou sem recuperação na janela (`censurada`): 11 (`censurada` em `run_metrics`,
  notebook Seção 2).
  - 10 do baseline em s2, todas sem detecção: `002_s2_gray_currency_baseline_r03`, `004_..._r10`,
    `010_..._r07`, `015_..._r04`, `022_..._r01`, `026_..._r09`, `032_..._r06`, `052_..._r05`, `055_..._r02` e
    `067_..._r08`. Entram com o fim da janela (`TTD_capped` = 1195 s); o TTR delas vai de 600 a 635 s.
  - 1 do MECADE em s3: `020_s3_podkill_cart_mecade_r08`, com BLOCK e mitigação em 50 s e recuperação em
    165 s, mas sem ALERT (a correlação de 2 de 3 sinais não fechou). Entra com `TTD_capped` = 1195 s e
    `TTR_capped` = 165 s.
- `falha_execucao`: 0. Nenhum par saiu da comparação.
- Limite de 10%: contam `falha_execucao` de qualquer braço e `censurada` do MECADE. Total 1 de 70 (1,4%),
  dentro do limite. As 10 do baseline não contam e estão relatadas aqui.
- Desvio de execução registrado pelo orquestrador: `censuradas_baseline_fora_do_limite`, 10 linhas em
  `data/desvios_execucao.jsonl` e `data/campaign.log`, de 14/11 03:31 a 15/11 08:58 UTC, com o total
  acumulado de 1 a 10. É o registro das 10 execuções do baseline acima, não uma parada.
- Nenhuma execução refeita e nenhuma fora da ordem sorteada (`tentativa` e `fora_da_ordem` nos `meta.json`).
- Procedimento: desta vez os dados brutos (commit `9040444`), o manifesto, a análise e este documento estão
  em commits separados, como pede a Seção 9 de `docs/EVIDENCIAS.md`. Rodei o notebook uma vez antes do
  commit dos dados, sem tocar em `data/`, e de novo depois dele; o `analysis/metricas_por_replica.csv` saiu
  idêntico byte a byte.

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

- **Especificidade.** 5 BLOCK em 10 controles dão especificidade de 0,5 (IC 95% [0,187; 0,813]). B = 47 sai de
  2 × o maior I de 10 controles de calibração (23,47), e os controles oficiais chegaram a I de 82 a 713 e a
  max D de 5,0 a 10,1, contra 3,65 na calibração. O ruído do estado estacionário tem cauda que 10 controles
  não cobrem, como já tinha acontecido na campanha 1 (I máximo de 19,75 na calibração e de 514,1 nos
  controles oficiais). Em modo proteção, essa cauda vira falso bloqueio. A consequência para a leitura da H2
  é direta: o ganho de TTR em s2 e s3 vem de um BLOCK que dispara cedo para quase qualquer desvio, e a mesma
  sensibilidade bloqueia metade dos controles. Os dados não sustentam que a margem de 2× separa ruído de
  incidente neste ambiente.
- **BLOCK sem ALERT.** O LIMIT integra `D_agr` acima da zona morta sem passar pela correlação de 2 de 3
  sinais. Por isso há BLOCK antes do ALERT em s2 e s3, BLOCK sem ALERT no `070_c0_controle_mecade_r01` e
  a execução `020_s3` censurada por falta de detecção, embora tenha recuperado em 165 s.
- **s1 e o restart precoce.** Em s1 a mitigação sai 10 a 20 s depois da injeção e o incidente fica maior e
  mais longo que no baseline (TTR, área e convergência do lado contrário). Não verifiquei a causa no
  cluster; os dados mostram só que o restart nesse momento não removeu a latência e que a degradação
  passou do fim da falha. Esse é o principal motivo de a H2 não sair ACEITA.
- **Classificação.** Com B = 47, toda execução com falha sai `critico` nos dois braços; a classe não
  discrimina os braços.
- **n = 10 por cenário.** O Wilcoxon tem poder baixo e o menor p possível é 0,0020. Não leio p > 0,05 como
  ausência de efeito. Em `area_incidente` de s1 o IC exclui zero com p de Wilcoxon de 0,084, o que mostra
  como o IC bootstrap com 10 pontos fica estreito.
- **Bootstrap.** O IC percentil da mediana com 10 pontos tem cobertura abaixo da nominal e extremos presos às
  estatísticas de ordem; em TTD de s2 sai degenerado, porque o baseline fica no fim da janela nas 10.
- **s2 no baseline.** As 10 execuções do baseline ficam sem detecção; TTD e área do baseline em s2 medem a
  falta de detecção da regra reativa, não uma detecção tardia.
- **Camada 6 em perfil mínimo.** JSONL com hash encadeado, sem blockchain. Δ_audit,p95 vem de poucos eventos
  por controle e Δcpu é razão de medianas de 5 valores.
- **Múltiplas comparações.** A análise principal não tem correção; o Holm por família é secundário e, aqui,
  só muda o TTD de s3.
- Valem também as limitações da Seção 7 do `docs/PROTOCOLO.md`, de `docs/EVIDENCIAS.md` e da campanha 1
  (Online Boutique como único sistema-alvo, MTTR penalizando detecção mais cedo).

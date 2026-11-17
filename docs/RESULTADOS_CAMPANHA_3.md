# Resultados da campanha mvc-2026-11-c3

A campanha 3 fecha como **calibração inviável**, o desfecho fechado 2 da Seção 7.2 do `docs/PROTOCOLO_C3.md`.
A regra de B da Seção 3.4 falhou numa das condições de viabilidade: 2 dos 3 pilotos do braço baseline do s3
não tiveram ALERT antes de 415 s. Pela Seção 7.2, nenhuma execução oficial roda, nem com a regra trocada, e
qualquer regra nova fica para uma campanha 4, com pré-registro próprio. Decidi o fechamento em 17/11/2026.

Sigo o formato de `docs/RESULTADOS_CAMPANHA_2.md`, adaptado ao desfecho: há Fase 0 e calibração, e não há
execução oficial, comparação pareada nem veredito. Cada número traz a origem entre parênteses: função de
`analysis/` ou `orchestrator/`, ou arquivo de `data/`. Relato os números como saíram, sem ajuste.

## 1. Identificação

- `campaign_id`: `mvc-2026-11-c3` (`config/campaign.yaml`; campo `campaign_id` dos 48 `meta.json` de
  `data/calibracao/runs/`).
- Pré-registro: tag `mvc-2026-11-c3-prereg` em `cc672b9` (15/11 20:47, Brasília).
- Código das execuções de calibração: `git_commit` = `71ad5fb` nos 48 `meta.json`, o commit com o
  `clientes_apos_s` final da Fase 0. Todos com `git_dirty = false`, `tentativa = 1`, `fora_da_ordem = false`,
  `status = complete`, `machine_types` = 3 × `e2-standard-2`.
- `config/campaign.yaml`: SHA-256 `91d685b2…0360ba111b8`, igual ao `config_sha256` dos 48 `meta.json`.
  `git diff mvc-2026-11-c3-prereg HEAD -- config/` sai vazio: os valores calibrados nunca foram congelados,
  porque a calibração saiu inviável.
- Plano de calibração `data/calibracao/plan_r1.csv`: 48 execuções, SHA-256 `916663e9…bb8a6a265`, igual ao da
  Seção 6 do protocolo. O plano oficial `data/plan_mvc-2026-11-c3.csv` (SHA-256 `359cd792…88b41`) não foi
  executado.
- `git diff mvc-2026-11-c3-prereg HEAD` nos arquivos da lista da Seção 8.1 do protocolo (axiomas, regra
  reativa, `calibrate.py`, `metrics.py`, `veredito.py`, cenários s2, s3 e c0, gerador de planos e os dois
  planos): vazio.
- Ordem no tempo (UTC): node pool a 3 em 16/11 10:27:34 (`data/calibracao/campaign.log`); primeira execução
  `cal1_001` com reset em 16/11 10:35:33; última `cal1_048` concluída em 17/11 08:14:22; node pool a 0 em
  17/11 08:17:38.
- Hash do manifesto final: pendente.

## 2. Fase 0

Cinco execuções do s1 fora dos planos, prefixo `diag_`, em 16/11 de 00:30 a 02:50 UTC
(`data/diagnostico/fase0.log`; A rodou numa sessão e B, C1, C2 e D em outra). Saída de `make fase0-analise`
sem edição em `data/diagnostico/analise_fase0.json` (`analisar` de `orchestrator/fase0.py`). O resultado já
está no `CHANGELOG.md` de 16/11; repito os números aqui.

| Execução | Desenho | Rollout do alvo (s) | Volta pela regra da cascata (`cascata_ok`) |
|---|---|---|---|
| A | restart só do alvo em 15 s | 3,305 | nenhuma janela de 60 s até 150 s depois do restart |
| B | restart só do alvo em 120 s | 3,039 | começa em 170 s (50 s depois do restart) |
| C1 | alvo em 40 s, clientes depois | 3,798 | começa em 145 s (105 s depois do restart) |
| C2 | alvo em 40 s, clientes depois | 2,697 | começa em 140 s (100 s depois do restart) |
| D | alvo em 425 s, clientes depois | 2,781 | começa em 520 s (95 s depois do restart) |

- `clientes_apos_s`: 20 s. O maior rollout foi 3,798 s (C1); mais 10 s e para cima em 5 s dá 15 s, e o piso
  de 20 s do intervalo [20, 60] leva a 20 (`clientes_apos_s` de `orchestrator/fase0.py`). C1 e C2 testaram a
  cascata com 45 s; a calibração rodou com 20 s, um atraso que a Fase 0 não testou, como a Seção 3.1 do
  protocolo já declarava.
- Cascata: fica. C1 e C2 voltaram 105 s e 100 s depois do restart do alvo, dentro de 150 s (`cascata_ok`).
- H4: **não confirmada** (`H4.resultado`). Condição 1 vale em A: retransmissões de 8 para 9 e bytes
  retransmitidos de 532 para 622 numa conexão do checkoutservice ao ClusterIP:3550. Condição 2 sem dado em B:
  nenhuma conexão ao ClusterIP do alvo na última leitura antes do restart. Condição 3 não satisfeita em C1
  (frontend e checkoutservice com 7 leituras de conexão ao ClusterIP:3550 mais de 15 s depois de
  MITIGATION_CLIENTES) e em C2 (checkoutservice com 7 leituras; frontend sem tupla anterior ao restart). A
  leitura é por tupla ao ClusterIP, e um cliente novo abre conexão ao mesmo ClusterIP:3550; isso pode explicar
  a condição 3, mas não verifiquei.
- D: a Seção 3.1 pede o TTR de D ao lado da mediana de 525 s do baseline de s1 da campanha 2. O `steps.csv`
  da Fase 0 grava só p95, p99 e error_rate, sem D, e nem `analisar` nem `run_metrics` calculam o TTR dessas
  execuções. O que existe é o início da volta pela regra da cascata, 520 s depois da injeção, que não é o TTR
  da campanha 2 (lá, `D_agr` ≤ d_off por 60 s). Não calculo um TTR novo aqui e registro a falta como desvio
  (Seção 7).

## 3. Calibração (Fase 1)

Rodada 1, 30 controles e 3 pares por cenário, 48 execuções, todas com dados. Regra `calibrate_c3` de
`analysis/calibrate.py` (`calibracao.regra_B: alerta_piloto`). Rodei `make calibrar` na VM do controlador e
de novo na cópia local; a saída local é idêntica byte a byte à da VM. Os números abaixo são essa saída.

| Medida | Valor | Origem |
|---|---|---|
| Controles com dados / mínimo | 30 / 27 | `medido.n_controles`, `calibracao.controles_minimos` |
| Pilotos do braço baseline com dados / mínimo | 9 / 9 | `medido.n_pilotos`, `calibracao.pilotos_minimos` |
| Piso de p95 (mediana de M_base dos controles) | 0,3755 s | `pisos.p95` |
| Piso de p99 (mediana de M_base dos controles) | 0,8594 s | `pisos.p99` |
| Piso de error_rate | 0,01 | `pisos.error_rate` (piso do config) |
| Amostras de `D_agr` nos controles | 7200 | `medido.n_amostras` |
| P50 de `D_agr` nos controles, com os pisos novos | 0,517 | `medido.p50_D_agr` |
| P99 de `D_agr` nos controles, com os pisos novos | 3,675 | `medido.p99_D_agr` |
| Máximo de `D_agr` nos controles | 10,222 | `medido.max_D_agr` |
| d_off = deadband (P99 para cima na primeira casa) | 3,7 | `d_off`, `deadband` |
| d_on (d_off + 0,2) | 3,9 | `d_on` |
| ALERT espúrio nos controles com tau 15, 20, 25, 30 s | 3, 3, 3, 1 | `medido.alertas_espurios_por_tau` |
| tau_dwell | 30 s, sem solução (`tau_sem_solucao`) | `tau_dwell` |
| I condicionado ao ALERT nos controles, com tau 30 s | 0 em 29; 42,16 em `cal1_007_c0_controle_mecade_r28` | `medido.I_controles` |
| Limite do piloto (ação da regra reativa) | 415 s | `medido.limite_piloto_s` |
| B (menor I dos pilotos com ALERT, 30 s depois do ALERT, para baixo na dezena) | 680 | `budget_B` |
| Viável | **não** | `viavel` |

Os ALERTs espúrios com tau de 15 a 25 s saem de `cal1_007`, `cal1_010` e `cal1_022`, um em cada; com 30 s,
só `cal1_007` (`_alertas` sobre `_recalcula_D`, os mesmos passos de `calibrate_c3`).

Pilotos do braço baseline, com os pisos novos, d_on 3,9 e tau 30 s (`medido.pilotos`, `medido.pilotos_sem_alert`):

| Piloto | Cenário | Primeiro ALERT (s) | I 30 s depois do ALERT |
|---|---|---|---|
| `cal1_027_s1_latencia_productcatalog_baseline_r02` | s1 | 35 | 1177,1 |
| `cal1_031_s1_latencia_productcatalog_baseline_r01` | s1 | 35 | 2618,3 |
| `cal1_037_s1_latencia_productcatalog_baseline_r03` | s1 | 40 | 1236,5 |
| `cal1_013_s2_gray_currency_baseline_r02` | s2 | 95 | 836,1 |
| `cal1_019_s2_gray_currency_baseline_r01` | s2 | 90 | 853,1 |
| `cal1_047_s2_gray_currency_baseline_r03` | s2 | 95 | 681,9 |
| `cal1_002_s3_podkill_cart_baseline_r02` | s3 | 295 | 2609,1 |
| `cal1_011_s3_podkill_cart_baseline_r03` | s3 | sem ALERT antes de 415 s | - |
| `cal1_020_s3_podkill_cart_baseline_r01` | s3 | sem ALERT antes de 415 s | - |

Condições de viabilidade da Seção 3.4 e da Seção 7.1:

| Condição | Valor | Resultado |
|---|---|---|
| Mínimo de controles e pilotos com dados | 30 ≥ 27 e 9 ≥ 9 | cumpre |
| B > 0 | 680 | cumpre |
| B ≥ 2 × maior I condicionado dos controles | 680 ≥ 84,32 (2 × 42,16) | cumpre |
| Todo piloto com ALERT antes de 415 s | 7 de 9; faltam `cal1_011` e `cal1_020`, os dois de s3 | **não cumpre** |

A última condição decide: a calibração é inviável pela Seção 7.2, item 2. O tau sem solução, sozinho, não
tornaria a calibração inviável (Seção 4 do protocolo); com tau 30 s, a margem de 2× teve conteúdo e foi cumprida.

Para comparação, sem efeito em nada: na calibração da campanha 2, com pisos de 0,05, o P99 de `D_agr` nos
controles foi 2,831, o máximo 3,653 e o d_on 3,1 (`docs/RESULTADOS_CAMPANHA_2.md`, Seção 2).

## 4. Composição de regime pelo limiar de 0,16 s

M_base de p95 de cada execução, lido de `M_base.p95` nos `meta.json` de `data/calibracao/runs/`, contra o
limiar de 0,16 s da Seção 3.5 do protocolo:

| Grupo | n | Abaixo de 0,16 s | Em 0,16 s ou mais | Mínimo | Mediana | Máximo |
|---|---|---|---|---|---|---|
| Controles | 30 | 0 | 30 | 0,216 | 0,3755 | 0,954 |
| Pares (pilotos e braço MECADE) | 18 | 0 | 18 | 0,219 | 0,333 | 0,542 |
| Todas | 48 | 0 | 48 | 0,216 | 0,362 | 0,954 |

A calibração caiu inteira no regime alto. O regime baixo, onde ficaram 30 das 70 execuções oficiais da
campanha 2 e os 5 controles com falso bloqueio, não tem nenhum controle de calibração. Era o risco que a
Seção 3.5 já declarava. O critério de quebra de trocabilidade da Seção 3.5 compara controles oficiais com os
de calibração e não se aplica, porque não há controle oficial.

## 5. Execuções da calibração e integridade

- 48 de 48 com status `complete`, 0 `falha_execucao`, nenhuma refeita (`tentativa = 1` e um par
  início/concluída em cada `tentativas.jsonl`), nenhuma fora da ordem sorteada. Não houve completamento da
  Seção 7.1 e não há `desvios_execucao.jsonl` da calibração.
- `make verify-audit AUDIT_DIR=data/calibracao/audit`: 24 trilhas verificadas, 0 com falha.
- Dados versionados: `data/calibracao/runs/` (48 execuções), `data/calibracao/audit/` (24 trilhas) e
  `data/calibracao/campaign.log`, copiados da VM do controlador. A saída do terminal da rodada na VM (subida dos nós, smoke e
  `make run-calibracao`, em `calib_r1.out`) não vai para o repositório, porque traz o ID do projeto da nuvem na linha do `gcloud`
  (decisão D2 do `CAMPANHA_STATUS.md`). O que ela tem de evidência está no `campaign.log`.
- Valores em uso durante as execuções: o controlador rodou com o `config/campaign.yaml` da tag de
  pré-registro, que ainda traz os valores da campanha 2 como marcadores (d_on 3,1, d_off 2,9, tau 15 s,
  B 47, pisos de 0,05), com `limit_gate: alert`. É o previsto: a Seção 4 congela os valores só depois da
  calibração, e `calibrate_c3` refaz D, I e ALERT offline a partir das medidas brutas e do M_base. Os eventos
  gravados em tempo de execução não medem a regra da campanha 3 e não decidem nada. Só os descrevo: ALERT em 6
  dos 30 controles e BLOCK em 3 deles (`cal1_007`, `cal1_010`, `cal1_022`, com `action: none`), lidos de
  `events` nos `meta.json`.
- Braço MECADE da calibração (só confere o pipeline e a mitigação de s1, Seção 4): as 9 execuções têm ALERT,
  BLOCK e MITIGATION com os valores marcadores; em s1 o restart do alvo sai em 20 s e MITIGATION_CLIENTES em
  40, 45 e 40 s. No braço baseline de s1, MITIGATION em 430, 425 e 425 s e MITIGATION_CLIENTES em 455, 450 e
  445 s. A cascata rodou nos dois braços, como prevê a Seção 3.1.

## 6. O que a campanha 3 não testou

- Nenhuma execução oficial rodou. O plano oficial de 80 execuções fica sem dados.
- H1, H2 e H3 não foram testadas na campanha 3. Não há veredito, nem pela regra D1 nem pelo Holm, e não há
  diferença pareada, McNemar, falsos bloqueios oficiais nem overhead de auditoria.
- TSR não se aplica: é uma medida das execuções oficiais, e não há nenhuma.
- A previsão da Seção 6.1 para s3 (critério de recuperação NÃO ATENDE) não foi testada.
- Os vereditos das campanhas 1 e 2 continuam os mesmos, nas tags `mvc-2026-11-final` e
  `mvc-2026-11-c2-final`. A campanha 3 não muda nenhum deles.
- Uma regra nova (de B, de ALERT, de tau ou de pisos) só pode entrar numa campanha 4, com pré-registro próprio
  e calibração nova (Seção 7.2). Os dados desta calibração, inclusive a Seção 9 abaixo, só podem motivar o
  desenho dessa regra, e isso terá de ficar declarado no pré-registro da campanha 4.

## 7. Desvios e procedimento

- TTR de D da Fase 0 não calculado (Seção 2). A Seção 3.1 e o `CHANGELOG.md` de 16/11 previam relatá-lo. D
  não decidia nada, e o desfecho não muda.
- `calib_r1.out` fora do repositório (Seção 5). O manifesto de evidências cobre `data/calibracao/` sem ele.
- Nenhum outro desvio. O `config/campaign.yaml` e os arquivos protegidos ficaram como na tag de pré-registro,
  salvo a mudança de `clientes_apos_s` prevista na Seção 3.1 (Seção 1).
- Prazo: a calibração terminou em 17/11 às 05:17 (Brasília), dentro da data de corte (a) da Seção 7.3
  (18/11 às 23:59). O fechamento é pelo desfecho 2, não por prazo.

## 8. Custo

Não tenho fonte de faturamento para a campanha 3: o faturamento do provedor confirma com atraso e não li o
valor. Fica registrado só o tempo de cluster da calibração, de 16/11 10:27:34 a 17/11 08:17:38 UTC, cerca de
21 h 50 min com 3 nós `e2-standard-2` (`data/calibracao/campaign.log`), mais a Fase 0 de 16/11 00:30 a 02:50
UTC (`data/diagnostico/fase0.log`, sem o horário da subida dos nós) e a VM do controlador ligada o tempo todo.

## 9. Por que dois pilotos de s3 não alertaram (exploratório, não pré-registrado)

Esta seção é descritiva e exploratória. Nada dela estava no pré-registro, nada dela muda o desfecho, e ela
não propõe valor para nenhuma campanha. Refiz D com os pisos novos e passei as séries dos três pilotos de s3,
de 0 a 415 s, pelo `AxiomEvaluator` com d_on 3,9, d_off 3,7, tau 30 s, k = 2 e `limit_gate: alert`, os mesmos
passos de `_recalcula_D` e `_trilha` em `calibrate_c3`.

Como o ALERT funciona aqui (`AxiomEvaluator.step` em `mecade/axioms.py`): o contador `t_above` soma 5 s a
cada passo com pelo menos 2 dos 3 sinais acima de d_on e só zera quando os 3 ficam abaixo de d_off. Em s3 a
taxa de erro fica alta durante quase toda a falha, então o contador não zera, e o ALERT sai quando a soma dos
passos com 2 sinais acima de 3,9 chega a 30 s, seguidos ou não.

| Piloto | M_base p95 / p99 (s) | Pisos ativos | Passos com D_err > 3,9 | Passos com D_p95 > 3,9 | Passos com D_p99 > 3,9 | Maior D_p95 | Maior D_p99 | Passos com 2 sinais > 3,9 | `t_above` máximo antes de 415 s |
|---|---|---|---|---|---|---|---|---|---|
| `cal1_002` | 0,342 / 0,717 | p95 e p99 | 73 de 83 | 1 | 12 | 4,70 | 4,41 | 12 | 60 s (ALERT em 295 s) |
| `cal1_011` | 0,408 / 0,883 | nenhum | 73 de 83 | 0 | 3 | 3,56 | 3,97 | 3 | 15 s (em 345 s) |
| `cal1_020` | 0,542 / 0,896 | nenhum | 73 de 83 | 0 | 2 | 2,54 | 3,95 | 2 | 10 s (em 345 s) |

O que os dados mostram:

- Nos três pilotos a taxa de erro satura: D_err chega a 100 (erro de 1,0 sobre o piso de 0,01) e fica acima
  de d_on em 73 dos 83 passos. O erro sozinho é 1 sinal, e o ALERT pede 2.
- O segundo sinal teria de ser uma latência acima de 3,9 vezes a base. Nos três pilotos o p99 bruto passa
  pouco de 4,4 s (4,50, 4,39 e 4,43 s), e os D de latência ficam perto do limite: o maior D_p99 foi 3,97 em
  `cal1_011` e 3,95 em `cal1_020`, logo acima de 3,9, por 3 e 2 passos. O p95 nunca passou de 3,9 nesses dois.
- Os pisos novos não explicam esses dois casos: em `cal1_011` e `cal1_020` o M_base de p95 e de p99 fica acima
  dos pisos, e o D é o mesmo da regra sem piso. No piloto que alertou, `cal1_002`, os dois pisos estavam
  ativos (M_base abaixo deles), o que reduz D, e ainda assim ele somou 30 s.
- `cal1_002` alertou em 295 s porque juntou 12 passos com 2 sinais acima de 3,9, em grupos de até 4 passos
  (perto de 105 a 120 s, 290 a 310 s e 340 a 355 s). O contador ficou em 20 s de 120 a 290 s e fechou os 30 s
  em 295 s, 50 s antes do REACTIVE_FIRE de 345 s.
- Com d_on 3,9, o ALERT de s3 depende de a latência passar de quase 4 vezes a base em pelo menos 6 passos, e o
  s3 deste ambiente fica na borda disso. O d_on subiu de 3,1 (campanha 2) para 3,9 porque o P99 de `D_agr`
  nos controles subiu de 2,831 para 3,675 (Seção 3). Não verifiquei por que o ruído dos controles subiu, nem
  por que o p99 do s3 parece parar perto de 4,4 s; uma hipótese é o timeout dos clientes, que não testei.

Repito: essa leitura não muda o desfecho. A regra de viabilidade foi fixada antes dos dados e saiu inviável.

## 10. Limitações

- **Uma rodada de calibração.** Com 3 pilotos por cenário, 2 sem ALERT em s3 bastam para a inviabilidade.
  A regra pedia todos os 9, e foi assim que a fixei.
- **Regime único.** A calibração ficou toda no regime alto de M_base de p95 (Seção 4). Mesmo viável, ela não
  teria controle no regime baixo da campanha 2.
- **Fase 0 com n = 1 por desenho.** A H4 ficou não confirmada com condições lidas por tupla ao ClusterIP, e a
  condição 3 pode ter saído falsa por construção da leitura. O TTR de D não foi calculado.
- **Tau sem solução.** Um ALERT espúrio em 30 controles sobrou com tau 30 s (`cal1_007`). Com a calibração
  inviável, isso não chega a ser testado contra controles oficiais.
- Valem também as limitações da Seção 3.5 do `docs/PROTOCOLO_C3.md`, de `docs/EVIDENCIAS.md` e das campanhas
  1 e 2.

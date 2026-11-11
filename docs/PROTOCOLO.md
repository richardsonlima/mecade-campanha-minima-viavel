# Protocolo experimental da Campanha Mínima Viável

Este é o protocolo operacional que corresponde à Seção 4.4 da dissertação, na v0.8. Se alguma coisa
aqui divergir do texto, resolvo antes de começar as réplicas oficiais. Os critérios de aceitação vêm
da Tabela 4.6 e as hipóteses, da Tabela 4.1.

## 1. Pergunta

Diante do mesmo incidente (mesma falha, mesma duração, mesma carga), o MECADE detecta mais cedo e
restaura o estado estacionário mais rápido, com menos degradação acumulada, do que um baseline
reativo convencional? E faz isso sem disparar bloqueios quando não há falha nenhuma?

## 2. Desenho

O sistema-alvo é o Online Boutique v0.10.5 (11 microsserviços), com carga em malha aberta a 20 RPS
e semente fixa. Os braços são pareados, e sorteio a ordem dentro de cada par.

| Braço | Detecção | Ação |
|---|---|---|
| `baseline` | regra reativa no estilo do Prometheus: `p99 > 2× baseline` ou `erro > 5%`, verdadeira de forma contínua por 300 s | runbook do cenário, aplicado 120 s depois do disparo |
| `mecade` | axiomas ALERT, LIMIT e BLOCK (Listagem 3.1), avaliados a cada 5 s | a mesma ação do runbook, acionada pelo BLOCK |
| controle (`c0`) | axiomas, sem nenhuma injeção | qualquer BLOCK aqui conta como falso bloqueio |

A falha dura 600 s nos dois braços (`block.stop_injection: false`). Decidi que o BLOCK não desliga
a falha, ele só aciona a mitigação mais cedo. Se o BLOCK interrompesse a própria injeção, a
degradação acabaria por definição e o MECADE ganharia a comparação sem mérito nenhum.

Cenários (os registros completos estão em `scenarios/`):

| ID | Falha no Chaos Mesh | Alvo | Mitigação do runbook |
|---|---|---|---|
| s1 | NetworkChaos `delay` de 400 ms ± 100 ms, contínuo | uma instância do `productcatalogservice` | `rollout restart`, que substitui a instância |
| s2 | Schedule de NetworkChaos `delay` de 1500 ms ± 1000 ms, rajadas de 20 s a cada 60 s | uma instância do `currencyservice` | `rollout restart` |
| s3 | Schedule de PodChaos `pod-kill` a cada 45 s | `cartservice`, selecionado por rótulo | `scale` para 3 réplicas |

São 10 réplicas por combinação de cenário e braço, mais 10 de controle: 70 no total, umas 31 horas
de execução. Se o tempo apertar, uso `make plan-contingency`, que fica só com s2 (gray failure) e
s3 (pod kill) e mantém o pareamento.

## 3. Linha do tempo de uma réplica

```
reset (limpo injeções, volto réplicas para 1, reinicio o alvo) → warmup de 120 s
→ baseline de 300 s (M_base é a mediana de cada sinal nessa janela)
→ t = 0, INJECT → falha por 600 s → FAULT_END → 600 s de recuperação → limpeza e exportação
```

## 4. Desfechos

As definições exatas estão em `analysis/metrics.py`.

| Desfecho | Como calculo | Critério da Tabela 4.6 |
|---|---|---|
| TTD | primeiro ALERT (mecade) ou disparo da regra (baseline), contado a partir da injeção | H1, detecção e estabilidade da latência (ver Seção 8) |
| TTR | primeiro instante depois da mitigação em que `D_agr ≤ d_off` se mantém por 60 s | H2, recuperação |
| MTTR | TTR menos TTD | H2, recuperação |
| dentro do RTO | proporção de réplicas com `MTTR ≤ RTO` do cenário | H2, recuperação |
| classe | crítico, degradado ou aceitável, com a mesma regra offline nos dois braços | H2, classificação |
| área | soma de D_agr·Δt durante o incidente (`area_incidente`) | H1, detecção e estabilidade da latência |
| variabilidade de P95/P99 | desvio-padrão de cada sinal durante o incidente (`p95_std`, `p99_std`; ver Seção 8) | H1, detecção e estabilidade da latência |
| RRIndex_run | 1/(1 + V̄), com V igual à média dos D_m² | H2, convergência |
| falsos bloqueios | fração dos controles em que houve BLOCK, no máximo 1 em 10 (Seção 8) | H1, falsos bloqueios |
| Δ_audit,p95 | p95 do custo de enfileirar o evento, até 5 ms, nos controles com auditoria | H3, overhead |
| Δcpu | CPU do controlador nos controles com auditoria contra sem auditoria, até 8% | H3, overhead |
| TSR no incidente | 1 menos a taxa média de erro entre 0 e 600 s | só descritivo |

A vazão de 1000 eventos/s da Camada 6 não é exercida pela carga da campanha, como diz a Tabela 4.6.

Para a análise uso Wilcoxon pareado, delta de Cliff e intervalo de confiança de 95% por bootstrap
da mediana das diferenças, separado por cenário.

Dois rótulos diferentes para réplicas com problema:

- **`censurada`:** réplica com falha injetada que rodou até o fim, mas sem detecção ou sem restauração.
  Não é descartada: é reportada como censurada e entra na análise principal com o fim da janela como
  valor conservador (`TTD_capped`, `TTR_capped`, `MTTR_capped`).
- **`falha_execucao`:** réplica que falhou 3 vezes na execução e não tem dados. O par dela sai da
  comparação pareada e é relatado.

Limite de 10% de réplicas perdidas (minha decisão, 2026-11-11): contam as `falha_execucao` de qualquer
braço e as `censurada` do braço MECADE. As `censurada` do baseline não contam no limite, mas continuam
relatadas (log de parada, `desvios_execucao.jsonl` e análise). Passando do limite, a campanha para e eu
decido o que fazer. Uma
réplica refeita sai da ordem sorteada, e isso é um desvio, registrado em `desvios_execucao.jsonl`,
no `CHANGELOG.md` e em `CAMPANHA_STATUS.md`.

## 5. Decisões de implementação que preciso levar para a dissertação

| # | Decisão | Motivo | Onde está na v0.8 |
|---|---|---|---|
| D1 | O LIMIT integra `max(0, D_agr − deadband)` e não `D_agr` | Integrando o desvio bruto, o ruído normal do estado estacionário se acumula a janela inteira e estoura o B sem falha nenhuma. O teste `test_noise_below_deadband_never_violates_budget` mostra isso. | Listagem 3.1, Eq. 3.3 e Tabela 4.5 |
| D2 | `D = |M − M_base| / max(M_base, piso)` | Com a taxa de erro, o baseline é praticamente zero e o D explode | Eq. 3.2 e Tabela 4.5 |
| D3 | `k = 2` em `n = 3`, com p95, p99 e taxa de erro | p95 e p99 andam juntos, então a regra k-de-n fica mais permissiva do que o texto dá a entender | Tabela 4.5 e Seção 4.5, declarada como limitação |
| D4 | O BLOCK aciona a mitigação mas não para a injeção | Comparação justa, como expliquei na Seção 2 | Tabela 4.5 e discussão da Seção 4.4.1 |
| D5 | O controlador roda fora do cluster e avalia a cada 5 s via Prometheus | Mais simples e mais fácil de auditar | Tabela 4.5 e Seção 4.5: a latência de decisão em milissegundos não é medida |
| D6 | η_I e η_t ficam fora da campanha | As métricas exigem demanda escalonada, e a campanha opera em carga fixa. Ficam para a Fase 4, e as aproximações saíram do código | Tabela 4.5 e Seção 4.5 |
| D7 | RRIndex_run = 1/(1 + V̄), com V igual à média dos D_m² | Forma limitada que adotei na Seção 3.4, com uma escolha concreta de V | Eq. 3.11 e Tabela 4.5 |
| D8 | Só o BLOCK aciona a mitigação, o ALERT não age | Segue a hierarquia da Tabela 3.11 | Tabela 4.5 |

## 6. Calibração (Fase 1), antes das réplicas oficiais

A regra já está decidida e não muda depois de ver os dados. `make calibrar` a aplica:

1. Rodo 3 réplicas de controle e 1 piloto por cenário e braço (`make plan-calibracao run-calibracao`).
   Esses dados ficam em `data/calibracao/`, com `run_id` próprio, e não entram na análise.
2. `d_off` e `deadband` ficam no P99 de `D_agr` nos controles, arredondado para cima com uma casa decimal.
   `d_on` fica 0,2 acima de `d_off`.
3. `budget_B` é o menor valor em que nenhum controle passa de 50% de B e, no piloto de s1, o desvio
   acumulado não esgota B antes de 300 s de falha.
4. `tau_dwell` fica em 15 s, a não ser que os controles tenham ALERT espúrio. Nesse caso sobe de 5 em 5 s
   até 30 s.
5. Congelo o `config/campaign.yaml`, mudo o `campaign_id`, gero o plano com `make plan`, faço commit e só
   então começo as réplicas oficiais. Anoto a calibração no CHANGELOG.

Os pisos M_min aparecem na região calibrável da v0.8, mas a regra da Fase 1 não os ajusta. Ficam nos
valores de `config/campaign.yaml`.

## 7. O que esta campanha não testa

Declaro isso nos Capítulos 4 e 5:

- auditoria em blockchain (aqui só existe o perfil mínimo da Camada 6);
- *egress fault injection*;
- latência de decisão na escala de milissegundos (ver D5);
- generalização (Fase 4) e produção de verdade, porque a campanha cobre os estágios E1 e E2 da
  trilha de adoção.

## 8. Decisões do autor antes da primeira réplica oficial

Precisam estar registradas aqui, em commit anterior à primeira réplica oficial.

| Item | Situação |
|---|---|
| Limiar de falsos bloqueios (H1, Tabela 4.6) | decidido em 2026-11-11: no máximo 1 BLOCK em 10 réplicas de controle (`analysis.false_block_max_rate: 0.1` em `config/campaign.yaml`) |
| TTD como critério de aceitação ou métrica descritiva | decidido em 2026-11-11: critério de aceitação, vale a Tabela 4.6 da v0.8 |
| Limite de réplicas perdidas | decidido em 2026-11-11: 10%, contando `falha_execucao` de qualquer braço e `censurada` do MECADE; `censurada` do baseline é só relatada (Seção 4) |
| Medida da variabilidade de P95/P99 | a v0.8 não define. O código usa o desvio-padrão durante o incidente, a confirmar |

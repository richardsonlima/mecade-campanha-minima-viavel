# Protocolo experimental da Campanha Mínima Viável

Este é o protocolo operacional que corresponde à Seção 4.4 da dissertação. Se alguma coisa aqui
divergir do texto, resolvo antes de começar as réplicas oficiais.

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

| Desfecho | Como calculo | Critério da Tabela 4.2 |
|---|---|---|
| TTD | primeiro ALERT (mecade) ou disparo da regra (baseline), contado a partir da injeção | |
| TTR | primeiro instante depois da mitigação em que `D_agr ≤ d_off` se mantém por 60 s | recuperação |
| MTTR | TTR menos TTD, só quando houve detecção | recuperação, `≤ RTO` do cenário |
| área | soma de D_agr·Δt de t = 0 até o fim da janela | estabilidade |
| TSR no incidente | 1 menos a taxa média de erro entre 0 e 600 s | recuperação |
| classe | crítico, degradado ou aceitável, com a mesma regra offline nos dois braços | classificação |
| RRIndex_run | 1/(1 + V̄), com V igual à média dos D_m² | convergência |
| falsos bloqueios | fração dos controles em que houve BLOCK | falsos bloqueios |
| Δ_audit,p95 | p95 do custo de enfileirar o evento no caminho de decisão | overhead, até 5 ms |

Para a análise uso Wilcoxon pareado, delta de Cliff e intervalo de confiança de 95% por bootstrap
da mediana das diferenças, separado por cenário. Réplicas sem restauração ou sem detecção ficam
censuradas e aparecem à parte. A métrica `TTR_capped` usa o fim da janela nesses casos, o que é
conservador.

## 5. Decisões de implementação que preciso levar para a dissertação

| # | Decisão | Motivo | Onde atualizar |
|---|---|---|---|
| D1 | O LIMIT integra `max(0, D_agr − deadband)` e não `D_agr` | Integrando o desvio bruto, o ruído normal do estado estacionário se acumula a janela inteira e estoura o B sem falha nenhuma. O teste `test_noise_below_deadband_never_violates_budget` mostra isso. | Listagem 3.1, Eq. 3.6 e Tabela 3.11 |
| D2 | `D = |M − M_base| / max(M_base, piso)` | Com a taxa de erro, o baseline é praticamente zero e o D explode | Eq. 3.1 e 3.4 |
| D3 | `k = 2` em `n = 3`, com p95, p99 e taxa de erro | p95 e p99 andam juntos, então a regra k-de-n fica mais permissiva do que o texto dá a entender | Camada 3, correlação multi-sinal (declaro como limitação ou troco um sinal) |
| D4 | O BLOCK aciona a mitigação mas não para a injeção | Comparação justa, como expliquei na Seção 2 | Cap. 4, desenho da campanha |
| D5 | O controlador roda fora do cluster e avalia a cada 5 s via Prometheus | Mais simples e mais fácil de auditar | Limitação: a latência de decisão em milissegundos não é medida nesta campanha |
| D6 | η_I e η_t estão como aproximações | Ainda preciso conferir a definição exata em Al-Said Ahmad e Andras (2021) | Cap. 3, Tabela 3.4. Substituo antes da análise final |
| D7 | RRIndex_run = 1/(1 + V̄), com V igual à média dos D_m² | Forma limitada que adotei na Seção 3.4.2, agora com uma escolha concreta de V | Seção 3.4.2 |
| D8 | Só o BLOCK aciona a mitigação, o ALERT não age | Segue a hierarquia da Tabela 3.11 | |

## 6. Calibração (Fase 1), antes das réplicas oficiais

1. Rodo 3 réplicas de controle e olho a distribuição de `D_agr` sem falha. `d_off` e `deadband`
   ficam pelo menos no percentil 99 desse ruído, e `d_on` bem acima de `d_off`, para a histerese
   funcionar.
2. Rodo uma réplica piloto de cada cenário em cada braço e ajusto o `budget_B`. Nenhum controle
   pode chegar perto de B, e a classificação precisa separar os casos. Na simulação, com os valores
   iniciais, todas as réplicas com falha saíram como críticas, o que indica que o B está baixo para
   o tamanho das falhas.
3. Congelo o `config/campaign.yaml`, gero o plano com `make plan`, faço commit e só então começo as
   réplicas oficiais. Anoto a calibração no CHANGELOG. As réplicas de calibração ficam fora da análise.

## 7. O que esta campanha não testa

Declaro isso nos Capítulos 4 e 5:

- auditoria em blockchain (aqui só existe o perfil mínimo da Camada 6);
- *egress fault injection*;
- latência de decisão na escala de milissegundos (ver D5);
- generalização (Fase 4) e produção de verdade, porque a campanha cobre os estágios E1 e E2 da
  trilha de adoção.

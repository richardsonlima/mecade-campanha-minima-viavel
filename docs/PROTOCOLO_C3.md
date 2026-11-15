# Pré-registro da campanha 3 (`mvc-2026-11-c3`)

Escrevi este protocolo em 15/11/2026, depois de fechar a campanha 2 (tag `mvc-2026-11-c2-final`) e antes de
qualquer execução da campanha 3. Vale o `docs/PROTOCOLO.md` em tudo o que este documento e o
`docs/PROTOCOLO_C2.md` não mudam. A campanha 3 é um teste confirmatório novo, com calibração nova.

## 1. Pergunta e declaração

A campanha 2 mostrou que o MECADE em modo proteção cumpre o RTO onde a regra reativa não cumpre (s2 9/10,
s3 7/10), mas deixou três defeitos: piorou o s1 (TTR mediano 1042,5 s contra 525 s), teve 5 falsos bloqueios
em 10 controles, um deles sem ALERT, e a classe "crítico" não separa os braços. A campanha 3 pergunta: com
esses defeitos corrigidos na raiz, o MECADE reduz o TTR, cumpre o RTO mais vezes que a regra reativa nos
três cenários e mantém a taxa de falsos bloqueios em até 0,1?

Declaração, antes dos dados:

1. A campanha 2 não é reanalisada. Os resultados dela ficam como estão na tag `mvc-2026-11-c2-final` e no
   `docs/RESULTADOS_CAMPANHA_2.md`. Nenhuma regra nova é aplicada aos dados oficiais da campanha 2 para gerar
   um resultado novo dela.
2. Os dados oficiais das campanhas 1 e 2 só motivaram o desenho das regras (Seção 3). Nenhum valor numérico
   da campanha 3 sai deles: pisos, zona morta, d_on, tau e B saem da calibração nova (Seção 4).
3. Não ajusto parâmetro depois da calibração. Um resultado ruim na campanha 3 (veredito NÃO ATENDE, falso
   bloqueio acima do limiar, s1 pior que o baseline) entra na dissertação com o mesmo peso de um resultado bom.
4. As três campanhas entram na dissertação: a 1 como resultado principal, a 2 e a 3 como confirmações com
   desenho diferente, cada uma com o próprio pré-registro.

## 2. O que fica igual

- Sistema-alvo, versões (`versions.env`), cluster GKE (3 nós e2-standard-2 sob demanda, exclusão de
  manutenção) e controlador fora do cluster.
- Cenários s2, s3 e c0 sem mudança de registro. s1 muda só a mitigação (Seção 3.1). RTO de 180 s, contado da
  injeção, nos três.
- Braço baseline (regra reativa, `for` 300 s, atraso de 120 s), linha do tempo (warmup 120, baseline 300,
  falha 600, recuperação 600, passo 5 s) e `recovery.hold` de 60 s.
- `k` = 2 de 3 sinais (p95, p99, error_rate), agregação `max`, histerese d_on = d_off + 0,2 e a regra de tau
  (15 s, sobe de 5 em 5 até 30 s, `tau_sem_solucao` 30).
- `block.stop_injection: false`: o incidente dura 600 s nos dois braços.
- Hipóteses H1, H2 e H3, mapa de critérios do `docs/PROTOCOLO_C2.md` (Seção 4) com a única mudança da Seção
  5 abaixo, regra de veredito D1, McNemar exato, Holm por família como análise secundária, "≤" nos limiares.
- Limite de 10% de perdidas, regra das 3 falhas e tratamento das censuradas.

## 3. Mudanças e a evidência que motiva cada uma

### 3.1 s1: a mitigação renova as conexões dos clientes

Evidência (séries por réplica da campanha 2, motivação apenas):

- Na regra reativa (restart perto de 425 s) e na campanha 1 (restart perto de 330 s), o restart acontece
  depois de a falha passar a falhar rápido (a partir de uns 60 s: p95 perto de 0,02 s e erro perto de 0,95,
  sem endpoints prontos), e o serviço volta de 45 a 180 s depois, ainda com a falha ativa.
- No braço MECADE o restart sai entre 10 e 20 s, quando o pod antigo ainda tem conexões estabelecidas e o
  netem ativo. As requisições ficam presas até o timeout de 3 s (p95 perto de 4,9 s). A volta principal vem
  em momentos diferentes (de 295 a 705 s depois do restart), sem relação com o fim da falha em 600 s. Depois
  dela sobra um resíduo de 4,3% a 4,4% de erro, igual a 1/23, a fração de chamadas do `/cart/checkout`, que
  passa pela conexão própria do checkoutservice.
- O resíduo termina de 975 a 1070 s depois do restart em 9 de 10 réplicas, a escala do timeout de
  retransmissão do TCP (`tcp_retries2` = 15, uns 925 s) numa conexão cujo FIN ou RST se perdeu.
- No s2 o restart também sai com a falha ativa (65 a 70 s) e funciona: o pod antigo morre depois do fim da
  rajada de 20 s, e o fechamento das conexões sai.

Hipótese de mecanismo (H4, provável e não confirmada): o restart com o netem ativo derruba a interface do
pod antigo com os pacotes de fechamento na fila, e os clientes gRPC (frontend, checkoutservice) ficam com
conexões mortas até o TCP desistir. Descartei como causa principal: a falha ser reaplicada no pod novo (o
seletor por nome não pega o pod novo, e a volta não acompanha o fim da falha), a perda de cache (a escala é de
minutos) e a janela do ALERT_CLEAR (a telemetria bruta do cliente fica degradada; o avaliador não é zerado).

Mudança: depois do restart do alvo, a mitigação de s1 reinicia frontend, checkoutservice e
recommendationservice (`mitigacao.clientes` em `scenarios/s1_latencia_productcatalog.yaml`, versão 2;
evento `MITIGATION_CLIENTES`). Vale nos dois braços.

Fase 0 (diagnóstico, antes da calibração, 4 execuções fora do plano oficial e fora da calibração, prefixo
`diag_`, dados versionados em `data/diagnostico/`):

| Execução | O que faz |
|---|---|
| A | s1, restart só do alvo em t = 15 s |
| B | s1, restart só do alvo em t = 120 s |
| C1, C2 | s1, restart do alvo em t = 15 s e dos clientes depois de `clientes_apos_s` |

Em todas registro `kubectl get pods -w`, endpoints do alvo, eventos do namespace, restartCount, `ss -tni` no
frontend e no checkoutservice (contêiner efêmero de `kubectl debug`) a cada 15 s e o tempo do rollout do alvo.

Regras da Fase 0, fixadas agora:

- `clientes_apos_s` = tempo do rollout do alvo medido em A, B, C1 e C2 (o maior), mais 10 s, arredondado para
  cima em 5 s, entre 20 e 60 s. O valor provisório no cenário é 45 s.
- A cascata fica se, em C1 e C2, error_rate ≤ 0,01 e p95 ≤ 2 × M_base de p95 por 60 s seguidos começam até
  150 s depois do restart do alvo. Se não, `clientes` sai do cenário, s1 volta à mitigação da campanha 2 e
  registro como previsão que o TTR de s1 no braço MECADE será pior que no baseline.
- H4 fica confirmada se A mostrar conexões ESTABLISHED para o IP do pod antigo, depois de ele sair dos
  endpoints, com retransmissões crescentes, e B e C não mostrarem. Relato o resultado nos dois sentidos.

### 3.2 LIMIT condicionado ao ALERT

Evidência: o controle 070 da campanha 2 teve BLOCK sem nenhum ALERT, e a réplica 020_s3 também. A integral
cresce com um único sinal acima da zona morta, o que contradiz o k-de-n do ALERT. Nos controles a taxa de erro
foi sempre 0, então todo o ruído vem de p95 e p99, dois quantis do mesmo histograma.

Mudança: `axioms.limit_gate: alert` (D3 em `mecade/axioms.py`). O desvio acumulado só cresce enquanto o ALERT
está ativo. BLOCK sem ALERT deixa de ser possível. O padrão `none` mantém o comportamento das campanhas 1 e 2.

### 3.3 Pisos de latência calibrados

Evidência: nos 33 controles das campanhas 1 e 2, a correlação de Spearman entre o I do controle e o p99 de
base é -0,68 (p = 1,3e-5): a cauda de ruído vem do denominador pequeno. Na campanha 2 o p95 de base caiu de
uns 0,23 s para uns 0,10 s a partir da execução 028, e de vez a partir da 045. Os 5 controles com falso
bloqueio estão todos no regime baixo, e nenhum dos 5 do regime alto bloqueou (Fisher exato bilateral,
p = 0,008). Os 10 controles da calibração da campanha 2 eram todos do regime alto (p95 de base ≥ 0,22 s):
calibração e oficial não eram trocáveis.

Mudança: os pisos de p95 e p99 passam a ser a mediana de M_base dos controles da calibração. O piso da taxa
de erro fica em 0,01. Com piso, uma queda do nível de base não infla D.

### 3.4 Regra de B

Evidência: com o LIMIT condicionado ao ALERT, o I dos controles de calibração fica em 0 ou perto disso, e a
regra da campanha 2 (B = 2 × maior I dos controles) degenera em B perto de 0. Com B = 47 na campanha 2, o B
ficou dentro da cauda de ruído dos controles oficiais.

Mudança: B = menor I condicionado ao ALERT 30 s depois do primeiro ALERT, entre os 9 pilotos do braço
baseline da calibração (3 por cenário), arredondado para baixo na dezena. A regra é viável só se B ≥ 2 × o
maior I condicionado dos 30 controles de calibração e se todo piloto tiver ALERT antes da ação da regra
reativa (415 s). Se não for viável, paro e registro, sem trocar a regra.

Por que os 30 s: deixam o BLOCK no máximo 30 s depois de um ALERT confirmado no piloto mais brando, e a
margem de 2× sobre o ruído é a mesma das campanhas 1 e 2. O B é um limite de proteção, ligado à confirmação
do incidente, e não à duração da falha, que foi o motivo de a condição (b) da campanha 1 sair.

### 3.5 Calibração maior e espalhada no tempo

Evidência: com B no máximo de n controles e trocabilidade, a chance de um controle novo passar de B é no
máximo 1/(n + 1). Com 10 controles, a chance de a taxa real passar de 0,1 é 0,35; com 30, 0,04. A campanha 2
mostrou que a trocabilidade não vale se a calibração cair num regime só.

Mudança: 30 controles de calibração (antes 10), na ordem sorteada junto com os 18 pares (3 por cenário), e
M_base de p95 de cada execução vira covariável registrada (Seção 5).

### 3.6 A classe "crítico" sai

Evidência: a classe é calculada com a mesma integral, a mesma zona morta e o mesmo B do LIMIT
(`analysis/metrics.py`, classificação offline). No braço MECADE da campanha 2, "crítico" coincide com BLOCK
em 40 de 40 réplicas, e todas as 30 do baseline são "crítico". A classe mede o detector, não o sistema.

Mudança: a classe tripartite sai do relatório da campanha 3. A exposição fica descrita por `area_incidente`
(já no critério de H1) e por I_max/B, que reporto sem critério.

## 4. Fase 1: calibração

Plano separado do oficial (`make plan-calibracao`, prefixo `cal1_`, semente própria): 30 controles e 3 pares
por cenário, 48 execuções. Nenhum dado das campanhas 1 e 2 e nenhum dado da Fase 0 entra na calibração. A
regra fica em `calibrate_c3()` de `analysis/calibrate.py` (`calibracao.regra_B: alerta_piloto`):

| Parâmetro | Regra |
|---|---|
| pisos de p95 e p99 | mediana de M_base nos 30 controles |
| piso de error_rate | 0,01, como nas campanhas 1 e 2 |
| d_off = deadband | P99 de D_agr nos controles, com os pisos novos, para cima na primeira casa |
| d_on | d_off + 0,2 |
| tau_dwell | 15 s, sobe de 5 em 5 até 30 s se houver ALERT espúrio; se nada zerar, 30 s e a contagem vai para o relatório |
| limit_gate | alert |
| B | Seção 3.4 |

Os pares do braço MECADE só conferem o pipeline e a mitigação de s1. Congelo pisos, d_on, d_off, deadband,
tau e B no `config/campaign.yaml` antes da primeira execução oficial.

## 5. Critérios, limiares e veredito

| H | Critério | Componentes que decidem | Em relação à campanha 2 |
|---|---|---|---|
| H2 | Recuperação | `TTR_capped` menor; `rto_ok_ttr` maior, McNemar exato | igual |
| H2 | Convergência | `RRIndex_run` maior | igual |
| H1 | Detecção e estabilidade | `TTD_capped`, `area_incidente`, `p95_std`, `p99_std` menores | igual |
| H1 | Falsos bloqueios | taxa ≤ 0,1, com 20 controles (no máximo 2 BLOCK) | n de 10 para 20; limiar igual |
| H3 | Overhead da auditoria | Δ_audit,p95 ≤ 5 ms e Δcpu ≤ 8% | igual |

A classe tripartite sai (Seção 3.6). RTO, hold e o limiar de falsos bloqueios ficam: mudar qualquer um deles
mudaria a pergunta.

Também reporto, sem critério: MTTR, I_max/B, log10 V̄, TSR, taxa de ALERT nos controles, BLOCK sem ALERT
(esperado 0 por construção), o tempo entre ALERT e BLOCK e, em s1, o tempo entre MITIGATION e
MITIGATION_CLIENTES. O regime de base (M_base de p95 de cada execução) vai para o relatório e para uma análise
estratificada descritiva (abaixo e acima da mediana da calibração). Ela não decide veredito.

## 6. n e poder

Plano oficial: 10 execuções por cenário e braço e 20 controles, 80 no total, ordem sorteada com a semente
`20261115`.

- `rto_ok_ttr`: a regra reativa não cumpre o RTO por construção (300 s de `for` mais 120 s de atraso > 180 s),
  então todo par discordante é a favor do MECADE e o McNemar exato com n = 10 rejeita com 6 ou mais
  sucessos. Poder: 0,63 se a taxa real do MECADE for 0,6; 0,85 se for 0,7; 0,998 se for 0,9. Na campanha 2 foi
  0,9 em s2 e 0,7 em s3. Com n = 12 o poder em 0,7 seria 0,96, mas não cabe no prazo (Seção 8).
- `TTR_capped` (Wilcoxon pareado): poder de 0,79 com n = 10 para efeito padronizado de 1,0 (simulação com
  4000 repetições). Os efeitos da campanha 2 em s2 e s3 foram muito maiores.
- Falsos bloqueios: com 20 controles e no máximo 2 BLOCK, a chance de passar é 0,92 se a taxa real for 0,05.
  Com 0 em 20, o limite superior unilateral de 95% (Clopper-Pearson) é 0,139.

## 7. Desvios previstos

- s3: com o LIMIT condicionado ao ALERT, o BLOCK de s3 deve sair mais tarde que na campanha 2 (o ALERT de s3
  saiu com mediana de 100 s nas séries anteriores, contra uns 50 s do BLOCK da campanha 2). `rto_ok_ttr` em s3
  pode cair abaixo de 7/10. Se cair, é resultado.
- s1: se a Fase 0 tirar a cascata, prevejo s1 pior que o baseline de novo (Seção 3.1).
- Regime de base: se o p95 de base mudar de nível durante a campanha, reporto e mantenho a análise.
- Calibração inviável (Seção 3.4) ou tau sem solução: paro, registro e decido com os números na mão, sem
  rodar o plano oficial.
- Prazo: se o plano oficial não começar até 17/11 às 8h, não reduzo n. A campanha segue e, se não fechar a
  tempo da dissertação, entra como incompleta, com o que tiver rodado.

## 8. Ordem dos passos e custo

1. Commit deste protocolo, do config e do código no branch `campanha-3`; tag anotada `mvc-2026-11-c3-prereg`;
   push do branch e da tag.
2. Fase 0 (4 execuções, umas 2 h de cluster), regra da Seção 3.1, commit do cenário de s1 com o valor final.
3. Calibração (48 execuções, umas 22 h), `make calibrar`, congelamento, commit, tag
   `mvc-2026-11-c3-calibracao` e push, antes da primeira execução oficial.
4. 80 execuções oficiais (umas 36 h), backup em três cópias (VM, bucket em `oficial-c3/`, `calibracao-c3/`
   e `diagnostico-c3/`, local).
5. Análise, `docs/RESULTADOS_CAMPANHA_3.md`, tag `mvc-2026-11-c3-final`, `make evidencias ESTRITO=1` e
   conferência das três cópias.

São umas 60 h de cluster no total, com 27 min por execução como na campanha 2.

## 9. Dados das campanhas anteriores neste branch

O branch `campanha-3` sai do `campanha-2` e não traz os dados nem as figuras da campanha 2, para que nenhum
controle anterior entre na calibração da campanha 3 e o manifesto de evidências cubra só a campanha 3. Os
dados da campanha 1 ficam na tag `mvc-2026-11-final` e os da campanha 2 na tag `mvc-2026-11-c2-final`.

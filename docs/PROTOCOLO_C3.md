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
2. Usei os dados oficiais e de calibração das campanhas 1 e 2 para desenhar as regras, e não só para
   motivá-las: testei regras alternativas e a regra final nesses dados. A Seção 1.1 lista tudo o que olhei e
   o resultado de cada teste. Nenhum valor numérico da campanha 3 sai deles: pisos, zona morta, d_on, tau e B
   saem da calibração nova (Seção 4). O limiar de regime de 0,16 s (Seção 3.5) é a única constante tirada
   desses dados, só para estratificar e relatar, sem efeito em decisão nem em veredito.
3. Não ajusto parâmetro depois da calibração. Um resultado ruim na campanha 3 (veredito NÃO ATENDE, falso
   bloqueio acima do limiar, s1 pior que o baseline) entra na dissertação com o mesmo peso de um resultado bom.
4. As três campanhas entram na dissertação: a 1 como resultado principal, a 2 e a 3 como confirmações com
   desenho diferente, cada uma com o próprio pré-registro.

### 1.1 O que já olhei nos dados das campanhas 1 e 2 (exploração)

Tudo abaixo é exploração feita antes deste pré-registro, sobre os dados das tags `mvc-2026-11-final` e
`mvc-2026-11-c2-final`. Nenhum desses números fixa valor da campanha 3. As regras das Seções 3, 4, 5 e 7 ficam
congeladas a partir da tag `mvc-2026-11-c3-prereg`: a campanha 3 confirma essas regras, não as explora.
Qualquer mudança depois da tag é desvio (Seção 8.1).

1. **Quatro regras de LIMIT nos controles.** I máximo nos controles, com os parâmetros de cada campanha:

   | Grupo | R0 (regra das campanhas 1 e 2) | R1 (≥ 2 sinais acima da zona morta) | R2 (2º maior D) | R3 (só com ALERT) |
   |---|---|---|---|---|
   | C1 oficiais | 489 | 486 | 214 | 325 |
   | C2 oficiais | 713 | 450 | 329 | 320 |
   | C2 calibração | 23,5 | 3,9 | 1,8 | 0 |

   R1 falha na fase de falha rápida do s1 (p95 cai abaixo da base). Escolhi R3 (Seção 3.2).
2. **Regra final nos controles oficiais.** R3 com pisos de p95 e p99 iguais à mediana de M_base da calibração
   da campanha 2 (p95 0,277 s, p99 0,725 s; zona morta 2,5): C2 oficiais com I > 0 em 0 de 10; C1 oficiais em
   3 de 10, com I máximo de 253,2. Os tempos de ALERT ficaram iguais aos dos pisos antigos: s1 perto de 20 s,
   s2 perto de 80 s, s3 com mediana perto de 100 s e máximo de 165 s (braço baseline de C1 e C2, 20 réplicas;
   o §6.1 usa um conjunto maior, de 30 réplicas).
3. **Regra de B simulada.** B = menor I sob R3, 30 s depois do primeiro ALERT, nas séries de C1 e C2: mínimos
   de 1213 (s1), 1564 (s2) e 1814 (s3), logo B perto de 1210, contra 2 × 253 = 506 do maior ruído observado.
   `calibrate_c3` sobre a calibração da campanha 2 (1 piloto por cenário) deu B = 1680, viável. Escolhi a
   janela de 30 s e a margem de 2× sabendo que a regra é viável nesses dados.
4. **Pisos e regime.** Spearman entre I do controle e p99 de base (-0,68, p = 1,3e-5), a troca de regime da
   campanha 2 e o Fisher exato (p = 0,008) da Seção 3.3; os níveis de M_base de p95 da Seção 3.5.
5. **Mecanismo de s1.** As séries por réplica da Seção 3.1.
6. **Previsão de H2.** Os tempos de ALERT sob a regra final e os tempos entre mitigação e restauração da
   campanha 2, usados na Seção 6.1.

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
- Tratamento das censuradas. O limite de 10% de perdidas e a regra das 3 falhas valem no plano oficial, com o
  desfecho fechado da Seção 7.2; na Fase 0 e na calibração valem as regras da Seção 7.1.
- TTR procurado depois do primeiro evento MITIGATION (`analysis/metrics.py`), não depois de
  MITIGATION_CLIENTES. É intencional: uma volta que acontece antes da cascata dos clientes conta como volta.

## 3. Mudanças e a evidência que motiva cada uma

### 3.1 s1: a mitigação renova as conexões dos clientes

Evidência (séries por réplica da campanha 2, exploração da Seção 1.1):

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

Fase 0 (diagnóstico, antes da calibração, 5 execuções fora do plano oficial e fora da calibração, prefixo
`diag_`, dados versionados em `data/diagnostico/`):

| Execução | O que faz | Para quê |
|---|---|---|
| A | s1, restart só do alvo em t = 15 s | condição do braço MECADE da campanha 2 (teste de H4) |
| B | s1, restart só do alvo em t = 120 s | restart com a falha já em fase de falha rápida (controle de H4) |
| C1, C2 | s1, restart do alvo em t = 40 s e dos clientes depois de `clientes_apos_s` = 45 s | BLOCK esperado da campanha 3 em s1 (ALERT perto de 20 s, mais até 30 s); decide a cascata |
| D | s1, restart do alvo em t = 425 s e dos clientes depois de 45 s | condição do braço baseline; só relato |

Em todas registro `kubectl get pods -w`, endpoints do alvo, eventos do namespace, restartCount, `ss -tni` no
frontend e no checkoutservice (contêiner efêmero de `kubectl debug`) a cada 15 s e o tempo do rollout do alvo.
O tempo do rollout é medido do início do `kubectl rollout restart deployment/<alvo>` até o fim, com sucesso, do
`kubectl rollout status deployment/<alvo>`.

Regras da Fase 0, fixadas agora:

- `clientes_apos_s` = o maior tempo do rollout do alvo medido nas execuções com dado (A, B, C1, C2 e D), mais
  10 s, arredondado para cima em 5 s e cortado ao intervalo [20, 60] s: um valor abaixo de 20 vira 20, acima de
  60 vira 60, e o corte não invalida a Fase 0. O valor provisório no cenário é 45 s.
- A cascata fica se, em C1 e em C2, error_rate ≤ 0,01 e p95 ≤ 2 × M_base de p95 por 60 s seguidos começam até
  150 s depois do restart do alvo. Se não, `clientes` sai do cenário, s1 volta à mitigação da campanha 2 e
  registro como previsão que o TTR de s1 no braço MECADE será pior que no baseline.
- H4 fica confirmada se valerem as três condições, todas lidas no `ss -tni` do frontend e do checkoutservice:
  (1) em A, há conexão ESTABLISHED para o IP do pod antigo depois de ele sair dos endpoints, com retransmissões
  crescentes entre duas coletas seguidas; (2) em B, não há conexão para o IP do pod antigo depois de ele sair
  dos endpoints; (3) em C1 e em C2, as conexões para o IP do pod antigo somem até 15 s depois de
  MITIGATION_CLIENTES. Entre o restart do alvo e MITIGATION_CLIENTES, C pode mostrar conexões presas, como A,
  e isso não conta contra a H4. Faltando qualquer condição, a H4 não é confirmada. Relato o resultado nos dois
  sentidos.
- D não decide nada. Relato o TTR de D ao lado dos TTR do baseline de s1 da campanha 2 (mediana 525 s), como
  indicação de o quanto a cascata muda o braço baseline. Com uma execução só, isso é indicação, não medida.

Limitações declaradas: com o restart em 40 s, a janela da regra da cascata ("até 150 s depois do restart")
termina em 190 s da injeção, acima do RTO de 180 s. A cascata pode ficar sem que o s1 cumpra o RTO; isso é
coerente, porque o critério que decide é o TTR, mas fica declarado. A Fase 0 só testa o restart em 15, 40, 120 e
425 s: um BLOCK de s1 fora de cerca de 25 a 55 s na campanha 3 fica sem teste da cascata. C1 e C2 testam a
cascata com 45 s; se o valor final for outro, a campanha roda com um
atraso que a Fase 0 não testou, e não repito a Fase 0 por isso. O efeito da cascata no baseline fica medido só
por D. Se a cascata piorar o baseline, a vantagem do MECADE em s1 fica inflada, e isso entra na discussão.

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
baseline da calibração (3 por cenário), arredondado para baixo na dezena. A regra é viável só se B > 0,
B ≥ 2 × o maior I condicionado dos controles de calibração e todo piloto tem ALERT antes da ação da regra
reativa (415 s). Se não for viável, vale o desfecho fechado da Seção 7.2.

Por que os 30 s: deixam o BLOCK no máximo 30 s depois de um ALERT confirmado no piloto mais brando. O B é um
limite de proteção, ligado à confirmação do incidente, e não à duração da falha, que foi o motivo de a condição
(b) da campanha 1 sair.

O que a margem de 2× garante de fato: quase nada, na maioria dos casos. O tau sobe até zerar os ALERTs
espúrios dos controles de calibração (Seção 4). Quando zera, nenhum controle tem ALERT, o I condicionado de
todos é 0 e a condição B ≥ 2 × 0 é vazia. A margem só atua quando nenhum tau até 30 s zera os ALERTs espúrios
(`tau_sem_solucao`). A garantia real, nesse caso comum, é outra: um controle novo só bloqueia se tiver ALERT
espúrio, e, com 0 ALERT espúrio em n controles de calibração trocáveis com o oficial, a chance de um controle
novo ter ALERT espúrio é no máximo 1/(n + 1), 1/31 com 30 controles. Isso depende de trocabilidade, e a
Seção 1.1 (item 2) já mostra que ela falha entre campanhas: a regra final, com os pisos da calibração da
campanha 2, deu I > 0 em 3 de 10 controles oficiais da campanha 1. A campanha 2 dá a comparação certa
(calibração e oficial do mesmo cluster) e deu 0 de 10.

### 3.5 Calibração maior, sem garantia de cobrir os dois regimes de base

Evidência: com B no máximo de n controles e trocabilidade, a chance de um controle novo passar de B é no
máximo 1/(n + 1). Com 10 controles, a chance de a taxa real passar de 0,1 é 0,35; com 30, 0,04. A campanha 2
mostrou que a trocabilidade não vale se a calibração cair num regime só.

Mudança: 30 controles de calibração (antes 10), na ordem sorteada junto com os 18 pares (3 por cenário), e
M_base de p95 de cada execução vira covariável registrada (Seção 5).

O que isso não garante: a calibração é um bloco contínuo de umas 22 h, antes do plano oficial. A ordem
sorteada espalha os controles dentro do bloco, mas não força os dois regimes. Na campanha 2 a troca de regime
veio depois de umas 12 h e de umas 20 h de execução, e não achei a causa. A calibração pode cair inteira num
regime, e o oficial em outro. Não tenho como forçar a cobertura sem saber a causa.

Por que o piso pela mediana protege a H1 mesmo assim: o denominador de D é max(M_base, piso).

- Calibração no regime alto e oficial no baixo: o piso fica acima do M_base dos controles oficiais, então D
  é menor que sem piso. Não há inflação de D, nem de falso bloqueio. O custo é sensibilidade: nas réplicas com
  falha injetada, D também sai menor, o que pode atrasar ALERT e BLOCK (efeito em H2, não em H1).
- Calibração no regime baixo e oficial no alto: o M_base oficial fica acima do piso, e D é o mesmo da regra
  sem piso. No regime alto a campanha 2 não teve falso bloqueio (0 de 5).

O caso que sobra sem proteção é um regime novo, abaixo do menor M_base da calibração e com ruído relativo maior.
Esse é o caso que o critério de quebra de trocabilidade abaixo detecta.

Limiar de regime, fixado agora e fora dos dados da campanha 3: M_base de p95 = 0,16 s. Vem da exploração da
Seção 1.1 e declaro isso: na campanha 1 os 70 M_base de p95 ficaram em 0,212 s ou mais; na campanha 2, 30
ficaram abaixo de 0,16 s (mediana 0,11 s) e 40 em 0,16 s ou mais (mediana 0,25 s), com só 2 entre 0,15 e
0,17 s; os 16 da calibração da campanha 2 ficaram em 0,219 s ou mais. O 0,16 s fica no vão entre os dois
regimes, perto do ponto médio de 0,10 e 0,23 s. Ele serve para a análise estratificada e para relatar a
composição de regime da calibração e do oficial. Não entra em nenhuma decisão do controlador nem no veredito.

Quebra de trocabilidade: registro como quebra se pelo menos uma destas valer, e então qualifico o resultado
de falsos bloqueios no relatório, sem mudar nada:

1. mais de 20% dos controles oficiais (5 ou mais de 20) com M_base de p95 abaixo do menor M_base de p95 dos
   controles de calibração;
2. mais de 20% dos controles oficiais num regime (pelo limiar de 0,16 s) que tem menos de 3 controles na
   calibração.

### 3.6 A classe "crítico" sai

Evidência: a classe é calculada com a mesma integral, a mesma zona morta e o mesmo B do LIMIT
(`analysis/metrics.py`, classificação offline). No braço MECADE da campanha 2, "crítico" coincide com BLOCK
em 40 de 40 réplicas, e todas as 30 do baseline são "crítico". A classe mede o detector, não o sistema.

Mudança: a classe tripartite sai do relatório da campanha 3. A exposição fica descrita por `area_incidente`
(já no critério de H1) e por I_max/B, que reporto sem critério.

## 4. Fase 1: calibração

Plano separado do oficial (`make plan-calibracao RODADA=1`, prefixo `cal1_`, semente própria 20262115, a do oficial mais 1000): 30 controles e
3 pares por cenário, 48 execuções. Nenhum dado das campanhas 1 e 2 e nenhum dado da Fase 0 entra na
calibração. A regra fica em `calibrate_c3()` de `analysis/calibrate.py` (`calibracao.regra_B: alerta_piloto`):

| Parâmetro | Regra |
|---|---|
| pisos de p95 e p99 | mediana de M_base nos controles válidos |
| piso de error_rate | 0,01, como nas campanhas 1 e 2 |
| d_off = deadband | P99 de D_agr nos controles, com os pisos novos, para cima na primeira casa |
| d_on | d_off + 0,2 |
| tau_dwell | 15 s, sobe de 5 em 5 até 30 s se houver ALERT espúrio; se nada zerar, 30 s e a contagem vai para o relatório |
| limit_gate | alert |
| B | Seção 3.4 |

Calibração válida: no mínimo 27 dos 30 controles e os 9 pilotos do braço baseline com dados (Seção 7.1). Os
pares do braço MECADE só conferem o pipeline e a mitigação de s1; a falta deles não invalida a calibração e
fica relatada. Com menos de 30 controles válidos, o limite de 1/(n + 1) da Seção 3.4 passa a 1/(n + 1) com o
n real (1/28 com 27).

Tau sem solução não é, sozinho, calibração inviável: o tau fica em 30 s, a contagem de ALERTs espúrios vai
para o relatório e a viabilidade se decide pela condição de B da Seção 3.4, que nesse caso tem conteúdo.

Congelo pisos (em `signals.p95.floor` e `signals.p99.floor`), d_on, d_off, deadband, tau e B (em `axioms`) no
`config/campaign.yaml` antes da primeira execução oficial, copiados da saída de `calibrate_c3`, e confiro o
config contra essa saída antes da tag de calibração.

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

O critério de falsos bloqueios é uma estimativa pontual comparada ao limiar, como nas campanhas 1 e 2, e não um
teste. A chance de passar (no máximo 2 em 20) é 0,92 se a taxa real for 0,05, 0,68 se for 0,10, 0,40 se for
0,15 e 0,21 se for 0,20. Ao lado do veredito relato o IC de Clopper-Pearson da taxa (com 0 em 20 o limite
superior unilateral de 95% é 0,139; com 2 em 20, 0,283).

Também reporto, sem critério: MTTR, I_max/B, log10 V̄, TSR, taxa de ALERT nos controles, BLOCK sem ALERT
(esperado 0 por construção), o tempo entre ALERT e BLOCK e, em s1, o tempo entre MITIGATION e
MITIGATION_CLIENTES. O regime de base (M_base de p95 de cada execução) vai para o relatório, com a composição
da calibração e do oficial pelo limiar de 0,16 s (Seção 3.5), e para uma análise estratificada descritiva
(abaixo de 0,16 s e em 0,16 s ou mais). Ela não decide veredito.

## 6. n e poder

Plano oficial: 10 execuções por cenário e braço e 20 controles, 80 no total, ordem sorteada com a semente
`20261115`. Os dois planos já estão gerados e versionados neste commit (o sorteio é determinístico, e gerei
duas vezes com o mesmo hash):

| Plano | Arquivo | Execuções | SHA-256 |
|---|---|---|---|
| oficial | `data/plan_mvc-2026-11-c3.csv` | 80 | `359cd792ca39b685d2417cc940d01a72eafecc2b9cdc762fe715915b2bb88b41` |
| calibração | `data/calibracao/plan_r1.csv` | 48 | `916663e947ed6d791c8e5a3f33b8d231be6be9a907b922ce87cf20c8b8a6a265` |

- `rto_ok_ttr`: a regra reativa não cumpre o RTO por construção (300 s de `for` mais 120 s de atraso > 180 s),
  então todo par discordante é a favor do MECADE e o McNemar exato com n = 10 rejeita com 6 ou mais
  sucessos. Poder: 0,63 se a taxa real do MECADE for 0,6; 0,85 se for 0,7; 0,998 se for 0,9. Na campanha 2 foi
  0,9 em s2 e 0,7 em s3. Com n = 12 o poder em 0,7 seria 0,96, mas não cabe no prazo (Seção 8).
- `TTR_capped` (Wilcoxon pareado): poder de 0,79 com n = 10 para efeito padronizado de 1,0 (simulação com
  4000 repetições). Os efeitos da campanha 2 em s2 e s3 foram muito maiores.
- Falsos bloqueios: Seção 5.

### 6.1 Previsão de H2 por cenário

Modelo simples, com dados das campanhas 1 e 2 (Seção 1.1, item 6), declarado como estimativa grosseira:
restauração = ALERT + L + atraso, com L o tempo entre ALERT e BLOCK (entre 5 e 30 s pela regra de B) e o
atraso entre a mitigação e a restauração tirado da campanha 2. Os tempos de ALERT são os da regra final
(pisos da calibração da campanha 2); em s3 só entram as réplicas sem mitigação antes de 400 s (baseline
de C1 e C2 e MECADE de C1). Combino todos os pares (ALERT,
atraso), supondo que um não depende do outro, e o atraso não depende do instante da mitigação.

| Cenário | ALERT (regra final) | Atraso até restaurar | P(rto_ok) por réplica | `rto_ok_ttr` esperado | Poder do McNemar (≥ 6/10) |
|---|---|---|---|---|---|
| s2 | 75 a 85 s (40 réplicas de C1 e C2) | 45 a 70 s em 9 de 10, uma com 230 s (campanha 2, mitigação em 65 a 70 s) | 0,89 a 0,90 | 9/10 | 0,99 ou mais |
| s3 | mediana 100 s, 60 a 265 s (30 réplicas: baseline de C1 e C2 e MECADE de C1, sem mitigação antes de 400 s) | mediana 120 s, 55 a 255 s (campanha 2, mitigação em 50 a 55 s) | 0,09 a 0,19 | 1 a 2 de 10 | menor que 0,01 |
| s3, sensibilidade | igual | campanhas 1 e 2 juntas, 30 a 255 s | 0,24 a 0,38 | 2 a 4 de 10 | 0,02 a 0,14 |
| s1 | perto de 20 s | depende da Fase 0 | desconhecida | desconhecido | desconhecido |

Previsão registrada: em s3 o MECADE da campanha 3 não deve cumprir o RTO na maioria das réplicas, e o critério
de recuperação de s3 deve sair NÃO ATENDE. O motivo é de desenho: com o LIMIT condicionado ao ALERT, a
mitigação de s3 sai depois do ALERT (perto de 100 s), e o atraso de restauração depois do scale já passa de
80 s na maioria das réplicas da campanha 2. A campanha 2 cumpriu 7/10 porque bloqueou a 50 a 55 s, antes do
ALERT, justamente pela integral sem k-de-n que a Seção 3.2 corrige.

Poder conjunto da H2: pela regra D1, a H2 só sai ACEITA se todos os critérios (TTR, `rto_ok_ttr` e
`RRIndex_run`) atenderem nos três cenários. Com o poder do McNemar de s3 de até 0,14 nos dois modelos, a
chance de H2 ACEITA fica em até 0,14, antes de contar s1, TTR e convergência. H2 PARCIAL é o desfecho mais
provável, e é um desfecho aceito: não mudo o desenho por causa disso. A troca está declarada: a campanha 3
compra especificidade (BLOCK só com ALERT confirmado, Seção 3.2) ao preço de tempo de mitigação em s3.

## 7. Regras de exceção, desfechos fechados e desvios previstos

### 7.1 Execução que falha

- **Fase 0.** Uma execução que falha (port-forward, rollout travado, coleta sem dado) é refeita até 3 vezes
  com o mesmo desenho. Sem dado depois disso: se for C1 ou C2, a cascata sai (desfecho conservador da Seção
  3.1); se for A ou B, H4 fica "não testada"; se for D, o efeito no baseline fica "não medido". O
  `clientes_apos_s` usa as execuções com dado; se nenhuma tiver o tempo do rollout, a cascata sai. Tudo vai
  para `data/diagnostico/` e para o relatório.
- **Calibração.** Vale a regra das 3 falhas do `docs/PROTOCOLO.md` (Seção 4) por execução. Se, no fim da
  ordem sorteada, houver menos de 27 controles ou menos de 9 pilotos do braço baseline com dados, completo uma
  vez as execuções que faltam, no fim da ordem e na mesma ordem relativa, sem sortear de novo (desvio
  registrado em `desvios_execucao.jsonl`). Cada execução completada tem também até 3 tentativas. Se ainda
  faltar, a calibração é inviável (Seção 7.2). A conferência é mecânica: `calibrate_c3` recebe os mínimos de
  `calibracao.controles_minimos` (27) e `calibracao.pilotos_minimos` (9) do config, conta os controles e os
  pilotos do braço baseline com dados (`medido.n_controles`, `medido.n_pilotos`) e devolve inviável abaixo
  deles (`medido.abaixo_do_minimo`).
- **Plano oficial.** Regra das 3 falhas e limite de 10% do `docs/PROTOCOLO.md`. Uma réplica perdida pode ser
  refeita uma vez no fim da ordem (desvio registrado). Se o limite ainda passar depois disso, a campanha 3
  fecha como "incompleta" (Seção 7.2), em vez do "eu decido" do `docs/PROTOCOLO.md`.

### 7.2 Desfechos fechados

A campanha 3 termina num destes desfechos, e só neles:

1. **Concluída.** Calibração válida e viável, plano oficial dentro do limite de 10%, veredito pela regra D1.
2. **Calibração inviável.** Calibração com menos execuções válidas que o mínimo da Seção 7.1, ou B que falha
   em alguma condição da Seção 3.4 (B = 0, piloto sem ALERT antes de 415 s, ou B < 2 × maior I dos controles).
   Nenhuma execução oficial roda, nem com a regra trocada. A campanha 3 fecha como "calibração inviável" e é
   relatada assim, com os números da calibração e da Fase 0, no `docs/RESULTADOS_CAMPANHA_3.md`. Qualquer regra
   nova fica para uma campanha 4, com pré-registro próprio.
3. **Incompleta.** Perdidas acima do limite depois da reexecução, ou prazo esgotado pelas datas de corte da
   Seção 7.3. Relato o que
   rodou, com o veredito calculado sobre os pares válidos e marcado como de campanha incompleta.

### 7.3 Desvios previstos

- s3: previsão numérica na Seção 6.1. Se `rto_ok_ttr` de s3 cair, como previsto, é resultado.
- s1: se a Fase 0 tirar a cascata, prevejo s1 pior que o baseline de novo (Seção 3.1).
- Regime de base: se o p95 de base mudar de nível durante a campanha, relato a composição pelo limiar de 0,16 s
  e aplico o critério de quebra de trocabilidade da Seção 3.5. Mantenho a análise.
- Prazo: se o plano oficial não começar até 17/11 às 8h, não reduzo n. Datas de corte (horário de Brasília):
  (a) se a calibração não terminar até 18/11 às 23:59, nenhuma execução oficial começa e a campanha 3 fecha
  como incompleta, com a Fase 0 e a calibração relatadas; (b) se o plano oficial não terminar até 20/11 às
  23:59, paro a execução e a campanha fecha como incompleta, com o que tiver rodado. Por que essas datas: o
  plano oficial leva umas 36 h, então começar logo depois de 18/11 23:59 (quarta, dentro da janela de push da
  tag de calibração) termina por volta de 20/11 às 12h, e 21/11 fica para a análise e o texto da dissertação. A
  margem de umas 12 h entre o fim previsto e o corte (b) cobre reexecuções e reaquecimento do cluster.

## 8. Ordem dos passos e custo

1. Commit deste protocolo, do config, do código e dos dois planos no branch `campanha-3`; tag anotada
   `mvc-2026-11-c3-prereg`; push do branch e da tag.
2. Fase 0 (5 execuções, umas 2,5 h de cluster), regra da Seção 3.1, commit do cenário de s1 com o valor final.
3. Calibração (48 execuções, umas 22 h), `make calibrar`, congelamento, commit, tag
   `mvc-2026-11-c3-calibracao` e push, antes da primeira execução oficial. O push segue a janela de horário do
   repositório (dias úteis, só entre 19h e 8h45). Se a calibração acabar fora da janela, a espera é prevista:
   os nós podem ir a 0 nesse intervalo, reaquecer o cluster depois não é desvio, e nenhuma execução oficial
   começa antes do push da tag de calibração.
4. 80 execuções oficiais (umas 36 h), backup em três cópias (VM, bucket em `oficial-c3/`, `calibracao-c3/`
   e `diagnostico-c3/`, local).
5. Análise, `docs/RESULTADOS_CAMPANHA_3.md`, tag `mvc-2026-11-c3-final`, `make evidencias ESTRITO=1` e
   conferência das três cópias.

São umas 60 h de cluster no total, com 27 min por execução como na campanha 2.

### 8.1 O que o código pode mudar entre as tags

Entre `mvc-2026-11-c3-prereg` e `mvc-2026-11-c3-calibracao`, só isto, e tudo com `make test` passando:

1. script da Fase 0 (arquivo novo, só coleta e mede o tempo do rollout como na Seção 3.1);
2. captura de eventos do Kubernetes e dos dados da Fase 0 no runner, sem efeito em nenhuma decisão do
   controlador;
3. escala do node pool a 0 ao fim de cada plano, no runner;
4. `analysis/evidencias.py` e o backup passam a incluir `data/diagnostico`;
5. registro do tipo de máquina dos nós no `meta.json`;
6. script e teste de congelamento, que copiam a saída de `calibrate_c3` para o config e conferem um contra o
   outro, e a trava que recusa o plano oficial com o B ou os pisos da campanha 2;
7. `analysis/build_notebook.py`, `analysis/analysis.ipynb` e `data/ENVIRONMENT.md`;
8. no config e no cenário, só os valores fixados pelas regras: `clientes_apos_s` (ou a saída de `clientes`)
   pela Seção 3.1 e os valores calibrados pela Seção 4.

A lógica de decisão, o braço baseline, os cenários sem mudança e os planos não mudam:

```
git diff mvc-2026-11-c3-prereg mvc-2026-11-c3-calibracao -- \
  mecade/axioms.py mecade/reactive.py analysis/calibrate.py analysis/metrics.py analysis/veredito.py \
  scenarios/s2_gray_currency.yaml scenarios/s3_podkill_cart.yaml scenarios/c0_controle.yaml \
  orchestrator/plan_campaign.py data/plan_mvc-2026-11-c3.csv data/calibracao/plan_r1.csv
```

tem de sair vazio. Em `mecade/runner.py`, `scenarios/s1_latencia_productcatalog.yaml` e `config/campaign.yaml`
o diff só pode tocar os itens 2, 3, 5 e 8 acima, e cada trecho alterado (cada hunk do diff) fica citado no
`CHANGELOG.md`, com o item da lista a que pertence. Em particular, `mitigate()` e a cascata do runner não
mudam. Entre a
tag de calibração e a final, o código não muda, salvo documentação e notebook. Qualquer outra mudança é desvio,
registrado no `CHANGELOG.md` e no relatório.

## 9. Dados das campanhas anteriores neste branch

O branch `campanha-3` sai do `campanha-2` e não traz os dados nem as figuras da campanha 2, para que nenhum
controle anterior entre na calibração da campanha 3 e o manifesto de evidências cubra só a campanha 3. Os
dados da campanha 1 ficam na tag `mvc-2026-11-final`, com manifesto
`5d24630b37a99867070b1d151c2e4ff06712e4fff459e551b61ec30c0aed391b`, e os da campanha 2 na tag
`mvc-2026-11-c2-final`, com manifesto final (modo estrito)
`b1effa76c7e18201440cc06aa01b682a0b39571e4e39403c4484f313b2867967`. Os resultados ficam em
`docs/RESULTADOS_CAMPANHA_1.md` e `docs/RESULTADOS_CAMPANHA_2.md`.

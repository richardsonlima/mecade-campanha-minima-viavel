# MECADE: Campanha Mínima Viável

Repositório experimental da minha dissertação de mestrado no ITA (PG-EEC-I), *MECADE: Um Modelo de
Engenharia do Caos para Avaliação da Garantia de Dependabilidade em Sistemas Críticos Distribuídos*.

Aqui eu comparo, em réplicas pareadas, o MECADE (axiomas ALERT, LIMIT e BLOCK) com um baseline
reativo convencional. Os dois braços enfrentam o mesmo incidente, com a mesma carga, no Online
Boutique rodando em Kubernetes.

```
                ┌──────────── Kubernetes (kind ou GKE Standard) ────────────┐
 mecade-loadgen ──► Online Boutique (ns boutique) ◄── Chaos Mesh (Camada 4)
   (carga fixa,        │                                     ▲
    métricas) ──► Prometheus (Camada 2) ◄────────────────────┤
                └──────────────────│──────────────────────────│───────────────┘
                                   ▼                          │ CRDs / mitigação
                 orquestrador + controlador MECADE ───────────┘
                 (Camadas 3 e 5; auditoria da Camada 6 em data/audit)
```

## Para subir o ambiente

```bash
make venv && make test      # os testes já incluem uma campanha simulada inteira
make kind-up && make install
make port-forward           # deixo rodando em outro terminal
make smoke && make plan && make pilot
```

O passo a passo que sigo está em [`docs/RUNBOOK.md`](docs/RUNBOOK.md). O protocolo e as decisões
de implementação estão em [`docs/PROTOCOLO.md`](docs/PROTOCOLO.md), e a correspondência com os
capítulos da dissertação em [`docs/MAPEAMENTO_DISSERTACAO.md`](docs/MAPEAMENTO_DISSERTACAO.md).

## Organização

```
versions.env            versões fixadas (não mudo durante a campanha)
infra/                  kind, GKE Standard e valores dos charts Helm
target/                 Online Boutique v0.10.5 via kustomize, sem loadgenerator e sem LoadBalancer
load/k8s/               meu gerador de carga (malha aberta, semente fixa, métricas Prometheus)
scenarios/              registros de cenário (Tabela 3.3) com os templates das injeções
config/campaign.yaml    parâmetros da campanha: tempos, sinais, axiomas, baseline, auditoria
mecade/                 controlador: axiomas, baseline reativo, auditoria, execução de réplica, simulação
orchestrator/           plano randomizado e execução retomável
analysis/               métricas, testes pareados e notebook
tests/                  testes unitários e de ponta a ponta
data/                   saídas da campanha (detalhes em data/README.md)
```

## Versões

| Componente | Versão |
|---|---|
| Online Boutique | v0.10.5 |
| Chaos Mesh (Helm) | 2.8.4 |
| kube-prometheus-stack (Helm) | 90.0.0 |
| kind / imagem do nó | v0.33.0 / kindest/node v1.37.0 |
| Python do controlador | 3.11 ou mais novo, dependências em `requirements.txt` |

Não uso o GKE Autopilot porque o `chaos-daemon` do Chaos Mesh precisa de pod privilegiado, e o
Autopilot só libera isso para parceiros da lista dele. Fico com o GKE Standard e nós sob demanda.
Evitei nós Spot de propósito: uma preempção no meio de uma réplica seria uma falha que eu não
planejei, e isso contamina a comparação.

Fixei o Online Boutique na v0.10.5, e não na v0.10.7, porque a partir da v0.10.6 os manifestos
apontam para o registro `online-boutique-ci`. A v0.10.5 ainda usa o `google-samples`, que é o
registro público de sempre. Se eu mudar de versão, troco a URL em `target/kustomization.yaml` e
em `versions.env` e anoto no `CHANGELOG.md`.

## Sobre a simulação

O `make sim` roda o plano inteiro contra um modelo bem simples (`mecade/sim.py`), em poucos
segundos. Serve só para eu testar o pipeline sem cluster. Esses dados ficam em `data/sim/`,
saem marcados com `backend: sim` e a análise os ignora por padrão. Nada disso entra na dissertação.

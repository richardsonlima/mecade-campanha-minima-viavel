# Runbook da campanha

Na máquina preciso de Docker, `kubectl`, `helm` 3, `kind` v0.33.0 e Python 3.11 ou mais novo.
Para o GKE, também do `gcloud`.

## Dia 1: ambiente local no kind

```bash
make venv && make test            # 15 testes, incluindo a campanha simulada de ponta a ponta
make kind-up                      # uns 2 minutos
make install                      # uns 10 minutos (Online Boutique, Prometheus e Chaos Mesh)
make port-forward                 # em outro terminal, e deixo rodando
make smoke                        # p95, p99 e error_rate precisam responder depois de ~1 min de carga
```

Grafana em http://localhost:3000 (usuário admin, senha mecade) e Chaos Dashboard em
http://localhost:2333.

Para um teste manual de injeção, aplico um cenário renderizado e acompanho o p99 subir no Prometheus:

```bash
.venv/bin/python - <<'PY'
from mecade.config import load_scenario, render_chaos
from mecade.backends import Kubectl
k = Kubectl("boutique"); sc = load_scenario("s1_latencia_productcatalog")
k.apply(render_chaos(sc["chaos"], name="teste-manual", ns="boutique", pods=k.pods(sc["alvo"]), fault_s=120))
PY
# para limpar: make clean-chaos
```

## Dias 2 e 3: piloto e calibração (Fase 1)

```bash
make plan && make pilot           # 2 réplicas reais completas, mais ou menos 1 hora
```

Com o `analysis/analysis.ipynb` apontando para `data/runs`, sigo a Seção 6 do `docs/PROTOCOLO.md`.
Ajusto o `config/campaign.yaml`, apago as réplicas de calibração de `data/runs/`, anoto no
CHANGELOG, gero o plano definitivo com `make plan` e faço commit.

## 17/10: ponto de decisão

Se a calibração não estiver congelada até 17/10, passo para o plano de contingência:

```bash
make plan-contingency             # s2 e s3, com as mesmas 10 réplicas por célula
```

## A partir do dia 4: réplicas oficiais no GKE Standard

```bash
PROJECT=<id-do-projeto> make gke-create
make install && make port-forward   # o port-forward em outro terminal
make smoke
make run                            # retomável; com Ctrl+C ele limpa as injeções antes de sair
make gke-down                       # no fim de cada lote, node pool em 0 para poupar crédito
make gke-up                         # antes do lote seguinte (não precisa reinstalar nada)
```

Para os lotes noturnos rodo `nohup make run > lote_$(date +%F).log 2>&1 &`. O port-forward tem que
continuar de pé. Se ele cair, a réplica em andamento é registrada como falha, o orquestrador passa
para a próxima e depois é só rodar `make run` de novo para retomar.

## Análise

```bash
make verify-audit                 # confere a integridade das trilhas da Camada 6
make analyze                      # executa o notebook (também dá para abrir no Jupyter ou no VS Code)
```

O resultado sai em `analysis/metricas_por_replica.csv`, e as figuras, em 300 dpi, em `analysis/figures/`.

## Problemas que já previ

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `make smoke` devolve `None` | a carga ainda está subindo ou o ServiceMonitor não foi coletado | esperar 1 ou 2 minutos e conferir o alvo `mecade-loadgen` em Status > Targets no Prometheus |
| NetworkChaos sem efeito | runtime ou socket errado no chaos-daemon | conferir `infra/helm/chaos-mesh.values.yaml` (containerd) e os logs do `chaos-daemon` |
| réplica marcada como FALHOU | port-forward caiu ou o kubectl estourou o tempo | rodar `make run` de novo, ele retoma de onde parou |
| créditos do GCP descendo rápido | nós ligados fora dos lotes | `make gke-down` |

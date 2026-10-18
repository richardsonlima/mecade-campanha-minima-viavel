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

Antes de criar o cluster:

- Faço o upgrade da conta do GCP para paga. Em Free Trial só dá para ter 8 vCPUs ligadas ao mesmo
  tempo, e o cluster usa 12 (mais 2 da VM do controlador). O crédito que sobrou continua valendo.
- Crio um alerta de orçamento em Faturamento > Orçamentos e alertas (50%, 90% e 100% do crédito).
- Instalo o plugin de autenticação: `gcloud components install gke-gcloud-auth-plugin`.

```bash
PROJECT=<id-do-projeto> make gke-create      # cluster, exclusão de manutenção e data/ENVIRONMENT.md
make install                                  # pode rodar do notebook mesmo
PROJECT=<id-do-projeto> make controller-vm    # VM e2-small na mesma zona
gcloud compute ssh mecade-ctl --zone us-central1-a
```

Na VM, uma vez só:

```bash
gcloud container clusters get-credentials mecade-mvc --zone us-central1-a
git clone https://github.com/richardsonlima/mecade-mvc-01.git && cd mecade-mvc-01
make venv && make test
```

Em cada lote, na VM, dentro do tmux (`tmux new -s campanha`, ou `tmux attach -t campanha`):

```bash
make gke-up                       # janela 1: sobe os nós e espera tudo ficar pronto
make port-forward-loop            # janela 1: Prometheus em localhost:9090, reabre se cair
make smoke                        # janela 2: depois de ~2 min de carga
make run                          # janela 2: retomável; Ctrl+C limpa as injeções antes de sair
make gke-down                     # no fim do lote: limpa injeções e leva os nós a 0
```

Posso fechar o notebook com o tmux rodando. Para acompanhar, `gcloud compute ssh mecade-ctl` e
`tmux attach -t campanha`. Para o Grafana, faço o port-forward do 3000 do meu notebook mesmo.
Desligo a VM fora dos lotes (`gcloud compute instances stop mecade-ctl`), porque ela também consome
crédito, ainda que pouco.

Ao zerar os nós, o Prometheus perde o histórico (é emptyDir). Isso não afeta a campanha, porque cada
réplica já exporta `steps.csv` e `prom_range.csv` para `data/runs/` na VM. No fim, copio `data/` da
VM para o notebook com `gcloud compute scp --recurse mecade-ctl:~/mecade-mvc-01/data ./ --zone us-central1-a`.

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
| créditos do GCP descendo rápido | nós ou VM ligados fora dos lotes | `make gke-down` e parar a VM |
| `gke-create` falha por cota de CPUs | conta ainda em Free Trial (limite de 8 vCPUs) | upgrade da conta para paga |
| `kubectl` pede o gke-gcloud-auth-plugin | plugin não instalado | `gcloud components install gke-gcloud-auth-plugin` |

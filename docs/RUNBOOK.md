# Runbook da campanha

Na máquina preciso de Docker, `kubectl`, `helm` 3, `kind` v0.33.0 e Python 3.12 ou mais novo.
Para o GKE, também do `gcloud`.

## Dia 1: ambiente local no kind

```bash
make venv && make test            # testes, incluindo a campanha simulada de ponta a ponta
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

## Calibração (Fase 1)

Roda fora do plano oficial. Os dados ficam em `data/calibracao/`, com `run_id` começando em `cal<rodada>_`,
e nada disso consome réplica oficial nem entra na análise.

```bash
make plan-calibracao RODADA=1     # 3 controles e 1 par por cenário
make run-calibracao RODADA=1      # 9 réplicas, cerca de 4 horas
make calibrar                     # aplica a regra da Seção 6 do docs/PROTOCOLO.md
make sim                          # confere o pipeline com os parâmetros novos
```

Depois atualizo o `config/campaign.yaml` e o `campaign_id`, anoto no CHANGELOG, gero o plano com `make plan`
e faço commit. Se a calibração não congelar em 2 rodadas (cerca de 9 horas de cluster), passo para
`make plan-contingency`: s2 e s3, com as mesmas 10 réplicas por célula, 50 no total.

## Réplicas oficiais no GKE Standard

Antes de criar o cluster:

- Três `e2-standard-2` e a VM `e2-small` somam 8 vCPUs e cabem no Free Trial. Máquina maior exige upgrade da
  conta, e essa decisão é do dono da conta.
- Crio um alerta de orçamento em Faturamento > Orçamentos e alertas (50%, 90% e 100%).
- Instalo o plugin de autenticação: `gcloud components install gke-gcloud-auth-plugin`.

```bash
PROJECT=<id-do-projeto> MACHINE=e2-standard-2 make gke-create   # cluster, exclusão de manutenção e data/ENVIRONMENT.md
make install                                  # pode rodar do notebook mesmo
PROJECT=<id-do-projeto> make controller-vm    # VM e2-small com Debian 13 na mesma zona
git bundle create /tmp/mecade.bundle HEAD     # o commit da campanha, sem depender de push
gcloud compute scp /tmp/mecade.bundle mecade-ctl:~ --zone us-central1-a
gcloud compute ssh mecade-ctl --zone us-central1-a
```

Na VM, uma vez só, depois de o startup-script criar `/var/lib/mecade-pronto`:

```bash
gcloud container clusters get-credentials mecade-mvc --zone us-central1-a
git clone mecade.bundle mecade-mvc-01 && cd mecade-mvc-01
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

O `make run` trata sozinho as falhas de réplica: limpa as injeções, espera 120 s e refaz a réplica em uma
passada seguinte. Ele sai com código 3 se mais de 10% das réplicas forem perdidas e com código 4 depois de
3 falhas seguidas. Nos dois casos os nós continuam ligados e gastando crédito até alguém agir.
Se eu decidir seguir além dos 10%, rodo `.venv/bin/python -m orchestrator.run_campaign --sem-limite-perdidas`
e registro a decisão no CHANGELOG. Reboot da VM não reinicia a campanha: confiro o tmux e rodo `make run` de novo.

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
| réplica marcada como FALHOU | port-forward caiu ou o kubectl estourou o tempo | o orquestrador refaz sozinho; na terceira falha ela vira `falha_execucao` |
| `make run` saiu com código 4 | 3 falhas seguidas, ambiente instável | conferir cluster e port-forward, `make clean-chaos` e rodar `make run` de novo |
| `make run` saiu com código 3 | mais de 10% das réplicas perdidas | parar e decidir; `make gke-down` para não gastar crédito |
| créditos do GCP descendo rápido | nós ou VM ligados fora dos lotes | `make gke-down` e parar a VM |
| `gke-create` falha por cota de CPUs | máquina grande demais para o Free Trial (limite de 8 vCPUs) | usar `e2-standard-2`; upgrade só com decisão do dono da conta |
| `kubectl` pede o gke-gcloud-auth-plugin | plugin não instalado | `gcloud components install gke-gcloud-auth-plugin` |

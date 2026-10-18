# CHANGELOG da campanha

Qualquer mudança de versão, parâmetro ou cenário depois que as réplicas oficiais começarem vai
anotada aqui. Réplicas rodadas antes e depois de uma mudança não são comparáveis entre si.

## 2026-10-11, v0.1.0

- Estrutura inicial com Online Boutique v0.10.5, Chaos Mesh 2.8.4, kube-prometheus-stack 90.0.0 e kind v0.33.0.
- Cenários s1, s2 e s3 (versão 1) e controle c0.
- Parâmetros dos axiomas ainda nos valores iniciais. A calibração acontece na Fase 1.

## 2026-10-18, v0.1.1

- `create-cluster.sh`: tirei o `--no-enable-autoupgrade`, que o GKE recusa em cluster com release
  channel. No lugar, crio uma exclusão de manutenção `no_minor_or_node_upgrades` até 15/12/2026.
  Também confiro a cota de CPUs antes de criar e gravo `data/ENVIRONMENT.md`.
- Nova VM do controlador (`make controller-vm`) na mesma zona do cluster, para os lotes longos não
  dependerem do meu notebook.
- `make port-forward-loop` reabre o port-forward do Prometheus se ele cair.
- `make gke-down` limpa as injeções antes de zerar os nós; `make gke-up` espera tudo ficar pronto.
- Voltei o `.gitignore`, que não tinha subido no primeiro commit.
- Nada disso muda parâmetro, cenário ou versão da pilha. As réplicas continuam comparáveis.

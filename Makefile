# Campanha Mínima Viável do MECADE. `make help` lista os alvos.
SHELL := /bin/bash
include versions.env
export
PY := .venv/bin/python

help: ## lista os alvos
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n",$$1,$$2}'

venv: ## cria o ambiente Python do controlador/análise
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

test: ## testes unitários + teste de ponta a ponta em simulação
	$(PY) -m pytest -q

# cluster local (kind)
kind-up: ## cria o cluster kind (1 control-plane + 3 workers)
	kind create cluster --config infra/kind/kind-config.yaml --image $(KIND_NODE_IMAGE)

kind-down: ## remove o cluster kind
	kind delete cluster --name mecade

# GKE Standard
gke-create: ## cria o cluster GKE Standard (exige PROJECT=<id>)
	infra/gke/create-cluster.sh

gke-up: ## node pool -> 3 nós e espera tudo voltar (antes de rodar)
	infra/gke/scale.sh 3
	kubectl wait --for=condition=Ready nodes --all --timeout=10m
	kubectl -n $(NAMESPACE_MONITORING) wait --for=condition=available deployment --all --timeout=10m
	kubectl -n $(NAMESPACE_CHAOS) wait --for=condition=available deployment --all --timeout=10m
	kubectl -n $(NAMESPACE_TARGET) wait --for=condition=available deployment --all --timeout=10m
	@echo "Prometheus voltou vazio (emptyDir). Espero uns 2 min de carga e rodo make smoke."

gke-down: clean-chaos ## limpa injeções e leva o node pool a 0 nós (fora das janelas de execução)
	infra/gke/scale.sh 0

controller-vm: ## cria a VM do controlador na mesma zona do cluster (exige PROJECT=<id>)
	infra/gke/controller-vm.sh

# pilha
install: ## instala Prometheus, Chaos Mesh, Online Boutique e gerador de carga
	infra/install-stack.sh

port-forward: ## expõe Prometheus (9090), Grafana (3000) e Chaos Dashboard (2333); fica rodando
	kubectl -n $(NAMESPACE_MONITORING) port-forward svc/kps-prometheus 9090:9090 & \
	kubectl -n $(NAMESPACE_MONITORING) port-forward svc/kps-grafana 3000:80 & \
	kubectl -n $(NAMESPACE_CHAOS) port-forward svc/chaos-dashboard 2333:2333 & \
	wait

port-forward-loop: ## igual ao port-forward, mas reabre sozinho se cair (uso nos lotes longos)
	while true; do \
	  kubectl -n $(NAMESPACE_MONITORING) port-forward svc/kps-prometheus 9090:9090; \
	  echo "port-forward caiu em $$(date -u +%FT%TZ), reabrindo" | tee -a data/runs/portforward.log; sleep 2; \
	done

smoke: ## pré-voo: confere se os sinais de decisão respondem no Prometheus
	$(PY) -m mecade.cli smoke

# campanha
plan: ## gera o plano randomizado (data/plan_<campanha>.csv)
	$(PY) -m orchestrator.plan_campaign

plan-contingency: ## plano reduzido: 2 cenários (contingência)
	$(PY) -m orchestrator.plan_campaign --scenarios s2_gray_currency,s3_podkill_cart

pilot: ## executa as próximas 2 réplicas (validação do protocolo)
	$(PY) -m orchestrator.run_campaign --limit 2

run: ## executa (ou retoma) o plano completo
	$(PY) -m orchestrator.run_campaign

sim: ## roda o plano em simulação (só testa o pipeline, não é evidência)
	$(PY) -m orchestrator.plan_campaign --out data/sim/plan.csv && \
	$(PY) -m orchestrator.run_campaign --backend sim --plan data/sim/plan.csv

notebook: ## regenera analysis/analysis.ipynb (sem saídas)
	$(PY) analysis/build_notebook.py

analyze: ## executa o notebook sobre data/runs
	$(PY) analysis/run_notebook.py

verify-audit: ## verifica a integridade de todas as trilhas de auditoria
	@for f in data/audit/*.jsonl; do echo -n "$$f: "; $(PY) -m mecade.cli verify-audit $$f; done

clean-chaos: ## remove qualquer injeção ativa (uso em emergência)
	kubectl -n $(NAMESPACE_TARGET) delete schedules.chaos-mesh.org,networkchaos.chaos-mesh.org,podchaos.chaos-mesh.org --all


.PHONY: analyze help venv test kind-up kind-down gke-create gke-up gke-down controller-vm port-forward-loop install port-forward smoke plan plan-contingency pilot run sim notebook verify-audit clean-chaos

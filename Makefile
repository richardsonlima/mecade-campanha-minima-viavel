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

plan-calibracao: ## plano da rodada de calibração em data/calibracao/ (RODADA=1 ou 2)
	$(PY) -m orchestrator.plan_campaign --calibracao $(or $(RODADA),1)

run-calibracao: ## executa a rodada de calibração, fora de data/runs (RODADA=1 ou 2)
	$(PY) -m orchestrator.run_campaign --calibracao --plan data/calibracao/plan_r$(or $(RODADA),1).csv

calibrar: ## aplica a regra da Fase 1 aos dados de data/calibracao/runs
	$(PY) -m analysis.calibrate

pilot: ## executa 2 réplicas do plano de calibração, sem tocar no plano oficial
	$(PY) -m orchestrator.run_campaign --calibracao --plan data/calibracao/plan_r$(or $(RODADA),1).csv --limit 2

run: ## executa (ou retoma) o plano completo
	$(PY) -m orchestrator.run_campaign

sim: ## roda o plano em simulação do zero (só testa o pipeline, não é evidência)
	rm -rf data/sim/runs data/sim/audit data/sim/campaign.log data/sim/desvios_execucao.jsonl
	$(PY) -m orchestrator.plan_campaign --out data/sim/plan.csv && \
	$(PY) -m orchestrator.run_campaign --backend sim --plan data/sim/plan.csv

notebook: ## regenera analysis/analysis.ipynb (sem saídas)
	$(PY) analysis/build_notebook.py

analyze: ## executa o notebook sobre data/runs
	$(PY) analysis/run_notebook.py

AUDIT_DIR ?= data/audit
verify-audit: ## verifica a integridade de todas as trilhas de auditoria (falha se qualquer uma falhar)
	@shopt -s nullglob; n=0; falhas=0; \
	for f in $(AUDIT_DIR)/*.jsonl; do n=$$((n+1)); echo -n "$$f: "; $(PY) -m mecade.cli verify-audit "$$f" || falhas=$$((falhas+1)); done; \
	echo "$$n trilhas verificadas, $$falhas com falha"; test $$falhas -eq 0

evidencias: ## gera data/EVIDENCIAS_MANIFESTO.json (commit, tag, plano, SHA-256, verify-audit, versões; ESTRITO=1 falha se sujo, sem tag ou fora do git)
	$(PY) -m analysis.evidencias gerar $(if $(filter 1,$(ESTRITO)),--estrito)

verificar-evidencias: ## recalcula os hashes de uma cópia e compara com o manifesto (RAIZ=<cópia> MANIFESTO=<arquivo>)
	$(PY) -m analysis.evidencias verificar $(if $(RAIZ),--raiz $(RAIZ)) $(if $(MANIFESTO),--manifesto $(MANIFESTO))

clean-chaos: ## remove qualquer injeção ativa (uso em emergência)
	kubectl -n $(NAMESPACE_TARGET) delete schedules.chaos-mesh.org,networkchaos.chaos-mesh.org,podchaos.chaos-mesh.org --all


.PHONY: plan-calibracao run-calibracao calibrar analyze help venv test kind-up kind-down gke-create gke-up gke-down controller-vm port-forward-loop install port-forward smoke plan plan-contingency pilot run sim notebook verify-audit evidencias verificar-evidencias clean-chaos

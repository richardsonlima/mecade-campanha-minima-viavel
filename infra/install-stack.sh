#!/usr/bin/env bash
# Instala kube-prometheus-stack, Chaos Mesh, Online Boutique e o gerador de carga no cluster do
# contexto atual do kubectl (kind ou GKE Standard).
set -euo pipefail
cd "$(dirname "$0")/.."
source versions.env

echo ">> Contexto kubectl: $(kubectl config current-context)"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo add chaos-mesh https://charts.chaos-mesh.org >/dev/null
helm repo update >/dev/null

echo ">> kube-prometheus-stack ${KUBE_PROMETHEUS_STACK_CHART_VERSION}"
helm upgrade --install kps prometheus-community/kube-prometheus-stack \
  --version "${KUBE_PROMETHEUS_STACK_CHART_VERSION}" \
  -n "${NAMESPACE_MONITORING}" --create-namespace \
  -f infra/helm/kube-prometheus-stack.values.yaml --wait --timeout 10m

echo ">> Chaos Mesh ${CHAOS_MESH_CHART_VERSION}"
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  --version "${CHAOS_MESH_CHART_VERSION}" \
  -n "${NAMESPACE_CHAOS}" --create-namespace \
  -f infra/helm/chaos-mesh.values.yaml --wait --timeout 10m

echo ">> Online Boutique ${ONLINE_BOUTIQUE_VERSION} (namespace ${NAMESPACE_TARGET})"
kubectl create namespace "${NAMESPACE_TARGET}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k target/
kubectl -n "${NAMESPACE_TARGET}" wait --for=condition=available deployment --all --timeout=10m

echo ">> Gerador de carga MECADE"
kubectl apply -k load/k8s/
kubectl -n "${NAMESPACE_TARGET}" rollout status deployment/mecade-loadgen --timeout=5m

echo ">> Instalação concluída. Em seguida: make port-forward (outro terminal) e make smoke"

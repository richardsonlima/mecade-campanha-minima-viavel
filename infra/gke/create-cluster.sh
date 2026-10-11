#!/usr/bin/env bash
# GKE Standard zonal. Não uso Autopilot porque o chaos-daemon do Chaos Mesh precisa de pod privilegiado.
# Nós sob demanda e não Spot, porque uma preempção seria uma falha não planejada no meio da réplica.
set -euo pipefail
PROJECT="${PROJECT:?defina PROJECT=<id-do-projeto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
CLUSTER="${CLUSTER:-mecade-mvc}"
MACHINE="${MACHINE:-e2-standard-4}"
NODES="${NODES:-3}"

gcloud config set project "$PROJECT"
gcloud services enable container.googleapis.com
gcloud container clusters create "$CLUSTER" \
  --zone "$ZONE" \
  --num-nodes "$NODES" \
  --machine-type "$MACHINE" \
  --disk-size 50 \
  --release-channel regular \
  --no-enable-autoupgrade \
  --logging=SYSTEM \
  --monitoring=SYSTEM
gcloud container clusters get-credentials "$CLUSTER" --zone "$ZONE"
echo "Cluster criado. Versão do Kubernetes (anotar em data/ENVIRONMENT.md): $(kubectl version -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')"

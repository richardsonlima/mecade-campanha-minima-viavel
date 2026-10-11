#!/usr/bin/env bash
# Zero o node pool fora das janelas de execução, para poupar crédito, e volto para 3 antes de rodar.
#   ./scale.sh 0
#   ./scale.sh 3
set -euo pipefail
N="${1:?uso: scale.sh <num-nos>}"
ZONE="${ZONE:-us-central1-a}"
CLUSTER="${CLUSTER:-mecade-mvc}"
gcloud container clusters resize "$CLUSTER" --zone "$ZONE" --node-pool default-pool --num-nodes "$N" --quiet

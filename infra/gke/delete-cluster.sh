#!/usr/bin/env bash
# Apaga o cluster no fim da campanha, depois que o data/ estiver exportado.
set -euo pipefail
ZONE="${ZONE:-us-central1-a}"
CLUSTER="${CLUSTER:-mecade-mvc}"
gcloud container clusters delete "$CLUSTER" --zone "$ZONE" --quiet

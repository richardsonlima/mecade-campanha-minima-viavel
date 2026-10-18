#!/usr/bin/env bash
# Cria uma VM pequena na mesma zona do cluster para rodar o controlador e o orquestrador.
# Assim as ~31 h de réplicas não dependem do meu notebook acordado nem de um port-forward
# atravessando a internet. Uso: PROJECT=<id> infra/gke/controller-vm.sh
# Depois: gcloud compute ssh mecade-ctl --zone us-central1-a
set -euo pipefail
PROJECT="${PROJECT:?defina PROJECT=<id-do-projeto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
VM="${VM:-mecade-ctl}"

gcloud compute instances create "$VM" \
  --project "$PROJECT" --zone "$ZONE" \
  --machine-type e2-small \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 20GB \
  --scopes cloud-platform \
  --metadata startup-script='#!/bin/bash
set -e
apt-get update
apt-get install -y git make tmux python3-venv python3-pip kubectl google-cloud-cli-gke-gcloud-auth-plugin
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
'
echo "VM criada. Na VM:"
echo "  gcloud container clusters get-credentials ${CLUSTER:-mecade-mvc} --zone $ZONE"
echo "  git clone https://github.com/richardsonlima/mecade-mvc-01.git && cd mecade-mvc-01"
echo "  make venv && make test"
echo "  tmux new -s campanha   (janela 1: make port-forward-loop, janela 2: make run)"

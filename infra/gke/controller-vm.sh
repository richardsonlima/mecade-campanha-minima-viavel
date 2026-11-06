#!/usr/bin/env bash
# Cria uma VM pequena na mesma zona do cluster para rodar o controlador e o orquestrador.
# Assim as ~31 h de réplicas não dependem do meu notebook acordado nem de um port-forward
# atravessando a internet. Uso: PROJECT=<id> infra/gke/controller-vm.sh
# Depois: gcloud compute ssh mecade-ctl --zone us-central1-a
#
# Uso debian-13 porque numpy==2.5.4 e scipy==1.18.1 exigem Python 3.12 ou mais novo, e o debian-12
# traz 3.11. O repositório da Google entra de forma explícita para o script não depender do que
# vem pré-configurado na imagem.
set -euo pipefail
PROJECT="${PROJECT:?defina PROJECT=<id-do-projeto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
VM="${VM:-mecade-ctl}"
HERE="$(cd "$(dirname "$0")" && pwd)"

gcloud compute instances create "$VM" \
  --project "$PROJECT" --zone "$ZONE" \
  --machine-type e2-small \
  --image-family debian-13 --image-project debian-cloud \
  --boot-disk-size 20GB \
  --scopes cloud-platform \
  --metadata-from-file startup-script="$HERE/controller-startup.sh"
echo "VM criada. Espero o startup-script terminar (existe /var/lib/mecade-pronto) e, na VM:"
echo "  gcloud container clusters get-credentials ${CLUSTER:-mecade-mvc} --zone $ZONE"
echo "  git clone do bundle do commit local (docs/RUNBOOK.md) && cd mecade-mvc-01"
echo "  make venv && make test"
echo "  tmux new -s campanha   (janela 1: make port-forward-loop, janela 2: make run)"

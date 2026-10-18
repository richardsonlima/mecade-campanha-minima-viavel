#!/usr/bin/env bash
# GKE Standard zonal. Não uso Autopilot porque o chaos-daemon do Chaos Mesh precisa de pod privilegiado.
# Nós sob demanda e não Spot, porque uma preempção seria uma falha não planejada no meio da réplica.
#
# Atenção a duas coisas que aprendi antes de rodar:
# 1. Conta em Free Trial só deixa 8 vCPUs ligadas ao mesmo tempo. Três e2-standard-4 são 12 vCPUs,
#    então preciso fazer o upgrade da conta para paga antes (o crédito que sobrou continua valendo).
# 2. Cluster em release channel não aceita desligar o auto-upgrade dos nós. Em vez disso, crio uma
#    exclusão de manutenção que bloqueia upgrade de nó e de versão minor até o fim da campanha.
set -euo pipefail
PROJECT="${PROJECT:?defina PROJECT=<id-do-projeto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
CLUSTER="${CLUSTER:-mecade-mvc}"
MACHINE="${MACHINE:-e2-standard-4}"
NODES="${NODES:-3}"
FREEZE_START="${FREEZE_START:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
FREEZE_END="${FREEZE_END:-2026-12-15T00:00:00Z}"

command -v gke-gcloud-auth-plugin >/dev/null || {
  echo "Falta o gke-gcloud-auth-plugin: gcloud components install gke-gcloud-auth-plugin"; exit 1; }

gcloud config set project "$PROJECT"
gcloud services enable container.googleapis.com compute.googleapis.com

QUOTA=$(gcloud compute regions describe "${ZONE%-*}" --format=json \
  | python3 -c 'import json,sys;q=[x for x in json.load(sys.stdin)["quotas"] if x["metric"]=="CPUS"][0];print(int(q["limit"]))')
NEED=$(( NODES * 4 ))
if (( QUOTA < NEED )); then
  echo "Cota de CPUs na região é $QUOTA e preciso de $NEED. Faço o upgrade da conta ou peço aumento de cota."; exit 1
fi

gcloud container clusters create "$CLUSTER" \
  --zone "$ZONE" \
  --num-nodes "$NODES" \
  --machine-type "$MACHINE" \
  --disk-size 50 \
  --release-channel regular \
  --logging=SYSTEM \
  --monitoring=SYSTEM

# Congela a versão dos nós durante a campanha. Patch do control plane ainda pode acontecer;
# se acontecer, anoto no CHANGELOG com a data.
gcloud container clusters update "$CLUSTER" --zone "$ZONE" \
  --add-maintenance-exclusion-name campanha-mecade \
  --add-maintenance-exclusion-start "$FREEZE_START" \
  --add-maintenance-exclusion-end "$FREEZE_END" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

gcloud container clusters get-credentials "$CLUSTER" --zone "$ZONE"
mkdir -p data
{
  echo "# Ambiente da campanha"
  echo "- criado em: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- projeto/zona/cluster: $PROJECT / $ZONE / $CLUSTER"
  echo "- nós: $NODES x $MACHINE, sob demanda"
  echo "- Kubernetes: $(kubectl version -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')"
  echo "- exclusão de manutenção: $FREEZE_START até $FREEZE_END (no_minor_or_node_upgrades)"
} > data/ENVIRONMENT.md
cat data/ENVIRONMENT.md

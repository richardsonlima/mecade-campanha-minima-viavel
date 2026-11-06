#!/usr/bin/env bash
# GKE Standard zonal. Não uso Autopilot porque o chaos-daemon do Chaos Mesh precisa de pod privilegiado.
# Nós sob demanda e não Spot, porque uma preempção seria uma falha não planejada no meio da réplica.
#
# Atenção a duas coisas que aprendi antes de rodar:
# 1. Conta em Free Trial só deixa 8 vCPUs ligadas ao mesmo tempo. Três e2-standard-2 mais a VM e2-small
#    somam 8 e cabem. Três e2-standard-4 somam 14 e exigem upgrade da conta, que só o dono decide.
# 2. Cluster em release channel não aceita desligar o auto-upgrade dos nós. Em vez disso, crio uma
#    exclusão de manutenção que bloqueia upgrade de nó e de versão minor até o fim da campanha.
set -euo pipefail
PROJECT="${PROJECT:?defina PROJECT=<id-do-projeto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
CLUSTER="${CLUSTER:-mecade-mvc}"
MACHINE="${MACHINE:-e2-standard-4}"
NODES="${NODES:-3}"
CONTROLLER_VCPUS="${CONTROLLER_VCPUS:-2}"   # a VM e2-small do controlador entra na mesma cota
FREEZE_START="${FREEZE_START:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
FREEZE_END="${FREEZE_END:-2026-12-15T00:00:00Z}"

command -v gke-gcloud-auth-plugin >/dev/null || {
  echo "Falta o gke-gcloud-auth-plugin: gcloud components install gke-gcloud-auth-plugin"; exit 1; }

gcloud config set project "$PROJECT"
gcloud services enable container.googleapis.com compute.googleapis.com

VCPUS=$(gcloud compute machine-types describe "$MACHINE" --zone "$ZONE" --format='value(guestCpus)')
NEED=$(( NODES * VCPUS + CONTROLLER_VCPUS ))
# O Free Trial limita a região e também o projeto inteiro, então confiro as duas cotas.
QUOTA_REGION=$(gcloud compute regions describe "${ZONE%-*}" --format=json \
  | python3 -c 'import json,sys;print(int(next(q["limit"] for q in json.load(sys.stdin)["quotas"] if q["metric"]=="CPUS")))')
QUOTA_GLOBAL=$(gcloud compute project-info describe --format=json \
  | python3 -c 'import json,sys;print(int(next(q["limit"] for q in json.load(sys.stdin)["quotas"] if q["metric"]=="CPUS_ALL_REGIONS")))')
QUOTA=$(( QUOTA_REGION < QUOTA_GLOBAL ? QUOTA_REGION : QUOTA_GLOBAL ))
if (( QUOTA < NEED )); then
  echo "Cota de CPUs é $QUOTA (região $QUOTA_REGION, projeto $QUOTA_GLOBAL) e preciso de $NEED: $NODES x $MACHINE ($VCPUS vCPUs) mais $CONTROLLER_VCPUS da VM. Não crio o cluster."; exit 1
fi
if [[ "${QUOTA_CHECK_ONLY:-0}" == 1 ]]; then
  echo "Cota ok: preciso de $NEED vCPUs e tenho $QUOTA."; exit 0
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

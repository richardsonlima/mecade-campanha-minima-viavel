#!/bin/bash
# Startup-script da VM do controlador (Debian 13). Testado em contêiner debian:13.
# Roda a cada boot da VM. Depois da primeira vez não faz nada, para um reboot não mexer nas versões.
set -e
[ -f /var/lib/mecade-pronto ] && exit 0
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg
install -d -m 755 /usr/share/keyrings
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | gpg --dearmor --yes -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/mecade-google-cloud-sdk.list
apt-get update
apt-get install -y git make tmux python3-venv python3-pip google-cloud-cli kubectl google-cloud-cli-gke-gcloud-auth-plugin
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
touch /var/lib/mecade-pronto

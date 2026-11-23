#!/usr/bin/env bash
# Instala/atualiza as units do portal VinOT na VM. Idempotente. Uso (como ubuntu, usa sudo):
#   ./install.sh base    renderer + vinot-secrets.service (inicia e valida). Reusa o OCI CLI do root (/opt/oci-cli).
#   ./install.sh app     vinot-portal.service
#   ./install.sh boot    habilita no boot
# O renderer roda como root: é COPIADO para /usr/local/lib/vinot e /etc/vinot (root:root); o repo é gravável pelo usuário.
set -euo pipefail
cd "$(dirname "$0")"; S="sudo"
VAULT_DIR="$HOME/GitHub/barbosamaria-streaming/infra/vault"
case "${1:-}" in
base)
  [ -x /opt/oci-cli/bin/oci ] || { echo "ABORTADO: falta /opt/oci-cli (rode barbosamaria-streaming/infra/systemd/install.sh base)"; exit 1; }
  $S install -d -m 755 /usr/local/lib/vinot /etc/vinot
  $S install -m 755 -o root -g root vinot-secrets-render.sh /usr/local/lib/vinot/
  printf 'VAULT_ID=%s\nOCI_BIN=/opt/oci-cli/bin/oci\n' "$(cd "$VAULT_DIR" && ./tofu.sh output -raw vault_id)" | $S tee /etc/vinot/vinot-secrets.conf >/dev/null
  $S chmod 644 /etc/vinot/vinot-secrets.conf
  $S install -m 644 vinot-secrets.service /etc/systemd/system/vinot-secrets.service
  $S systemctl daemon-reload
  $S systemctl start vinot-secrets.service
  $S systemctl is-active vinot-secrets.service ;;
app)
  $S install -m 644 vinot-portal.service /etc/systemd/system/vinot-portal.service
  $S systemctl daemon-reload ;;
boot)
  $S systemctl enable vinot-secrets.service vinot-portal.service
  $S systemctl is-enabled vinot-secrets.service vinot-portal.service ;;
*) echo "uso: $0 base|app|boot"; exit 2 ;;
esac

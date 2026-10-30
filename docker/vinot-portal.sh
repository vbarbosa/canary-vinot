#!/bin/sh
# Recria o container vinot-portal (imagem construída a partir de ~/vinot-portal/portal) com os segredos vindos do OCI Vault.
# Segredos: /run/vault-secrets/vinot-portal/portal (tmpfs, vault-secrets@vinot-portal) -> /run/secrets (env + smtp-password).
# Configuração não secreta: docker/.env e docker/portal.env (0600, fora do git). Chamado por vault-compose@vinot-portal.
set -eu
cd "$(dirname "$0")"
IMG="${VINOT_PORTAL_IMAGE:-vinot-portal:novo}"
docker rm -f vinot-portal >/dev/null 2>&1 || true
exec docker run -d --name vinot-portal --restart unless-stopped --network otbr_canary-net \
  -p 100.70.92.116:8091:8091 --user nobody --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges:true \
  --env-file .env --env-file portal.env \
  -e MYSQL_HOST=database -e SMTP_PASSWORD_FILE=/run/secrets/smtp-password -e VAULT_ENV_FILE=/run/secrets/env \
  -e "VAULT_REQUIRED=MYSQL_PASS PORTAL_SECRET" \
  --mount type=bind,source=/usr/local/lib/vault-secrets/entrypoint.sh,target=/vault/entrypoint.sh,readonly \
  --mount type=bind,source=/run/vault-secrets/vinot-portal/portal,target=/run/secrets,readonly \
  -v /home/ubuntu/vinot-portal/data:/gamedata/data:ro -v /home/ubuntu/vinot-portal/data-otservbr-global:/gamedata/data-otservbr-global:ro \
  -v /home/ubuntu/vinot-downloads:/downloads:ro \
  --entrypoint /bin/sh "$IMG" /vault/entrypoint.sh uvicorn app.main:app --host 0.0.0.0 --port 8091 --proxy-headers --forwarded-allow-ips '*'

#!/usr/bin/env bash
# Roda como root pelo vinot-secrets.service: lê do OCI Vault (Instance Principal) e grava em /run/vinot-secrets (tmpfs).
# Nunca imprime valores. Falha fechada: sem .ready se faltar o segredo.
set -euo pipefail
umask 077
source /etc/vinot/vinot-secrets.conf     # VAULT_ID, OCI_BIN
OUT=/run/vinot-secrets
export SUPPRESS_LABEL_WARNING=True OCI_CLI_AUTH=instance_principal

get() {  # $1 = nome no cofre; retry curto contra falha transitória
  local v i
  for i in 1 2 3 4 5 6; do
    v=$("$OCI_BIN" secrets secret-bundle get-secret-bundle-by-name --secret-name "$1" --vault-id "$VAULT_ID" \
        --stage CURRENT --query 'data."secret-bundle-content".content' --raw-output 2>/dev/null) && [ -n "$v" ] \
      && { printf '%s' "$v" | base64 -d; return 0; }
    sleep 10
  done
  echo "vinot-secrets: não consegui ler '$1' do cofre" >&2; return 1
}

rm -f "$OUT/.ready"
SMTP=$(get vinot-portal__SMTP_PASSWORD)
[ -n "$SMTP" ] || { echo "vinot-secrets: SMTP_PASSWORD vazio" >&2; exit 1; }
mkdir -p "$OUT/portal"
chown 65534:65534 "$OUT/portal"; chmod 0700 "$OUT/portal"      # uid "nobody" do container portal
t=$(mktemp "$OUT/portal/.tmp.XXXXXX"); printf '%s' "$SMTP" > "$t"; chown 65534:65534 "$t"; chmod 0400 "$t"; mv -f "$t" "$OUT/portal/smtp-password"
touch "$OUT/.ready"
echo "vinot-secrets: ok (1 segredo)"

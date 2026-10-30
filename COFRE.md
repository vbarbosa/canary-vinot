# Segredos no OCI Vault

Desde 30/10/2026 os segredos técnicos deste projeto (senhas de banco, chaves, tokens) **vêm do OCI Vault em runtime** e não ficam em `.env` nem na configuração dos containers.
O mecanismo é comum aos projetos desta VM: `vault-secrets@<projeto>.service` lê o Vault com a identidade da VM (Instance Principal) e grava em `/run/vault-secrets/<projeto>` (tmpfs). Documentação completa: `manchete-stack/infra/vm/vault-secrets/README.md`.
O `.env` (0600) guarda só configuração e, quando houver, senhas de contas de usuário da aplicação.

## Este projeto
- **otbr** (`docker/`): `server`, `login` e `cockpit` recebem `MYSQL_PASS`/`MYSQL_PASSWORD` e `COCKPIT_SECRET` por `docker/docker-compose.vault.yml` (carregado via `COMPOSE_FILE` no `docker/.env`). O `config.lua` lê `os.getenv("MYSQL_PASS")`. Segredos: `otbr-mysql-password`, `otbr-mysql-root-password`, `otbr-cockpit-secret` (compartimento `canary-vinot`), todos rotacionados em 30/10 (a senha antiga estava nos `config*.lua.dist` deste repositório público).
- **vinot-portal**: recriado por `docker/vinot-portal.sh`; segredos de `vault-secrets@vinot-portal` (inclui o SMTP). Config não secreta em `docker/portal.env` (fora do git).
- Boot: `vault-compose@otbr` e `vault-compose@vinot-portal` sobem depois dos segredos.
- `~/vinot-deploy/cockpit-autodeploy.sh` lê a senha do tmpfs (sudo) e a passa ao container por variável herdada.

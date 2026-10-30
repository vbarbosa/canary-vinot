# Segredos no cofre (OCI Vault)

Os segredos deste projeto (key.pem, docker/.env) estão no OCI Vault `bm-streaming-vault` (compartimento `barbosamaria-streaming`, região sa-saopaulo-1), com nome `canary-vinot__<arquivo>__<VARIAVEL>`. O arquivo no disco continua funcionando; o cofre é a cópia de segurança e a fonte para recriá-lo.

Ferramenta e IaC ficam em `~/GitHub/barbosamaria-streaming/infra/vault/`:
- Enviar mudanças: `python3 cofre.py push`
- Conferir / recriar arquivos: `python3 cofre.py pull` (`--write` grava os arquivos; sobrescreve os atuais)
- Projeto novo ou arquivo novo: adicionar linha em `projetos.manifest`
- Ver na web: Secret Management, compartimento `barbosamaria-streaming`.

Nenhum valor de segredo está neste repositório.

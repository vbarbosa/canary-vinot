# Débitos técnicos

Decisões provisórias que precisam ser desfeitas ou revistas. Cada item diz o que foi feito, por que, e o que falta.

## DT-1: e-mail do portal (resolvido em 30/10/2026)

O portal estava sem SMTP e com `PORTAL_DEV=1`: o link de confirmação só aparecia na tela. Um cadastro de 25/10 venceu sem criar conta. A solução provisória era enviar pelo domínio do Manchete; acabou não sendo necessária: o `barbosamaria.online` foi verificado no Resend e o remetente é `nao-responda@barbosamaria.online`.

Segredo (`SMTP_PASSWORD`): Vault `bm-streaming-vault`, compartimento `vinot-portal`, nome `vinot-portal__SMTP_PASSWORD`. `vinot-secrets.service` o grava em `/run/vinot-secrets/portal/smtp-password` (tmpfs) e o container lê por `SMTP_PASSWORD_FILE`. Mesmo desenho do Stream Play (units em `docker/systemd/`, `./install.sh base|app|boot`). Rotação: criar nova versão do segredo no Vault, `sudo systemctl restart vinot-secrets`, recriar o container do portal. O resto da configuração (`SMTP_HOST`, `MAIL_FROM`, `PORTAL_DEV`...) fica em `docker/portal.env`, sem segredo.

## DT-2: o portal não tem endereço público (aberto desde 30/10/2026)

**Situação.** O túnel do Cloudflare (`/etc/cloudflared/config.yml`) só publica `jogo.barbosamaria.online`. O portal escuta em `127.0.0.1:8091` e `PORTAL_BASE_URL` aponta para o IP da Tailnet. Os links dos e-mails só abrem para quem está na Tailnet.

**Como quitar.** Seguir `portal/README.md` (regra `vinot.barbosamaria.online` no túnel, `cloudflared tunnel route dns`, reinício do cloudflared) e então trocar `PORTAL_BASE_URL` e `PORTAL_DEV=0`. Antes de abrir, rever o interruptor de cadastros (`portal_signups`) e o Turnstile, descritos na seção Security do README do portal.

## DT-3: o portal em produção é um container manual (aberto desde 30/10/2026)

**Situação.** O `vinot-portal` que serve o site não vem do `docker-compose.yml` deste repositório: foi criado à mão a partir do clone `~/vinot-portal` (imagem `vinot-portal:latest`, porta `100.70.92.116:8091`). Em 30/10 o código do clone foi integrado ao `main` (commit `4bf175a`), o clone foi alinhado ao `origin/main` e o container foi recriado a partir dele, com o SMTP ligado (`SMTP_PASSWORD_FILE` e bind de `/run/vinot-secrets/portal`, `PORTAL_DEV=0`). Rollback: container parado `vinot-portal-old` e imagem `vinot-portal:rollback-20261030b`.

**Pendente.** Como é container manual, não sobe sozinho no reboot sem `/run/vinot-secrets`: depois do boot, subir à mão. `docker/systemd/vinot-portal.service` existe mas **não foi instalado** (subiria o portal do compose por cima do manual).

**Como quitar.** Subir o portal pelo compose com `PORTAL_BIND=100.70.92.116` e `PORTAL_DOWNLOADS_DIR=/home/ubuntu/vinot-downloads` (hoje o compose monta `../data*` deste repo, e o manual monta o clone), desligar o container manual, apagar o clone, e então `./docker/systemd/install.sh app && ./install.sh boot`.

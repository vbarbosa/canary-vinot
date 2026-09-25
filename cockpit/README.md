# Cockpit VinOT

Painel web do mestre do jogo. Python + FastAPI + htmx, sem build.
A spec completa está no documento "Spec: Painel Administrativo VinOT (Cockpit)".

## Como funciona

- O login é a própria conta do jogo (tabela `accounts`, senha SHA1 igual ao servidor).
  Só entra conta que tem personagem God (`group_id` 6). A senha é conferida de novo a
  cada página: se mudar no jogo, o painel desloga.
- Ações em jogador viram linhas em `cockpit_commands`. O script
  `data/scripts/globalevents/cockpit.lua` lê essa fila a cada segundo e executa só as
  ações da lista fechada dele. Se o jogador estiver offline, itens, level, skills, outfit
  e montaria ficam na fila e entram quando ele logar.
- A cada 5 segundos o mesmo script grava quem está online em `cockpit_online`.
- Tudo que o painel faz fica em `cockpit_audit` (tela Histórico).
- Contas e personagens são criados, editados e apagados direto no banco (personagem só offline).
  Tibia coins também vão direto no banco, porque o servidor relê o saldo a cada uso.
- Métricas: CPU, memória, disco e uptime vêm do `/proc` da VM; jogadores, monstros e NPCs
  vêm da tabela `cockpit_metrics`, que a ponte Lua grava a cada minuto (guarda 7 dias).
- Logs: o painel lê só os arquivos dentro das pastas de `COCKPIT_LOG_DIRS`
  (padrão: `logs/` do servidor e `data/logs/` dos comandos de GM), em modo somente leitura.

## Subir na VM Oracle

1. No `docker/.env`, preencha `COCKPIT_BIND` com o IP da Tailscale da VM e
   `COCKPIT_SECRET` com `openssl rand -hex 32`.
2. Reinicie o servidor do jogo uma vez, para ele carregar `cockpit.lua`.
3. `cd docker && docker compose up -d --build cockpit`
4. Abra `http://100.70.92.116:8090` pela Tailscale.

Para atualizar na mão: `git pull` e `docker compose up -d --build cockpit`. O jogo não cai.

## Esteira (CI/CD)

- **Testes:** `.github/workflows/cockpit.yml` roda em todo PR e push na `main` que mexa no
  painel: compila o Python, carrega todos os templates e o `items.xml`, e confere a sintaxe
  do `cockpit.lua`.
- **Deploy:** a VM puxa sozinha. `deploy/auto-deploy.sh` roda no cron a cada minuto, busca
  o branch `DEPLOY_BRANCH` (padrão `main`) e, se tiver commit novo:
  - mudou `cockpit/` → reconstrói e sobe só o painel (o jogo não cai);
  - mudou `cockpit.lua` → reinicia o servidor do jogo (desligue com `RESTART_GAME=no`
    quando tiver gente jogando);
  - outras mudanças → só registra no log.

  Não precisa abrir porta nem guardar senha no GitHub. O log fica em `logs/deploy.log`,
  visível na tela Logs do painel. Instalação na VM (`crontab -e`):

      * * * * * DEPLOY_BRANCH=main flock -n /tmp/cockpit-deploy.lock ~/GitHub/canary-vinot/cockpit/deploy/auto-deploy.sh >> ~/GitHub/canary-vinot/logs/deploy.log 2>&1

## Ícones dos itens

Os ícones saem dos sprites do cliente 13.40. Rode uma vez na VM (baixa os assets do
GitHub, é grande):

    docker compose run --rm cockpit python tools/extract_icons.py --download

Sem ícones, o painel mostra um "?" no lugar e continua funcionando.

## Rodar local

    pip install -r requirements.txt
    MYSQL_HOST=127.0.0.1 MYSQL_DATABASE=otservbr-global COCKPIT_DATA_DIR=../data uvicorn app.main:app --port 8090

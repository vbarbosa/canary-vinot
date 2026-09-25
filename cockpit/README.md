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
- Agenda: tarefas que o painel roda sozinho (salvar, anúncio, limpar o chão, presentes, abrir e
  fechar o servidor). Quem executa é o próprio painel, uma vez por minuto, em horário de Brasília
  (`COCKPIT_TZ`). Com o painel desligado, as tarefas esperam ele voltar.
- Gráficos: o painel grava CPU, memória, carga, disco e o tempo de resposta do jogo a cada minuto
  em `cockpit_host_metrics` (7 dias). Os gráficos usam uPlot, copiado em `app/static`.
- Teleporte: a lista de lugares vem do datapack (templos, paradas de viagem dos NPCs, NPCs, a área
  com mais spawns de cada monstro e casas), mais os lugares salvos no painel. A foto é um recorte do
  mapa público do TibiaMaps, baixado na primeira vez para `COCKPIT_MAP_DIR`. O filtro Criaturas lista
  os monstros do mapa; escolhendo um, aparecem todos os pontos onde ele nasce (áreas vizinhas juntas),
  com a cidade mais perto, e dá para levar a turma direto.
- Economia: gold em bancos, mochilas, depósitos e guildas, Tibia coins, mercado e casas; um
  retrato por hora em `cockpit_economy` (90 dias).
- Mundo: autoloot, stamina, viagens grátis, acessos de quest, loot boost na party, rates e estágios de XP,
  skill e magic. O painel guarda em `cockpit_settings` e a ponte grava `cockpit-world.lua` ao lado do
  `config.lua` (que carrega esse arquivo por último; a ponte acrescenta essa linha se faltar), recarrega o
  config e troca as tabelas de estágios, sem reiniciar. Na primeira vez o painel aplica o pacote aprovado.
- Imobiliária: as 984 casas do mapa (`world/otservbr-house.xml`) com o dono da tabela `houses`. Dar,
  passar e despejar vão pela ponte Lua (`house_owner`). O aluguel do jogo fica desligado
  (`houseRentPeriod = "never"`) e quem cobra é o painel: semanal ou mensal, uma porcentagem do aluguel do
  mapa ou um valor próprio por casa, direto do banco do dono (`house_rent`, online ou offline). Sem saldo,
  tenta de novo no dia seguinte; depois de N falhas, despeja. Tudo fica no livro-caixa
  (`cockpit_house_log`), inclusive quem comprou casa no jogo.
- Logo: `tools/make_logo.py` desenha o logo em pixel art a partir das grades no próprio arquivo.

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

# Getting Started with docker

## - Requirements
- Docker 19 and docker-compose 1.17
- Execute the script root directory /docker/data/download-myaac.sh
- To use global ip change the login.py on world to use that ip and
also change in config.lua.dist
- Client pointing to http://<ip>:8080/login.php

### Default Values (docker-compose.yml)
- Ports: 7171, 7172, 80(web), 3306, 8080(login)
- Database Server: database
- Database Name/User/Password: otserver

### - Commands
To compile and start database, webserver and otserver just run
```
$ docker-compose up -d
```
Sometimes the server will not start due to database take too long to start
so you can restart it
```
docker-compose restart otserver

or

docker-compose stop otserver
docker-compose start otserver
```

To compile your changes in otserver, just stop and start
```
$ docker-compose up -d --build otserver
```

### - Observations
- The data folder persist db and webserver data;

## Operação nesta VM (Vinot)

Estado observado em 30/10/2026. Esta parte é específica da VM `manchete-store-server`; o resto deste arquivo é do projeto Canary original.

### Projeto Compose e containers
O compose desta pasta tem `name: otbr`. O `docker-compose.override.yml` é carregado junto (portas no IP do Tailscale e imagem do login local). Containers que rodam hoje:

| Container | Serviço | Porta publicada | Observação |
|---|---|---|---|
| `otbr-database-1` | `database` (mariadb) | `127.0.0.1:3306` | tem healthcheck; volume `otbr_db-volume` |
| `otbr-server-1` | `server` (jogo) | `100.70.92.116:7171` e `:7172` | monta `../data`, `../data-otservbr-global`, `../logs` |
| `otbr-login-1` | `login` (imagem `vinot/login-server:local`) | `100.70.92.116:8080`, `127.0.0.1:9090` | |
| `otbr-cockpit-1` | `cockpit` | `100.70.92.116:8090` | volume `otbr_cockpit-icons` |

Rede `otbr_canary-net`. Os serviços `server`, `login`, `cockpit` e `portal` esperam o `database` ficar saudável (`depends_on: service_healthy`).

O serviço `portal` existe no compose, mas **não é o que roda**. O container `vinot-portal` é outro: foi criado à mão em 08/10 a partir de um segundo clone deste mesmo repositório (`~/vinot-portal`, branch `main`), com a imagem `vinot-portal:latest`, porta `100.70.92.116:8091`, montando `~/vinot-portal/data*` e `~/vinot-downloads`, ligado à rede `otbr_canary-net`. Não tem labels do Compose, então não pertence a nenhum projeto. A imagem `otbr-portal` (do compose) existe, sem container.
Cuidado: um `docker compose up -d` sem lista de serviços tentaria criar o `portal` do compose na porta 8091. Suba só o que roda: `docker compose up -d database server login cockpit`.

### Inicialização e recuperação
- Não há unit systemd para este projeto. Quem o inicia é o Docker: todos os serviços do compose têm `restart: unless-stopped`, então os que estavam rodando quando a VM desligou voltam quando o Docker inicia.
- O Docker agora inicia no boot (habilitado em 30/10), depois do bloqueio do IMDS e de esperar o IP do Tailscale por até 90 s. A espera importa: as portas são publicadas no IP `100.70.92.116`.
- O `database` tem healthcheck; os demais só iniciam quando ele fica saudável. Container que cai é reiniciado pelo Docker.
- `vinot-portal` está com `restart: no` (aplicado com `docker update` em 30/10, por decisão: permanece manual até a origem ser formalizada). Isso não está registrado em nenhum compose: se o container for recriado à mão, volta à política padrão do `docker run`.
- Os containers deste projeto agora não alcançam o IMDS da OCI (regra nftables do host). Nenhum deles precisa dele.

Validado: o estado acima foi lido do Docker em 30/10 (4 containers rodando, `otbr-database-1` saudável, políticas conferidas com `docker inspect`). **Não testado:** que os quatro voltem sozinhos num reboot real, e a ordem em relação ao Tailscale e ao bloqueio do IMDS.

### Operação
```
cd ~/GitHub/canary-vinot/docker
docker compose ps
docker compose up -d database server login cockpit      # sobe o que roda hoje (sem o portal do compose)
docker compose logs -f server
docker inspect otbr-server-1 --format '{{.HostConfig.RestartPolicy.Name}} {{.State.Status}}'
```
Antes de recriar `otbr-server-1`, avise quem estiver jogando: recriar derruba a sessão.

### Segredos
As variáveis de `docker/.env` e a `key.pem` da raiz têm cópia no OCI Vault (compartimento `canary-vinot`; ver `COFRE.md`). A VM não tem permissão de ler esse compartimento (IAM restrito ao streaming), então o `.env` continua em disco e não é carregado do cofre. Só a administração humana lê essas cópias.

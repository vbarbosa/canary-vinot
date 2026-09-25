#!/usr/bin/env bash
# Pull-based deploy for the VM: runs from cron, needs no inbound access and no GitHub secrets.
# Brings in new commits of DEPLOY_BRANCH and rebuilds only what changed.
#   cockpit/**                              -> rebuild and restart the panel (game keeps running)
#   data/scripts/globalevents/cockpit.lua   -> restart the game server (only if RESTART_GAME=yes)
#   anything else                           -> logged; restart or rebuild the game by hand
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BRANCH="${DEPLOY_BRANCH:-main}"
RESTART_GAME="${RESTART_GAME:-yes}"
cd "$REPO"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [deploy] $*"; }

git fetch -q origin "$BRANCH"
old="$(git rev-parse HEAD)"
new="$(git rev-parse "origin/$BRANCH")"
[ "$old" = "$new" ] && exit 0

if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
	log "repo está no branch $(git rev-parse --abbrev-ref HEAD), esperado $BRANCH; nada feito"
	exit 1
fi

changed="$(git diff --name-only "$old" "$new")"
if ! git merge -q --ff-only "$new"; then
	log "não deu para avançar $BRANCH sem merge (mudança local no repo?); nada feito"
	exit 1
fi
log "atualizado ${old:0:7} -> ${new:0:7}: $(git log --format=%s -1 "$new")"

cd docker
if grep -q '^cockpit/' <<<"$changed"; then
	log "reconstruindo o painel"
	docker compose up -d --build cockpit
	log "painel no ar"
fi

if grep -qx 'data/scripts/globalevents/cockpit.lua' <<<"$changed"; then
	if [ "$RESTART_GAME" = "yes" ]; then
		log "ponte Lua mudou, reiniciando o servidor do jogo"
		docker compose restart server
		log "servidor do jogo reiniciado"
	else
		log "ponte Lua mudou; reinicie o servidor do jogo quando der (RESTART_GAME=no)"
	fi
fi

other="$(grep -v -e '^cockpit/' -e '^data/scripts/globalevents/cockpit.lua$' <<<"$changed" || true)"
if [ -n "$other" ]; then
	log "outras mudanças, não aplicadas automaticamente:"
	while IFS= read -r f; do echo "    $f"; done <<<"$other"
fi

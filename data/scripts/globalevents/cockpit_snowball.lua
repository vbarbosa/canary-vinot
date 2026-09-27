-- Snowball fight, started from the Cockpit panel (tela Eventos).
-- Players throw with !bola in the direction they face; a hit is a point and freezes the target for a moment.
-- Snowballs refill over time. Free-for-all or red against blue. Most points when time runs out wins.

CockpitEvents = CockpitEvents or {}

local S = { running = false }
CockpitEvents.snowball = S

local RANGE = 6
local TITLE = "Bolas de neve"

local function teamScores()
	if not S.G.teams then
		return nil
	end
	local t = { 0, 0 }
	for _, info in pairs(S.G.players) do
		t[info.team] = t[info.team] + info.score
	end
	return t
end

local function finish(reason)
	if not S.running then
		return
	end
	S.running = false
	local A, G = CockpitArena, S.G
	local scores = teamScores()
	A.finish(G, TITLE, A.best(G, scores), reason .. "; " .. A.scoreLine(G, scores))
end

local function tick()
	local A, G = CockpitArena, S.G
	G.tickEvent = nil
	if not S.running then
		return
	end
	G.elapsed = G.elapsed + 1
	for guid, info in pairs(G.players) do
		local p = Player(info.name)
		if not p then
			G.players[guid] = nil
		else
			if not A.inArena(G, p:getPosition()) then
				p:teleportTo(p:getClosestFreePosition(G.center, 4))
				p:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Nao saia da arena!")
			end
			if G.elapsed % S.reload == 0 and info.ammo < S.ammo then
				info.ammo = info.ammo + 1
			end
		end
	end
	if A.count(G) < 2 then
		return finish("sobrou menos de 2 jogadores")
	end
	if G.elapsed >= G.seconds then
		return finish("tempo acabou")
	end
	if G.elapsed % 30 == 0 then
		A.tell(G, A.scoreLine(G, teamScores()))
	end
	G.tickEvent = addEvent(tick, 1000)
end

function S.start(cfg)
	if S.running then
		return false, "ja tem uma guerra de bolas de neve rolando"
	end
	local A = CockpitArena
	local G = A.new(cfg)
	S.G = G
	S.ammo = A.num(G, "ammo", 1, 50, 10)
	S.reload = A.num(G, "reload", 1, 60, 4)
	S.freeze = A.num(G, "freeze", 0, 10, 2)
	G.teams = A.num(G, "teams", 0, 1, 1) == 1
	if A.gather(G, cfg.names, G.teams) < 2 then
		A.each(G, A.home)
		return false, "precisa de pelo menos 2 jogadores online"
	end
	for _, info in pairs(G.players) do
		info.ammo = S.ammo
	end
	S.running = true
	A.tell(G, "Guerra de bolas de neve! Diga !bola para jogar na direcao em que voce esta virado. Cada acerto vale 1 ponto.")
	G.tickEvent = addEvent(tick, 1000)
	return true, "Bolas de neve comecou com " .. A.count(G) .. " jogador(es)"
end

function S.stop()
	if not S.running then
		return false, "nenhuma guerra de bolas de neve rolando"
	end
	finish("parado pelo Mestre")
	return true, "Bolas de neve encerrado"
end

local freeze = Condition(CONDITION_PARALYZE)
freeze:setFormula(-0.9, 0, -0.9, 0)

local throw = TalkAction("!bola")

function throw.onSay(player, words, param)
	local G = S.G
	local info = S.running and G.players[player:getGuid()]
	if not info then
		player:sendCancelMessage("Voce nao esta numa guerra de bolas de neve.")
		return false
	end
	if info.last == os.time() then
		return false
	end
	if info.ammo <= 0 then
		player:sendCancelMessage("Sem bolas! Espere juntar mais neve.")
		return false
	end
	info.last, info.ammo = os.time(), info.ammo - 1
	local from = player:getPosition()
	local dir = player:getDirection()
	local at = Position(from)
	for _ = 1, RANGE do
		local nextPos = Position(at)
		nextPos:getNextPosition(dir)
		local tile = Tile(nextPos)
		if not tile or tile:hasFlag(TILESTATE_BLOCKSOLID) then
			break
		end
		at = nextPos
		local target = tile:getTopCreature()
		local hit = target and target:isPlayer() and G.players[target:getGuid()]
		if hit and (not G.teams or hit.team ~= info.team) then
			from:sendDistanceEffect(at, CONST_ANI_SNOWBALL)
			at:sendMagicEffect(CONST_ME_ICEAREA)
			info.score = info.score + 1
			if S.freeze > 0 then
				freeze:setParameter(CONDITION_PARAM_TICKS, S.freeze * 1000)
				target:addCondition(freeze)
			end
			target:sendTextMessage(MESSAGE_EVENT_ADVANCE, player:getName() .. " te acertou com uma bola de neve!")
			player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Acertou " .. target:getName() .. "! Pontos: " .. info.score .. ". Bolas: " .. info.ammo .. ".")
			return false
		end
	end
	from:sendDistanceEffect(at, CONST_ANI_SNOWBALL)
	at:sendMagicEffect(CONST_ME_POFF)
	player:sendCancelMessage("Errou! Bolas: " .. info.ammo .. ".")
	return false
end

throw:separator(" ")
throw:groupType("normal")
throw:register()

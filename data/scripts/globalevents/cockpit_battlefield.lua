-- Battlefield, started from the Cockpit panel (tela Eventos). Red against blue with real fighting.
-- Nobody really dies: a blow that would kill takes a life instead, heals the player and sends them back to
-- their side. With no lives left they go home. Teammates cannot hurt each other.
-- A no-PvP world is switched to PvP while it runs and switched back at the end.

CockpitEvents = CockpitEvents or {}

local B = { running = false }
CockpitEvents.battlefield = B

local TITLE = "Battlefield"

local function side(team)
	local G = B.G
	local dx = math.max(2, G.radius - 3)
	return Position(G.center.x + (team == 1 and -dx or dx), G.center.y, G.center.z)
end

local function livesLeft()
	local t = { 0, 0 }
	for _, info in pairs(B.G.players) do
		t[info.team] = t[info.team] + info.lives
	end
	return t
end

local function finish(reason)
	if not B.running then
		return
	end
	B.running = false
	local A, G = CockpitArena, B.G
	local lives = livesLeft()
	local winners = {}
	if lives[1] ~= lives[2] then
		local best = lives[1] > lives[2] and 1 or 2
		for _, info in pairs(G.players) do
			if info.team == best then
				winners[#winners + 1] = info.name
			end
		end
	end
	A.each(G, function(p)
		p:unregisterEvent("CockpitBattleHP")
	end)
	A.finish(G, TITLE, winners, string.format("%s; vidas: Vermelho %d x %d Azul; %s", reason, lives[1], lives[2], A.scoreLine(G)))
	if B.restoreWorld then
		Game.setWorldType(B.restoreWorld)
		B.restoreWorld = nil
	end
end

local function tick()
	local A, G = CockpitArena, B.G
	G.tickEvent = nil
	if not B.running then
		return
	end
	G.elapsed = G.elapsed + 1
	for guid, info in pairs(G.players) do
		local p = Player(info.name)
		if not p then
			G.players[guid] = nil
		elseif not A.inArena(G, p:getPosition()) then
			p:teleportTo(p:getClosestFreePosition(side(info.team), 3))
		end
	end
	local lives = livesLeft()
	if lives[1] == 0 or lives[2] == 0 then
		return finish("um time ficou sem ninguem")
	end
	if G.elapsed >= G.seconds then
		return finish("tempo acabou")
	end
	if G.elapsed % 60 == 0 then
		A.tell(G, string.format("Vidas: Vermelho %d x %d Azul", lives[1], lives[2]))
	end
	G.tickEvent = addEvent(tick, 1000)
end

function B.start(cfg)
	if B.running then
		return false, "ja tem um Battlefield rolando"
	end
	local A = CockpitArena
	local G = A.new(cfg)
	B.G = G
	local lives = A.num(G, "lives", 1, 10, 2)
	if A.gather(G, cfg.names, true, function(info)
		return A.spot(G, side(info.team), 1)
	end) < 2 then
		A.each(G, A.home)
		return false, "precisa de pelo menos 2 jogadores online"
	end
	A.each(G, function(p, info)
		info.lives = lives
		p:registerEvent("CockpitBattleHP")
	end)
	if Game.getWorldType() == WORLD_TYPE_NO_PVP then
		B.restoreWorld = WORLD_TYPE_NO_PVP
		Game.setWorldType(WORLD_TYPE_PVP)
	end
	B.running = true
	A.tell(G, "Battlefield! Vermelho contra Azul, cada um com " .. lives .. " vida(s). Ninguem morre de verdade. Vence o time que sobrar.")
	G.tickEvent = addEvent(tick, 1000)
	return true, "Battlefield comecou com " .. A.count(G) .. " jogador(es)"
end

function B.stop()
	if not B.running then
		return false, "nenhum Battlefield rolando"
	end
	finish("parado pelo Mestre")
	return true, "Battlefield encerrado"
end

local hp = CreatureEvent("CockpitBattleHP")

function hp.onHealthChange(creature, attacker, primaryDamage, primaryType, secondaryDamage, secondaryType, origin)
	local G = B.G
	local info = B.running and creature:isPlayer() and G.players[creature:getGuid()]
	if not info or primaryType == COMBAT_HEALING then
		return primaryDamage, primaryType, secondaryDamage, secondaryType
	end
	local from = attacker and attacker:isPlayer() and G.players[attacker:getGuid()]
	if from and from.team == info.team and attacker ~= creature then
		return 0, primaryType, 0, secondaryType
	end
	if primaryDamage + secondaryDamage < creature:getHealth() then
		return primaryDamage, primaryType, secondaryDamage, secondaryType
	end
	-- would die: lose a life instead
	info.lives = info.lives - 1
	if from then
		from.score = from.score + 1
	end
	local A = CockpitArena
	local who = from and attacker:getName() or "a arena"
	creature:getPosition():sendMagicEffect(CONST_ME_MORTAREA)
	if info.lives <= 0 then
		A.tell(G, creature:getName() .. " foi derrubado por " .. who .. " e esta fora!")
		addEvent(function(guid)
			if B.running then
				A.leave(G, guid, "sem vidas")
			end
		end, 0, creature:getGuid())
	else
		A.tell(G, creature:getName() .. " foi derrubado por " .. who .. ". Vidas: " .. info.lives .. ".")
		creature:addHealth(creature:getMaxHealth())
		addEvent(function(name, team)
			local p = Player(name)
			if p and B.running then
				p:teleportTo(p:getClosestFreePosition(side(team), 3))
			end
		end, 0, creature:getName(), info.team)
	end
	return 0, primaryType, 0, secondaryType
end

hp:register()

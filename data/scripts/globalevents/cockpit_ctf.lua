-- Capture the flag, started from the Cockpit panel (tela Eventos).
-- Red base on the west of the arena, blue on the east. Step on the enemy base to take their flag and bring it
-- to your own base (with your own flag at home) to score. An enemy standing next to the carrier sends the flag back.

CockpitEvents = CockpitEvents or {}

local C = { running = false }
CockpitEvents.ctf = C

local TITLE = "Capture a bandeira"
local GRACE = 2 -- half-second ticks after a pick-up before the carrier can be tagged

local function base(team)
	local G = C.G
	local dx = G.radius - 2
	return Position(G.center.x + (team == 1 and -dx or dx), G.center.y, G.center.z)
end

local function carrierOf(team)
	local guid = C.flags[team].carrier
	return guid and C.G.players[guid] and Player(C.G.players[guid].name), guid
end

local function returnFlag(team, why)
	C.flags[team].carrier = nil
	base(team):sendMagicEffect(CockpitArena.TEAMS[team].effect)
	CockpitArena.tell(C.G, "Bandeira do time " .. CockpitArena.TEAMS[team].name .. " voltou para a base (" .. why .. ").")
end

local function finish(reason)
	if not C.running then
		return
	end
	C.running = false
	local A, G = CockpitArena, C.G
	A.finish(G, TITLE, A.best(G, C.caps), reason .. "; " .. A.scoreLine(G, C.caps))
end

local function tick()
	local A, G = CockpitArena, C.G
	G.tickEvent = nil
	if not C.running then
		return
	end
	G.elapsed = G.elapsed + 1 -- half seconds
	for guid, info in pairs(G.players) do
		local p = Player(info.name)
		if not p then
			G.players[guid] = nil
			for team = 1, 2 do
				if C.flags[team].carrier == guid then
					returnFlag(team, info.name .. " saiu do jogo")
				end
			end
		elseif not A.inArena(G, p:getPosition()) then
			for team = 1, 2 do
				if C.flags[team].carrier == guid then
					returnFlag(team, info.name .. " saiu da arena")
				end
			end
			p:teleportTo(p:getClosestFreePosition(base(info.team), 3))
		end
	end
	if A.count(G, function(i)
		return i.team == 1
	end) == 0 or A.count(G, function(i)
		return i.team == 2
	end) == 0 then
		return finish("um time ficou vazio")
	end

	for guid, info in pairs(G.players) do
		local p = Player(info.name)
		local pos = p:getPosition()
		local mine, enemy = info.team, 3 - info.team
		-- take the enemy flag
		if not C.flags[enemy].carrier and pos:getDistance(base(enemy)) <= 1 then
			C.flags[enemy].carrier, C.flags[enemy].since = guid, G.elapsed
			A.tell(G, info.name .. " pegou a bandeira do time " .. A.TEAMS[enemy].name .. "!")
		end
		-- score: carrying the enemy flag, own flag at home, back at own base
		if C.flags[enemy].carrier == guid and not C.flags[mine].carrier and pos:getDistance(base(mine)) <= 1 then
			C.caps[mine] = C.caps[mine] + 1
			C.flags[enemy].carrier = nil
			info.score = info.score + 1
			A.tell(G, info.name .. " capturou a bandeira! " .. A.scoreLine(G, C.caps))
			pos:sendMagicEffect(CONST_ME_FIREWORK_YELLOW)
			if C.caps[mine] >= C.limit then
				return finish("time " .. A.TEAMS[mine].name .. " chegou a " .. C.limit)
			end
		end
	end

	-- tag: an enemy next to the carrier sends the flag home
	for team = 1, 2 do
		local carrier = carrierOf(team)
		if carrier and G.elapsed - (C.flags[team].since or 0) > GRACE then
			local cpos = carrier:getPosition()
			for _, info in pairs(G.players) do
				if info.team == team then
					local p = Player(info.name)
					if p and p:getPosition().z == cpos.z and p:getPosition():getDistance(cpos) <= 1 then
						returnFlag(team, info.name .. " pegou " .. carrier:getName())
						break
					end
				end
			end
		end
	end

	if G.elapsed % 2 == 0 then
		for team = 1, 2 do
			local carrier = carrierOf(team)
			if carrier then
				carrier:getPosition():sendMagicEffect(A.TEAMS[team].effect)
			else
				base(team):sendMagicEffect(A.TEAMS[team].effect)
			end
		end
	end
	if G.elapsed >= G.seconds * 2 then
		return finish("tempo acabou")
	end
	if G.elapsed % 60 == 0 then
		A.tell(G, A.scoreLine(G, C.caps))
	end
	G.tickEvent = addEvent(tick, 500)
end

function C.start(cfg)
	if C.running then
		return false, "ja tem um Capture a bandeira rolando"
	end
	local A = CockpitArena
	local G = A.new(cfg)
	C.G = G
	C.limit = A.num(G, "caps", 1, 20, 3)
	C.caps = { 0, 0 }
	C.flags = { {}, {} }
	if A.gather(G, cfg.names, true, function(info)
		return A.spot(G, base(info.team), 1)
	end) < 2 then
		A.each(G, A.home)
		return false, "precisa de pelo menos 2 jogadores online"
	end
	C.running = true
	A.tell(G, "Capture a bandeira! Pise na base inimiga para pegar a bandeira e traga para a sua. Encostar no inimigo que carrega a sua bandeira faz ela voltar. Vence quem fizer " .. C.limit .. ".")
	G.tickEvent = addEvent(tick, 500)
	return true, "Capture a bandeira comecou com " .. A.count(G) .. " jogador(es)"
end

function C.stop()
	if not C.running then
		return false, "nenhum Capture a bandeira rolando"
	end
	finish("parado pelo Mestre")
	return true, "Capture a bandeira encerrado"
end

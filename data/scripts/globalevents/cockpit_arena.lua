-- Shared helpers for the Cockpit mini-games (cockpit_<kind>.lua): taking players to the arena,
-- red and blue teams, sending everyone home, prizes and writing the result for the panel.

CockpitArena = CockpitArena or {}
local A = CockpitArena

A.TEAMS = {
	{ name = "Vermelho", color = 94, effect = CONST_ME_FIREWORK_RED },
	{ name = "Azul", color = 88, effect = CONST_ME_FIREWORK_BLUE },
}

-- cfg comes from the bridge: center, radius, names, eventId, seconds, prize, gold, raw (all key=value pairs)
function A.new(cfg)
	return {
		running = false,
		center = cfg.center,
		radius = math.max(4, math.min(cfg.radius or 8, 30)),
		eventId = cfg.eventId or 0,
		seconds = cfg.seconds or 300,
		prize = cfg.prize or "",
		gold = cfg.gold or 0,
		raw = cfg.raw or {},
		players = {}, -- guid -> { name, team, score, ... }
		elapsed = 0,
	}
end

function A.num(G, key, lo, hi, default)
	local v = tonumber(G.raw[key]) or default
	return math.max(lo, math.min(hi, math.floor(v)))
end

function A.player(G, guid)
	local info = G.players[guid]
	return info and Player(info.name)
end

function A.each(G, fn)
	for guid, info in pairs(G.players) do
		local p = Player(info.name)
		if p then
			fn(p, info, guid)
		end
	end
end

function A.count(G, filter)
	local n = 0
	for _, info in pairs(G.players) do
		if not filter or filter(info) then
			n = n + 1
		end
	end
	return n
end

function A.tell(G, text)
	A.each(G, function(p)
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, text)
	end)
end

function A.inArena(G, pos)
	return pos.z == G.center.z and pos:getDistance(G.center) <= G.radius + 1
end

function A.spot(G, around, spread)
	local p = Position(around.x + math.random(-spread, spread), around.y + math.random(-spread, spread), around.z)
	return p
end

local function paint(p, team)
	local outfit = p:getOutfit()
	outfit.lookHead, outfit.lookBody, outfit.lookLegs, outfit.lookFeet = team.color, team.color, team.color, team.color
	local c = Condition(CONDITION_OUTFIT)
	c:setOutfit(outfit)
	c:setTicks(-1)
	p:addCondition(c)
end

-- Teleports the named players in. With teams, splits them into red and blue by level so both sides are even.
-- spawnFor(info) may return where each one starts (default: near the centre). Returns how many came.
function A.gather(G, names, teams, spawnFor)
	local list = {}
	for _, name in ipairs(names) do
		local p = Player(name)
		if p then
			list[#list + 1] = p
		end
	end
	table.sort(list, function(a, b)
		return a:getLevel() > b:getLevel()
	end)
	for i, p in ipairs(list) do
		local info = { name = p:getName(), score = 0 }
		if teams then
			-- 1,2,2,1,1,2,2,1... keeps the strongest spread between the two sides
			local slot = (i - 1) % 4
			info.team = (slot == 0 or slot == 3) and 1 or 2
		end
		local target = spawnFor and spawnFor(info) or A.spot(G, G.center, 2)
		local pos = p:getClosestFreePosition(target, 4)
		if pos.x ~= 0 then
			G.players[p:getGuid()] = info
			p:teleportTo(pos)
			pos:sendMagicEffect(CONST_ME_TELEPORT)
			if teams then
				paint(p, A.TEAMS[info.team])
				p:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Voce esta no time " .. A.TEAMS[info.team].name .. ".")
			end
		end
	end
	return A.count(G)
end

function A.home(p)
	p:removeCondition(CONDITION_OUTFIT)
	p:removeCondition(CONDITION_INFIGHT)
	p:setSkull(SKULL_NONE)
	p:setSkullTime(0)
	p:addHealth(p:getMaxHealth())
	p:addMana(p:getMaxMana())
	p:teleportTo(p:getTown():getTemplePosition())
	p:getPosition():sendMagicEffect(CONST_ME_TELEPORT)
end

function A.leave(G, guid, why)
	local info = G.players[guid]
	if not info then
		return
	end
	G.players[guid] = nil
	local p = Player(info.name)
	if p then
		A.home(p)
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Voce saiu do evento: " .. why .. ".")
	end
	G.out = G.out or {}
	G.out[#G.out + 1] = info.name
end

function A.givePrize(G, p)
	for id, count in G.prize:gmatch("(%d+):(%d+)") do
		p:addItem(tonumber(id), tonumber(count))
	end
	if G.gold > 0 then
		p:setBankBalance(p:getBankBalance() + G.gold)
	end
	p:getPosition():sendMagicEffect(CONST_ME_FIREWORK_YELLOW)
end

-- winners: list of names; title: e.g. "Bolas de neve"; details: short text for the panel
function A.finish(G, title, winners, details)
	G.running = false
	if G.tickEvent then
		stopEvent(G.tickEvent)
		G.tickEvent = nil
	end
	local won = {}
	for _, name in ipairs(winners) do
		won[name] = true
	end
	A.each(G, function(p, info)
		if won[info.name] then
			A.givePrize(G, p)
		end
		if not G.stayPut then
			A.home(p)
		end
	end)
	local text = #winners > 0 and (title .. ": vitoria de " .. table.concat(winners, ", ") .. "!") or (title .. " terminou sem vencedor.")
	for _, p in ipairs(Game.getPlayers()) do
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, text)
	end
	db.query(string.format("UPDATE `cockpit_events` SET `status` = 'done', `ended_at` = %d, `winners` = %s, `details` = %s WHERE `id` = %d", os.time(), db.escapeString(table.concat(winners, ", ")), db.escapeString(details or ""), G.eventId))
	G.players = {}
end

-- names with the best score (score > 0), or the whole best team when teams play
function A.best(G, teamScores)
	local winners = {}
	if teamScores then
		local best = math.max(teamScores[1], teamScores[2])
		if best <= 0 and not G.anyoneWins then
			return winners
		end
		for _, info in pairs(G.players) do
			if teamScores[info.team] == best then
				winners[#winners + 1] = info.name
			end
		end
		return winners
	end
	local best = 0
	for _, info in pairs(G.players) do
		best = math.max(best, info.score)
	end
	if best > 0 then
		for _, info in pairs(G.players) do
			if info.score == best then
				winners[#winners + 1] = info.name
			end
		end
	end
	return winners
end

function A.scoreLine(G, teamScores)
	if teamScores then
		return string.format("Placar: Vermelho %d x %d Azul", teamScores[1], teamScores[2])
	end
	local list = {}
	for _, info in pairs(G.players) do
		list[#list + 1] = info
	end
	table.sort(list, function(a, b)
		return a.score > b.score
	end)
	local parts = {}
	for i = 1, math.min(5, #list) do
		parts[#parts + 1] = list[i].name .. " " .. list[i].score
	end
	return "Placar: " .. table.concat(parts, ", ")
end

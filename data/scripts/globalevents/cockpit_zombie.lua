-- Zombie mini-game, started from the Cockpit panel (tela Eventos).
-- Players are taken to an arena; zombies hunt them and one touch takes a player out.
-- The last one standing (or everyone left when time runs out) wins the prize.
-- Results go to `cockpit_events` so the panel can show them.

CockpitEvents = CockpitEvents or {}

local Z = { running = false }
CockpitEvents.zombie = Z

local COUNTDOWN = 10 -- seconds between the teleport and the first zombie
local MONSTER = "Zombie"

local function participants()
	local list = {}
	for guid in pairs(Z.alive) do
		local p = Player(Z.names[guid])
		if p then
			list[#list + 1] = p
		end
	end
	return list
end

local function tell(text, all)
	for guid in pairs(all and Z.names or Z.alive) do
		local p = Player(Z.names[guid])
		if p then
			p:sendTextMessage(MESSAGE_EVENT_ADVANCE, text)
		end
	end
end

local function aliveCount()
	local n = 0
	for _ in pairs(Z.alive) do
		n = n + 1
	end
	return n
end

local function spawnZombies(amount)
	for _ = 1, amount do
		local pos = Position(Z.center.x + math.random(-Z.radius + 1, Z.radius - 1), Z.center.y + math.random(-Z.radius + 1, Z.radius - 1), Z.center.z)
		local monster = Game.createMonster(MONSTER, pos, false, true)
		if monster then
			monster:registerEvent("CockpitZombieShield")
			monster:changeSpeed(Z.speed)
			monster:setSkull(SKULL_BLACK)
			Z.zombies[monster:getId()] = true
			pos:sendMagicEffect(CONST_ME_MORTAREA)
		end
	end
end

local function clearZombies()
	for cid in pairs(Z.zombies) do
		local m = Monster(cid)
		if m then
			m:getPosition():sendMagicEffect(CONST_ME_POFF)
			m:remove()
		end
	end
	Z.zombies = {}
end

local function sendHome(player)
	player:unregisterEvent("CockpitZombieHit")
	player:addHealth(player:getMaxHealth())
	player:teleportTo(player:getTown():getTemplePosition())
	player:getPosition():sendMagicEffect(CONST_ME_TELEPORT)
end

local function eliminate(player, why)
	local guid = player:getGuid()
	if not Z.alive[guid] then
		return
	end
	Z.alive[guid] = nil
	Z.out[#Z.out + 1] = player:getName()
	player:getPosition():sendMagicEffect(CONST_ME_MORTAREA)
	sendHome(player)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Voce esta fora do Zombie: " .. why .. ".")
	tell(player:getName() .. " " .. why .. "! Restam " .. aliveCount() .. ".")
end

local function givePrize(player)
	for id, count in Z.prize:gmatch("(%d+):(%d+)") do
		player:addItem(tonumber(id), tonumber(count))
	end
	if Z.gold > 0 then
		player:setBankBalance(player:getBankBalance() + Z.gold)
	end
	player:getPosition():sendMagicEffect(CONST_ME_FIREWORK_YELLOW)
end

local function finish(reason)
	if not Z.running then
		return
	end
	Z.running = false
	if Z.tickEvent then
		stopEvent(Z.tickEvent)
		Z.tickEvent = nil
	end
	clearZombies()
	local winners = {}
	for _, p in ipairs(participants()) do
		winners[#winners + 1] = p:getName()
		givePrize(p)
		sendHome(p)
	end
	local text = #winners > 0 and ("Vencedor(es) do Zombie: " .. table.concat(winners, ", ") .. "!") or "Os zombies venceram desta vez!"
	for _, p in ipairs(Game.getPlayers()) do
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, text)
	end
	db.query(string.format(
		"UPDATE `cockpit_events` SET `status` = 'done', `ended_at` = %d, `winners` = %s, `details` = %s WHERE `id` = %d",
		os.time(), db.escapeString(table.concat(winners, ", ")),
		db.escapeString(reason .. (#Z.out > 0 and ("; saiu: " .. table.concat(Z.out, ", ")) or "")), Z.eventId
	))
end

local function tick()
	Z.tickEvent = nil
	if not Z.running then
		return
	end
	Z.elapsed = Z.elapsed + 1
	for guid in pairs(Z.alive) do
		local p = Player(Z.names[guid])
		if not p then
			Z.alive[guid] = nil
			Z.out[#Z.out + 1] = Z.names[guid] .. " (saiu do jogo)"
		elseif p:getPosition().z ~= Z.center.z or p:getPosition():getDistance(Z.center) > Z.radius + 1 then
			eliminate(p, "saiu da arena")
		end
	end
	local alive = aliveCount()
	if alive == 0 or (Z.started > 1 and alive <= 1) then
		return finish(alive == 1 and "ultimo de pe" or "todos pegos")
	end
	if Z.elapsed >= Z.seconds then
		return finish("tempo acabou")
	end
	if Z.elapsed == COUNTDOWN then
		tell("Os zombies acordaram! Corra!", true)
		spawnZombies(Z.first)
	elseif Z.elapsed < COUNTDOWN then
		for _, p in ipairs(participants()) do
			p:say(tostring(COUNTDOWN - Z.elapsed), TALKTYPE_MONSTER_SAY)
		end
	elseif (Z.elapsed - COUNTDOWN) % Z.every == 0 then
		spawnZombies(1)
		tell("Mais um zombie entrou na arena!")
	end
	Z.tickEvent = addEvent(tick, 1000)
end

-- cfg: center (Position), radius, names (list), seconds, first, every, speed, prize ("id:count,..."), gold, eventId
function Z.start(cfg)
	if Z.running then
		return false, "ja tem um Zombie rolando"
	end
	Z.center, Z.radius = cfg.center, math.max(4, math.min(cfg.radius, 30))
	Z.seconds, Z.first, Z.every = cfg.seconds + COUNTDOWN, math.max(1, cfg.first), math.max(5, cfg.every)
	Z.speed, Z.prize, Z.gold, Z.eventId = cfg.speed, cfg.prize or "", cfg.gold or 0, cfg.eventId
	Z.alive, Z.names, Z.zombies, Z.out, Z.elapsed = {}, {}, {}, {}, 0
	for _, name in ipairs(cfg.names) do
		local p = Player(name)
		if p then
			local pos = p:getClosestFreePosition(Position(Z.center.x + math.random(-2, 2), Z.center.y + math.random(-2, 2), Z.center.z), 4)
			if pos.x ~= 0 then
				Z.alive[p:getGuid()] = true
				Z.names[p:getGuid()] = p:getName()
				p:teleportTo(pos)
				pos:sendMagicEffect(CONST_ME_TELEPORT)
				p:registerEvent("CockpitZombieHit")
			end
		end
	end
	Z.started = aliveCount()
	if Z.started == 0 then
		return false, "ninguem online para jogar"
	end
	Z.running = true
	tell("Zombie! Fuja dos zombies e nao saia da arena. Comeca em " .. COUNTDOWN .. " segundos.", true)
	Z.tickEvent = addEvent(tick, 1000)
	return true, "Zombie comecou com " .. Z.started .. " jogador(es)"
end

function Z.stop()
	if not Z.running then
		return false, "nenhum Zombie rolando"
	end
	finish("parado pelo Mestre")
	return true, "Zombie encerrado"
end

-- a zombie touch takes the player out instead of hurting
local hit = CreatureEvent("CockpitZombieHit")

function hit.onHealthChange(creature, attacker, primaryDamage, primaryType, secondaryDamage, secondaryType, origin)
	if Z.running and creature:isPlayer() and attacker and Z.zombies[attacker:getId()] then
		eliminate(creature, "foi pego por um zombie")
		return 0, primaryType, 0, secondaryType
	end
	return primaryDamage, primaryType, secondaryDamage, secondaryType
end

hit:register()

-- players cannot kill the zombies
local shield = CreatureEvent("CockpitZombieShield")

function shield.onHealthChange(creature, attacker, primaryDamage, primaryType, secondaryDamage, secondaryType, origin)
	return 0, primaryType, 0, secondaryType
end

shield:register()

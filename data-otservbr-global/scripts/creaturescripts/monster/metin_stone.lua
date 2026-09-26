-- Pedra Metin: waves as it loses health, loot for everyone who hit it when it dies. Per-instance state
-- (MetinState, a global table keyed by the monster's creature id) is set by the bridge
-- (data/scripts/globalevents/cockpit.lua, action metin_spawn) right after it creates the monster; this
-- file only reads it. Lost on restart, same as the panel's other in-memory state.
MetinState = MetinState or {}

-- "75,Rotworm,5;50,Rotworm Queen,1" -> [{at=75, name="Rotworm", amount=5}, ...], furthest wave first
function MetinParseWaves(text)
	local out = {}
	for at, name, amount in string.gmatch(text or "", "(%d+),([^,;]+),(%d+)") do
		out[#out + 1] = { at = tonumber(at), name = name, amount = tonumber(amount) }
	end
	table.sort(out, function(a, b) return a.at > b.at end)
	return out
end

-- "3031,80,10,50;3035,40,1,5" -> [{item=3031, chance=80, min=10, max=50}, ...]
function MetinParseLoot(text)
	local out = {}
	for item, chance, lo, hi in string.gmatch(text or "", "(%d+),(%d+),(%d+),(%d+)") do
		out[#out + 1] = { item = tonumber(item), chance = tonumber(chance), min = tonumber(lo), max = tonumber(hi) }
	end
	return out
end

-- Ground with no blocking flag, close to a Metin Stone, for the monsters its waves spawn.
local function spotNear(center, radius)
	for _ = 1, 12 do
		local pos = Position(center.x + math.random(-radius, radius), center.y + math.random(-radius, radius), center.z)
		local tile = Tile(pos)
		if tile and tile:getGround() and not tile:hasFlag(TILESTATE_BLOCKSOLID) and not tile:getTopCreature() then
			return pos
		end
	end
	return center
end

local metinThink = CreatureEvent("MetinStoneThink")

function metinThink.onThink(creature)
	local state = MetinState[creature:getId()]
	if not state then
		return true
	end
	local maxHp = creature:getMaxHealth()
	if maxHp <= 0 then
		return true
	end
	local hp = creature:getHealth()
	local pct = (hp / maxHp) * 100
	if hp ~= state.lastReported then
		state.lastReported = hp
		db.query(string.format("UPDATE `cockpit_metin_active` SET `health_now` = %d WHERE `id` = %d", hp, state.activeId))
	end
	local pos = creature:getPosition()
	for _, wave in ipairs(state.waves) do
		if pct <= wave.at and not state.fired[wave.at] then
			state.fired[wave.at] = true
			for _ = 1, wave.amount do
				Game.createMonster(wave.name, spotNear(pos, 3), false, true)
			end
			pos:sendMagicEffect(CONST_ME_MAGIC_RED)
			Game.broadcastMessage(string.format("A pedra Metin ficou furiosa e chamou %d %s!", wave.amount, wave.name), MESSAGE_EVENT_ADVANCE)
		end
	end
	return true
end

metinThink:register()

local metinDeath = CreatureEvent("MetinStoneDeath")

function metinDeath.onDeath(creature)
	local state = MetinState[creature:getId()]
	MetinState[creature:getId()] = nil
	if not state then
		return true
	end
	local monster = creature:getMonster()
	local damageMap = monster and monster:getDamageMap() or {}
	for cid, entry in pairs(damageMap) do
		local player = Player(cid)
		local given = {}
		if player then
			for _, drop in ipairs(state.loot) do
				if math.random(1, 100) <= drop.chance then
					local amount = math.random(drop.min, drop.max)
					player:addItem(drop.item, amount)
					given[#given + 1] = amount .. "x " .. drop.item
				end
			end
		end
		db.query(string.format(
			"INSERT INTO `cockpit_metin_damage` (`active_id`, `player_id`, `player_name`, `damage`, `loot`) VALUES (%d, %d, %s, %d, %s)",
			state.activeId, player and player:getGuid() or 0, db.escapeString(player and player:getName() or "desconhecido"),
			entry.total, db.escapeString(table.concat(given, ", "))
		))
	end
	db.query(string.format(
		"UPDATE `cockpit_metin_active` SET `status` = 'destroyed', `health_now` = 0, `ended_at` = %d WHERE `id` = %d",
		os.time(), state.activeId
	))
	creature:getPosition():sendMagicEffect(CONST_ME_EXPLOSIONHIT)
	Game.broadcastMessage("A pedra Metin foi destruida!", MESSAGE_EVENT_ADVANCE)
	return true
end

metinDeath:register()

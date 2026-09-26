-- Cockpit bridge: the web admin panel (cockpit/) writes rows into `cockpit_commands`
-- and this script runs them against the live game. Only the actions listed in
-- `actions` below can run; the panel never sends Lua or SQL to execute.
-- It also writes a snapshot of who is online to `cockpit_online` for the panel.

local POLL_INTERVAL = 1000
local SNAPSHOT_EVERY = 5 -- polls
local BATCH_SIZE = 100
local MAGIC_SKILL = 99

local tablesSql = {
	[[CREATE TABLE IF NOT EXISTS `cockpit_commands` (
		`id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		`action` VARCHAR(32) NOT NULL,
		`target` VARCHAR(255) NOT NULL DEFAULT '',
		`arg1` BIGINT NOT NULL DEFAULT 0,
		`arg2` BIGINT NOT NULL DEFAULT 0,
		`arg3` BIGINT NOT NULL DEFAULT 0,
		`arg4` BIGINT NOT NULL DEFAULT 0,
		`text` VARCHAR(1024) NOT NULL DEFAULT '',
		`status` VARCHAR(16) NOT NULL DEFAULT 'pending',
		`result` VARCHAR(255) NOT NULL DEFAULT '',
		`created_by` VARCHAR(255) NOT NULL DEFAULT '',
		`created_at` INT UNSIGNED NOT NULL DEFAULT 0,
		`done_at` INT UNSIGNED NOT NULL DEFAULT 0,
		PRIMARY KEY (`id`),
		KEY `cockpit_commands_status` (`status`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_metrics` (
		`ts` INT UNSIGNED NOT NULL,
		`players` INT NOT NULL DEFAULT 0,
		`monsters` INT NOT NULL DEFAULT 0,
		`npcs` INT NOT NULL DEFAULT 0,
		`lua_kb` INT NOT NULL DEFAULT 0,
		`started_at` INT UNSIGNED NOT NULL DEFAULT 0,
		PRIMARY KEY (`ts`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_online` (
		`player_id` INT NOT NULL,
		`name` VARCHAR(255) NOT NULL,
		`level` INT NOT NULL DEFAULT 0,
		`vocation` VARCHAR(64) NOT NULL DEFAULT '',
		`health` INT NOT NULL DEFAULT 0,
		`healthmax` INT NOT NULL DEFAULT 0,
		`posx` INT NOT NULL DEFAULT 0,
		`posy` INT NOT NULL DEFAULT 0,
		`posz` INT NOT NULL DEFAULT 0,
		`updated_at` INT UNSIGNED NOT NULL DEFAULT 0,
		PRIMARY KEY (`player_id`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_metin_types` (
		`id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
		`name` VARCHAR(64) NOT NULL,
		`health` INT UNSIGNED NOT NULL DEFAULT 5000,
		`waves` VARCHAR(1000) NOT NULL DEFAULT '',
		`loot` VARCHAR(1000) NOT NULL DEFAULT '',
		`created_at` INT UNSIGNED NOT NULL DEFAULT 0,
		PRIMARY KEY (`id`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_metin_active` (
		`id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
		`type_id` INT UNSIGNED NOT NULL,
		`type_name` VARCHAR(64) NOT NULL DEFAULT '',
		`x` INT NOT NULL,
		`y` INT NOT NULL,
		`z` TINYINT NOT NULL,
		`health_max` INT UNSIGNED NOT NULL DEFAULT 0,
		`health_now` INT UNSIGNED NOT NULL DEFAULT 0,
		`status` VARCHAR(12) NOT NULL DEFAULT 'alive',
		`created_by` VARCHAR(255) NOT NULL DEFAULT '',
		`created_at` INT UNSIGNED NOT NULL DEFAULT 0,
		`ended_at` INT UNSIGNED NULL,
		PRIMARY KEY (`id`),
		KEY `cockpit_metin_active_status` (`status`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_metin_damage` (
		`id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
		`active_id` INT UNSIGNED NOT NULL,
		`player_id` INT UNSIGNED NOT NULL DEFAULT 0,
		`player_name` VARCHAR(255) NOT NULL DEFAULT '',
		`damage` INT UNSIGNED NOT NULL DEFAULT 0,
		`loot` VARCHAR(500) NOT NULL DEFAULT '',
		PRIMARY KEY (`id`),
		KEY `cockpit_metin_damage_active` (`active_id`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_dungeon_auto` (
		`name` VARCHAR(64) NOT NULL,
		`disabled` TINYINT NOT NULL DEFAULT 0,
		`time_to_defeat` INT NULL,
		`time_to_fight_again` INT NULL,
		`extra_item_id` INT NULL,
		`extra_item_qty` INT NOT NULL DEFAULT 1,
		`extra_chance` DECIMAL(5,2) NOT NULL DEFAULT 100,
		PRIMARY KEY (`name`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
	[[CREATE TABLE IF NOT EXISTS `cockpit_dungeon_status` (
		`name` VARCHAR(64) NOT NULL,
		`players_inside` INT UNSIGNED NOT NULL DEFAULT 0,
		`updated_at` INT UNSIGNED NOT NULL DEFAULT 0,
		PRIMARY KEY (`name`)
	) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4]],
}

-- Actions that only make sense while the target is online. Anything else waits
-- in the queue and runs the next time the player logs in.
local onlineOnly = {
	set_group = true,
	kick = true,
	heal = true,
	teleport = true,
	temple = true,
	effect = true,
	say_over = true,
	summon_to = true,
	place_dummy = true,
}

local function finish(id, status, result)
	db.query(string.format("UPDATE `cockpit_commands` SET `status` = %s, `result` = %s, `done_at` = %d WHERE `id` = %d", db.escapeString(status), db.escapeString(result or ""), os.time(), id))
end

local function setSkill(player, skill, level)
	level = math.max(skill == MAGIC_SKILL and 0 or 10, math.min(level, 200))
	if skill == MAGIC_SKILL then
		player:setMagicLevel(level)
	elseif skill >= SKILL_FIST and skill <= SKILL_FISHING then
		player:setSkillLevel(skill, level)
	else
		return false, "skill invalida"
	end
	return true, "skill " .. skill .. " = " .. level
end

local function setLevel(player, level)
	level = math.max(1, math.min(level, 2000))
	local diff = Game.getExperienceForLevel(level) - player:getExperience()
	if diff > 0 then
		player:addExperience(diff, false)
	elseif diff < 0 then
		player:removeExperience(-diff, false)
	end
	player:addHealth(player:getMaxHealth())
	player:addMana(player:getMaxMana())
	return true, "level " .. player:getLevel()
end

local function parseColors(text)
	local c = {}
	for n in (text or ""):gmatch("%d+") do
		c[#c + 1] = math.min(tonumber(n), 132)
	end
	return c
end

local actions = {}

-- arg1 = item id, arg2 = count
actions.give_item = function(player, cmd)
	local itemType = ItemType(cmd.arg1)
	if cmd.arg1 < 100 or itemType:getId() == 0 then
		return false, "item inexistente"
	end
	local count = math.max(1, math.min(cmd.arg2, 1000))
	-- for items with charges (exercise weapons, runes) the count passed to addItem is the charge count,
	-- so give `count` full items instead
	local charges = itemType:getCharges()
	if charges > 0 and not itemType:isStackable() then
		for _ = 1, math.min(count, 20) do
			if not player:addItem(itemType:getId(), charges, true) then
				return false, "sem espaco"
			end
		end
	elseif not player:addItem(itemType:getId(), count, true) then
		return false, "sem espaco"
	end
	player:getPosition():sendMagicEffect(CONST_ME_GIFT_WRAPS)
	if cmd.text ~= "" then
		player:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
	end
	return true, count .. "x " .. itemType:getName()
end

-- text = inscription on the trophy
actions.give_trophy = function(player, cmd)
	if not CockpitGiveTrophy(player, cmd.text) then
		return false, "sem espaco"
	end
	return true, "trofeu entregue"
end

-- arg1 = extra spins on the lucky wheel (cockpit_wheel.lua)
actions.give_spins = function(player, cmd)
	local amount = math.max(1, math.min(cmd.arg1, 100))
	if not CockpitGiveSpins then
		return false, "roleta nao carregada"
	end
	CockpitGiveSpins(player, amount)
	return true, amount .. " giro(s)"
end

-- arg1 = gold coins
actions.give_money = function(player, cmd)
	local amount = math.max(1, math.min(cmd.arg1, 1000000000))
	player:setBankBalance(player:getBankBalance() + amount)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "O Mestre depositou " .. amount .. " gold no seu banco.")
	return true, amount .. " gold no banco"
end

-- arg1 = amount; never takes more than the player has in the bank
actions.take_money = function(player, cmd)
	local amount = math.min(math.max(1, cmd.arg1), player:getBankBalance())
	if amount <= 0 then
		return false, "banco vazio"
	end
	player:setBankBalance(player:getBankBalance() - amount)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "O Mestre retirou " .. amount .. " gold do seu banco.")
	return true, amount .. " gold retirado"
end

-- puts an exercise dummy on the tile in front of the player (kept after restart only inside a house)
actions.place_dummy = function(player, cmd)
	local pos = player:getPosition()
	pos:getNextPosition(player:getDirection())
	local tile = Tile(pos)
	if not tile or tile:hasFlag(TILESTATE_BLOCKSOLID) or tile:getCreatureCount() > 0 then
		return false, "sem espaco na frente"
	end
	if not Game.createItem(28558, 1, pos) then
		return false, "nao deu para criar"
	end
	pos:sendMagicEffect(CONST_ME_MAGIC_BLUE)
	return true, "dummy colocado"
end

-- arg1 = level
actions.set_level = function(player, cmd)
	return setLevel(player, cmd.arg1)
end

-- arg1 = skill id (99 = magic level), arg2 = level
actions.set_skill = function(player, cmd)
	return setSkill(player, cmd.arg1, cmd.arg2)
end

-- arg1 = looktype, arg2 = addons (0-3), arg3 = mount id (0 = none), text = "head,body,legs,feet"
actions.set_outfit = function(player, cmd)
	local outfit = player:getOutfit()
	local lookType = cmd.arg1
	if lookType > 0 then
		player:addOutfitAddon(lookType, math.max(0, math.min(cmd.arg2, 3)))
		outfit.lookType = lookType
		outfit.lookAddons = math.max(0, math.min(cmd.arg2, 3))
	end
	local c = parseColors(cmd.text)
	if #c == 4 then
		outfit.lookHead, outfit.lookBody, outfit.lookLegs, outfit.lookFeet = c[1], c[2], c[3], c[4]
	end
	if cmd.arg3 > 0 then
		player:addMount(cmd.arg3)
	end
	player:setOutfit(outfit)
	player:getPosition():sendMagicEffect(CONST_ME_MAGIC_BLUE)
	return true, "outfit " .. outfit.lookType
end

-- arg1 = mount id
actions.add_mount = function(player, cmd)
	if not player:addMount(cmd.arg1) then
		return false, "montaria invalida ou ja possui"
	end
	return true, "montaria " .. cmd.arg1
end

-- arg1 = group id (1 player, 2 tutor, 3 senior tutor, 4 gamemaster, 5 community manager, 6 god)
actions.set_group = function(player, cmd)
	local group = Group(cmd.arg1)
	if not group or not player:setGroup(group) then
		return false, "grupo invalido"
	end
	return true, "grupo " .. group:getName()
end

actions.kick = function(player)
	if player:getGroup():getAccess() then
		return false, "nao kicka staff"
	end
	player:remove()
	return true, "kickado"
end

-- Dungeon do grupo (painel > Dungeons): zera o cooldown de um boss-lever pra um jogador. text = nome do boss.
actions.dungeon_cooldown_reset = function(player, cmd)
	if not BossLever[cmd.text] then
		return false, "dungeon desconhecida"
	end
	player:setBossCooldown(cmd.text, 0)
	return true, "cooldown zerado"
end

actions.heal = function(player)
	player:addHealth(player:getMaxHealth())
	player:addMana(player:getMaxMana())
	player:getPosition():sendMagicEffect(CONST_ME_MAGIC_GREEN)
	return true, "curado"
end

-- Ground with no blocking flag, so the player lands somewhere they can actually walk out of.
local function walkable(pos)
	local tile = Tile(pos)
	return tile and tile:getGround() and not tile:hasFlag(TILESTATE_BLOCKSOLID) and not tile:hasFlag(TILESTATE_TELEPORT)
end

-- How many of the 8 neighbours are also walkable: a lone walkable tile surrounded by walls
-- (a sealed pocket you can't step out of) scores 0, a normal room floor scores several.
local function walkableNeighbours(pos)
	local n = 0
	for dx = -1, 1 do
		for dy = -1, 1 do
			if (dx ~= 0 or dy ~= 0) and walkable(Position(pos.x + dx, pos.y + dy, pos.z)) then
				n = n + 1
			end
		end
	end
	return n
end

-- Exact spot first (spawn points are usually fine); otherwise the closest walkable tile nearby,
-- ring by ring, so a teleport never drops the player where they cannot move. Prefers a tile with
-- walkable neighbours (an actual floor) over a lone walkable tile boxed in by walls, so the
-- player doesn't land somewhere with no way out.
local function nearestWalkable(pos, maxR)
	local fallback = walkable(pos) and pos or nil
	if fallback and walkableNeighbours(pos) >= 2 then
		return fallback
	end
	for r = 1, maxR do
		for dx = -r, r do
			for dy = -r, r do
				if math.max(math.abs(dx), math.abs(dy)) == r then
					local p = Position(pos.x + dx, pos.y + dy, pos.z)
					if walkable(p) then
						if walkableNeighbours(p) >= 2 then
							return p
						end
						fallback = fallback or p
					end
				end
			end
		end
	end
	return fallback
end

-- arg1, arg2, arg3 = x, y, z
actions.teleport = function(player, cmd)
	local pos = nearestWalkable(Position(cmd.arg1, cmd.arg2, cmd.arg3), 6)
	if not pos then
		return false, "sem lugar andavel por perto"
	end
	player:getPosition():sendMagicEffect(CONST_ME_POFF)
	player:teleportTo(pos)
	pos:sendMagicEffect(CONST_ME_TELEPORT)
	return true, pos.x .. "," .. pos.y .. "," .. pos.z
end

actions.temple = function(player)
	local pos = player:getTown():getTemplePosition()
	player:teleportTo(pos)
	pos:sendMagicEffect(CONST_ME_TELEPORT)
	return true, "templo"
end

-- target = player to move, text = name of the player to move next to
actions.summon_to = function(player, cmd)
	local dest = Player(cmd.text)
	if not dest then
		return false, cmd.text .. " offline"
	end
	local pos = dest:getPosition()
	player:teleportTo(pos)
	pos:sendMagicEffect(CONST_ME_TELEPORT)
	return true, "junto de " .. dest:getName()
end

-- arg1 = magic effect id
actions.effect = function(player, cmd)
	local effect = cmd.arg1 > 0 and cmd.arg1 or CONST_ME_FIREWORK_RED
	player:getPosition():sendMagicEffect(effect)
	return true, "efeito " .. effect
end

-- text shown over the player's head in orange, as if the player said it
actions.say_over = function(player, cmd)
	player:say(cmd.text, TALKTYPE_MONSTER_SAY)
	return true, "falou"
end

-- Narration to one player (big centered text)
actions.narrate_to = function(player, cmd)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
	return true, "narrado"
end

-- Actions without a player target
local globalActions = {}

globalActions.broadcast = function(cmd)
	for _, p in ipairs(Game.getPlayers()) do
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
	end
	return true, "enviado a " .. Game.getPlayerCount() .. " jogadores"
end

globalActions.close_server = function()
	Game.setGameState(GAME_STATE_CLOSED)
	return true, "servidor fechado para jogadores"
end

globalActions.open_server = function()
	Game.setGameState(GAME_STATE_NORMAL)
	return true, "servidor aberto"
end

globalActions.clean_map = function()
	return true, (cleanMap() or 0) .. " itens removidos do chao"
end

globalActions.save = function()
	saveServer()
	return true, "servidor salvo"
end

-- arg1 = house id, arg2 = new owner guid (0 = evict; the old owner's items go to their depot)
globalActions.house_owner = function(cmd)
	local house = House(cmd.arg1)
	if not house then
		return false, "casa nao existe"
	end
	local name = ""
	if cmd.arg2 > 0 then
		local resultId = db.storeQuery("SELECT `name` FROM `players` WHERE `id` = " .. cmd.arg2)
		if not resultId then
			return false, "jogador nao existe"
		end
		name = Result.getString(resultId, "name")
		Result.free(resultId)
	end
	house:setHouseOwner(cmd.arg2)
	local owner = Player(name)
	if owner and cmd.text ~= "" then
		owner:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
	end
	return true, cmd.arg2 > 0 and (house:getName() .. " agora e de " .. name) or (house:getName() .. " ficou livre")
end

-- arg1 = house id, arg2 = rent in gold, arg3 = owner guid the panel expects; paid from the bank, online or not
globalActions.house_rent = function(cmd)
	local house = House(cmd.arg1)
	if not house or house:getOwnerGuid() ~= cmd.arg3 or cmd.arg3 == 0 then
		return false, "dono mudou"
	end
	local amount = math.max(0, cmd.arg2)
	local player = Player(cmd.target)
	if player and player:getGuid() == cmd.arg3 then
		if player:getBankBalance() < amount then
			player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Seu banco nao tem " .. amount .. " gold para o aluguel da casa " .. house:getName() .. ".")
			return false, "sem saldo"
		end
		player:setBankBalance(player:getBankBalance() - amount)
		player:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
		return true, amount .. " gold pago"
	end
	local resultId = db.storeQuery("SELECT `balance` FROM `players` WHERE `id` = " .. cmd.arg3)
	if not resultId then
		return false, "dono mudou"
	end
	local balance = Result.getNumber(resultId, "balance")
	Result.free(resultId)
	if balance < amount then
		return false, "sem saldo"
	end
	db.query("UPDATE `players` SET `balance` = `balance` - " .. amount .. " WHERE `id` = " .. cmd.arg3 .. " AND `balance` >= " .. amount)
	return true, amount .. " gold pago (offline)"
end

-- arg1 = house id, arg2 = buyer guid, arg3 = price; sells a free house for gold from the buyer's bank, online or not
globalActions.house_sell = function(cmd)
	local house = House(cmd.arg1)
	if not house then
		return false, "casa nao existe"
	end
	if house:getOwnerGuid() ~= 0 then
		return false, "a casa ja tem dono"
	end
	local price = math.max(0, cmd.arg3)
	local resultId = db.storeQuery("SELECT `name`, `balance` FROM `players` WHERE `id` = " .. cmd.arg2)
	if not resultId then
		return false, "jogador nao existe"
	end
	local name, balance = Result.getString(resultId, "name"), Result.getNumber(resultId, "balance")
	Result.free(resultId)
	local player = Player(name)
	if player then
		if player:getBankBalance() < price then
			player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Seu banco nao tem " .. price .. " gold para a casa " .. house:getName() .. ".")
			return false, "sem saldo"
		end
		player:setBankBalance(player:getBankBalance() - price)
	else
		if balance < price then
			return false, "sem saldo"
		end
		db.query("UPDATE `players` SET `balance` = `balance` - " .. price .. " WHERE `id` = " .. cmd.arg2 .. " AND `balance` >= " .. price)
	end
	house:setHouseOwner(cmd.arg2)
	if player and cmd.text ~= "" then
		player:sendTextMessage(MESSAGE_EVENT_ADVANCE, cmd.text)
	end
	return true, house:getName() .. " vendida para " .. name .. " por " .. price .. " gold"
end

-- The Vinot trophy: a golden goblet with the panel's inscription, only given from the panel.
local TROPHY_ITEM = 5805
local function trophyText(v)
	return (tostring(v or ""):gsub("%c", " "):sub(1, 200))
end

function CockpitGiveTrophy(player, text)
	local item = player:addItem(TROPHY_ITEM, 1)
	if not item then
		return false
	end
	item:setActionId(45002)
	item:setAttribute(ITEM_ATTRIBUTE_NAME, "trofeu do Vinot")
	item:setAttribute(ITEM_ATTRIBUTE_DESCRIPTION, trophyText(text))
	player:getPosition():sendMagicEffect(CONST_ME_FIREWORK_YELLOW)
	return true
end

-- Guilds. The game keeps a loaded guild's bank balance and motd in memory (and writes the balance back
-- on save), so change them here when it is loaded; otherwise the database is the truth.
globalActions.guild_balance = function(cmd)
	local amount = math.max(0, math.floor(cmd.arg2))
	local guild = Guild(cmd.arg1)
	if guild then
		guild:setBankBalance(amount)
	end
	db.query("UPDATE `guilds` SET `balance` = " .. amount .. " WHERE `id` = " .. math.floor(cmd.arg1))
	return true, "banco da guild: " .. amount .. " gold" .. (guild and "" or " (ninguem online)")
end

globalActions.guild_motd = function(cmd)
	local guild = Guild(cmd.arg1)
	if guild then
		guild:setMotd(cmd.text)
	end
	return true, "mensagem da guild trocada"
end

-- text = raid name: a Lua raid (Raid.registry) or a legacy XML raid, like the /raid command
globalActions.start_raid = function(cmd)
	if Raid and Raid.registry and Raid.registry[cmd.text] then
		if Raid.registry[cmd.text]:tryStart(true) then
			return true, "raid solta"
		end
		return false, "a raid nao pode comecar agora"
	end
	local ret = Game.startRaid(cmd.text)
	if ret ~= RETURNVALUE_NOERROR then
		return false, Game.getReturnMessage(ret)
	end
	return true, "raid solta"
end

-- Mini-games (scripts in cockpit_<kind>.lua). arg1-3 = arena centre, arg4 = radius,
-- text = "id=..;kind=..;players=A|B;seconds=..;first=..;every=..;speed=..;prize=id:count,..;gold=.."
globalActions.event_start = function(cmd)
	local cfg = {}
	for k, v in cmd.text:gmatch("(%w+)=([^;]*)") do
		cfg[k] = v
	end
	local game = CockpitEvents and CockpitEvents[cfg.kind or ""]
	if not game then
		return false, "evento desconhecido"
	end
	local names = {}
	for name in (cfg.players or ""):gmatch("[^|]+") do
		names[#names + 1] = name
	end
	local id = tonumber(cfg.id) or 0
	local ok, msg = game.start({
		center = Position(cmd.arg1, cmd.arg2, cmd.arg3),
		radius = cmd.arg4,
		names = names,
		eventId = id,
		seconds = tonumber(cfg.seconds) or 300,
		first = tonumber(cfg.first) or 2,
		every = tonumber(cfg.every) or 30,
		speed = tonumber(cfg.speed) or 100,
		prize = cfg.prize or "",
		gold = tonumber(cfg.gold) or 0,
		raw = cfg,
	})
	db.query(string.format("UPDATE `cockpit_events` SET `status` = %s, `details` = %s WHERE `id` = %d", db.escapeString(ok and "running" or "error"), db.escapeString(msg), id))
	return ok, msg
end

-- text = kind
globalActions.event_stop = function(cmd)
	local game = CockpitEvents and CockpitEvents[cmd.text]
	if not game then
		return false, "evento desconhecido"
	end
	return game.stop()
end

-- World settings from the panel. Only these keys are written, with values checked here again.
local WORLD_FILE = "cockpit-world.lua"
local WORLD_MARK = "-- cockpit: world settings"
local WORLD_BOOLS = { "autoLoot", "staminaPz", "staminaTrainer", "toggleTravelsFree", "toggleFreeQuest", "partyShareLootBoosts", "rateUseStages", "toggleServerIsRetroPVP", "disableLegacyRaids" }
local WORLD_TYPES = { ["no-pvp"] = WORLD_TYPE_NO_PVP, ["pvp"] = WORLD_TYPE_PVP, ["pvp-enforced"] = WORLD_TYPE_PVP_ENFORCED }
local WORLD_RATES = { "rateExp", "rateSkill", "rateMagic", "rateLoot" }
local WORLD_STAGES = { "experienceStages", "skillsStages", "magicLevelStages" }

local function readWorld()
	local saved = {}
	local resultId = db.storeQuery("SELECT `k`, `v` FROM `cockpit_settings` WHERE `k` LIKE 'world.%'")
	if resultId then
		repeat
			saved[Result.getString(resultId, "k"):sub(7)] = Result.getString(resultId, "v")
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return saved
end

-- "1-50:10,51-:2" -> stage table, or nil when anything is off
local function parseStages(text)
	local stages = {}
	for lo, hi, mult in (text or ""):gmatch("(%d+)%-(%d*):(%d+)") do
		local stage = { minlevel = tonumber(lo), multiplier = math.min(tonumber(mult), 100) }
		if hi ~= "" then
			stage.maxlevel = tonumber(hi)
		end
		stages[#stages + 1] = stage
	end
	return #stages > 0 and stages or nil
end

-- config.lua is not in git; make sure it loads the panel's file last (once)
local function ensureWorldLoader()
	local f = io.open("config.lua", "r")
	if not f then
		return false
	end
	local text = f:read("*a")
	f:close()
	if text:find(WORLD_MARK, 1, true) then
		return true
	end
	f = io.open("config.lua", "a")
	if not f then
		return false
	end
	f:write("\n" .. WORLD_MARK .. " (written by the Cockpit panel; these win over the values above)\n")
	f:write('local cockpitWorld = io.open("' .. WORLD_FILE .. '")\nif cockpitWorld then\n\tcockpitWorld:close()\n\tdofile("' .. WORLD_FILE .. '")\nend\n')
	f:close()
	return true
end

local function applyStages(saved)
	for _, name in ipairs(WORLD_STAGES) do
		local stages = parseStages(saved[name])
		if stages then
			_G[name] = stages
		end
	end
end

-- Plain printable text for config.lua strings (the panel already strips accents and quotes)
local function worldText(v, max)
	v = tostring(v or ""):gsub('[%c\\"]', ""):sub(1, max)
	return v
end

-- The Vinot statue: an item placed next to the Thais temple (or where the panel says) with the panel's text.
-- Items created here are not saved with the map, so it is placed again on every start.
local SIGN_ITEM = 2027 -- hero statue
local SIGN_AID = 45001
CockpitWelcome = CockpitWelcome or ""

local function signSpot(saved)
	local x, y, z = (saved.signPos or ""):match("^(%d+),(%d+),(%d+)$")
	if x then
		return Position(tonumber(x), tonumber(y), tonumber(z))
	end
	local town = Town("Thais")
	local temple = town and town:getTemplePosition()
	if not temple then
		return nil
	end
	for r = 2, 4 do
		for dx = -r, r do
			for dy = -r, r do
				if math.max(math.abs(dx), math.abs(dy)) == r then
					local pos = Position(temple.x + dx, temple.y + dy, temple.z)
					local tile = Tile(pos)
					if tile and tile:getGround() and not tile:hasFlag(TILESTATE_BLOCKSOLID) and not tile:hasFlag(TILESTATE_FLOORCHANGE) and not tile:hasFlag(TILESTATE_TELEPORT) and tile:getItemCount() == 0 and not tile:getTopCreature() then
						return pos
					end
				end
			end
		end
	end
	return nil
end

local function placeSign(saved)
	if CockpitSignPos then
		local tile = Tile(CockpitSignPos)
		local old = tile and tile:getItemById(SIGN_ITEM)
		if old and old:getActionId() == SIGN_AID then
			old:remove()
		end
		CockpitSignPos = nil
	end
	local text = worldText(saved.signText, 200)
	if text == "" then
		return
	end
	local pos = signSpot(saved)
	local item = pos and Game.createItem(SIGN_ITEM, 1, pos)
	if not item then
		logger.warn("[cockpit] nao achei lugar para a estatua do templo")
		return
	end
	item:setActionId(SIGN_AID)
	item:setAttribute(ITEM_ATTRIBUTE_NAME, "estatua do Vinot")
	item:setAttribute(ITEM_ATTRIBUTE_ARTICLE, "uma")
	item:setAttribute(ITEM_ATTRIBUTE_DESCRIPTION, text)
	CockpitSignPos = pos
	db.query(string.format("INSERT INTO `cockpit_settings` (`k`, `v`) VALUES ('world._signAt', '%d,%d,%d') ON DUPLICATE KEY UPDATE `v` = VALUES(`v`)", pos.x, pos.y, pos.z))
end

local function applyTexts(saved)
	CockpitWelcome = worldText(saved.welcome, 200)
	if saved.serverName and saved.serverName ~= "" then
		SERVER_NAME = worldText(saved.serverName, 30)
	end
	placeSign(saved)
end

globalActions.apply_world = function()
	local saved = readWorld()
	local lines = { "-- Written by the Cockpit panel (tela Mundo). Edit it there, not here." }
	for _, key in ipairs(WORLD_BOOLS) do
		if saved[key] then
			lines[#lines + 1] = key .. " = " .. (saved[key] == "1" and "true" or "false")
		end
	end
	for _, key in ipairs(WORLD_RATES) do
		local v = tonumber(saved[key])
		if v then
			lines[#lines + 1] = key .. " = " .. math.max(1, math.min(100, math.floor(v)))
		end
	end
	if WORLD_TYPES[saved.worldType or ""] then
		lines[#lines + 1] = 'worldType = "' .. saved.worldType .. '"'
	end
	local level = tonumber(saved.protectionLevel)
	if level then
		lines[#lines + 1] = "protectionLevel = " .. math.max(1, math.min(1000, math.floor(level)))
	end
	local pz = tonumber(saved.pzLockedSeconds)
	if pz then
		lines[#lines + 1] = "pzLocked = " .. math.max(0, math.min(3600, math.floor(pz))) * 1000
	end
	-- houses (tela Imobiliaria): price per sqm (-1 turns !buyhouse off), rent part of the price, level to buy
	local sqm, buyLevel, rentMult = tonumber(saved.housePriceEachSQM), tonumber(saved.houseBuyLevel), tonumber(saved.housePriceRentMultiplier)
	if sqm then
		lines[#lines + 1] = "housePriceEachSQM = " .. math.max(-1, math.min(100000000, math.floor(sqm)))
	end
	if buyLevel then
		lines[#lines + 1] = "houseBuyLevel = " .. math.max(0, math.min(5000, math.floor(buyLevel)))
	end
	if rentMult then
		lines[#lines + 1] = string.format("housePriceRentMultiplier = %.2f", math.max(0, math.min(100, rentMult)))
	end
	-- daily server save (tela Mundo)
	for _, key in ipairs({ "globalServerSaveShutdown", "globalServerSaveCleanMap" }) do
		if saved[key] then
			lines[#lines + 1] = key .. " = " .. (saved[key] == "1" and "true" or "false")
		end
	end
	if saved.globalServerSaveShutdown then
		lines[#lines + 1] = "globalServerSaveNotifyMessage = " .. (saved.globalServerSaveShutdown == "1" and "true" or "false")
	end
	local saveTime = tostring(saved.globalServerSaveTime or ""):match("^(%d%d:%d%d):%d%d$")
	if saveTime then
		lines[#lines + 1] = string.format('globalServerSaveTime = "%s:00"', saveTime)
	end
	local notify = tonumber(saved.globalServerSaveNotifyDuration)
	if notify then
		lines[#lines + 1] = "globalServerSaveNotifyDuration = " .. math.max(1, math.min(60, math.floor(notify)))
	end
	if saved.serverName and saved.serverName ~= "" then
		lines[#lines + 1] = string.format("serverName = %q", worldText(saved.serverName, 30))
	end
	if saved.serverMotd then
		lines[#lines + 1] = string.format("serverMotd = %q", worldText(saved.serverMotd, 200))
	end
	local f = io.open(WORLD_FILE, "w")
	if not f then
		return false, "nao consegui gravar " .. WORLD_FILE
	end
	f:write(table.concat(lines, "\n") .. "\n")
	f:close()
	if not ensureWorldLoader() then
		return false, "nao consegui ligar o arquivo no config.lua"
	end
	applyStages(saved)
	if not Game.reload(RELOAD_TYPE_CONFIG) then
		return false, "config.lua nao recarregou"
	end
	applyTexts(saved)
	-- the world type is read only at startup; set it live too
	if WORLD_TYPES[saved.worldType or ""] then
		Game.setWorldType(WORLD_TYPES[saved.worldType])
	end
	return true, "ajustes aplicados"
end

local function run(cmd, player)
	local handler = actions[cmd.action]
	if not handler then
		return false, "acao desconhecida"
	end
	local ok, status, result = pcall(handler, player, cmd)
	if not ok then
		logger.error("[cockpit] {} failed: {}", cmd.action, tostring(status))
		return false, "erro no servidor"
	end
	return status, result
end

local function readCommands(where)
	local list = {}
	local resultId = db.storeQuery("SELECT `id`, `action`, `target`, `arg1`, `arg2`, `arg3`, `arg4`, `text` FROM `cockpit_commands` WHERE " .. where .. " ORDER BY `id` LIMIT " .. BATCH_SIZE)
	if not resultId then
		return list
	end
	repeat
		list[#list + 1] = {
			id = Result.getNumber(resultId, "id"),
			action = Result.getString(resultId, "action"),
			target = Result.getString(resultId, "target"),
			arg1 = Result.getNumber(resultId, "arg1"),
			arg2 = Result.getNumber(resultId, "arg2"),
			arg3 = Result.getNumber(resultId, "arg3"),
			arg4 = Result.getNumber(resultId, "arg4"),
			text = Result.getString(resultId, "text"),
		}
	until not Result.next(resultId)
	Result.free(resultId)
	return list
end

local function processCommand(cmd)
	local global = globalActions[cmd.action]
	if global then
		local ok, status, result = pcall(global, cmd)
		if not ok then
			logger.error("[cockpit] {} failed: {}", cmd.action, tostring(status))
			finish(cmd.id, "error", "erro no servidor")
		else
			finish(cmd.id, status and "done" or "error", result)
		end
		return
	end

	local player = Player(cmd.target)
	if not player then
		if onlineOnly[cmd.action] or not actions[cmd.action] then
			finish(cmd.id, "error", actions[cmd.action] and "jogador offline" or "acao desconhecida")
		end
		-- other actions stay pending until the player logs in
		return
	end
	local ok, result = run(cmd, player)
	finish(cmd.id, ok and "done" or "error", result)
end

local function writeSnapshot()
	db.query("DELETE FROM `cockpit_online`")
	local rows = {}
	local now = os.time()
	for _, p in ipairs(Game.getPlayers()) do
		local pos = p:getPosition()
		rows[#rows + 1] = string.format("(%d, %s, %d, %s, %d, %d, %d, %d, %d, %d)", p:getGuid(), db.escapeString(p:getName()), p:getLevel(), db.escapeString(p:getVocation():getName()), p:getHealth(), p:getMaxHealth(), pos.x, pos.y, pos.z, now)
	end
	if #rows > 0 then
		db.query("INSERT INTO `cockpit_online` (`player_id`, `name`, `level`, `vocation`, `health`, `healthmax`, `posx`, `posy`, `posz`, `updated_at`) VALUES " .. table.concat(rows, ","))
	end
end

local startedAt = os.time()
local METRICS_KEEP_DAYS = 7

local function writeMetrics()
	local now = os.time()
	db.query(string.format("INSERT IGNORE INTO `cockpit_metrics` (`ts`, `players`, `monsters`, `npcs`, `lua_kb`, `started_at`) VALUES (%d, %d, %d, %d, %d, %d)", now, Game.getPlayerCount(), Game.getMonsterCount(), Game.getNpcCount(), math.floor(collectgarbage("count")), startedAt))
	db.query("DELETE FROM `cockpit_metrics` WHERE `ts` < " .. (now - METRICS_KEEP_DAYS * 86400))
end

-- Automatic Lua raids: the panel's overrides (tela Raids > Automaticas) from `cockpit_raid_auto`.
-- Off = the minute roll skips it (the panel and the Agenda can still force it). Chance = a flat % per minute check,
-- replacing the raid's own curve (initialChance growing to targetChancePerDay); min players replaces minActivePlayers.
local raidOff = {}

local function applyRaidAuto()
	if not (Raid and Raid.registry) then
		return 0
	end
	raidOff = {}
	for _, raid in pairs(Raid.registry) do
		if raid.cockpitDefaults then
			local d = raid.cockpitDefaults
			raid.initialChance, raid.targetChancePerDay, raid.maxChancePerCheck, raid.minActivePlayers = d[1], d[2], d[3], d[4]
		end
	end
	local n = 0
	local resultId = db.storeQuery("SELECT `name`, `enabled`, IFNULL(`chance`, -1) AS `chance`, IFNULL(`min_players`, -1) AS `min_players` FROM `cockpit_raid_auto`")
	if resultId then
		repeat
			local raid = Raid.registry[Result.getString(resultId, "name")]
			if raid then
				raid.cockpitDefaults = raid.cockpitDefaults or { raid.initialChance, raid.targetChancePerDay, raid.maxChancePerCheck, raid.minActivePlayers }
				raidOff[raid.name] = Result.getNumber(resultId, "enabled") == 0
				local chance, minPlayers = tonumber(Result.getString(resultId, "chance")), Result.getNumber(resultId, "min_players")
				if chance >= 0 then -- a flat chance per minute check
					raid.initialChance, raid.targetChancePerDay, raid.maxChancePerCheck = chance, chance, math.min(100, chance)
				end
				if minPlayers >= 0 then
					raid.minActivePlayers = minPlayers
				end
				n = n + 1
			end
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return n
end

if Raid and not Raid.cockpitWrapped then
	local tryStart = Raid.tryStart
	Raid.tryStart = function(self, force)
		if not force and raidOff[self.name] then
			return false
		end
		return tryStart(self, force)
	end
	Raid.cockpitWrapped = true
end

globalActions.raid_auto = function()
	return true, applyRaidAuto() .. " raid(s) com ajuste do painel"
end

-- Dungeon do grupo (painel > Dungeons): panel controls on top of the existing boss-lever rooms
-- (data/libs/functions/boss_lever.lua), no new map. Overrides come from `cockpit_dungeon_auto`.
local function applyDungeonAuto()
	local n = 0
	local resultId = db.storeQuery("SELECT `name`, `disabled`, IFNULL(`time_to_defeat`, -1) AS `time_to_defeat`, " .. "IFNULL(`time_to_fight_again`, -1) AS `time_to_fight_again` FROM `cockpit_dungeon_auto`")
	if resultId then
		repeat
			local name = Result.getString(resultId, "name")
			local lever = BossLever[name]
			if lever then
				lever.disabled = Result.getNumber(resultId, "disabled") == 1
				local ttd = Result.getNumber(resultId, "time_to_defeat")
				local ttf = Result.getNumber(resultId, "time_to_fight_again")
				if ttd >= 0 then
					lever.timeToDefeat = ttd
				end
				if ttf >= 0 then
					lever.timeToFightAgain = ttf
				end
				n = n + 1
			end
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return n
end

globalActions.dungeon_auto = function()
	return true, applyDungeonAuto() .. " dungeon(s) com ajuste do painel"
end

-- text = boss name. Clears the boss room's zone so a stuck group can enter again.
globalActions.dungeon_free = function(cmd)
	local lever = BossLever[cmd.text]
	if not lever then
		return false, "dungeon desconhecida"
	end
	local zone = lever:getZone()
	zone:refresh()
	zone:removePlayers()
	if lever.timeoutEvent then
		stopEvent(lever.timeoutEvent)
		lever.timeoutEvent = nil
	end
	return true, "sala liberada"
end

-- Painel > Teleporte > Soltar monstro/boss. text = nome do monstro, arg1/2/3 = x/y/z.
globalActions.spawn_monster = function(cmd)
	local pos = nearestWalkable(Position(cmd.arg1, cmd.arg2, cmd.arg3), 6)
	if not pos then
		return false, "sem lugar andavel por perto"
	end
	local ok, monster = pcall(Game.createMonster, cmd.text, pos, false, true)
	if not ok or not monster then
		return false, "monstro nao existe: " .. cmd.text
	end
	pos:sendMagicEffect(CONST_ME_TELEPORT)
	return true, cmd.text .. " solto em " .. pos.x .. "," .. pos.y .. "," .. pos.z
end

local function writeDungeonStatus()
	for name, lever in pairs(BossLever) do
		if type(lever) == "table" and lever.getZone then
			local ok, count = pcall(function()
				return lever:getZone():countPlayers()
			end)
			if ok then
				db.query(string.format("INSERT INTO `cockpit_dungeon_status` (`name`, `players_inside`, `updated_at`) VALUES (%s, %d, %d) " .. "ON DUPLICATE KEY UPDATE `players_inside` = VALUES(`players_inside`), `updated_at` = VALUES(`updated_at`)", db.escapeString(name), count, os.time()))
			end
		end
	end
end

-- Pedra Metin (cockpit/app/metin.py). arg1 = type id, arg2/3/4 = x/y/z, text = the cockpit_metin_active row id.
-- MetinState (a global table, populated here) is read by data-otservbr-global/scripts/creaturescripts/monster/metin_stone.lua
-- on think (waves) and on death (loot + damage), and is the only place the stone's config lives once it's spawned.
MetinState = MetinState or {}

globalActions.metin_spawn = function(cmd)
	local resultId = db.storeQuery("SELECT `name`, `health`, `waves`, `loot` FROM `cockpit_metin_types` WHERE `id` = " .. cmd.arg1)
	if not resultId then
		return false, "tipo de pedra nao existe mais"
	end
	local name, health = Result.getString(resultId, "name"), Result.getNumber(resultId, "health")
	local waves, loot = Result.getString(resultId, "waves"), Result.getString(resultId, "loot")
	Result.free(resultId)
	local pos = Position(cmd.arg2, cmd.arg3, cmd.arg4)
	if not Tile(pos) then
		return false, "posicao invalida"
	end
	local monster = Game.createMonster("Metin Stone", pos, false, true)
	if not monster then
		return false, "nao consegui criar a pedra"
	end
	monster:setMaxHealth(health)
	monster:setHealth(health)
	MetinState[monster:getId()] = {
		activeId = tonumber(cmd.text) or 0,
		waves = MetinParseWaves(waves),
		loot = MetinParseLoot(loot),
		fired = {},
	}
	pos:sendMagicEffect(CONST_ME_TELEPORT)
	Game.broadcastMessage("Uma pedra Metin (" .. name .. ") apareceu!", MESSAGE_EVENT_ADVANCE)
	return true, "pedra criada em " .. pos.x .. "," .. pos.y .. "," .. pos.z
end

-- arg1 = the cockpit_metin_active row id to remove (whatever live monster has that id in MetinState)
globalActions.metin_remove = function(cmd)
	for monsterId, state in pairs(MetinState) do
		if state.activeId == cmd.arg1 then
			local creature = Creature(monsterId)
			MetinState[monsterId] = nil
			if creature then
				creature:remove()
			end
			db.query(string.format("UPDATE `cockpit_metin_active` SET `status` = 'removed', `ended_at` = %d WHERE `id` = %d AND `status` = 'alive'", os.time(), cmd.arg1))
			return true, "pedra removida"
		end
	end
	return false, "essa pedra ja nao esta mais lá"
end

local startup = GlobalEvent("CockpitStartup")

function startup.onStartup()
	for _, sql in ipairs(tablesSql) do
		db.query(sql)
	end
	db.query("DELETE FROM `cockpit_online`")
	-- any Metin Stone still "alive" belonged to the previous run: MetinState (in memory) is gone with it
	db.query(string.format("UPDATE `cockpit_metin_active` SET `status` = 'expired', `ended_at` = %d WHERE `status` = 'alive'", os.time()))
	-- rewrite cockpit-world.lua with this version of the bridge: a panel deploy may have applied the world with the
	-- old bridge just before the restart, leaving out keys this version knows
	local ok, applied, msg = pcall(globalActions.apply_world)
	if not (ok and applied) then
		logger.warn("[cockpit] apply_world on startup: {}", tostring(ok and msg or applied))
		local saved = readWorld()
		applyStages(saved) -- config.lua already read cockpit-world.lua; the stage tables live here
		applyTexts(saved)
	end
	applyRaidAuto()
	applyDungeonAuto()
	startedAt = os.time()
	writeMetrics()
	logger.info("[cockpit] bridge ready")
	return true
end

startup:register()

local metricsEvent = GlobalEvent("CockpitMetrics")

function metricsEvent.onThink()
	writeMetrics()
	writeDungeonStatus()
	return true
end

metricsEvent:interval(60 * 1000)
metricsEvent:register()

local polls = 0
local poll = GlobalEvent("CockpitPoll")

function poll.onThink(interval)
	for _, cmd in ipairs(readCommands("`status` = 'pending'")) do
		processCommand(cmd)
	end
	polls = polls + 1
	if polls >= SNAPSHOT_EVERY then
		polls = 0
		writeSnapshot()
	end
	return true
end

poll:interval(POLL_INTERVAL)
poll:register()

-- Commands queued while the player was offline run right after login.
local login = CreatureEvent("CockpitLogin")

function login.onLogin(player)
	local cid = player:getId()
	local where = "`status` = 'pending' AND `target` = " .. db.escapeString(player:getName())
	addEvent(function()
		local p = Player(cid)
		if not p then
			return
		end
		for _, cmd in ipairs(readCommands(where)) do
			local ok, result = run(cmd, p)
			finish(cmd.id, ok and "done" or "error", result)
		end
	end, 1000)
	return true
end

login:register()

-- Welcome text from the panel (tela Mundo), shown in the middle of the screen on every login
local welcome = CreatureEvent("CockpitWelcome")

function welcome.onLogin(player)
	if CockpitWelcome and CockpitWelcome ~= "" then
		addEvent(function(name)
			local p = Player(name)
			if p then
				p:sendTextMessage(MESSAGE_EVENT_ADVANCE, CockpitWelcome)
			end
		end, 1500, player:getName())
	end
	return true
end

welcome:register()

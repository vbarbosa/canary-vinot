-- One-time server migration: creates a level 1000, fully equipped hunting
-- template for each of the four vocations, all on the "god" login account.
--
-- Runs once on server startup (tracked by the Migration framework in
-- data/scripts/lib/register_migrations.lua) and is safe to leave in the
-- codebase afterwards: KV.scoped("migrations") remembers it already ran,
-- and the per-character name check below is a second guard in case someone
-- already created one of these characters by hand.

local GOD_ACCOUNT_NAME = "god"
local TARGET_LEVEL = 1000

local SUPPLIES = {
	{ names = { "Ultimate Health Potion" }, count = 100 },
	{ names = { "Great Mana Potion" }, count = 100 },
	{ names = { "Great Spirit Potion" }, count = 50 },
	{ names = { "Sudden Death Rune" }, count = 25 },
	{ names = { "Intense Healing Rune" }, count = 25 },
	{ names = { "Platinum Coin" }, count = 100 },
}

-- One entry per vocation, keyed by the promoted vocation id in
-- data/XML/vocations.xml. Growth rates (gainhp/gainmana/gaincap) are
-- copied from that same file so health/mana/capacity match what the
-- character would have if it had actually leveled up to 1000.
local TEMPLATES = {
	[5] = { -- Master Sorcerer
		characterName = "Vinot Sorcerer",
		gainHealth = 5,
		gainMana = 30,
		gainCap = 10,
		maglevel = 150,
		skills = { [SKILL_SHIELD] = 60 },
		equipment = {
			{ slot = CONST_SLOT_HEAD, names = { "Magician Hat", "Wizard's Hat" } },
			{ slot = CONST_SLOT_NECKLACE, names = { "Stone Skin Amulet", "Bonfire Amulet" } },
			{ slot = CONST_SLOT_ARMOR, names = { "Zaoan Robe", "Robe" } },
			{ slot = CONST_SLOT_LEGS, names = { "Zaoan Legs" } },
			{ slot = CONST_SLOT_FEET, names = { "Boots of Haste", "Steel Boots" } },
			{ slot = CONST_SLOT_RING, names = { "Ring of Healing", "Might Ring" } },
			{ slot = CONST_SLOT_LEFT, names = { "Wand of Inferno", "Wand of Cosmic Energy" } },
			{ slot = CONST_SLOT_RIGHT, names = { "Spellbook of Warding", "Spellbook of Mind Control" } },
			{ slot = CONST_SLOT_BACKPACK, names = { "Golden Backpack", "Backpack" } },
		},
	},
	[6] = { -- Elder Druid
		characterName = "Vinot Druid",
		gainHealth = 5,
		gainMana = 30,
		gainCap = 10,
		maglevel = 150,
		skills = { [SKILL_SHIELD] = 60 },
		equipment = {
			{ slot = CONST_SLOT_HEAD, names = { "Magician Hat", "Wizard's Hat" } },
			{ slot = CONST_SLOT_NECKLACE, names = { "Stone Skin Amulet", "Bonfire Amulet" } },
			{ slot = CONST_SLOT_ARMOR, names = { "Zaoan Robe", "Robe" } },
			{ slot = CONST_SLOT_LEGS, names = { "Zaoan Legs" } },
			{ slot = CONST_SLOT_FEET, names = { "Boots of Haste", "Steel Boots" } },
			{ slot = CONST_SLOT_RING, names = { "Ring of Healing", "Might Ring" } },
			{ slot = CONST_SLOT_LEFT, names = { "Snakebite Rod", "Rod of Corruption" } },
			{ slot = CONST_SLOT_RIGHT, names = { "Spellbook of Warding", "Spellbook of Mind Control" } },
			{ slot = CONST_SLOT_BACKPACK, names = { "Golden Backpack", "Backpack" } },
		},
	},
	[7] = { -- Royal Paladin
		characterName = "Vinot Paladin",
		gainHealth = 10,
		gainMana = 15,
		gainCap = 20,
		maglevel = 0,
		skills = { [SKILL_DISTANCE] = 150, [SKILL_SHIELD] = 150 },
		equipment = {
			{ slot = CONST_SLOT_HEAD, names = { "Crown Helmet", "Royal Helmet" } },
			{ slot = CONST_SLOT_NECKLACE, names = { "Stone Skin Amulet", "Bonfire Amulet" } },
			{ slot = CONST_SLOT_ARMOR, names = { "Crown Armor", "Golden Armor" } },
			{ slot = CONST_SLOT_LEGS, names = { "Crown Legs", "Golden Legs" } },
			{ slot = CONST_SLOT_FEET, names = { "Boots of Haste", "Steel Boots" } },
			{ slot = CONST_SLOT_RING, names = { "Might Ring", "Stealth Ring" } },
			{ slot = CONST_SLOT_LEFT, names = { "Royal Bow", "Crossbow", "Bow" } },
			{ slot = CONST_SLOT_AMMO, names = { "Sniper Arrow", "Flaming Arrow", "Arrow" } },
			{ slot = CONST_SLOT_BACKPACK, names = { "Golden Backpack", "Backpack" } },
		},
	},
	[8] = { -- Elite Knight
		characterName = "Vinot Knight",
		gainHealth = 15,
		gainMana = 5,
		gainCap = 25,
		maglevel = 0,
		skills = { [SKILL_SWORD] = 150, [SKILL_SHIELD] = 150, [SKILL_FIST] = 60 },
		equipment = {
			{ slot = CONST_SLOT_HEAD, names = { "Crown Helmet", "Royal Helmet", "Warrior Helmet" } },
			{ slot = CONST_SLOT_NECKLACE, names = { "Stone Skin Amulet", "Bonfire Amulet", "Silver Amulet" } },
			{ slot = CONST_SLOT_ARMOR, names = { "Crown Armor", "Golden Armor", "Studded Armor" } },
			{ slot = CONST_SLOT_LEGS, names = { "Crown Legs", "Golden Legs", "Plate Legs" } },
			{ slot = CONST_SLOT_FEET, names = { "Boots of Haste", "Steel Boots", "Leather Boots" } },
			{ slot = CONST_SLOT_RING, names = { "Might Ring", "Stealth Ring", "Silver Ring" } },
			{ slot = CONST_SLOT_LEFT, names = { "Fireborn Giant Sword", "Two Handed Sword", "Fire Sword" } },
			{ slot = CONST_SLOT_RIGHT, names = { "Demon Shield", "Ancient Shield", "Tower Shield" } },
			{ slot = CONST_SLOT_BACKPACK, names = { "Golden Backpack", "Backpack" } },
		},
	},
}

-- Base stats at level 1 are the standard Tibia defaults (150 HP, 0 mana,
-- 400 cap) before any vocation growth is applied.
local BASE_HEALTH, BASE_MANA, BASE_CAP = 150, 0, 400

local function resolveItemId(names)
	for _, name in ipairs(names) do
		local itemType = ItemType(name)
		if itemType and itemType:getId() ~= 0 then
			return itemType:getId(), name
		end
	end
	return nil, names[1]
end

local function createTemplate(vocationId, config, accountId)
	local name = config.characterName

	local existingResult = db.storeQuery("SELECT `id` FROM `players` WHERE `name` = " .. db.escapeString(name))
	if existingResult then
		Result.free(existingResult)
		logger.warn("[vinot] Template skipped: a character named '{}' already exists.", name)
		return
	end

	local healthmax = BASE_HEALTH + (TARGET_LEVEL - 1) * config.gainHealth
	local manamax = BASE_MANA + (TARGET_LEVEL - 1) * config.gainMana
	local cap = BASE_CAP + (TARGET_LEVEL - 1) * config.gainCap

	local inserted = db.query(
		"INSERT INTO `players` (`name`, `group_id`, `account_id`, `level`, `vocation`, `health`, `healthmax`, `mana`, `manamax`, `cap`, `sex`, `town_id`, `conditions`) VALUES ("
			.. db.escapeString(name)
			.. ", 1, "
			.. accountId
			.. ", 1, "
			.. vocationId
			.. ", "
			.. healthmax
			.. ", "
			.. healthmax
			.. ", "
			.. manamax
			.. ", "
			.. manamax
			.. ", "
			.. cap
			.. ", 1, 1, '')"
	)

	if not inserted then
		logger.error("[vinot] Template failed: could not insert player row for '{}'.", name)
		return
	end

	local player = Game.getOfflinePlayer(name)
	if not player then
		logger.error("[vinot] Template failed: player '{}' was inserted but could not be loaded.", name)
		return
	end

	player:setLevel(TARGET_LEVEL)
	if config.maglevel and config.maglevel > 0 then
		player:setMagicLevel(config.maglevel)
	end
	for skillId, skillLevel in pairs(config.skills) do
		player:setSkillLevel(skillId, skillLevel)
	end

	local towns = Game.getTowns()
	if towns and towns[1] then
		player:teleportTo(towns[1]:getTemplePosition(), false)
	end

	for _, entry in ipairs(config.equipment) do
		local itemId, attemptedName = resolveItemId(entry.names)
		if itemId then
			local result = player:addItem(itemId, 1, false, 0, entry.slot)
			if not result then
				logger.warn("[vinot] '{}': could not equip '{}' (slot {}): no free slot or incompatible with current gear.", name, attemptedName, entry.slot)
			end
		else
			logger.warn("[vinot] '{}': none of the configured items for slot {} exist on this server: {}", name, entry.slot, table.concat(entry.names, ", "))
		end
	end

	for _, entry in ipairs(SUPPLIES) do
		local itemId, attemptedName = resolveItemId(entry.names)
		if itemId then
			player:addItem(itemId, entry.count)
		else
			logger.warn("[vinot] '{}': supply item not found on this server: {}", name, attemptedName)
		end
	end

	player:save()
	logger.info("[vinot] Created level {} '{}' on account '{}'.", TARGET_LEVEL, name, GOD_ACCOUNT_NAME)
end

local migration = Migration("20260928010000_create_vinot_god_templates")

function migration:onExecute()
	local accountResult = db.storeQuery("SELECT `id` FROM `accounts` WHERE `name` = " .. db.escapeString(GOD_ACCOUNT_NAME))
	if not accountResult then
		logger.error("[vinot] Migration failed: no account named '{}' found.", GOD_ACCOUNT_NAME)
		return
	end
	local accountId = Result.getNumber(accountResult, "id")
	Result.free(accountResult)

	for vocationId, config in pairs(TEMPLATES) do
		createTemplate(vocationId, config, accountId)
	end
end

migration:register()

-- One-time server migration: creates a level 1000 Elite Knight, fully
-- equipped for hunting, on the "god" login account.
--
-- Runs once on server startup (tracked by the Migration framework in
-- data/scripts/lib/register_migrations.lua) and is safe to leave in the
-- codebase afterwards: KV.scoped("migrations") remembers it already ran,
-- and the player-name check below is a second guard in case someone
-- already created a character with the same name by hand.

local CHARACTER_NAME = "Vinot Knight"
local GOD_ACCOUNT_NAME = "god"
local TARGET_LEVEL = 1000
local ELITE_KNIGHT_VOCATION_ID = 8 -- "Elite Knight" in data/XML/vocations.xml (promoted Knight)

-- Growth rates taken straight from data/XML/vocations.xml (Knight):
-- gainhp="15" gainmana="5" gaincap="25". Base stats at level 1 are the
-- standard Tibia defaults (150 HP, 0 mana, 400 cap) before any vocation
-- bonus is applied.
local BASE_HEALTH, GAIN_HEALTH = 150, 15
local BASE_MANA, GAIN_MANA = 0, 5
local BASE_CAP, GAIN_CAP = 400, 25

local SKILL_LEVEL = 150 -- sword fighting + shielding, well past the old "master" milestone
local FIST_SKILL_LEVEL = 60

-- Equipment: {slot, list of item names to try in priority order}.
-- Every name is resolved through ItemType at runtime and skipped with a
-- warning if it doesn't exist in this server's items.xml, so a wrong guess
-- here never corrupts the character -- it just leaves that slot empty and
-- says so in the log.
local EQUIPMENT = {
	{ slot = CONST_SLOT_HEAD, names = { "Crown Helmet", "Royal Helmet", "Warrior Helmet" } },
	{ slot = CONST_SLOT_NECKLACE, names = { "Stone Skin Amulet", "Bonfire Amulet", "Silver Amulet" } },
	{ slot = CONST_SLOT_ARMOR, names = { "Crown Armor", "Golden Armor", "Studded Armor" } },
	{ slot = CONST_SLOT_LEGS, names = { "Crown Legs", "Golden Legs", "Plate Legs" } },
	{ slot = CONST_SLOT_FEET, names = { "Boots of Haste", "Steel Boots", "Leather Boots" } },
	{ slot = CONST_SLOT_RING, names = { "Might Ring", "Stealth Ring", "Silver Ring" } },
	{ slot = CONST_SLOT_LEFT, names = { "Fireborn Giant Sword", "Two Handed Sword", "Fire Sword" } },
	{ slot = CONST_SLOT_RIGHT, names = { "Demon Shield", "Ancient Shield", "Tower Shield" } },
	{ slot = CONST_SLOT_BACKPACK, names = { "Golden Backpack", "Backpack" } },
}

-- Hunting supplies dropped into the backpack: {item name candidates, count}.
local SUPPLIES = {
	{ names = { "Ultimate Health Potion" }, count = 100 },
	{ names = { "Great Mana Potion" }, count = 100 },
	{ names = { "Great Spirit Potion" }, count = 50 },
	{ names = { "Sudden Death Rune" }, count = 25 },
	{ names = { "Intense Healing Rune" }, count = 25 },
	{ names = { "Platinum Coin" }, count = 100 },
}

local function resolveItemId(names)
	for _, name in ipairs(names) do
		local itemType = ItemType(name)
		if itemType and itemType:getId() ~= 0 then
			return itemType:getId(), name
		end
	end
	return nil, names[1]
end

local migration = Migration("20260928010000_create_vinot_god_knight")

function migration:onExecute()
	local existingResult = db.storeQuery("SELECT `id` FROM `players` WHERE `name` = " .. db.escapeString(CHARACTER_NAME))
	if existingResult then
		Result.free(existingResult)
		logger.warn("[vinot] Migration skipped: a character named '{}' already exists.", CHARACTER_NAME)
		return
	end

	local accountResult = db.storeQuery("SELECT `id` FROM `accounts` WHERE `name` = " .. db.escapeString(GOD_ACCOUNT_NAME))
	if not accountResult then
		logger.error("[vinot] Migration failed: no account named '{}' found.", GOD_ACCOUNT_NAME)
		return
	end
	local accountId = Result.getNumber(accountResult, "id")
	Result.free(accountResult)

	local healthmax = BASE_HEALTH + (TARGET_LEVEL - 1) * GAIN_HEALTH
	local manamax = BASE_MANA + (TARGET_LEVEL - 1) * GAIN_MANA
	local cap = BASE_CAP + (TARGET_LEVEL - 1) * GAIN_CAP

	local inserted = db.query(
		"INSERT INTO `players` (`name`, `group_id`, `account_id`, `level`, `vocation`, `health`, `healthmax`, `mana`, `manamax`, `cap`, `sex`, `town_id`, `conditions`) VALUES ("
			.. db.escapeString(CHARACTER_NAME)
			.. ", 1, "
			.. accountId
			.. ", 1, "
			.. ELITE_KNIGHT_VOCATION_ID
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
		logger.error("[vinot] Migration failed: could not insert player row for '{}'.", CHARACTER_NAME)
		return
	end

	local player = Game.getOfflinePlayer(CHARACTER_NAME)
	if not player then
		logger.error("[vinot] Migration failed: player '{}' was inserted but could not be loaded.", CHARACTER_NAME)
		return
	end

	player:setLevel(TARGET_LEVEL)
	player:setSkillLevel(SKILL_SWORD, SKILL_LEVEL)
	player:setSkillLevel(SKILL_SHIELD, SKILL_LEVEL)
	player:setSkillLevel(SKILL_FIST, FIST_SKILL_LEVEL)

	local towns = Game.getTowns()
	if towns and towns[1] then
		player:teleportTo(towns[1]:getTemplePosition(), false)
	end

	for _, entry in ipairs(EQUIPMENT) do
		local itemId, attemptedName = resolveItemId(entry.names)
		if itemId then
			local result = player:addItem(itemId, 1, false, 0, entry.slot)
			if not result then
				logger.warn("[vinot] Could not equip '{}' (slot {}): no free slot or incompatible with current gear.", attemptedName, entry.slot)
			end
		else
			logger.warn("[vinot] None of the configured items for slot {} exist on this server: {}", entry.slot, table.concat(entry.names, ", "))
		end
	end

	for _, entry in ipairs(SUPPLIES) do
		local itemId, attemptedName = resolveItemId(entry.names)
		if itemId then
			player:addItem(itemId, entry.count)
		else
			logger.warn("[vinot] Supply item not found on this server: {}", attemptedName)
		end
	end

	player:save()
	logger.info("[vinot] Created level {} Elite Knight '{}' on account '{}' (account id {}).", TARGET_LEVEL, CHARACTER_NAME, GOD_ACCOUNT_NAME, accountId)
end

migration:register()

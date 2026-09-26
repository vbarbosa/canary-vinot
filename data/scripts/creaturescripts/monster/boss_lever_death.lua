local onBossDeath = CreatureEvent("BossLeverOnDeath")

function onBossDeath.onDeath(creature)
	if not creature then
		return true
	end

	local name = creature:getName()
	local key = "boss." .. toKey(name)
	local zone = Zone(key)

	if not zone then
		return true
	end

	local bossLever = BossLever[name]
	if not bossLever then
		return true
	end

	if bossLever.timeoutEvent then
		stopEvent(bossLever.timeoutEvent)
		bossLever.timeoutEvent = nil
	end

	if bossLever.timeAfterKill > 0 then
		zone:sendTextMessage(MESSAGE_EVENT_ADVANCE, "The " .. name .. " has been defeated. You have " .. bossLever.timeAfterKill .. " seconds to leave the room.")
		bossLever.timeoutEvent = addEvent(function(zn)
			zn:refresh()
			zn:removePlayers()
		end, bossLever.timeAfterKill * 1000, zone)
	end
	-- Prêmio extra do painel (Cockpit > Dungeons > cockpit_dungeon_auto), opcional, por cima do loot normal.
	local extraId, extraQty, extraChance
	local resultId = db.storeQuery("SELECT `extra_item_id`, `extra_item_qty`, `extra_chance` FROM `cockpit_dungeon_auto` " .. "WHERE `name` = " .. db.escapeString(name) .. " AND `extra_item_id` IS NOT NULL")
	if resultId then
		extraId = Result.getNumber(resultId, "extra_item_id")
		extraQty = Result.getNumber(resultId, "extra_item_qty")
		extraChance = tonumber(Result.getString(resultId, "extra_chance"))
		Result.free(resultId)
	end

	onDeathForDamagingPlayers(creature, function(creature, player)
		player:takeScreenshot(SCREENSHOT_TYPE_BOSSDEFEATED)
		if extraId and math.random() * 100 <= extraChance then
			player:addItem(extraId, extraQty or 1)
		end
	end)
	return true
end

onBossDeath:register()

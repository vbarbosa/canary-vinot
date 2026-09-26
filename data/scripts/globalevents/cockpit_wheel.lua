-- Roleta da sorte, set up in the Cockpit panel (tela Roleta).
-- Players say !roleta. Each day gives some free spins; after that a spin costs gold from the bank.
-- The Mestre can also give extra spins from the panel. Prizes and chances live in `cockpit_wheel_prizes`,
-- the rules in `cockpit_settings` (wheel.*), and every spin is written to `cockpit_wheel_log`.

local SCOPE = "cockpit-wheel"

local function settings()
	local s = { enabled = "0", cost = "0", free = "1", place = "", radius = "3" }
	local resultId = db.storeQuery("SELECT `k`, `v` FROM `cockpit_settings` WHERE `k` LIKE 'wheel.%'")
	if resultId then
		repeat
			s[Result.getString(resultId, "k"):sub(7)] = Result.getString(resultId, "v")
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return s
end

local function prizes()
	local list, total = {}, 0
	local resultId = db.storeQuery("SELECT `id`, `label`, `kind`, `item_id`, `amount`, `weight` FROM `cockpit_wheel_prizes` WHERE `active` = 1 AND `weight` > 0")
	if resultId then
		repeat
			local p = {
				id = Result.getNumber(resultId, "id"),
				label = Result.getString(resultId, "label"),
				kind = Result.getString(resultId, "kind"),
				itemId = Result.getNumber(resultId, "item_id"),
				amount = Result.getNumber(resultId, "amount"),
				weight = Result.getNumber(resultId, "weight"),
			}
			total = total + p.weight
			list[#list + 1] = p
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return list, total
end

local function pick(list, total)
	local roll = math.random(1, total)
	for _, p in ipairs(list) do
		roll = roll - p.weight
		if roll <= 0 then
			return p
		end
	end
	return list[#list]
end

local function deliver(player, prize)
	if prize.kind == "item" then
		local it = ItemType(prize.itemId)
		if it:getId() == 0 then
			return "um item que sumiu da lista"
		end
		local count = math.max(1, prize.amount)
		if it:getCharges() > 0 and not it:isStackable() then
			player:addItem(prize.itemId, it:getCharges(), true)
		else
			player:addItem(prize.itemId, count, true)
		end
		return count .. "x " .. it:getName()
	elseif prize.kind == "gold" then
		player:setBankBalance(player:getBankBalance() + prize.amount)
		return prize.amount .. " gold no banco"
	elseif prize.kind == "xp" then
		player:addExperience(prize.amount, true)
		return prize.amount .. " de experiencia"
	elseif prize.kind == "spins" then
		local kv = player:kv():scoped(SCOPE)
		kv:set("bonus", (kv:get("bonus") or 0) + prize.amount)
		return prize.amount .. " giro(s) extra"
	end
	return nil -- "nada": try again
end

local spinning = {}

local wheel = TalkAction("!roleta")

function wheel.onSay(player, words, param)
	local s = settings()
	if s.enabled ~= "1" then
		player:sendCancelMessage("A roleta da sorte esta fechada agora.")
		return false
	end
	local x, y, z = s.place:match("^(%d+),(%d+),(%d+)$")
	if x and (player:getPosition().z ~= tonumber(z) or player:getPosition():getDistance(Position(tonumber(x), tonumber(y), tonumber(z))) > tonumber(s.radius or 3)) then
		player:sendCancelMessage("Va ate a roleta da sorte para girar.")
		return false
	end
	if spinning[player:getGuid()] then
		return false
	end
	local list, total = prizes()
	if #list == 0 then
		player:sendCancelMessage("A roleta esta sem premios.")
		return false
	end

	local kv = player:kv():scoped(SCOPE)
	local today = os.date("%Y-%m-%d")
	if kv:get("day") ~= today then
		kv:set("day", today)
		kv:set("used", 0)
	end
	local used, free, bonus, cost = kv:get("used") or 0, tonumber(s.free) or 0, kv:get("bonus") or 0, tonumber(s.cost) or 0
	local paid = "gratis"
	if used < free then
		kv:set("used", used + 1)
	elseif bonus > 0 then
		kv:set("bonus", bonus - 1)
		paid = "giro extra"
	elseif cost > 0 then
		if player:getBankBalance() < cost then
			player:sendCancelMessage("Os giros gratis de hoje acabaram. Um giro custa " .. cost .. " gold do banco.")
			return false
		end
		player:setBankBalance(player:getBankBalance() - cost)
		paid = cost .. " gold"
	else
		player:sendCancelMessage("Os giros de hoje acabaram. Volte amanha!")
		return false
	end

	local prize = pick(list, total)
	local guid, name = player:getGuid(), player:getName()
	spinning[guid] = true
	player:say("A roleta gira...", TALKTYPE_MONSTER_SAY)
	for i = 1, 3 do
		addEvent(function()
			local p = Player(name)
			if p then
				p:getPosition():sendMagicEffect(i == 3 and CONST_ME_FIREWORK_YELLOW or CONST_ME_MAGIC_BLUE)
			end
		end, i * 700)
	end
	addEvent(function()
		spinning[guid] = nil
		local p = Player(name)
		if not p then
			return
		end
		local got = deliver(p, prize)
		local text = got and ("Roleta da sorte: " .. prize.label .. " (" .. got .. ")!") or "Roleta da sorte: nao foi dessa vez. Tente de novo!"
		p:sendTextMessage(MESSAGE_EVENT_ADVANCE, text)
		db.query(string.format("INSERT INTO `cockpit_wheel_log` (`at`, `player`, `prize_id`, `label`, `paid`) VALUES (%d, %s, %d, %s, %s)", os.time(), db.escapeString(name), prize.id, db.escapeString(prize.label), db.escapeString(paid)))
	end, 2500)
	return false
end

wheel:separator(" ")
wheel:groupType("normal")
wheel:register()

-- panel action (cockpit.lua calls it): give extra spins
function CockpitGiveSpins(player, amount)
	local kv = player:kv():scoped(SCOPE)
	kv:set("bonus", (kv:get("bonus") or 0) + amount)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "O Mestre te deu " .. amount .. " giro(s) na roleta da sorte! Diga !roleta.")
	return true
end

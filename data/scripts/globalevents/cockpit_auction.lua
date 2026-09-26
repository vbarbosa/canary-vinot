-- Leiloes de casas, abertos pelo painel Cockpit (tela Imobiliaria). The server has no website, so bids happen here:
-- !leilao lists the open auctions, !lance <n> <valor> bids. The panel closes the auction and charges the winner.

local EXTEND = 5 * 60 -- a bid in the last 5 minutes pushes the end 5 minutes out

local function openAuctions(id)
	local list = {}
	local where = "`status` = 'open' AND `ends_at` > UNIX_TIMESTAMP()" .. (id and (" AND `id` = " .. id) or "")
	local resultId = db.storeQuery("SELECT `id`, `house`, `town`, `min_bid`, `ends_at`, `top_bid`, `top_player_id`, `top_name` FROM `cockpit_auctions` WHERE " .. where .. " ORDER BY `ends_at`")
	if resultId then
		repeat
			list[#list + 1] = {
				id = Result.getNumber(resultId, "id"),
				house = Result.getString(resultId, "house"),
				town = Result.getString(resultId, "town"),
				minBid = Result.getNumber(resultId, "min_bid"),
				endsAt = Result.getNumber(resultId, "ends_at"),
				topBid = Result.getNumber(resultId, "top_bid"),
				topId = Result.getNumber(resultId, "top_player_id"),
				topName = Result.getString(resultId, "top_name"),
			}
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return list
end

local function timeLeft(endsAt)
	local s = math.max(0, endsAt - os.time())
	if s >= 3600 then
		return math.floor(s / 3600) .. "h" .. string.format("%02d", math.floor(s % 3600 / 60))
	end
	return math.ceil(s / 60) .. " min"
end

local function nextBid(a)
	if a.topBid <= 0 then
		return a.minBid
	end
	return math.max(a.minBid, a.topBid + math.max(1, math.floor(a.topBid * 5 / 100)))
end

local list = TalkAction("!leilao")

function list.onSay(player, words, param)
	local auctions = openAuctions()
	if #auctions == 0 then
		player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Nenhum leilao de casa aberto agora.")
		return false
	end
	local lines = { "Leiloes de casas (diga !lance numero valor):" }
	for _, a in ipairs(auctions) do
		local top = a.topBid > 0 and (a.topBid .. " gold de " .. a.topName) or "sem lances"
		lines[#lines + 1] = string.format("n%d %s (%s): %s, proximo lance %d, termina em %s", a.id, a.house, a.town, top, nextBid(a), timeLeft(a.endsAt))
	end
	player:showTextDialog(2160, table.concat(lines, "\n"))
	return false
end

list:separator(" ")
list:groupType("normal")
list:register()

local bid = TalkAction("!lance")

function bid.onSay(player, words, param)
	local id, amount = param:match("^%s*(%d+)[%s,]+(%d+)%s*$")
	id, amount = tonumber(id), tonumber(amount)
	if not id or not amount then
		player:sendCancelMessage("Use: !lance numero valor (ex.: !lance 3 50000). Veja os numeros com !leilao.")
		return false
	end
	local a = openAuctions(id)[1]
	if not a then
		player:sendCancelMessage("Esse leilao nao existe ou ja terminou.")
		return false
	end
	if player:getHouse() then
		player:sendCancelMessage("Voce ja tem uma casa.")
		return false
	end
	local level = configManager.getNumber(configKeys.HOUSE_BUY_LEVEL)
	if player:getLevel() < level then
		player:sendCancelMessage("Precisa de nivel " .. level .. " para ter casa.")
		return false
	end
	if a.topId == player:getGuid() then
		player:sendCancelMessage("Seu lance ja e o maior.")
		return false
	end
	local need = nextBid(a)
	if amount < need then
		player:sendCancelMessage("O lance precisa ser de pelo menos " .. need .. " gold.")
		return false
	end
	if player:getBankBalance() < amount then
		player:sendCancelMessage("Seu banco nao cobre esse lance. O valor sai do banco quando o leilao terminar.")
		return false
	end
	local now = os.time()
	local endsAt = math.max(a.endsAt, now + (a.endsAt - now < EXTEND and EXTEND or 0))
	db.query(string.format("UPDATE `cockpit_auctions` SET `top_bid` = %d, `top_player_id` = %d, `top_name` = %s, `ends_at` = %d WHERE `id` = %d AND `status` = 'open' AND `top_bid` < %d", amount, player:getGuid(), db.escapeString(player:getName()), endsAt, a.id, amount))
	db.query(string.format("INSERT INTO `cockpit_auction_bids` (`auction_id`, `player_id`, `name`, `amount`, `at`) VALUES (%d, %d, %s, %d, %d)", a.id, player:getGuid(), db.escapeString(player:getName()), amount, now))
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, string.format("Lance de %d gold na casa %s! Termina em %s.", amount, a.house, timeLeft(endsAt)))
	player:getPosition():sendMagicEffect(CONST_ME_MAGIC_GREEN)
	local previous = a.topId > 0 and Player(a.topName)
	if previous then
		previous:sendTextMessage(MESSAGE_EVENT_ADVANCE, string.format("%s cobriu seu lance na casa %s: agora e %d gold. !leilao para ver.", player:getName(), a.house, amount))
	end
	return false
end

bid:separator(" ")
bid:groupType("normal")
bid:register()

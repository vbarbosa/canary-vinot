-- Inscricao em evento, aberta pelo painel Cockpit (tela Eventos, evento pronto "com inscricao").
-- Players say !evento to join and !evento sair to leave. The panel reads `cockpit_signup_players`
-- and starts the event with whoever is online when the time is up.

local function openSignup()
	local resultId = db.storeQuery("SELECT `id`, `name`, `closes_at` FROM `cockpit_signups` WHERE `status` = 'open' AND `closes_at` > UNIX_TIMESTAMP() ORDER BY `id` DESC LIMIT 1")
	if not resultId then
		return nil
	end
	local row = { id = Result.getNumber(resultId, "id"), name = Result.getString(resultId, "name"), closesAt = Result.getNumber(resultId, "closes_at") }
	Result.free(resultId)
	return row
end

local function countSigned(id)
	local resultId = db.storeQuery("SELECT COUNT(*) AS `n` FROM `cockpit_signup_players` WHERE `signup_id` = " .. id)
	if not resultId then
		return 0
	end
	local n = Result.getNumber(resultId, "n")
	Result.free(resultId)
	return n
end

local signup = TalkAction("!evento")

function signup.onSay(player, words, param)
	local row = openSignup()
	if not row then
		player:sendCancelMessage("Nenhuma inscricao aberta agora.")
		return false
	end
	local guid = player:getGuid()
	local left = math.max(1, math.ceil((row.closesAt - os.time()) / 60))
	if param:lower():find("sair") then
		db.query(string.format("DELETE FROM `cockpit_signup_players` WHERE `signup_id` = %d AND `player_id` = %d", row.id, guid))
		player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Voce saiu da inscricao de " .. row.name .. ".")
		return false
	end
	db.query(string.format("INSERT IGNORE INTO `cockpit_signup_players` (`signup_id`, `player_id`, `name`, `at`) VALUES (%d, %d, %s, %d)", row.id, guid, db.escapeString(player:getName()), os.time()))
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, string.format("Inscrito em %s! Comeca em %d min, fique online. (%d inscrito(s); !evento sair para desistir)", row.name, left, countSigned(row.id)))
	player:getPosition():sendMagicEffect(CONST_ME_MAGIC_GREEN)
	return false
end

signup:separator(" ")
signup:groupType("normal")
signup:register()

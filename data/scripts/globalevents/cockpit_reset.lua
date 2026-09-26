-- Reset de progresso, configurado na tela Reset do painel (cockpit_settings, chaves reset.*).
-- Jogador diz !reset: volta pro level 1 (mantém itens, gold e casas) e ganha um bônus permanente
-- de vida e mana que soma a cada reset. A contagem fica em `cockpit_player_resets`, lida pelo painel.

local function settings()
	local s = { enabled = "0", min_level = "200", max = "0", bonus_hp = "20", bonus_mp = "10" }
	local resultId = db.storeQuery("SELECT `k`, `v` FROM `cockpit_settings` WHERE `k` LIKE 'reset.%'")
	if resultId then
		repeat
			s[Result.getString(resultId, "k"):sub(7)] = Result.getString(resultId, "v")
		until not Result.next(resultId)
		Result.free(resultId)
	end
	return s
end

local function currentCount(guid)
	local resultId = db.storeQuery("SELECT `count` FROM `cockpit_player_resets` WHERE `player_id` = " .. guid)
	if not resultId then
		return 0
	end
	local count = Result.getNumber(resultId, "count")
	Result.free(resultId)
	return count
end

local reset = TalkAction("!reset")

function reset.onSay(player, words, param)
	local s = settings()
	if s.enabled ~= "1" then
		player:sendCancelMessage("O reset de progresso esta desligado agora.")
		return false
	end

	local minLevel = tonumber(s.min_level) or 200
	if player:getLevel() < minLevel then
		player:sendCancelMessage("Voce precisa ser level " .. minLevel .. " para resetar.")
		return false
	end

	local guid = player:getGuid()
	local count = currentCount(guid)
	local max = tonumber(s.max) or 0
	if max > 0 and count >= max then
		player:sendCancelMessage("Voce ja chegou no limite de " .. max .. " reset(s).")
		return false
	end

	-- volta para level 1 pela experiencia, igual ao /addskill do painel
	local diff = Game.getExperienceForLevel(1) - player:getExperience()
	if diff < 0 then
		player:removeExperience(-diff, false)
	end

	local bonusHp = (tonumber(s.bonus_hp) or 0)
	local bonusMp = (tonumber(s.bonus_mp) or 0)
	player:setMaxHealth(math.max(1, player:getMaxHealth() + bonusHp))
	player:setMaxMana(math.max(0, player:getMaxMana() + bonusMp))
	player:addHealth(player:getMaxHealth())
	player:addMana(player:getMaxMana())

	count = count + 1
	db.query("INSERT INTO `cockpit_player_resets` (`player_id`, `count`, `updated_at`) VALUES (" .. guid .. ", " .. count .. ", " .. os.time() .. ") ON DUPLICATE KEY UPDATE `count` = " .. count .. ", `updated_at` = " .. os.time())

	player:getPosition():sendMagicEffect(CONST_ME_HOLYDAMAGE)
	player:sendTextMessage(MESSAGE_EVENT_ADVANCE, "Reset numero " .. count .. "! Voce volta pro level 1 com +" .. bonusHp .. " de vida e +" .. bonusMp .. " de mana permanentes.")
	return false
end

reset:register()

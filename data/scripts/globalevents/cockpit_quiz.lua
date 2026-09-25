-- Quiz, started from the Cockpit panel (tela Eventos). No arena: questions come from the panel's question
-- bank (`cockpit_quiz`), players answer with "!r resposta", the first right answer scores. Most points wins.

CockpitEvents = CockpitEvents or {}

local Q = { running = false }
CockpitEvents.quiz = Q

local TITLE = "Quiz"
local PAUSE = 4 -- seconds between questions

local ACCENTS = {
	["á"] = "a",
	["à"] = "a",
	["ã"] = "a",
	["â"] = "a",
	["ä"] = "a",
	["Á"] = "a",
	["À"] = "a",
	["Ã"] = "a",
	["Â"] = "a",
	["é"] = "e",
	["ê"] = "e",
	["è"] = "e",
	["É"] = "e",
	["Ê"] = "e",
	["í"] = "i",
	["ì"] = "i",
	["Í"] = "i",
	["ó"] = "o",
	["ô"] = "o",
	["õ"] = "o",
	["ò"] = "o",
	["ö"] = "o",
	["Ó"] = "o",
	["Ô"] = "o",
	["Õ"] = "o",
	["ú"] = "u",
	["ü"] = "u",
	["ù"] = "u",
	["Ú"] = "u",
	["ç"] = "c",
	["Ç"] = "c",
	["ñ"] = "n",
}

-- the game client may send Latin-1; map those bytes too
local LATIN1 = {}
for from, to in pairs({ ["\225\224\227\226\228\193\192\195\194"] = "a", ["\233\234\232\201\202"] = "e", ["\237\236\205"] = "i", ["\243\244\245\242\246\211\212\213"] = "o", ["\250\252\249\218"] = "u", ["\231\199"] = "c", ["\241"] = "n" }) do
	for i = 1, #from do
		LATIN1[from:sub(i, i)] = to
	end
end

-- plain ASCII for showing in the game (the client does not always handle UTF-8)
local function plain(text)
	for from, to in pairs(ACCENTS) do
		text = text:gsub(from, to)
	end
	return text
end

local function normalize(text)
	text = plain(text or ""):gsub("[\128-\255]", function(c)
		return LATIN1[c] or ""
	end)
	text = text:lower():gsub("[^%w ]", " "):gsub("%s+", " ")
	return text:match("^%s*(.-)%s*$")
end

local function finish(reason)
	if not Q.running then
		return
	end
	Q.running = false
	if Q.nextEvent then
		stopEvent(Q.nextEvent)
		Q.nextEvent = nil
	end
	local A, G = CockpitArena, Q.G
	A.finish(G, TITLE, A.best(G), reason .. "; " .. A.scoreLine(G))
end

local ask

local function reveal()
	Q.nextEvent = nil
	if not Q.running or not Q.current then
		return
	end
	CockpitArena.tell(Q.G, "Ninguem acertou. Resposta: " .. plain(Q.current.shown) .. ".")
	Q.current = nil
	Q.nextEvent = addEvent(ask, PAUSE * 1000)
end

ask = function()
	Q.nextEvent = nil
	if not Q.running then
		return
	end
	if CockpitArena.count(Q.G) == 0 then
		return finish("ninguem ficou online")
	end
	Q.index = Q.index + 1
	local item = Q.questions[Q.index]
	if not item then
		return finish("perguntas acabaram")
	end
	Q.current = item
	CockpitArena.tell(Q.G, string.format("Pergunta %d de %d: %s  (responda com !r e a resposta)", Q.index, #Q.questions, plain(item.question)))
	Q.nextEvent = addEvent(reveal, Q.answerTime * 1000)
end

function Q.start(cfg)
	if Q.running then
		return false, "ja tem um Quiz rolando"
	end
	local A = CockpitArena
	local G = A.new(cfg)
	Q.G = G
	local count = A.num(G, "questions", 1, 50, 10)
	Q.answerTime = A.num(G, "answer", 10, 120, 30)
	Q.questions, Q.index, Q.current = {}, 0, nil
	local resultId = db.storeQuery("SELECT `question`, `answers` FROM `cockpit_quiz` WHERE `active` = 1 ORDER BY RAND() LIMIT " .. count)
	if resultId then
		repeat
			local answers, shown = {}, nil
			for a in Result.getString(resultId, "answers"):gmatch("[^|]+") do
				shown = shown or a
				answers[normalize(a)] = true
			end
			Q.questions[#Q.questions + 1] = { question = Result.getString(resultId, "question"), answers = answers, shown = shown or "?" }
		until not Result.next(resultId)
		Result.free(resultId)
	end
	if #Q.questions == 0 then
		return false, "nenhuma pergunta ativa no banco do painel"
	end
	-- the quiz does not move anyone: players answer from wherever they are
	for _, name in ipairs(cfg.names) do
		local p = Player(name)
		if p then
			G.players[p:getGuid()] = { name = p:getName(), score = 0 }
		end
	end
	if A.count(G) == 0 then
		return false, "ninguem online para jogar"
	end
	G.stayPut = true
	Q.running = true
	A.tell(G, "Quiz! " .. #Q.questions .. " perguntas, " .. Q.answerTime .. " segundos cada. Responda com !r e a resposta. O primeiro que acertar leva o ponto.")
	Q.nextEvent = addEvent(ask, PAUSE * 1000)
	return true, "Quiz comecou com " .. A.count(G) .. " jogador(es)"
end

function Q.stop()
	if not Q.running then
		return false, "nenhum Quiz rolando"
	end
	finish("parado pelo Mestre")
	return true, "Quiz encerrado"
end

local answer = TalkAction("!r")

function answer.onSay(player, words, param)
	local info = Q.running and Q.G.players[player:getGuid()]
	if not info then
		player:sendCancelMessage("Voce nao esta num Quiz.")
		return false
	end
	if not Q.current then
		player:sendCancelMessage("Espere a proxima pergunta.")
		return false
	end
	if Q.current.answers[normalize(param)] then
		info.score = info.score + 1
		CockpitArena.tell(Q.G, player:getName() .. " acertou: " .. plain(Q.current.shown) .. "! " .. CockpitArena.scoreLine(Q.G))
		Q.current = nil
		if Q.nextEvent then
			stopEvent(Q.nextEvent)
		end
		Q.nextEvent = addEvent(ask, PAUSE * 1000)
	else
		player:sendCancelMessage("Nao e isso. Tente de novo!")
	end
	return false
end

answer:separator(" ")
answer:groupType("normal")
answer:register()

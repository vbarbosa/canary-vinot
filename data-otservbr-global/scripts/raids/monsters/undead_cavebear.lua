-- z=10: a caverna de Liberty Bay onde o Undead Cavebear realmente mora (raids/liberty_bay/undead_cavebear.xml,
-- a raid antiga, sempre usou z=10 nesse mesmo x,y). Essa aqui tinha z=7 (superfície), copiado de outra raid
-- de superfície; nesse chão a área não é o lugar certo do monstro.
local zone = Zone("farmine.undead-cavebear")
zone:addArea(Position(31909, 32554, 10), Position(31983, 32579, 10))

local raid = Raid("farmine.undead-cavebear", {
	zone = zone,
	allowedDays = { "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday" },
	minActivePlayers = 2,
	initialChance = 0.02,
	targetChancePerDay = 0.02,
	maxChancePerCheck = 0.6,
	minGapBetween = "12h",
})

for i = 1, 3 do
	raid
		:addSpawnMonsters({
			{
				name = "Undead Cavebear",
				amount = 3,
			},
		})
		:autoAdvance("2m")
end

raid:register()

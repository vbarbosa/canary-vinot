"""Everything a character has, read from the database: equipment, backpacks, depot, inbox, stash, house,
money, guild, deaths and the raw attributes. For someone online it is as of the last save.
"""

from collections import defaultdict

from . import db, economy, gamedata, realty

SLOTS = {1: "Cabeça", 2: "Colar", 3: "Mochila", 4: "Armadura", 5: "Mão direita", 6: "Mão esquerda",
         7: "Pernas", 8: "Pés", 9: "Anel", 10: "Munição", 11: "Bolsa da loja"}
SEX = {0: "feminino", 1: "masculino"}


def _tree(rows):
    """Item rows (pid = parent sid, roots under 100) -> roots with nested `inside` lists and counts."""
    names = gamedata.item_names()
    kids = defaultdict(list)
    for r in rows:
        kids[r["pid"]].append(r)

    def build(r):
        node = {"id": r["itemtype"], "name": names.get(r["itemtype"], f"item {r['itemtype']}"), "count": r["count"], "sid": r["sid"],
                "slot": r["pid"], "inside": [build(k) for k in sorted(kids.get(r["sid"], []), key=lambda k: k["sid"])]}
        node["total"] = 1 + sum(k["total"] for k in node["inside"])
        return node

    roots = [build(r) for r in sorted(rows, key=lambda r: (r["pid"], r["sid"])) if r["pid"] < 100]
    return roots


def _gold(rows):
    return sum(r["count"] * economy.COINS.get(r["itemtype"], 0) for r in rows)


def load(pid):
    p = db.one("SELECT p.*, o.player_id IS NOT NULL AS online, a.name AS account_name, a.email, a.coins, a.coins_transferable, a.premdays "
               "FROM players p JOIN accounts a ON a.id = p.account_id LEFT JOIN cockpit_online o ON o.player_id = p.id WHERE p.id = %s", pid)
    if not p:
        return None
    worn = db.all("SELECT pid, sid, itemtype, count FROM player_items WHERE player_id = %s", pid)
    depot = db.all("SELECT pid, sid, itemtype, count FROM player_depotitems WHERE player_id = %s", pid)
    inbox = db.all("SELECT pid, sid, itemtype, count FROM player_inboxitems WHERE player_id = %s", pid)
    names = gamedata.item_names()
    stash = [{"id": r["item_id"], "name": names.get(r["item_id"], f"item {r['item_id']}"), "count": r["item_count"]}
             for r in db.all("SELECT item_id, item_count FROM player_stash WHERE player_id = %s ORDER BY item_count DESC", pid)]
    houses = [h for h in realty.houses() if h["owner"] == pid]
    guild = db.one("SELECT g.id, g.name, r.name AS rank_name, m.nick FROM guild_membership m JOIN guilds g ON g.id = m.guild_id "
                   "JOIN guild_ranks r ON r.id = m.rank_id WHERE m.player_id = %s", pid)
    deaths = db.all("SELECT * FROM player_deaths WHERE player_id = %s ORDER BY time DESC LIMIT 10", pid)
    kills = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(unavenged), 0) AS unavenged FROM player_kills WHERE player_id = %s", pid)
    storages = db.one("SELECT COUNT(*) AS n FROM player_storage WHERE player_id = %s", pid)
    money = {"bank": int(p["balance"]), "carried": _gold(worn), "depot": _gold(depot) + _gold(inbox)}
    money["total"] = sum(money.values())
    return {
        "p": p, "slots": SLOTS, "sex": SEX.get(p["sex"], p["sex"]),
        "worn": _tree(worn), "depot": _tree(depot), "inbox": _tree(inbox), "stash": stash,
        "counts": {"worn": len(worn), "depot": len(depot), "inbox": len(inbox), "stash": sum(s["count"] for s in stash)},
        "houses": houses, "guild": guild, "deaths": deaths, "kills": kills, "storages": storages["n"], "money": money,
        "raw": {k: v for k, v in p.items() if not isinstance(v, (bytes, bytearray))},
    }

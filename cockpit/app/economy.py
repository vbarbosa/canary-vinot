"""Money in the world: gold in banks, backpacks and depots, Tibia coins, and hourly snapshots of the totals."""

import time

from . import db

# Coin items and what each is worth in gold.
COINS = {3031: 1, 3035: 100, 3043: 10000}
_COIN_SQL = "CASE itemtype " + " ".join(f"WHEN {i} THEN {v}" for i, v in COINS.items()) + " END"
_IDS = ",".join(str(i) for i in COINS)


def _items_gold(table):
    return f"SELECT player_id, SUM(`count` * {_COIN_SQL}) AS gold FROM {table} WHERE itemtype IN ({_IDS}) GROUP BY player_id"


def snapshot():
    """Current totals. Online players' in-memory changes show up after the server saves."""
    bank = db.one("SELECT COALESCE(SUM(balance), 0) AS g, COUNT(*) AS players, SUM(balance > 0) AS savers FROM players")
    carried = db.one(f"SELECT COALESCE(SUM(gold), 0) AS g FROM ({_items_gold('player_items')}) x")
    depot = db.one(
        f"SELECT COALESCE(SUM(gold), 0) AS g FROM ({_items_gold('player_depotitems')} UNION ALL {_items_gold('player_inboxitems')}) x"
    )
    guild = db.one("SELECT COALESCE(SUM(balance), 0) AS g FROM guilds")
    coins = db.one("SELECT COALESCE(SUM(coins), 0) AS c, COALESCE(SUM(coins_transferable), 0) AS t FROM accounts")
    parts = {"bank": int(bank["g"]), "carried": int(carried["g"]), "depot": int(depot["g"]), "guild": int(guild["g"])}
    total = sum(parts.values())
    return {**parts, "total": total, "players": bank["players"], "savers": int(bank["savers"] or 0),
            "per_player": total // bank["players"] if bank["players"] else 0, "coins": int(coins["c"]), "coins_t": int(coins["t"])}


def richest(n=10):
    return db.all(
        f"SELECT p.id, p.name, p.level, p.balance AS bank, COALESCE(c.gold, 0) AS carried, COALESCE(d.gold, 0) AS depot, "
        f"p.balance + COALESCE(c.gold, 0) + COALESCE(d.gold, 0) AS total FROM players p "
        f"LEFT JOIN ({_items_gold('player_items')}) c ON c.player_id = p.id "
        f"LEFT JOIN (SELECT player_id, SUM(gold) AS gold FROM ({_items_gold('player_depotitems')} UNION ALL {_items_gold('player_inboxitems')}) u GROUP BY player_id) d "
        f"ON d.player_id = p.id WHERE p.group_id < 4 ORDER BY total DESC LIMIT %s",
        n,
    )


def record():
    """One row per hour, kept 90 days."""
    ts = int(time.time()) // 3600 * 3600
    if db.one("SELECT ts FROM cockpit_economy WHERE ts = %s", ts):
        return
    e = snapshot()
    db.run("INSERT IGNORE INTO cockpit_economy (ts, gold, bank, coins) VALUES (%s,%s,%s,%s)", ts, e["total"], e["bank"], e["coins"] + e["coins_t"])
    db.run("DELETE FROM cockpit_economy WHERE ts < %s", ts - 90 * 86400)

"""Mercado: the game's market offers and history, read from `market_offers` and `market_history`.

Cancelling from the panel marks the offer as expired (created = 0). It leaves the market at once, and the game's own
expiry check (every checkExpiredMarketOffersEachMinutes, 60 by default, and at startup) gives back the items
(to the inbox) or the gold (to the bank) like any expired offer.
"""

import time

from . import db, gamedata

STATES = {0: "ativa", 1: "cancelada", 2: "expirou", 3: "vendida", 255: "vendida"}


def _names(rows):
    names = gamedata.item_names()
    for r in rows:
        r["item"] = names.get(r["itemtype"], f"item {r['itemtype']}")
        r["total"] = r["price"] * r["amount"]
    return rows


def _match(names, q):
    q = q.strip().lower()
    return [iid for iid, n in names.items() if q in n.lower()][:500] if q else []


def offers(q="", lado=""):
    where, args = ["o.created > 0"], []
    if lado in ("venda", "compra"):
        where.append("o.sale = %s")
        args.append(1 if lado == "venda" else 0)
    if q:
        ids = _match(gamedata.item_names(), q)
        where.append("(p.name LIKE %s" + (f" OR o.itemtype IN ({','.join(['%s'] * len(ids))})" if ids else "") + ")")
        args += [f"%{q.strip()}%", *ids]
    rows = db.all("SELECT o.*, p.name AS player FROM market_offers o JOIN players p ON p.id = o.player_id WHERE "
                  + " AND ".join(where) + " ORDER BY o.created DESC LIMIT 200", *args)
    return _names(rows)


def history(limit=40):
    rows = db.all("SELECT h.*, p.name AS player FROM market_history h JOIN players p ON p.id = h.player_id "
                  "ORDER BY h.inserted DESC LIMIT %s", limit)
    return _names(rows)


def stats(days=7):
    since = int(time.time()) - days * 86400
    return db.one("SELECT COUNT(*) AS n, COALESCE(SUM(price * amount), 0) AS volume FROM market_history "
                  "WHERE sale = 1 AND state IN (3, 255) AND inserted >= %s", since)


def cancel(oid):
    """Expire one offer; returns the offer or None."""
    o = db.one("SELECT o.*, p.name AS player FROM market_offers o JOIN players p ON p.id = o.player_id WHERE o.id = %s AND o.created > 0", oid)
    if o:
        db.run("UPDATE market_offers SET created = 0 WHERE id = %s", oid)
        _names([o])
    return o

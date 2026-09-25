"""Imobiliária: every house of the map, who owns it, and rent charged by the panel.

The map (world/otservbr-house.xml) says where each house is and its base rent; the `houses`
table says who owns it. The game's own rent is off (houseRentPeriod = "never"), so the panel
runs it: once a minute the scheduler calls tick(), which charges due rent from the owner's
bank through the Lua bridge, counts late payments and evicts after too many.
"""

import os
import time
import xml.etree.ElementTree as ET
from functools import lru_cache

from . import db, places

SQM_PRICE = int(os.environ.get("COCKPIT_HOUSE_SQM_PRICE", "1000"))  # housePriceEachSQM in config.lua
DAY = 86400
PERIODS = {"off": ("Sem aluguel", 0), "weekly": ("Toda semana", 7 * DAY), "monthly": ("Todo mês", 30 * DAY)}
DEFAULTS = {"period": "off", "percent": "100", "grace": "3"}
ACTOR = "imobiliária"
LOG_KINDS = {"aluguel": "💰 Aluguel pago", "atraso": "⏰ Sem saldo", "despejo": "🚪 Despejo", "dono": "🔑 Novo dono",
             "livre": "🏚 Ficou livre", "perdao": "🤝 Perdoado", "valor": "✏ Aluguel mudou"}


@lru_cache(maxsize=1)
def map_houses():
    """House id -> what the map says about it."""
    out = {}
    try:
        for h in ET.parse(os.path.join(places.DATAPACK, "world", "otservbr-house.xml")).getroot():
            hid = int(h.get("houseid"))
            out[hid] = {"id": hid, "name": h.get("name"), "x": int(h.get("entryx")), "y": int(h.get("entryy")), "z": int(h.get("entryz")),
                        "base_rent": int(h.get("rent") or 0), "size": int(h.get("size") or 0), "beds": int(h.get("beds") or 0),
                        "town_id": int(h.get("townid") or 0), "guildhall": h.get("guildhall") == "true"}
    except (OSError, ET.ParseError):
        pass
    return out


def settings():
    s = dict(DEFAULTS)
    s.update({r["k"]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k IN ('period', 'percent', 'grace')")})
    if s["period"] not in PERIODS:
        s["period"] = "off"
    s["percent"] = max(0, min(1000, int(s["percent"]) if str(s["percent"]).isdigit() else 100))
    s["grace"] = max(1, min(30, int(s["grace"]) if str(s["grace"]).isdigit() else 3))
    s["seconds"] = PERIODS[s["period"]][1]
    return s


def save_settings(period, percent, grace):
    old = settings()
    for k, v in (("period", period), ("percent", percent), ("grace", grace)):
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", k, str(v))
    new = settings()
    if new["period"] != old["period"]:
        # a new rule starts counting now: nobody pays the moment rent is switched on
        db.run("UPDATE cockpit_house_rent SET paid_until = %s, warnings = 0, next_try = 0", int(time.time()) + new["seconds"] if new["seconds"] else 0)
    return new


def rent_of(h, s):
    """What the owner pays each period: the value set by hand, or the map's rent times the percentage."""
    if h.get("rent_override") is not None:
        return int(h["rent_override"])
    return h["base_rent"] * s["percent"] // 100


def houses(s=None):
    """Every house on the map with its owner and rent state, sorted by town and name."""
    s = s or settings()
    db_rows = {r["id"]: r for r in db.all(
        "SELECT h.id, h.owner, h.paid, h.warnings, p.name AS owner_name, p.level AS owner_level, p.lastlogin "
        "FROM houses h LEFT JOIN players p ON p.id = h.owner")}
    rent = {r["house_id"]: r for r in db.all("SELECT * FROM cockpit_house_rent")}
    towns = {t["id"]: t["name"] for t in db.all("SELECT id, name FROM towns")}
    now = int(time.time())
    out = []
    for hid, m in map_houses().items():
        d, r = db_rows.get(hid, {}), rent.get(hid, {})
        h = dict(m, owner=int(d.get("owner") or 0), owner_name=d.get("owner_name") or "", owner_level=d.get("owner_level") or 0,
                 lastlogin=d.get("lastlogin") or 0, town=towns.get(m["town_id"], f"Cidade {m['town_id']}"),
                 rent_override=r.get("rent"), paid_until=int(r.get("paid_until") or 0), warnings=int(r.get("warnings") or 0),
                 charging=bool(r.get("cmd_id")), price=m["size"] * SQM_PRICE)
        h["rent"] = rent_of(h, s)
        h["late"] = bool(h["owner"] and s["seconds"] and h["rent"] and h["warnings"])
        h["status"] = "livre" if not h["owner"] else ("atrasada" if h["late"] else "ocupada")
        h["days_left"] = (h["paid_until"] - now) // DAY if h["owner"] and s["seconds"] and h["paid_until"] else None
        out.append(h)
    out.sort(key=lambda h: (h["town"], h["name"]))
    return out


def search(all_houses, q="", cidade="", situacao=""):
    q = q.strip().lower()
    rows = [h for h in all_houses
            if (not q or q in h["name"].lower() or q in h["owner_name"].lower())
            and (not cidade or str(h["town_id"]) == cidade)
            and (not situacao or (situacao == "guildhall" and h["guildhall"]) or h["status"] == situacao)]
    return rows


def one(hid, s=None):
    return next((h for h in houses(s) if h["id"] == hid), None)


def log(kind, h, player="", amount=0, note="", actor=ACTOR):
    db.run("INSERT INTO cockpit_house_log (ts, house_id, house, player, kind, amount, note, actor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
           int(time.time()), h["id"], h["name"], player, kind, int(amount), note[:255], actor)


def history(hid=None, limit=30):
    if hid:
        return db.all("SELECT * FROM cockpit_house_log WHERE house_id = %s ORDER BY id DESC LIMIT %s", hid, limit)
    return db.all("SELECT * FROM cockpit_house_log ORDER BY id DESC LIMIT %s", limit)


def income(days=30):
    r = db.one("SELECT COALESCE(SUM(amount), 0) AS g, COUNT(*) AS n FROM cockpit_house_log WHERE kind = 'aluguel' AND ts >= %s", int(time.time()) - days * DAY)
    return int(r["g"]), r["n"]


def _row(hid, owner=0):
    db.run("INSERT IGNORE INTO cockpit_house_rent (house_id, owner) VALUES (%s, %s)", hid, owner)
    return db.one("SELECT * FROM cockpit_house_rent WHERE house_id = %s", hid)


def set_owner(actor, h, guid, player_name=""):
    msg = f"A casa {h['name']} agora é sua! Presente do Mestre." if guid else ""
    return db.enqueue(actor, "house_owner", player_name or h["name"], h["id"], guid, text=msg)


def charge(actor, h, amount):
    cmd = db.enqueue(actor, "house_rent", h["owner_name"], h["id"], amount, h["owner"],
                     text=f"Aluguel da casa {h['name']}: {amount} gold, pago pelo seu banco.")
    db.run("UPDATE cockpit_house_rent SET cmd_id = %s WHERE house_id = %s", cmd, h["id"])
    return cmd


def forgive(actor, h, s):
    now = int(time.time())
    db.run("UPDATE cockpit_house_rent SET warnings = 0, next_try = 0, paid_until = %s WHERE house_id = %s",
           now + s["seconds"] if s["seconds"] else 0, h["id"])
    log("perdao", h, h["owner_name"], note="dívida perdoada, próximo período grátis", actor=actor)


def set_rent(actor, h, value):
    _row(h["id"], h["owner"])
    db.run("UPDATE cockpit_house_rent SET rent = %s WHERE house_id = %s", value, h["id"])
    log("valor", h, amount=value if value is not None else 0, note="valor próprio" if value is not None else "voltou ao padrão", actor=actor)


def tick():
    """Follow owner changes, settle finished charges and charge the rent that is due."""
    s = settings()
    now = int(time.time())
    period = s["seconds"]
    fresh = not db.one("SELECT 1 AS x FROM cockpit_house_rent LIMIT 1")
    rows = {r["house_id"]: r for r in db.all("SELECT * FROM cockpit_house_rent")}
    for h in houses(s):
        r = rows.get(h["id"])
        if not r:
            if not h["owner"]:
                continue
            r = _row(h["id"], -1)  # a new owner, except right after install, when current owners are not news
            if fresh:
                db.run("UPDATE cockpit_house_rent SET owner = %s, paid_until = %s WHERE house_id = %s", h["owner"], now + period if period else 0, h["id"])
                continue
        if r["owner"] != h["owner"]:
            db.run("UPDATE cockpit_house_rent SET owner = %s, paid_until = %s, warnings = 0, next_try = 0, cmd_id = 0 WHERE house_id = %s",
                   h["owner"], now + period if period and h["owner"] else 0, h["id"])
            if h["owner"]:
                log("dono", h, h["owner_name"], note="comprou ou recebeu a casa")
            elif r["owner"] > 0:
                last = db.one("SELECT kind FROM cockpit_house_log WHERE house_id = %s ORDER BY id DESC LIMIT 1", h["id"])
                if not last or last["kind"] != "despejo":
                    log("livre", h, note="a casa ficou sem dono")
            continue
        if r["cmd_id"]:
            _settle(h, r, s, now)
            continue
        if not (period and h["owner"] and h["rent"] > 0):
            continue
        if not r["paid_until"]:
            db.run("UPDATE cockpit_house_rent SET paid_until = %s WHERE house_id = %s", now + period, h["id"])
        elif r["paid_until"] <= now and r["next_try"] <= now:
            charge(ACTOR, h, h["rent"])


def _settle(h, r, s, now):
    cmd = db.one("SELECT status, result, arg2 FROM cockpit_commands WHERE id = %s", r["cmd_id"])
    if cmd and cmd["status"] == "pending":
        return
    if cmd and cmd["status"] == "done":
        paid = max(r["paid_until"], now - s["seconds"]) + s["seconds"] if s["seconds"] else 0
        db.run("UPDATE cockpit_house_rent SET cmd_id = 0, warnings = 0, next_try = 0, paid_until = %s WHERE house_id = %s", paid, h["id"])
        log("aluguel", h, h["owner_name"], cmd["arg2"])
        return
    result = (cmd or {}).get("result") or "sumiu da fila"
    if "saldo" not in result:
        db.run("UPDATE cockpit_house_rent SET cmd_id = 0, next_try = %s WHERE house_id = %s", now + 3600, h["id"])
        return
    warnings = r["warnings"] + 1
    db.run("UPDATE cockpit_house_rent SET cmd_id = 0, warnings = %s, next_try = %s WHERE house_id = %s", warnings, now + DAY, h["id"])
    log("atraso", h, h["owner_name"], cmd["arg2"], f"aviso {warnings} de {s['grace']}")
    if warnings >= s["grace"]:
        set_owner(ACTOR, h, 0)
        log("despejo", h, h["owner_name"], note=f"{warnings} aluguéis sem pagar; os itens vão para o depot")

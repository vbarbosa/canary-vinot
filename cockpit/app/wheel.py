"""Roleta da sorte: prizes, chances and rules set in the panel; the game spins it (data/scripts/globalevents/cockpit_wheel.lua).

Players say !roleta. Rules live in `cockpit_settings` (wheel.*), prizes in `cockpit_wheel_prizes` and every spin in
`cockpit_wheel_log`. The game reads the tables on each spin, so changes here count on the next spin.
"""

import re

from . import db, gamedata

KINDS = {"item": "Item", "gold": "Gold no banco", "xp": "Experiência", "spins": "Giros extra", "nada": "Nada (tente de novo)"}
SETTINGS = {"enabled": "1", "cost": "5000", "free": "1", "place": "", "radius": "3"}
PLACE_RE = re.compile(r"^\d{1,5},\d{1,5},\d{1,2}$")
SEED = [
    ("Nada, tente de novo", "nada", 0, 0, 30),
    ("Mil gold", "gold", 0, 1000, 25),
    ("Dez mil gold", "gold", 0, 10000, 6),
    ("Poções de vida", "item", 239, 20, 10),
    ("Poções de mana", "item", 238, 20, 10),
    ("Experiência", "xp", 0, 50000, 8),
    ("Giro extra", "spins", 0, 1, 8),
    ("Crystal coin", "item", 3043, 1, 3),
]


def seed():
    for k, v in SETTINGS.items():
        db.run("INSERT IGNORE INTO cockpit_settings (k, v) VALUES (%s, %s)", f"wheel.{k}", v)
    if not db.one("SELECT 1 AS x FROM cockpit_wheel_prizes LIMIT 1"):
        for label, kind, item, amount, weight in SEED:
            db.run("INSERT INTO cockpit_wheel_prizes (label, kind, item_id, amount, weight) VALUES (%s, %s, %s, %s, %s)", label, kind, item, amount, weight)


def settings():
    s = dict(SETTINGS)
    s.update({r["k"][6:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'wheel.%%'")})
    return s


def save_settings(f):
    def num(key, lo, hi):
        try:
            return str(max(lo, min(hi, int(f.get(key)))))
        except (TypeError, ValueError):
            return None

    place = str(f.get("place", "")).replace(" ", "")
    if place and not PLACE_RE.match(place):
        return "Lugar da roleta: use x,y,z ou deixe vazio para girar de qualquer lugar."
    values = {"enabled": "1" if f.get("enabled") else "0", "cost": num("cost", 0, 100_000_000), "free": num("free", 0, 50),
              "place": place, "radius": num("radius", 1, 20)}
    if None in values.values():
        return "Confira os números."
    for k, v in values.items():
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"wheel.{k}", v)
    return ""


def prizes():
    rows = db.all("SELECT * FROM cockpit_wheel_prizes ORDER BY active DESC, weight DESC, id")
    total = sum(r["weight"] for r in rows if r["active"]) or 1
    names = gamedata.item_names()
    for r in rows:
        r["chance"] = round(100 * r["weight"] / total, 1) if r["active"] else 0
        r["item_name"] = names.get(r["item_id"], "") if r["kind"] == "item" else ""
    return rows


def resolve_item(text):
    text = str(text).strip()
    names = gamedata.item_names()
    if text.isdigit():
        return int(text) if int(text) in names else 0
    low = text.lower()
    for iid, name in names.items():
        if name.lower() == low:
            return iid
    return 0


def save_prize(pid, f):
    label = " ".join(str(f.get("label", "")).split())[:64]
    kind = str(f.get("kind", ""))
    if kind not in KINDS or not label:
        return "Dê um nome e escolha o tipo do prêmio."
    try:
        amount = max(0, min(1_000_000_000, int(f.get("amount") or 0)))
        weight = max(0, min(10000, int(f.get("weight") or 0)))
    except ValueError:
        return "Quantidade e peso são números."
    item = 0
    if kind == "item":
        item = resolve_item(f.get("item", ""))
        if not item:
            return "Item não encontrado: use o número do item ou o nome exato em inglês."
        amount = max(1, min(amount, 1000))
    elif kind in ("gold", "xp", "spins") and amount < 1:
        return "Quanto vale o prêmio?"
    if pid:
        db.run("UPDATE cockpit_wheel_prizes SET label=%s, kind=%s, item_id=%s, amount=%s, weight=%s WHERE id=%s", label, kind, item, amount, weight, pid)
    else:
        db.run("INSERT INTO cockpit_wheel_prizes (label, kind, item_id, amount, weight) VALUES (%s, %s, %s, %s, %s)", label, kind, item, amount, weight)
    return ""


def log(limit=30):
    return db.all("SELECT * FROM cockpit_wheel_log ORDER BY id DESC LIMIT %s", limit)


def stats():
    return db.one(
        "SELECT COUNT(*) AS spins, COUNT(DISTINCT player) AS players, "
        "SUM(CASE WHEN paid LIKE '%% gold' THEN CAST(paid AS UNSIGNED) ELSE 0 END) AS gold_in "
        "FROM cockpit_wheel_log WHERE at >= UNIX_TIMESTAMP() - 7 * 86400"
    )

"""Hall da fama: rankings of the non-staff characters, read straight from the database."""

from . import db, economy

STAFF = 4  # group_id from here up is staff and stays out of the rankings

# key -> (label, icon, SQL expression shown, SQL order, unit)
BOARDS = {
    "level": ("Nível", "⭐", "p.level", "p.level DESC, p.experience DESC", "nível"),
    "maglevel": ("Magic level", "🔮", "p.maglevel", "p.maglevel DESC, p.manaspent DESC", "ML"),
    "skill_fist": ("Fist", "👊", "p.skill_fist", "p.skill_fist DESC, p.skill_fist_tries DESC", ""),
    "skill_club": ("Club", "🔨", "p.skill_club", "p.skill_club DESC, p.skill_club_tries DESC", ""),
    "skill_sword": ("Sword", "🗡", "p.skill_sword", "p.skill_sword DESC, p.skill_sword_tries DESC", ""),
    "skill_axe": ("Axe", "🪓", "p.skill_axe", "p.skill_axe DESC, p.skill_axe_tries DESC", ""),
    "skill_dist": ("Distance", "🏹", "p.skill_dist", "p.skill_dist DESC, p.skill_dist_tries DESC", ""),
    "skill_shielding": ("Shielding", "🛡", "p.skill_shielding", "p.skill_shielding DESC, p.skill_shielding_tries DESC", ""),
    "skill_fishing": ("Fishing", "🎣", "p.skill_fishing", "p.skill_fishing DESC, p.skill_fishing_tries DESC", ""),
    "rich": ("Mais ricos", "💰", None, None, "gold"),
    "online": ("Mais tempo jogando", "⏳", "p.onlinetime", "p.onlinetime DESC", "tempo"),
    "boss": ("Boss points", "👑", "p.boss_points", "p.boss_points DESC", "pontos"),
    "pvp": ("Matadores (PvP)", "⚔", "COUNT(k.player_id)", None, "mortes"),
    "deaths": ("Mais mortes", "💀", "COUNT(d.player_id)", None, "vezes"),
}


def board(key, vocs=None, n=50):
    """[{id, name, level, vocation, value}] for one board, best first."""
    where, args = f"p.group_id < {STAFF}", []
    if vocs:
        where += f" AND p.vocation IN ({','.join(['%s'] * len(vocs))})"
        args = list(vocs)
    if key == "rich":
        rows = economy.richest(500)
        if vocs:
            voc = {r["id"]: r["vocation"] for r in db.all("SELECT id, vocation FROM players")}
            rows = [r for r in rows if voc.get(r["id"]) in vocs]
        ids = {r["id"] for r in rows}
        extra = {r["id"]: r for r in db.all("SELECT id, vocation FROM players WHERE id IN (%s)" % ",".join(str(i) for i in ids))} if ids else {}
        return [dict(id=r["id"], name=r["name"], level=r["level"], vocation=extra.get(r["id"], {}).get("vocation", 0), value=int(r["total"]))
                for r in rows if r["total"] > 0][:n]
    if key == "pvp":
        sql = (f"SELECT p.id, p.name, p.level, p.vocation, COUNT(k.player_id) AS value FROM players p JOIN player_kills k ON k.player_id = p.id "
               f"WHERE {where} GROUP BY p.id ORDER BY value DESC LIMIT {int(n)}")
    elif key == "deaths":
        sql = (f"SELECT p.id, p.name, p.level, p.vocation, COUNT(d.player_id) AS value FROM players p JOIN player_deaths d ON d.player_id = p.id "
               f"WHERE {where} GROUP BY p.id ORDER BY value DESC LIMIT {int(n)}")
    else:
        _, _, expr, order, _ = BOARDS[key]
        sql = f"SELECT p.id, p.name, p.level, p.vocation, {expr} AS value FROM players p WHERE {where} ORDER BY {order} LIMIT {int(n)}"
    rows = db.all(sql, *args)
    return [r for r in rows if r["value"]] if key in ("online", "boss") else rows


def leaders():
    """The #1 of each board, for the top of the page."""
    out = []
    for key, (label, icon, *_rest) in BOARDS.items():
        top = board(key, n=1)
        if top and top[0]["value"]:
            out.append({"key": key, "label": label, "icon": icon, **top[0]})
    return out

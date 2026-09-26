"""Reset de progresso: personagem volta pro level 1 e ganha um bônus permanente de vida/mana.

Jogador usa !reset (data/scripts/globalevents/cockpit_reset.lua), que lê as regras daqui
(`cockpit_settings`, chaves reset.*) e grava a contagem em `cockpit_player_resets`.
"""

from . import db

SETTINGS = {"enabled": "0", "min_level": "200", "max": "0", "bonus_hp": "20", "bonus_mp": "10"}


def seed():
    for k, v in SETTINGS.items():
        db.run("INSERT IGNORE INTO cockpit_settings (k, v) VALUES (%s, %s)", f"reset.{k}", v)


def settings():
    s = dict(SETTINGS)
    s.update({r["k"][6:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'reset.%%'")})
    return s


def save_settings(f):
    def num(key, lo, hi):
        try:
            return str(max(lo, min(hi, int(f.get(key)))))
        except (TypeError, ValueError):
            return None

    values = {"enabled": "1" if f.get("enabled") else "0", "min_level": num("min_level", 1, 5000), "max": num("max", 0, 1000),
              "bonus_hp": num("bonus_hp", 0, 10000), "bonus_mp": num("bonus_mp", 0, 10000)}
    if None in values.values():
        return "Confira os números."
    for k, v in values.items():
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"reset.{k}", v)
    return ""


def count(pid):
    r = db.one("SELECT count FROM cockpit_player_resets WHERE player_id = %s", pid)
    return r["count"] if r else 0


def top(limit=20):
    return db.all(
        "SELECT r.count, p.name, p.level, p.vocation FROM cockpit_player_resets r JOIN players p ON p.id = r.player_id "
        "WHERE r.count > 0 ORDER BY r.count DESC, p.level DESC LIMIT %s", limit,
    )

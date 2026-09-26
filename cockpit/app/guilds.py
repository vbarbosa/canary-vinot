"""Guilds: what a website portal would do (create, members, ranks, leader, bank, wars), from the panel.

Membership, ranks and wars are read by the game when a player logs in, so the database is the truth and an
online member sees a change after relogging. The bank balance and the message of the day live in memory while
a member is online, so those two go through the Lua bridge (guild_balance, guild_motd).
"""

import re
import time

from . import db

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z ']{2,28}[A-Za-z]$")
RANK_LEVELS = {3: "Líder", 2: "Vice", 1: "Membro"}
WAR_STATUS = {0: "convite", 1: "em guerra", 2: "recusada", 3: "cancelada", 4: "encerrada", 5: "encerrada"}


def all_guilds(q=""):
    return db.all(
        "SELECT g.id, g.name, g.level, g.points, g.balance, g.creationdata, g.motd, p.name AS leader, p.id AS leader_id, "
        "(SELECT COUNT(*) FROM guild_membership m WHERE m.guild_id = g.id) AS members, "
        "(SELECT COUNT(*) FROM guild_membership m JOIN cockpit_online o ON o.player_id = m.player_id WHERE m.guild_id = g.id) AS online, "
        "(SELECT COUNT(*) FROM guild_wars w WHERE (w.guild1 = g.id OR w.guild2 = g.id) AND w.status = 1) AS wars "
        "FROM guilds g LEFT JOIN players p ON p.id = g.ownerid WHERE g.name LIKE %s ORDER BY g.name",
        f"%{q}%",
    )


def one(gid):
    g = db.one("SELECT g.*, p.name AS leader FROM guilds g LEFT JOIN players p ON p.id = g.ownerid WHERE g.id = %s", gid)
    if not g:
        return None
    g["ranks"] = db.all(
        "SELECT r.id, r.name, r.level, (SELECT COUNT(*) FROM guild_membership m WHERE m.rank_id = r.id) AS n "
        "FROM guild_ranks r WHERE r.guild_id = %s ORDER BY r.level DESC, r.id", gid,
    )
    g["members"] = db.all(
        "SELECT p.id, p.name, p.level, p.vocation, m.rank_id, m.nick, r.level AS rank_level, o.player_id IS NOT NULL AS online "
        "FROM guild_membership m JOIN players p ON p.id = m.player_id LEFT JOIN guild_ranks r ON r.id = m.rank_id "
        "LEFT JOIN cockpit_online o ON o.player_id = p.id WHERE m.guild_id = %s ORDER BY r.level DESC, p.name", gid,
    )
    g["invites"] = db.all(
        "SELECT p.id, p.name, i.date FROM guild_invites i JOIN players p ON p.id = i.player_id WHERE i.guild_id = %s ORDER BY i.date DESC", gid
    )
    g["wars"] = db.all(
        "SELECT w.*, (SELECT COUNT(*) FROM guildwar_kills k WHERE k.warid = w.id AND k.killerguild = w.guild1) AS kills1, "
        "(SELECT COUNT(*) FROM guildwar_kills k WHERE k.warid = w.id AND k.killerguild = w.guild2) AS kills2 "
        "FROM guild_wars w WHERE w.guild1 = %s OR w.guild2 = %s ORDER BY w.status = 1 DESC, w.id DESC LIMIT 20", gid, gid,
    )
    g["online"] = sum(1 for m in g["members"] if m["online"])
    return g


def free_players(q):
    """Players who are not in any guild, for adding or making a leader."""
    if len(q.strip()) < 2:
        return []
    return db.all(
        "SELECT p.id, p.name, p.level, p.vocation FROM players p LEFT JOIN guild_membership m ON m.player_id = p.id "
        "WHERE m.player_id IS NULL AND p.group_id < 6 AND p.name LIKE %s ORDER BY p.name LIMIT 20", f"%{q.strip()}%",
    )


def _rank(gid, level):
    r = db.one("SELECT id FROM guild_ranks WHERE guild_id = %s AND level = %s ORDER BY id LIMIT 1", gid, level)
    return r["id"] if r else None


def _in_guild(pid):
    return db.one("SELECT guild_id FROM guild_membership WHERE player_id = %s", pid)


def create(name, leader_pid):
    name = " ".join(name.split())
    if not NAME_RE.match(name):
        return None, "Nome da guild: 4 a 30 letras e espaços."
    if db.one("SELECT 1 AS x FROM guilds WHERE name = %s", name):
        return None, "Já existe uma guild com esse nome."
    p = db.one("SELECT id, name FROM players WHERE id = %s", leader_pid)
    if not p:
        return None, "Escolha o líder."
    if _in_guild(p["id"]):
        return None, f"{p['name']} já está em outra guild."
    gid = db.run("INSERT INTO guilds (name, ownerid, creationdata) VALUES (%s, %s, %s)", name, p["id"], int(time.time()))
    if not _rank(gid, 3):  # the schema trigger makes the three ranks; make them if it is missing
        for rname, level in (("The Leader", 3), ("Vice-Leader", 2), ("Member", 1)):
            db.run("INSERT INTO guild_ranks (guild_id, name, level) VALUES (%s, %s, %s)", gid, rname, level)
    db.run("INSERT INTO guild_membership (player_id, guild_id, rank_id) VALUES (%s, %s, %s)", p["id"], gid, _rank(gid, 3))
    db.run("DELETE FROM guild_invites WHERE player_id = %s", p["id"])
    return gid, f"Guild {name} criada com {p['name']} de líder."


def add_member(gid, pid, level=1):
    p = db.one("SELECT id, name FROM players WHERE id = %s", pid)
    if not p:
        return "Jogador não encontrado."
    if _in_guild(pid):
        return f"{p['name']} já está em uma guild."
    rank = _rank(gid, max(1, min(2, level)))
    db.run("INSERT INTO guild_membership (player_id, guild_id, rank_id) VALUES (%s, %s, %s)", pid, gid, rank)
    db.run("DELETE FROM guild_invites WHERE player_id = %s", pid)
    return ""


def remove_member(gid, pid):
    g = db.one("SELECT ownerid FROM guilds WHERE id = %s", gid)
    if g and g["ownerid"] == pid:
        return "Esse é o líder. Troque o líder antes de tirar."
    db.run("DELETE FROM guild_membership WHERE player_id = %s AND guild_id = %s", pid, gid)
    return ""


def set_member(gid, pid, rank_id, nick):
    g = db.one("SELECT ownerid FROM guilds WHERE id = %s", gid)
    rank = db.one("SELECT id, level FROM guild_ranks WHERE id = %s AND guild_id = %s", rank_id, gid)
    if not rank:
        return "Cargo inválido."
    if rank["level"] == 3 and g["ownerid"] != pid:
        return "Para pôr alguém como líder, use Tornar líder."
    if g["ownerid"] == pid and rank["level"] != 3:
        return "O líder continua líder. Passe a liderança antes."
    db.run("UPDATE guild_membership SET rank_id = %s, nick = %s WHERE player_id = %s AND guild_id = %s", rank["id"], nick.strip()[:15], pid, gid)
    return ""


def set_leader(gid, pid):
    g = db.one("SELECT ownerid FROM guilds WHERE id = %s", gid)
    m = db.one("SELECT 1 AS x FROM guild_membership WHERE player_id = %s AND guild_id = %s", pid, gid)
    if not g or not m:
        return "Só um membro da guild pode virar líder."
    if db.one("SELECT 1 AS x FROM guilds WHERE ownerid = %s AND id <> %s", pid, gid):
        return "Esse jogador já é líder de outra guild."
    db.run("UPDATE guild_membership SET rank_id = %s WHERE player_id = %s AND guild_id = %s", _rank(gid, 2), g["ownerid"], gid)
    db.run("UPDATE guild_membership SET rank_id = %s WHERE player_id = %s AND guild_id = %s", _rank(gid, 3), pid, gid)
    db.run("UPDATE guilds SET ownerid = %s WHERE id = %s", pid, gid)
    return ""


def rename_rank(gid, rank_id, name):
    name = " ".join(name.split())[:30]
    if len(name) < 2:
        return "Nome do cargo muito curto."
    db.run("UPDATE guild_ranks SET name = %s WHERE id = %s AND guild_id = %s", name, rank_id, gid)
    return ""


def add_rank(gid, name, level):
    name = " ".join(name.split())[:30]
    if len(name) < 2:
        return "Nome do cargo muito curto."
    db.run("INSERT INTO guild_ranks (guild_id, name, level) VALUES (%s, %s, %s)", gid, name, max(1, min(2, level)))
    return ""


def delete_rank(gid, rank_id):
    r = db.one("SELECT level, (SELECT COUNT(*) FROM guild_ranks x WHERE x.guild_id = %s AND x.level = r.level) AS same, "
               "(SELECT COUNT(*) FROM guild_membership m WHERE m.rank_id = r.id) AS n FROM guild_ranks r WHERE r.id = %s AND r.guild_id = %s",
               gid, rank_id, gid)
    if not r:
        return "Cargo não encontrado."
    if r["n"]:
        return "Tem gente nesse cargo. Mude eles antes."
    if r["same"] <= 1:
        return "Cada nível (líder, vice, membro) precisa de pelo menos um cargo."
    db.run("DELETE FROM guild_ranks WHERE id = %s", rank_id)
    return ""


def rename(gid, name):
    name = " ".join(name.split())
    if not NAME_RE.match(name):
        return "Nome da guild: 4 a 30 letras e espaços."
    if db.one("SELECT 1 AS x FROM guilds WHERE name = %s AND id <> %s", name, gid):
        return "Já existe uma guild com esse nome."
    db.run("UPDATE guilds SET name = %s WHERE id = %s", name, gid)
    db.run("UPDATE guild_wars SET name1 = %s WHERE guild1 = %s", name, gid)
    db.run("UPDATE guild_wars SET name2 = %s WHERE guild2 = %s", name, gid)
    return ""


def declare_war(gid, other, frags, days):
    a, b = db.one("SELECT id, name FROM guilds WHERE id = %s", gid), db.one("SELECT id, name FROM guilds WHERE id = %s", other)
    if not a or not b or a["id"] == b["id"]:
        return "Escolha a outra guild."
    if db.one("SELECT 1 AS x FROM guild_wars WHERE status = 1 AND ((guild1 = %s AND guild2 = %s) OR (guild1 = %s AND guild2 = %s))", gid, other, other, gid):
        return "Essas duas já estão em guerra."
    db.run(
        "INSERT INTO guild_wars (guild1, guild2, name1, name2, status, started, frags_limit, duration_days) VALUES (%s, %s, %s, %s, 1, %s, %s, %s)",
        a["id"], b["id"], a["name"], b["name"], int(time.time()), max(0, min(1000, frags)), max(0, min(60, days)),
    )
    return ""


def end_war(gid, war_id):
    db.run("UPDATE guild_wars SET status = 4, ended = %s WHERE id = %s AND (guild1 = %s OR guild2 = %s) AND status IN (0, 1)",
           int(time.time()), war_id, gid, gid)
    return ""

"""Mini-games run by the Lua bridge (data/scripts/globalevents/cockpit_<kind>.lua).

The panel picks the arena, who plays and the prize, writes a row in `cockpit_events` and queues
`event_start`; the game writes back when it starts and who won. Ready-made setups are presets,
which the Agenda can start on a schedule.
"""

import re

from . import db

KINDS = {
    "zombie": ("🧟 Zombie", "Zombies caçam a turma na arena. Encostou, saiu. Quem sobrar por último ganha.", True),
    "snowball": ("❄ Bolas de neve", "Guerra de bolas de neve em times.", False),
    "ctf": ("🚩 Capture a bandeira", "Dois times, uma bandeira de cada lado.", False),
    "battlefield": ("⚔ Battlefield", "Time contra time até sobrar um.", False),
    "quiz": ("❓ Quiz", "Perguntas no chat, quem responde primeiro pontua.", False),
}
DEFAULTS = {"radius": 8, "minutes": 5, "first": 2, "every": 30, "speed": 100, "gold": 0}
NAME_OK = re.compile(r"^[^|;=]{2,30}$")  # names travel inside the command text


def clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def settings_from(f):
    return {
        "radius": clamp(f.get("raio"), 4, 30, DEFAULTS["radius"]),
        "minutes": clamp(f.get("minutos"), 1, 30, DEFAULTS["minutes"]),
        "first": clamp(f.get("iniciais"), 1, 20, DEFAULTS["first"]),
        "every": clamp(f.get("a_cada"), 5, 300, DEFAULTS["every"]),
        "speed": clamp(f.get("velocidade"), 0, 400, DEFAULTS["speed"]),
        "kit_id": clamp(f.get("kit"), 0, 10**9, 0),
        "gold": clamp(f.get("gold"), 0, 100_000_000, 0),
    }


def prize_text(kit_id):
    kit = db.one("SELECT items FROM cockpit_kits WHERE id = %s", kit_id) if kit_id else None
    return kit["items"] if kit else ""


def start(actor, kind, x, y, z, s, names, label=""):
    """Queue one event; returns (ok, message)."""
    names = [n for n in dict.fromkeys(names) if NAME_OK.match(n)][:50]
    if kind not in KINDS or not KINDS[kind][2]:
        return False, "Esse evento ainda não existe."
    if not names:
        return False, "Ninguém online para jogar."
    if db.one("SELECT id FROM cockpit_events WHERE status IN ('queued', 'running') AND kind = %s", kind):
        return False, "Já tem um evento desses rolando. Pare antes de começar outro."
    eid = db.run("INSERT INTO cockpit_events (kind, name, started_at, status, players, created_by) VALUES (%s,%s,UNIX_TIMESTAMP(),'queued',%s,%s)",
                 kind, label or KINDS[kind][0], ", ".join(names), actor)
    text = (f"id={eid};kind={kind};players={'|'.join(names)};seconds={s['minutes'] * 60};first={s['first']};"
            f"every={s['every']};speed={s['speed']};prize={prize_text(s['kit_id'])};gold={s['gold']}")
    db.enqueue(actor, "event_start", "", x, y, z, s["radius"], text=text)
    return True, f"{KINDS[kind][0]} começando com {len(names)} jogador(es)."


def stop(actor, kind):
    db.run("UPDATE cockpit_events SET status = 'done', ended_at = UNIX_TIMESTAMP(), details = 'cancelado antes de começar' "
           "WHERE kind = %s AND status = 'queued'", kind)
    db.enqueue(actor, "event_stop", text=kind)


def run_preset(actor, preset_id, resolve):
    p = db.one("SELECT * FROM cockpit_event_presets WHERE id = %s", preset_id)
    if not p:
        return False, "Evento pronto não encontrado."
    return start(actor, p["kind"], p["x"], p["y"], p["z"], p, [n for n in resolve(p["alvo"]) if is_online(n)], p["name"])


def is_online(name):
    return bool(db.one("SELECT 1 AS x FROM cockpit_online WHERE name = %s", name))

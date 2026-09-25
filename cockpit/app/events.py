"""Mini-games run by the Lua bridge (data/scripts/globalevents/cockpit_<kind>.lua).

The panel picks the arena, who plays and the prize, writes a row in `cockpit_events` and queues
`event_start`; the game writes back when it starts and who won. Ready-made setups are presets,
which the Agenda can start on a schedule.
"""

import re

from . import db

KINDS = {
    "zombie": ("🧟 Zombie", "Zombies caçam a turma na arena. Encostou, saiu. Quem sobrar por último ganha.", True),
    "snowball": ("❄ Bolas de neve", "Cada um diz !bola para jogar na direção em que está virado. Acerto vale ponto e congela o alvo.", True),
    "ctf": ("🚩 Capture a bandeira", "Vermelho a oeste, azul a leste. Pise na base inimiga, traga a bandeira para a sua.", True),
    "battlefield": ("⚔ Battlefield", "Vermelho contra azul, luta de verdade, ninguém morre: cada queda gasta uma vida.", True),
    "quiz": ("❓ Quiz", "Perguntas do banco do painel; responde com !r. Não leva ninguém para arena.", True),
}
NO_ARENA = {"quiz"}
# kind-specific settings: key -> (label, lo, hi, default, help)
FIELDS = {
    "zombie": {
        "first": ("Zombies no início", 1, 20, 2, ""),
        "every": ("+1 zombie a cada (s)", 5, 300, 30, ""),
        "speed": ("Velocidade extra", 0, 400, 100, ""),
    },
    "snowball": {
        "ammo": ("Bolas por jogador", 1, 50, 10, "Quantas cabem na mão."),
        "reload": ("+1 bola a cada (s)", 1, 60, 4, ""),
        "freeze": ("Congela o alvo (s)", 0, 10, 2, "0 = não congela."),
        "teams": ("Times (1 = vermelho × azul, 0 = todos contra todos)", 0, 1, 1, ""),
    },
    "ctf": {
        "caps": ("Capturas para vencer", 1, 20, 3, ""),
    },
    "battlefield": {
        "lives": ("Vidas por jogador", 1, 10, 2, "Em mundo sem PvP, o jogo vira PvP enquanto o evento roda."),
    },
    "quiz": {
        "questions": ("Perguntas", 1, 50, 10, "Sorteadas do banco abaixo."),
        "answer": ("Tempo por pergunta (s)", 10, 120, 30, ""),
    },
}
DEFAULTS = {"radius": 8, "minutes": 5, "gold": 0}
NAME_OK = re.compile(r"^[^|;=]{2,30}$")  # names travel inside the command text


def clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def settings_from(f, kind="zombie"):
    s = {
        "radius": clamp(f.get("raio"), 4, 30, DEFAULTS["radius"]),
        "minutes": clamp(f.get("minutos"), 1, 60, DEFAULTS["minutes"]),
        "kit_id": clamp(f.get("kit"), 0, 10**9, 0),
        "gold": clamp(f.get("gold"), 0, 100_000_000, 0),
    }
    s["extra"] = {k: clamp(f.get(k), lo, hi, d) for k, (_, lo, hi, d, _) in FIELDS.get(kind, {}).items()}
    s["extra"]["trophy"] = 1 if f.get("trofeu") else 0
    return s


def extra_text(extra):
    return ";".join(f"{k}={v}" for k, v in extra.items())


def parse_extra(text, kind):
    raw = dict(part.split("=", 1) for part in (text or "").split(";") if "=" in part)
    extra = {k: clamp(raw.get(k), lo, hi, d) for k, (_, lo, hi, d, _) in FIELDS.get(kind, {}).items()}
    extra["trophy"] = clamp(raw.get("trophy"), 0, 1, 0)
    return extra


def preset_settings(p):
    extra = parse_extra(p.get("extra"), p["kind"])
    if p["kind"] == "zombie" and not p.get("extra"):  # presets saved before `extra` existed
        extra = {"first": p["first"], "every": p["every"], "speed": p["speed"], "trophy": 0}
    return {"radius": p["radius"], "minutes": p["minutes"], "kit_id": p["kit_id"], "gold": p["gold"], "extra": extra}


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
    text = (f"id={eid};kind={kind};players={'|'.join(names)};seconds={s['minutes'] * 60};"
            f"prize={prize_text(s['kit_id'])};gold={s['gold']};{extra_text(s['extra'])}")
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
    return start(actor, p["kind"], p["x"], p["y"], p["z"], preset_settings(p), [n for n in resolve(p["alvo"]) if is_online(n)], p["name"])


def is_online(name):
    return bool(db.one("SELECT 1 AS x FROM cockpit_online WHERE name = %s", name))


# ---------------------------------------------------------------- quiz question bank

QUIZ_SEED = [
    ("Qual cidade é a capital do reino do rei Tibianus?", "Thais", "cidades"),
    ("Qual NPC é o rei de Thais?", "Tibianus|King Tibianus|Rei Tibianus", "npcs"),
    ("Qual a capital dos anões?", "Kazordoon|Kazz", "cidades"),
    ("Em que cidade fica o grande templo dos elfos?", "Ab'Dendriel|Ab Dendriel|Abdendriel", "cidades"),
    ("Quantas vocações existem sem contar a promoção?", "5|cinco", "vocacoes"),
    ("Qual vocação usa rods?", "Druid|Druida", "vocacoes"),
    ("Qual vocação usa wands?", "Sorcerer|Feiticeiro", "vocacoes"),
    ("Qual vocação é a especialista em distância?", "Paladin|Paladino", "vocacoes"),
    ("Qual a vocação nova que luta com os punhos?", "Monk|Monge", "vocacoes"),
    ("Qual a palavra da magia de cura mais básica?", "exura", "magias"),
    ("Qual a magia para criar comida?", "exevo pan", "magias"),
    ("Qual a magia de luz mais simples?", "utevo lux", "magias"),
    ("Qual a magia de haste?", "utani hur", "magias"),
    ("Qual criatura dá o famoso 'Hydra Egg'?", "Hydra", "criaturas"),
    ("Qual o nome do dragão vermelho mais forte que o Dragon?", "Dragon Lord", "criaturas"),
    ("Qual criatura de Rookgaard carrega um machado, vive em cavernas e fala 'Grrrr'?", "Troll", "criaturas"),
    ("Qual a moeda que vale 100 gold coins?", "Platinum Coin|Platinum", "itens"),
    ("Qual a moeda que vale 10.000 gold coins?", "Crystal Coin|Crystal", "itens"),
    ("Qual item deixa ver os andares de baixo e de cima usando-o?", "Rope|corda", "itens"),
    ("Qual item serve para abrir buracos tampados no chão?", "Shovel|pa", "itens"),
    ("Qual o nome da ilha inicial para iniciantes?", "Rookgaard|Rook", "cidades"),
    ("Qual o nome do continente principal do Tibia?", "Tibia", "lore"),
    ("Qual o nome da cidade que fica no deserto?", "Darashia|Ankrahmun", "cidades"),
    ("Qual cidade é famosa pelos piratas e pela Liberty Bay?", "Liberty Bay", "cidades"),
    ("Qual o nome do servidor em que você está jogando?", "VinOT", "vinot"),
    ("Como se chama o Mestre do VinOT?", "Vinot", "vinot"),
    ("Qual o nome do painel do Mestre do VinOT?", "Cockpit", "vinot"),
]


def seed_quiz():
    if db.one("SELECT 1 AS x FROM cockpit_quiz LIMIT 1"):
        return
    for q, a, t in QUIZ_SEED:
        db.run("INSERT INTO cockpit_quiz (question, answers, topic) VALUES (%s, %s, %s)", q, a, t)


def quiz_all():
    return db.all("SELECT * FROM cockpit_quiz ORDER BY topic, id")


def quiz_save(qid, question, answers, topic):
    question = " ".join(str(question).split())[:255]
    answers = "|".join(a.strip() for a in str(answers).split("|") if a.strip())[:255]
    topic = " ".join(str(topic).split()).lower()[:32]
    if len(question) < 5 or not answers:
        return "Escreva a pergunta e pelo menos uma resposta."
    if qid:
        db.run("UPDATE cockpit_quiz SET question = %s, answers = %s, topic = %s WHERE id = %s", question, answers, topic, qid)
    else:
        db.run("INSERT INTO cockpit_quiz (question, answers, topic) VALUES (%s, %s, %s)", question, answers, topic)
    return ""

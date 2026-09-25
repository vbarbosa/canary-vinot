"""World settings: config.lua switches and XP/skill/magic stages, changed from the panel without a restart.

The panel stores them in `cockpit_settings` (keys `world.*`) and queues `apply_world`. The Lua bridge then
writes cockpit-world.lua next to config.lua (config.lua loads it last, so its values win), reloads the
config and rebuilds the stage tables. The list below is the whole allowlist: nothing else is written.
"""

import re

from . import db

# key -> (kind, label, help, default). Defaults are the approved "just switch it on" pack.
SWITCHES = {
    "autoLoot": ("bool", "Autoloot", "O loot vai direto para a mochila, sem abrir o corpo.", True),
    "staminaPz": ("bool", "Stamina na cidade", "Quem fica em área protegida recupera stamina.", True),
    "staminaTrainer": ("bool", "Stamina no treino", "Quem treina em dummy também recupera stamina.", True),
    "toggleTravelsFree": ("bool", "Viagens grátis", "Barcos, tapetes e outras viagens de NPC não cobram.", True),
    "toggleFreeQuest": ("bool", "Acessos de quest liberados", "Libera os acessos e portas das quests principais sem precisar fazer tudo antes.", True),
    "partyShareLootBoosts": ("bool", "Loot boost dividido na party", "Boosts de loot (prey, charms) valem para a party toda.", True),
    "rateUseStages": ("bool", "Rates por nível", "Usa as tabelas de estágios abaixo. Desligado, vale a rate fixa.", True),
    "toggleServerIsRetroPVP": ("bool", "Retro PvP", "PvP das antigas: sem proteção de party e sem modo seguro avançado.", False),
}
WORLD_TYPES = {"no-pvp": "Sem PvP (ninguém ataca ninguém)", "pvp": "PvP normal (com skull e punição)",
               "pvp-enforced": "PvP livre (sem skull, vale tudo)"}
NUMBERS = {
    "protectionLevel": ("Proteção até o nível", "Abaixo desse nível ninguém pode ser atacado por jogador.", 1, 1000, 7),
    "pzLockedSeconds": ("Tempo de PZ lock (s)", "Quanto tempo fica sem entrar em área protegida depois de atacar alguém.", 0, 3600, 60),
}
RATES = {
    "rateExp": ("XP fixa", 1),
    "rateSkill": ("Skill fixa", 1),
    "rateMagic": ("Magic level fixo", 1),
    "rateLoot": ("Loot", 1),
}
STAGES = {
    "experienceStages": ("XP por nível", "1-50:10,51-100:6,101-150:4,151-:2"),
    "skillsStages": ("Skills por nível de skill", "1-:1"),
    "magicLevelStages": ("Magic level por nível", "0-:1"),
}
STAGE_RE = re.compile(r"^(\d{1,4})-(\d{0,4}):(\d{1,3})$")


def parse_stages(text):
    """'1-50:10,51-:2' -> [(1, 50, 10), (51, None, 2)], or None if it does not make sense."""
    out = []
    for part in [p.strip() for p in str(text).split(",") if p.strip()]:
        m = STAGE_RE.match(part)
        if not m:
            return None
        lo, hi, mult = int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3))
        if (hi is not None and hi < lo) or mult < 1:
            return None
        out.append((lo, hi, mult))
    out.sort()
    return out or None


def format_stages(rows):
    return ",".join(f"{lo}-{hi if hi is not None else ''}:{m}" for lo, hi, m in rows)


def load():
    saved = {r["k"][6:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'world.%%'")}
    s = {"saved": bool(saved), "applied_at": int(saved.get("_applied") or 0)}
    for k, (_, _, _, default) in SWITCHES.items():
        s[k] = saved[k] == "1" if k in saved else default
    for k, (_, default) in RATES.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    s["worldType"] = saved.get("worldType") if saved.get("worldType") in WORLD_TYPES else "pvp"
    for k, (*_, default) in NUMBERS.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    for k, (_, default) in STAGES.items():
        s[k] = parse_stages(saved.get(k, default)) or parse_stages(default)
    return s


def save(values):
    """Store validated values; returns an error message or ''."""
    rows = {}
    for k in SWITCHES:
        rows[k] = "1" if values.get(k) else "0"
    for k in RATES:
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not 1 <= int(v) <= 100:
            return f"{RATES[k][0]}: use um número de 1 a 100."
        rows[k] = v
    if values.get("worldType") not in WORLD_TYPES:
        return "Escolha o tipo de mundo."
    rows["worldType"] = values["worldType"]
    for k, (label, _, lo, hi, _) in NUMBERS.items():
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not lo <= int(v) <= hi:
            return f"{label}: use um número de {lo} a {hi}."
        rows[k] = v
    for k, (label, _) in STAGES.items():
        parsed = parse_stages(values.get(k, ""))
        if not parsed or any(m > 100 for _, _, m in parsed):
            return f"{label}: confira as faixas (nível inicial, final e multiplicador de 1 a 100)."
        rows[k] = format_stages(parsed)
    for k, v in rows.items():
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"world.{k}", v)
    return ""


def apply(actor):
    db.run("INSERT INTO cockpit_settings (k, v) VALUES ('world._applied', UNIX_TIMESTAMP()) ON DUPLICATE KEY UPDATE v = VALUES(v)")
    return db.enqueue(actor, "apply_world", text="ajustes do mundo")


def seed(actor="cockpit"):
    """First run: store the approved pack and send it to the game once."""
    if db.one("SELECT 1 AS x FROM cockpit_settings WHERE k LIKE 'world.%%' LIMIT 1"):
        return
    s = load()
    save({**{k: s[k] for k in SWITCHES}, **{k: s[k] for k in RATES}, **{k: s[k] for k in NUMBERS}, "worldType": s["worldType"],
          **{k: format_stages(s[k]) for k in STAGES}})
    apply(actor)


def last_result():
    return db.one("SELECT status, result, done_at, created_at FROM cockpit_commands WHERE action = 'apply_world' ORDER BY id DESC LIMIT 1")

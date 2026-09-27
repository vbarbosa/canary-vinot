"""World settings: config.lua switches and XP/skill/magic stages, changed from the panel without a restart.

The panel stores them in `cockpit_settings` (keys `world.*`) and queues `apply_world`. The Lua bridge then
writes cockpit-world.lua next to config.lua (config.lua loads it last, so its values win), reloads the
config and rebuilds the stage tables. The list below is the whole allowlist: nothing else is written.
"""

import datetime as dt
import re
import unicodedata
from zoneinfo import ZoneInfo

from . import db

# key -> (kind, label, help, default). Defaults are the approved "just switch it on" pack.
SWITCHES = {
    "autoLoot": ("bool", "Autoloot", "O loot vai direto para a mochila, sem abrir o corpo.", True),
    "staminaPz": ("bool", "Stamina na cidade", "Quem fica em área protegida recupera stamina.", True),
    "staminaTrainer": ("bool", "Stamina no treino", "Quem treina em dummy também recupera stamina.", True),
    "staminaCutsXp": ("bool", "Stamina zerada corta XP", "Como no Tibia oficial: com a stamina em zero, o personagem para de ganhar experiência (continua jogando normal).", True),
    "toggleTravelsFree": ("bool", "Viagens grátis", "Barcos, tapetes e outras viagens de NPC não cobram.", True),
    "toggleFreeQuest": ("bool", "Acessos de quest liberados", "Libera os acessos e portas das quests principais sem precisar fazer tudo antes.", True),
    "partyShareLootBoosts": ("bool", "Loot boost dividido na party", "Boosts de loot (prey, charms) valem para a party toda.", True),
    "rateUseStages": ("bool", "Rates por nível", "Usa as tabelas de estágios abaixo. Desligado, vale a rate fixa.", True),
    "toggleServerIsRetroPVP": ("bool", "Retro PvP", "PvP das antigas: sem proteção de party e sem modo seguro avançado.", False),
    "preySystemEnabled": ("bool", "Sistema de Prey", "Sistema oficial do Tibia: escolhe até 3 criaturas pra ganhar bônus de XP, loot ou dano nelas.", True),
    "preyFreeThirdSlot": ("bool", "3º slot de Prey grátis", "Sem isso, o 3º slot de Prey só libera pra quem é premium.", False),
    "taskHuntingSystemEnabled": ("bool", "Sistema de Task Hunting", "Sistema oficial do Tibia: mata um número de criaturas escolhidas pra ganhar recompensa.", True),
    "taskHuntingFreeThirdSlot": ("bool", "3º slot de Task Hunting grátis", "Sem isso, o 3º slot só libera pra quem é premium.", False),
    "vipSystemEnabled": ("bool", "Sistema VIP (bônus de doador)", "Liga os bônus de XP/loot/skill abaixo para contas VIP, além do premium normal.", False),
    "vipAutoLootVipOnly": ("bool", "Autoloot só pra VIP", "Com 'Sistema VIP' ligado, restringe o autoloot a quem é VIP.", False),
    "experienceByKillingPlayers": ("bool", "Ganha XP matando jogador", "Como no PvP Enforced oficial: dá XP por matar outro jogador, dentro da faixa de nível do campo abaixo.", False),
}
# Stamina: mesmo padrão do Tibia oficial (referência usada pelos servidores OT bem avaliados),
# com tudo parametrizável. Faixas: verde (bônus), normal, vermelha (penalidade), preta (0 = corta XP se staminaCutsXp).
STAMINA = {
    "staminaMaxMinutes": ("Stamina máxima (minutos)", "Teto da stamina. Padrão Tibia: 2520 (42h).", 60, 6000, 2520),
    "staminaGreenMinutes": ("Início da faixa verde (minutos)", "Acima disso, quem é premium ganha o bônus de XP. Padrão Tibia: 2340 (39h).", 0, 6000, 2340),
    "staminaGreenBonusPercent": ("Bônus da faixa verde (%)", "100 = XP normal. Padrão Tibia: 150 (1,5x), só para premium.", 100, 300, 150),
    "staminaLowMinutes": ("Fim da faixa vermelha (minutos)", "Nessa stamina ou abaixo, o XP fica reduzido. Padrão Tibia: 840 (14h).", 0, 6000, 840),
    "staminaLowBonusPercent": ("XP na faixa vermelha (%)", "100 = XP normal. Padrão Tibia: 50 (metade).", 10, 100, 50),
    "staminaDrainRatePercent": ("Velocidade de gasto (%)", "100 = gasta 1 minuto de stamina por minuto jogado (padrão Tibia). Mais alto gasta mais rápido.", 10, 500, 100),
    "staminaGreenDelay": ("Recarga na cidade, faixa verde (min a cada X min)", "De quanto em quanto tempo recupera estando na faixa verde e em área protegida.", 1, 60, 5),
    "staminaOrangeDelay": ("Recarga na cidade, faixa normal (min a cada X min)", "De quanto em quanto tempo recupera nas outras faixas e em área protegida.", 1, 60, 1),
    "staminaPzGain": ("Quanto recupera por vez na cidade", "Minutos de stamina ganhos a cada recarga em área protegida.", 1, 60, 1),
    "staminaTrainerDelay": ("Recarga no treino (min a cada X min)", "De quanto em quanto tempo recupera treinando no dummy.", 1, 60, 5),
    "staminaTrainerGain": ("Quanto recupera por vez no treino", "Minutos de stamina ganhos a cada recarga no dummy.", 1, 60, 1),
}
# Prey e Task Hunting: sistemas oficiais do Tibia (padrão dos OTs bem avaliados), preço/tempo parametrizáveis.
HUNTING = {
    "preyBonusTime": ("Duração do bônus de Prey (segundos)", "Padrão Tibia: 7200 (2 horas).", 600, 86400, 7200),
    "preyFreeRerollTime": ("Espera pra lista de Prey grátis de novo (segundos)", "Padrão Tibia: 72000 (20 horas).", 3600, 604800, 72000),
    "preyRerollPricePerLevel": ("Preço de reroll de Prey (gold por nível)", "Multiplica pelo nível do personagem.", 0, 10000, 200),
    "preySelectListPrice": ("Preço pra travar criatura na Prey (gold)", "", 0, 10000, 5),
    "preyBonusRerollPrice": ("Preço pra trocar o tipo de bônus da Prey", "Também ativa o reroll automático.", 0, 10000, 1),
    "taskHuntingLimitedTasksExhaust": ("Espera pra nova criatura na Task Hunting (segundos)", "Depois de resgatar a recompensa. Padrão Tibia: 72000 (20 horas).", 600, 604800, 72000),
    "taskHuntingRerollPricePerLevel": ("Preço de reroll de Task Hunting (gold por nível)", "Multiplica pelo nível do personagem.", 0, 10000, 200),
    "taskHuntingSelectListPrice": ("Preço pra travar criatura na Task Hunting (gold)", "", 0, 10000, 5),
    "taskHuntingBonusRerollPrice": ("Preço pra trocar o bônus da Task Hunting", "", 0, 10000, 1),
    "taskHuntingFreeRerollTime": ("Espera pra lista de Task Hunting grátis de novo (segundos)", "Padrão Tibia: 72000 (20 horas).", 3600, 604800, 72000),
}
# Bônus de doador (sistema VIP, separado do premium normal). Zero desliga cada bônus.
VIP_BONUS = {
    "vipBonusExp": ("Bônus de XP pra VIP (%)", "0 desliga. Só vale com 'Sistema VIP' ligado.", 0, 100, 0),
    "vipBonusLoot": ("Bônus de loot pra VIP (%)", "0 desliga. Só vale com 'Sistema VIP' ligado.", 0, 100, 0),
    "vipBonusSkill": ("Bônus de skill pra VIP (%)", "0 desliga. Só vale com 'Sistema VIP' ligado.", 0, 100, 0),
}
# Skull e frag: sistema oficial do Tibia. Os tempos aqui usam minutos/horas/dias (o bridge converte pro
# formato em milissegundos que o config.lua espera nas duas primeiras chaves).
PVP_SKULL = {
    "fragsDecreaseHours": ("Tempo pra perder 1 frag (horas)", "Padrão Tibia: 24 (1 dia).", 1, 168, 24),
    "whiteSkullMinutes": ("Duração da skull branca (minutos)", "Fica com o ícone até esse tempo passar sem atacar de novo. Padrão Tibia: 15.", 1, 1440, 15),
    "dayKillsToRedSkull": ("Frags no dia pra virar skull vermelha", "Padrão Tibia: 3.", 1, 100, 3),
    "weekKillsToRedSkull": ("Frags na semana pra virar skull vermelha", "Padrão Tibia: 5.", 1, 100, 5),
    "monthKillsToRedSkull": ("Frags no mês pra virar skull vermelha", "Padrão Tibia: 10.", 1, 100, 10),
    "redSkullDuration": ("Duração da skull vermelha (dias)", "", 1, 365, 1),
    "blackSkullDuration": ("Duração da skull preta (dias)", "", 1, 365, 3),
    "orangeSkullDuration": ("Duração da skull laranja (dias)", "", 1, 365, 7),
    "expFromPlayersLevelRange": ("Faixa de nível pra XP matando jogador (%)", "Só ganha XP de PvP se o alvo estiver dentro dessa % do seu nível. Padrão Tibia: 75.", 0, 200, 75),
}
WORLD_TYPES = {"no-pvp": "Sem PvP (ninguém ataca ninguém)", "pvp": "PvP normal (com skull e punição)",
               "pvp-enforced": "PvP livre (sem skull, vale tudo)"}
NUMBERS = {
    "protectionLevel": ("Proteção até o nível", "Abaixo desse nível ninguém pode ser atacado por jogador.", 1, 1000, 7),
    "pzLockedSeconds": ("Tempo de PZ lock (s)", "Quanto tempo fica sem entrar em área protegida depois de atacar alguém.", 0, 3600, 60),
}
# Perda de XP/skill ao morrer. -1 usa a fórmula oficial do Tibia (a mesma referência dos OTs bem avaliados:
# quanto mais alto o nível, menor o % perdido); 0 desliga a perda; bênçãos e promoção reduzem ainda mais em qualquer caso.
DEATH_LOSE_MIN, DEATH_LOSE_MAX, DEATH_LOSE_DEFAULT = -1, 100, -1
DEATH_LOSE_LABEL = "Perda de XP/skill ao morrer (%)"
DEATH_LOSE_HELP = "-1 = fórmula oficial do Tibia (recomendado). 0 = sem perda nenhuma. Bênçãos e promoção reduzem ainda mais."
# Text shown to players. Accents become plain letters (the game client does not always show them) and quotes go.
TEXTS = {
    "serverName": ("Nome do servidor", "Aparece no jogo e no status. Na lista de personagens quem manda é o login (veja a nota).", 30, "VinOT"),
    "serverMotd": ("Mensagem do dia", "Mensagem do servidor para o cliente.", 200, "Bem-vindo ao VinOT, o mundo do Vinot!"),
    "welcome": ("Boas-vindas no jogo", "Aparece no meio da tela toda vez que alguém entra.", 200, "Bem-vindo ao VinOT! Aqui quem manda e o Vinot. Bom jogo!"),
    "signText": ("Texto da estátua do Vinot", "Aparece quando alguém dá look na estátua do templo. Vazio = sem estátua.", 200,
                 "Estatua do Vinot, o Mestre deste mundo. Que seus loots sejam gordos e suas mortes poucas."),
}
SIGN_RE = re.compile(r"^\d{1,5},\d{1,5},\d{1,2}$")


def plain_text(text, limit):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return " ".join(text.replace('"', "").replace("\\", "").split())[:limit]


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
    for k, (*_, default) in STAMINA.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    for k, (*_, default) in HUNTING.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    for k, (*_, default) in VIP_BONUS.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    for k, (*_, default) in PVP_SKULL.items():
        s[k] = int(saved[k]) if saved.get(k, "").isdigit() else default
    dv = saved.get("deathLosePercent", "")
    s["deathLosePercent"] = int(dv) if dv.lstrip("-").isdigit() else DEATH_LOSE_DEFAULT
    for k, (_, default) in STAGES.items():
        s[k] = parse_stages(saved.get(k, default)) or parse_stages(default)
    for k, (*_, default) in TEXTS.items():
        s[k] = saved.get(k, default)
    s["signPos"] = saved.get("signPos", "")
    s["signAt"] = saved.get("_signAt", "")
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
    for k, (label, _, lo, hi, _) in STAMINA.items():
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not lo <= int(v) <= hi:
            return f"{label}: use um número de {lo} a {hi}."
        rows[k] = v
    if not int(rows["staminaLowMinutes"]) < int(rows["staminaGreenMinutes"]) < int(rows["staminaMaxMinutes"]):
        return "Stamina: a faixa vermelha tem que ser menor que a verde, e a verde menor que a máxima."
    for k, (label, _, lo, hi, _) in HUNTING.items():
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not lo <= int(v) <= hi:
            return f"{label}: use um número de {lo} a {hi}."
        rows[k] = v
    for k, (label, _, lo, hi, _) in VIP_BONUS.items():
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not lo <= int(v) <= hi:
            return f"{label}: use um número de {lo} a {hi}."
        rows[k] = v
    for k, (label, _, lo, hi, _) in PVP_SKULL.items():
        v = str(values.get(k, "")).strip()
        if not v.isdigit() or not lo <= int(v) <= hi:
            return f"{label}: use um número de {lo} a {hi}."
        rows[k] = v
    dv = str(values.get("deathLosePercent", "")).strip()
    if not dv.lstrip("-").isdigit() or not DEATH_LOSE_MIN <= int(dv) <= DEATH_LOSE_MAX:
        return f"{DEATH_LOSE_LABEL}: use um número de {DEATH_LOSE_MIN} a {DEATH_LOSE_MAX}."
    rows["deathLosePercent"] = dv
    for k, (label, _, limit, _) in TEXTS.items():
        rows[k] = plain_text(values.get(k, ""), limit)
    if not rows["serverName"]:
        return "Dê um nome para o servidor."
    pos = str(values.get("signPos", "")).replace(" ", "")
    if pos and not SIGN_RE.match(pos):
        return "Lugar da estátua: use x,y,z (ex.: 32369,32241,7) ou deixe vazio para perto do templo de Thais."
    rows["signPos"] = pos
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
        # settings added in a later version: store their defaults once and apply
        missing = [k for k in TEXTS if not db.one("SELECT 1 AS x FROM cockpit_settings WHERE k = %s", f"world.{k}")]
        for k in missing:
            db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s)", f"world.{k}", TEXTS[k][3])
        if missing:
            apply(actor)
        return
    s = load()
    save({**{k: s[k] for k in SWITCHES}, **{k: s[k] for k in RATES}, **{k: s[k] for k in NUMBERS}, **{k: s[k] for k in STAMINA},
          **{k: s[k] for k in HUNTING}, **{k: s[k] for k in VIP_BONUS}, **{k: s[k] for k in PVP_SKULL},
          "deathLosePercent": s["deathLosePercent"], "worldType": s["worldType"],
          **{k: s[k] for k in TEXTS}, "signPos": "",
          **{k: format_stages(s[k]) for k in STAGES}})
    apply(actor)


def last_result():
    return db.one("SELECT status, result, done_at, created_at FROM cockpit_commands WHERE action = 'apply_world' ORDER BY id DESC LIMIT 1")


# ---------------------------------------------------------------- map pending (Remere's -> git -> deploy)
# cockpit/deploy/auto-deploy.sh writes map.pending_* into cockpit_settings when a pull touches the
# custom map (world/custom/*.otbm and its house/monster/npc/zone XMLs). The panel shows it here until
# someone clicks "carregar novo mapa" (load_new_map action in main.py), which restarts the game and
# clears the flag; the custom map is only (re)loaded when the game process starts.


def map_pending():
    saved = {r["k"][4:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'map.%%'")}
    if not saved.get("pending_sha"):
        return None
    return {"sha": saved["pending_sha"][:7], "at": int(saved.get("pending_at") or 0), "files": saved.get("pending_files", "")}


def clear_map_pending():
    db.run("DELETE FROM cockpit_settings WHERE k LIKE 'map.pending_%%'")


# ---------------------------------------------------------------- daily server save
# The game's global_server_save.lua: warns N minutes before, then (optionally) cleans the floor and shuts the game down,
# which saves everything; docker brings it back up. The time is the game container's clock (UTC); the panel shows Brasília.
SAVE_DEFAULTS = {"globalServerSaveShutdown": "1", "globalServerSaveTime": "06:00:00", "globalServerSaveNotifyDuration": "5",
                 "globalServerSaveCleanMap": "0"}
SAVE_TZ = "America/Sao_Paulo"


def _shift(hhmm, to_utc):
    h, m = (int(x) for x in hhmm.split(":")[:2])
    br, utc = ZoneInfo(SAVE_TZ), dt.timezone.utc
    day = dt.date.today()
    src = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=br if to_utc else utc)
    out = src.astimezone(utc if to_utc else br)
    return out.strftime("%H:%M")


def save_settings():
    saved = {r["k"][6:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'world.globalServerSave%%'")}
    s = {k: saved.get(k, v) for k, v in SAVE_DEFAULTS.items()}
    s["local_time"] = _shift(s["globalServerSaveTime"], to_utc=False)
    return s


def store_save(on, local_time, notify, clean):
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", local_time or ""):
        return "Horário: use HH:MM (ex.: 06:00)."
    try:
        notify = max(1, min(60, int(notify)))
    except (TypeError, ValueError):
        return "Aviso: minutos de 1 a 60."
    rows = {"globalServerSaveShutdown": "1" if on else "0", "globalServerSaveTime": _shift(local_time, to_utc=True) + ":00",
            "globalServerSaveNotifyDuration": str(notify), "globalServerSaveCleanMap": "1" if clean else "0"}
    for k, v in rows.items():
        db.run("INSERT INTO cockpit_settings (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", f"world.{k}", v)
    return ""

"""VinOT Wiki data, read straight from the game files so it always matches the server.

- Creatures: every data-otservbr-global/monster/**/*.lua (the `monster.*` tables).
- Items: data/items/items.xml (names, attributes) plus "who drops it" from the creature loot.
- Rates: the Cockpit's world settings (cockpit_settings `world.*`), falling back to data/stages.lua.

Files are re-read when any of them changes (checked at most once a minute), so a game deploy that
changes a monster shows up in the wiki without touching the portal.
"""

import glob
import logging
import os
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET

log = logging.getLogger("portal.wiki")

GAME = os.environ.get("PORTAL_GAME_DATA", os.path.join(os.path.dirname(__file__), "..", ".."))
MONSTER_DIR = os.path.join(GAME, "data-otservbr-global", "monster")
ITEMS_XML = os.path.join(GAME, "data", "items", "items.xml")
STAGES_LUA = os.path.join(GAME, "data", "stages.lua")
HIDDEN_DIRS = {"traps", "trainers", "familiars", "event_creatures"}

ELEMENTS = [
    ("COMBAT_PHYSICALDAMAGE", "physical", "Físico"),
    ("COMBAT_FIREDAMAGE", "fire", "Fogo"),
    ("COMBAT_EARTHDAMAGE", "earth", "Terra"),
    ("COMBAT_ENERGYDAMAGE", "energy", "Energia"),
    ("COMBAT_ICEDAMAGE", "ice", "Gelo"),
    ("COMBAT_HOLYDAMAGE", "holy", "Sagrado"),
    ("COMBAT_DEATHDAMAGE", "death", "Morte"),
    ("COMBAT_LIFEDRAIN", "lifedrain", "Dreno de vida"),
    ("COMBAT_MANADRAIN", "manadrain", "Dreno de mana"),
    ("COMBAT_DROWNDAMAGE", "drown", "Afogamento"),
]
ELEMENT_BY_CONST = {c: (k, pt) for c, k, pt in ELEMENTS}
IMMUNITY_PT = {
    "paralyze": "Paralisia", "invisible": "Invisível", "outfit": "Troca de outfit", "bleed": "Sangramento",
    "drunk": "Embriaguez", "fire": "Fogo", "energy": "Energia", "earth": "Veneno", "poison": "Veneno",
    "ice": "Gelo", "holy": "Sagrado", "death": "Morte", "drown": "Afogamento", "lifedrain": "Dreno de vida",
    "manadrain": "Dreno de mana", "physical": "Físico",
}
CLASS_PT = {
    "Amphibic": "Anfíbios", "Aquatic": "Aquáticos", "Bird": "Aves", "Construct": "Constructos", "Demon": "Demônios",
    "Dragon": "Dragões", "Elemental": "Elementais", "Extra Dimensional": "Extradimensionais", "Fey": "Fadas",
    "Giant": "Gigantes", "Human": "Humanos", "Humanoid": "Humanoides", "Lycanthrope": "Licantropos",
    "Magical": "Mágicos", "Mammal": "Mamíferos", "Plant": "Plantas", "Reptile": "Répteis", "Slime": "Gosmas",
    "Undead": "Mortos-vivos", "Vermin": "Vermes", "Inkborn": "Inkborn",
}
DIR_CLASS = {  # folder -> bestiary class, for creatures without a Bestiary block
    "amphibics": "Amphibic", "aquatics": "Aquatic", "birds": "Bird", "constructs": "Construct", "demons": "Demon",
    "dragons": "Dragon", "elementals": "Elemental", "extra_dimensional": "Extra Dimensional", "fey": "Fey",
    "giants": "Giant", "humans": "Human", "humanoids": "Humanoid", "lycanthropes": "Lycanthrope",
    "magicals": "Magical", "mammals": "Mammal", "plants": "Plant", "reptiles": "Reptile", "slimes": "Slime",
    "undeads": "Undead", "vermins": "Vermin",
}


# ------------------------------------------------------------------ tiny Lua table reader

class _Lua:
    """Reads the literal subset monster files use: tables, strings, numbers, booleans, constants."""

    TOKEN = re.compile(r"""
        (?P<ws>\s+|--\[\[.*?\]\]|--[^\n]*)
      | (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
      | (?P<num>-?0x[0-9a-fA-F]+|-?\d+\.?\d*(?:[eE][-+]?\d+)?)
      | (?P<name>[A-Za-z_][A-Za-z_0-9.]*)
      | (?P<op>[{}\[\]=,;()+\-*/])
    """, re.S | re.X)

    def __init__(self, text, pos):
        self.text, self.pos = text, pos

    def _next(self):
        while True:
            m = self.TOKEN.match(self.text, self.pos)
            if not m:
                raise ValueError("bad token at %d" % self.pos)
            self.pos = m.end()
            if m.lastgroup != "ws":
                return m.lastgroup, m.group()

    def _peek(self):
        save = self.pos
        tok = self._next()
        self.pos = save
        return tok

    def value(self):
        kind, tok = self._next()
        if kind == "op" and tok == "{":
            return self._table()
        if kind == "str":
            return _unquote(tok)
        if kind == "num":
            v = int(tok, 16) if "x" in tok.lower() else float(tok)
            v = int(v) if isinstance(v, float) and v.is_integer() else v
            return self._arith(v)
        if kind == "name":
            if tok == "true":
                return True
            if tok == "false":
                return False
            if tok == "nil":
                return None
            if self._peek() == ("op", "("):  # a call such as math.random(...): skip it
                depth = 0
                while True:
                    k, t = self._next()
                    depth += t == "(" if k == "op" else 0
                    depth -= t == ")" if k == "op" else 0
                    if depth == 0 and t == ")":
                        return None
            return tok  # a constant, e.g. COMBAT_FIREDAMAGE
        if kind == "op" and tok == "-":
            v = self.value()
            return -v if isinstance(v, (int, float)) else v
        raise ValueError("unexpected %r" % tok)

    def _arith(self, v):
        kind, tok = self._peek()
        if kind == "op" and tok in "+-*/" and tok:
            self._next()
            rhs = self.value()
            if isinstance(rhs, (int, float)):
                v = {"+": v + rhs, "-": v - rhs, "*": v * rhs, "/": v / rhs if rhs else v}[tok]
        return v

    def _table(self):
        arr, obj = [], {}
        while True:
            kind, tok = self._peek()
            if kind == "op" and tok == "}":
                self._next()
                break
            if kind == "op" and tok in ",;":
                self._next()
                continue
            if kind == "op" and tok == "[":
                self._next()
                key = self.value()
                self._next()  # ]
                self._next()  # =
                obj[key] = self.value()
                continue
            if kind == "name":
                save = self.pos
                self._next()
                if self._peek() == ("op", "="):
                    self._next()
                    obj[tok] = self.value()
                    continue
                self.pos = save
            arr.append(self.value())
        if obj and arr:
            obj["_list"] = arr
            return obj
        return obj if obj else arr


def _unquote(tok):
    body = tok[1:-1]
    body = re.sub(r"\\z\s*", "", body)
    return body.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")


FIELD_RE = re.compile(r"^monster\.(\w+)\s*=\s*", re.M)
NAME_RE = re.compile(r'Game\.createMonsterType\(\s*"([^"]+)"')


def parse_monster(text):
    m = NAME_RE.search(text)
    if not m:
        return None
    data = {"_name": m.group(1)}
    for f in FIELD_RE.finditer(text):
        try:
            data[f.group(1)] = _Lua(text, f.end()).value()
        except Exception:
            pass  # a field written as code: skip it, keep the rest
    return data


# ------------------------------------------------------------------ helpers

def slugify(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _num(v, default=0):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else default


def _as_list(v):
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return v.get("_list", [])
    return []


def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def fmt_chance(ch):
    p = ch / 1000  # loot chance is per 100000
    if p >= 10:
        return f"{p:.0f}%"
    if p >= 1:
        return f"{p:.1f}%".replace(".", ",")
    return f"{p:.2f}%".replace(".", ",")


def rarity(ch):
    p = ch / 1000
    return "comum" if p >= 25 else "incomum" if p >= 5 else "semi-raro" if p >= 1 else "raro" if p >= 0.2 else "muito-raro"


RARITY_PT = {"comum": "Comum", "incomum": "Incomum", "semi-raro": "Semi-raro", "raro": "Raro", "muito-raro": "Muito raro"}


# ------------------------------------------------------------------ loading

class _Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.stamp = None
        self.checked = 0
        self.data = None

    def _stamp(self):
        files = glob.glob(os.path.join(MONSTER_DIR, "**", "*.lua"), recursive=True)
        newest = max((os.path.getmtime(f) for f in files), default=0)
        items = os.path.getmtime(ITEMS_XML) if os.path.exists(ITEMS_XML) else 0
        return len(files), newest, items

    def get(self):
        now = time.time()
        with self.lock:
            if self.data is None or now - self.checked > 60:
                self.checked = now
                stamp = self._stamp()
                if stamp != self.stamp:
                    t0 = time.time()
                    self.data = _load()
                    self.stamp = stamp
                    log.info("wiki: %d creatures, %d items in %.1fs", len(self.data["creatures"]), len(self.data["items"]), time.time() - t0)
            return self.data


_store = _Store()


def _load_items():
    items, by_name = {}, {}
    if not os.path.exists(ITEMS_XML):
        return items, by_name
    for _, el in ET.iterparse(ITEMS_XML, events=("end",)):
        if el.tag != "item":
            continue
        name = el.get("name")
        if not name:
            el.clear()
            continue
        attrs = {a.get("key"): a.get("value") for a in el.findall("attribute") if a.get("key")}
        if el.get("id"):
            ids = [int(el.get("id"))]
        elif el.get("fromid") and el.get("toid"):
            ids = list(range(int(el.get("fromid")), int(el.get("toid")) + 1))
        else:
            ids = []
        for iid in ids:
            items[iid] = {"id": iid, "name": name, "article": el.get("article", ""), "plural": el.get("plural", ""), "attrs": attrs}
            by_name.setdefault(name.lower(), iid)
        el.clear()
    return items, by_name


def _creature(raw, path):
    folder = os.path.relpath(path, MONSTER_DIR).split(os.sep)[0]
    name = raw.get("name") if isinstance(raw.get("name"), str) else raw["_name"]
    outfit = raw.get("outfit") if isinstance(raw.get("outfit"), dict) else {}
    best = raw.get("Bestiary") if isinstance(raw.get("Bestiary"), dict) else {}
    boss = raw.get("bosstiary") if isinstance(raw.get("bosstiary"), dict) else {}
    flags = raw.get("flags") if isinstance(raw.get("flags"), dict) else {}
    defenses = raw.get("defenses") if isinstance(raw.get("defenses"), dict) else {}
    elements = {}
    for e in _as_list(raw.get("elements")):
        if isinstance(e, dict) and e.get("type") in ELEMENT_BY_CONST:
            elements[ELEMENT_BY_CONST[e["type"]][0]] = _num(e.get("percent"))
    immun = [str(i.get("type")) for i in _as_list(raw.get("immunities")) if isinstance(i, dict) and i.get("condition")]
    for key, val in elements.items():
        if val >= 100 and key not in immun:
            immun.append(key)
    loot = []
    for it in _as_list(raw.get("loot")):
        if not isinstance(it, dict) or not _num(it.get("chance")):
            continue
        loot.append({"id": _num(it.get("id"), None), "name": it.get("name") if isinstance(it.get("name"), str) else None,
                     "chance": _num(it.get("chance")), "max": int(_num(it.get("maxCount"), 1)) or 1})
    attacks = []
    melee = 0
    for a in _as_list(raw.get("attacks")):
        if not isinstance(a, dict):
            continue
        lo, hi = abs(_num(a.get("minDamage"))), abs(_num(a.get("maxDamage")))
        if a.get("name") == "melee":
            melee = max(melee, hi)
            continue
        kind = ELEMENT_BY_CONST.get(a.get("type"), (None, None))
        attacks.append({"name": str(a.get("name") or ""), "element": kind[0], "element_pt": kind[1],
                        "min": int(min(lo, hi)), "max": int(max(lo, hi)),
                        "area": bool(a.get("radius") or a.get("length")), "range": bool(a.get("range") or a.get("target"))})
    summons = [s.get("name") for s in _as_list(raw.get("summon") or raw.get("summons")) if isinstance(s, dict) and s.get("name")]
    if isinstance(raw.get("summon"), dict):
        summons += [s.get("name") for s in _as_list(raw["summon"].get("summons")) if isinstance(s, dict) and s.get("name")]
    voices = [v.get("text") for v in _as_list(raw.get("voices")) if isinstance(v, dict) and v.get("text")]
    cls = best.get("class") if isinstance(best.get("class"), str) else DIR_CLASS.get(folder, "")
    is_boss = folder == "bosses" or bool(boss) or bool(flags.get("rewardBoss"))
    return {
        "name": name, "slug": slugify(name), "folder": folder, "file": os.path.relpath(path, GAME),
        "description": raw.get("description") if isinstance(raw.get("description"), str) else "",
        "experience": int(_num(raw.get("experience"))), "health": int(_num(raw.get("maxHealth") or raw.get("health"))),
        "speed": int(_num(raw.get("speed"))), "race": raw.get("race") if isinstance(raw.get("race"), str) else "",
        "armor": int(_num(defenses.get("armor"))), "defense": int(_num(defenses.get("defense"))),
        "mitigation": _num(defenses.get("mitigation")),
        "looktype": int(_num(outfit.get("lookType"))), "looktype_ex": int(_num(outfit.get("lookTypeEx"))),
        "colors": [int(_num(outfit.get(k))) for k in ("lookHead", "lookBody", "lookLegs", "lookFeet")],
        "addons": int(_num(outfit.get("lookAddons"))),
        "class": cls, "class_pt": CLASS_PT.get(cls, cls), "boss": is_boss,
        "stars": int(_num(best.get("Stars"))), "charms": int(_num(best.get("CharmsPoints"))), "to_kill": int(_num(best.get("toKill"))),
        "locations": best.get("Locations") if isinstance(best.get("Locations"), str) else "",
        "race_id": int(_num(raw.get("raceId"))),
        "summonable": bool(flags.get("summonable")), "convinceable": bool(flags.get("convinceable")),
        "illusionable": bool(flags.get("illusionable")), "pushable": bool(flags.get("pushable")),
        "hostile": flags.get("hostile", True) is not False, "paralyze_immune": "paralyze" in immun,
        "summon_cost": int(_num(raw.get("manaCost"))),
        "elements": elements, "immunities": immun, "loot": loot, "melee": int(melee), "attacks": attacks,
        "summons": summons, "voices": voices[:6],
    }


def _load():
    items, by_name = _load_items()
    creatures, slugs = [], {}
    for path in sorted(glob.glob(os.path.join(MONSTER_DIR, "**", "*.lua"), recursive=True)):
        folder = os.path.relpath(path, MONSTER_DIR).split(os.sep)[0]
        if folder in HIDDEN_DIRS:
            continue
        try:
            raw = parse_monster(open(path, encoding="utf-8", errors="replace").read())
        except Exception as exc:
            log.warning("wiki: could not read %s: %s", path, exc)
            continue
        if not raw:
            continue
        c = _creature(raw, path)
        if not c["slug"] or c["slug"] in slugs:
            continue  # the same monster declared twice (quest copies): keep the first
        slugs[c["slug"]] = c
        creatures.append(c)
    drops = {}
    for c in creatures:
        for it in c["loot"]:
            iid = it["id"] or by_name.get((it["name"] or "").lower())
            it["id"] = iid
            info = items.get(iid)
            it["name"] = (info["name"] if info else it["name"]) or f"item {iid}"
            it["rarity"] = rarity(it["chance"])
            it["chance_pt"] = fmt_chance(it["chance"])
            if iid:
                drops.setdefault(iid, []).append((c["slug"], it["chance"], it["max"]))
        c["loot"].sort(key=lambda x: -x["chance"])
    creatures.sort(key=lambda c: c["name"].lower())
    classes = {}
    for c in creatures:
        if not c["boss"] and c["class"]:
            classes[c["class"]] = classes.get(c["class"], 0) + 1
    for iid in drops:
        drops[iid].sort(key=lambda d: -d[1])
    return {"creatures": creatures, "by_slug": slugs, "items": items, "drops": drops,
            "classes": sorted(classes.items(), key=lambda kv: CLASS_PT.get(kv[0], kv[0]))}


def data():
    return _store.get()


def creature(slug):
    return data()["by_slug"].get(slug)


def item(iid):
    d = data()
    info = d["items"].get(iid)
    if not info:
        return None
    return {**info, "slug": slugify(info["name"]), "drops": [(d["by_slug"][s], ch, mx) for s, ch, mx in d["drops"].get(iid, [])]}


def loot_items():
    d = data()
    out = [{**d["items"][i], "slug": slugify(d["items"][i]["name"]), "sources": len(src)} for i, src in d["drops"].items() if i in d["items"]]
    return sorted(out, key=lambda x: x["name"].lower())


# ------------------------------------------------------------------ rates

STAGE_KEYS = [("experienceStages", "Experiência", "level"), ("skillsStages", "Skills", "nível de skill"), ("magicLevelStages", "Magic level", "magic level")]


def _stages_file():
    out = {}
    try:
        text = open(STAGES_LUA, encoding="utf-8").read()
    except OSError:
        return out
    for key, _, _ in STAGE_KEYS:
        m = re.search(r"^%s\s*=\s*" % key, text, re.M)
        if m:
            try:
                rows = _Lua(text, m.end()).value()
                out[key] = [(int(_num(r.get("minlevel"))), int(_num(r.get("maxlevel"))) or None, int(_num(r.get("multiplier"), 1))) for r in rows if isinstance(r, dict)]
            except Exception:
                pass
    return out


def rates(db):
    """What the server uses right now: the Cockpit's saved world settings, else the files."""
    saved = {}
    try:
        saved = {r["k"][6:]: r["v"] for r in db.all("SELECT k, v FROM cockpit_settings WHERE k LIKE 'world.%%'")}
    except Exception:
        pass
    stages = _stages_file()
    for key, _, _ in STAGE_KEYS:
        text = saved.get(key)
        if text:
            rows = []
            for part in text.split(","):
                m = re.match(r"^(\d+)-(\d*):(\d+)$", part.strip())
                if m:
                    rows.append((int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3))))
            if rows:
                stages[key] = rows
    use_stages = saved.get("rateUseStages", "1") != "0"

    def num(k, d=1):
        v = saved.get(k, "")
        return int(v) if str(v).isdigit() else d

    switches = [
        ("autoLoot", "Autoloot", "O loot vai direto pra mochila."),
        ("staminaPz", "Stamina na cidade", "Quem fica em área protegida recupera stamina."),
        ("staminaTrainer", "Stamina no treino", "Treinar em dummy também recupera stamina."),
        ("toggleTravelsFree", "Viagens grátis", "Barcos, tapetes e viagens de NPC não cobram."),
        ("toggleFreeQuest", "Acessos de quest liberados", "As portas das quests principais já vêm abertas."),
        ("partyShareLootBoosts", "Loot boost na party", "Boosts de loot valem pra party toda."),
    ]
    return {
        "live": bool(saved), "use_stages": use_stages, "stages": [(k, label, unit, stages.get(k, [])) for k, label, unit in STAGE_KEYS],
        "fixed": [("XP", num("rateExp")), ("Skill", num("rateSkill")), ("Magic level", num("rateMagic")), ("Loot", num("rateLoot"))],
        "switches": [(label, text, saved.get(k, "1") == "1") for k, label, text in switches] if saved else [],
    }

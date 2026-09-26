"""The rest of the VinOT Wiki: spells and runes, NPCs (with what they buy and sell), quests, mounts,
outfits, the world map and one page per town. Same idea as build_mediawiki.py: every page is written
from the game files, nothing by hand.

    python tools/build_wiki_more.py OUT_DIR MAP_DIR

OUT_DIR gets pages-more.xml and more pictures in images/. MAP_DIR is the output of render_minimap.py
(floor-NN.png, bounds.json, towns.json).
"""

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import build_mediawiki as bm  # noqa: E402
import build_wiki_sprites as bws  # noqa: E402
import extract_creatures as ec  # noqa: E402
from app import wiki  # noqa: E402

G = wiki.GAME
VOC_BASE = {"sorcerer": "Sorcerer", "master sorcerer": "Sorcerer", "druid": "Druid", "elder druid": "Druid",
            "paladin": "Paladin", "royal paladin": "Paladin", "knight": "Knight", "elite knight": "Knight",
            "monk": "Monk", "exalted monk": "Monk"}
SPELL_GROUP = {"attack": "Magias de ataque", "healing": "Magias de cura", "support": "Magias de suporte",
               "conjuring": "Magias de conjuração", "party": "Magias de grupo", "house": "Magias de casa",
               "familiar": "Magias de familiar"}
CALL = re.compile(r"^\s*(spell|rune):(\w+)\((.*)\)\s*(?:--.*)?$", re.M)
STR = re.compile(r'"([^"]*)"')


def lua_args(raw):
    strs = STR.findall(raw)
    if strs:
        return strs
    raw = raw.strip()
    try:
        return [eval(raw, {"__builtins__": {}}, {})]  # numbers and simple arithmetic like 2 * 1000
    except Exception:
        return [raw]


# ------------------------------------------------------------------ spells and runes

def spells():
    out = []
    files = sorted(glob.glob(os.path.join(G, "data", "scripts", "spells", "**", "*.lua"), recursive=True))
    files += sorted(glob.glob(os.path.join(G, "data", "scripts", "runes", "*.lua")))
    for path in files:
        text = open(path, encoding="utf-8", errors="replace").read()
        s = {"file": path, "folder": os.path.basename(os.path.dirname(path)), "voc": set()}
        for kind, key, raw in CALL.findall(text):
            s["kind"] = kind
            args = lua_args(raw)
            if key == "vocation":
                for a in args:
                    base = VOC_BASE.get(str(a).split(";")[0].strip().lower())
                    if base:
                        s["voc"].add(base)
            elif args:
                s[key] = args[0]
        if s.get("name") and (s.get("words") or s.get("kind") == "rune"):
            out.append(s)
    return out


def fmt_ms(v):
    try:
        v = float(v) / 1000
    except (TypeError, ValueError):
        return ""
    return f"{v:g} s"


# ------------------------------------------------------------------ NPCs

NPC_NAME = re.compile(r'local\s+internalNpcName\s*=\s*"([^"]+)"|npcConfig\.name\s*=\s*"([^"]+)"')
SHOP_ROW = re.compile(r"\{[^{}]*itemName\s*=\s*\"([^\"]+)\"[^{}]*\}")


def npcs():
    out = {}
    for path in sorted(glob.glob(os.path.join(G, "data-otservbr-global", "npc", "*.lua"))):
        text = open(path, encoding="utf-8", errors="replace").read()
        m = NPC_NAME.search(text)
        if not m:
            continue
        name = m.group(1) or m.group(2)
        n = {"name": name, "slug": wiki.slugify(name), "shop": [], "voices": []}
        om = re.search(r"npcConfig\.outfit\s*=\s*", text)
        if om:
            try:
                n["outfit"] = wiki._Lua(text, om.end()).value()
            except Exception:
                n["outfit"] = {}
        vm = re.search(r"npcConfig\.voices\s*=\s*", text)
        if vm:
            try:
                v = wiki._Lua(text, vm.end()).value()
                n["voices"] = [x.get("text") for x in wiki._as_list(v.get("_list") if isinstance(v, dict) else v)
                               if isinstance(x, dict) and x.get("text")][:5]
            except Exception:
                pass
        sm = re.search(r"npcConfig\.shop\s*=\s*\{", text)
        if sm:
            depth, j = 1, sm.end()
            while depth and j < len(text):
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            for row in SHOP_ROW.finditer(text[sm.end():j]):
                r = row.group(0)
                buy = re.search(r"\bbuy\s*=\s*(\d+)", r)
                sell = re.search(r"\bsell\s*=\s*(\d+)", r)
                cid = re.search(r"clientId\s*=\s*(\d+)", r)
                n["shop"].append({"item": row.group(1), "id": int(cid.group(1)) if cid else None,
                                  "buy": int(buy.group(1)) if buy else None, "sell": int(sell.group(1)) if sell else None})
        out[name.lower()] = n
    # where they stand
    try:
        root = ET.parse(os.path.join(G, "data-otservbr-global", "world", "otservbr-npc.xml")).getroot()
        for group in root:
            cx, cy, cz = (int(group.get(k, 0)) for k in ("centerx", "centery", "centerz"))
            for child in group:
                n = out.get((child.get("name") or "").lower())
                if n and "pos" not in n:
                    n["pos"] = (cx + int(child.get("x", 0)), cy + int(child.get("y", 0)), int(child.get("z", cz)))
    except Exception as exc:
        print("npc positions:", exc, file=sys.stderr)
    return list(out.values())


# ------------------------------------------------------------------ quests

def quests():
    text = open(os.path.join(G, "data-otservbr-global", "lib", "core", "quests.lua"), encoding="utf-8", errors="replace").read()
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r'^\t\t\tname = "(.*)",\s*$', line)
        if m:
            cur = {"name": m.group(1), "missions": []}
            out.append(cur)
            continue
        m = re.match(r'^\t\t\t\t\tname = "(.*)",\s*$', line)
        if m and cur is not None:
            cur["missions"].append({"name": m.group(1), "description": ""})
            continue
        m = re.match(r'^\t\t\t\t\tdescription = "(.*)",\s*$', line)
        if m and cur is not None and cur["missions"]:
            cur["missions"][-1]["description"] = m.group(1).replace("\\n", " ")
    return out


# ------------------------------------------------------------------ pictures of outfits

def render_looktypes(wanted, out_dir, prefix):
    """{key: filename} for {key: (looktype, colors, addons)} drawn facing south."""
    infos = bws.infos(2, {lt for lt, _, _ in wanted.values() if lt})
    sprites = ec.Sprites()
    done = {}
    for key, (lt, colors, addons) in wanted.items():
        info = infos.get(lt)
        if not info:
            continue
        try:
            cols = dict(zip(("head", "body", "legs", "feet"), (ec.outfit_color(v) for v in colors)))
            add = tuple(a for a, bit in ((1, 1), (2, 2)) if addons & bit)
            img = ec.render_outfit(sprites, info, cols, addons=add, direction=2 if info["px"] > 2 else 0)
            img = bws.trim(img) if img else None
        except Exception as exc:
            print("failed", key, exc, file=sys.stderr)
            img = None
        if img:
            name = f"{prefix}-{key}.png"
            img.save(os.path.join(out_dir, name), optimize=True)
            done[key] = name
    return done


# ------------------------------------------------------------------ pages

def main(out, map_dir):
    img_dir = os.path.join(out, "images")
    os.makedirs(img_dir, exist_ok=True)
    dump = bm.Dump()
    towns = json.load(open(os.path.join(map_dir, "towns.json"), encoding="utf-8"))
    bounds = json.load(open(os.path.join(map_dir, "bounds.json")))
    main_towns = [t for t in towns if t["z"] == 7 and "tutorial" not in t["name"].lower()]

    def town_of(pos):
        if not pos or not main_towns:
            return None
        x, y, _ = pos
        best = min(main_towns, key=lambda t: (t["x"] - x) ** 2 + (t["y"] - y) ** 2)
        return best if (best["x"] - x) ** 2 + (best["y"] - y) ** 2 < 260 ** 2 else None

    item_titles = {bm.clean(bm.title_case(it["name"])) for it in wiki.data()["items"].values()}

    def item_link(name):
        t = bm.clean(bm.title_case(name))
        return f"[[{t}|{bm.title_case(name)}]]" if t in item_titles else bm.title_case(name)

    # ---------------- spells
    sp = spells()
    by_cat = {}
    for s in sp:
        rune = s["kind"] == "rune"
        title = bm.clean(bm.title_case(s["name"]))
        if not rune and title in item_titles:
            title += " (magia)"
        if rune:
            title = f"{title} (magia)"
        group = s.get("group", "")
        cat = "Runas (magias)" if rune else SPELL_GROUP.get(s["folder"], SPELL_GROUP.get(group, "Magias"))
        vocs = sorted(s["voc"]) or ["Todas"]
        rows = [("Palavras", f"''{s.get('words', '')}''" if s.get("words") else ""), ("Tipo", cat),
                ("Vocações", ", ".join(f"[[:Categoria:Magias de {v}|{v}]]" for v in vocs) if s["voc"] else "Todas"),
                ("Level", s.get("level") or s.get("runeLevel")), ("Magic level", s.get("magicLevel") or s.get("runeMagicLevel")),
                ("Mana", s.get("mana")), ("Premium", "sim" if str(s.get("isPremium")).lower() == "true" else ""),
                ("Cooldown", fmt_ms(s.get("cooldown"))), ("Cargas", s.get("charges")),
                ("Runa", item_link(s["name"]) if rune else "")]
        box = bm.infobox(bm.title_case(s["name"]), "", 0, rows)
        body = [box, "", f"'''{bm.title_case(s['name'])}''' é uma {'runa' if rune else 'magia'}"
                + (f" de {', '.join(vocs)}" if s["voc"] else "") + "."]
        cats = ["Magias", cat] + [f"Magias de {v}" for v in s["voc"]]
        body += [""] + [f"[[Categoria:{c}]]" for c in cats]
        dump.add(title, "\n".join(body))
        by_cat.setdefault(cat, []).append((title, s))
    # tables per vocation, like TibiaWiki's spell lists
    for voc in ("Sorcerer", "Druid", "Paladin", "Knight", "Monk"):
        mine = sorted((x for x in sp if voc in x["voc"] and x["kind"] == "spell"), key=lambda x: (int(float(x.get("level") or 0)), x["name"]))
        if not mine:
            continue
        rows = ['{| class="wikitable sortable"', "! Magia !! Palavras !! Level !! Mana !! Premium"]
        for x in mine:
            t = bm.clean(bm.title_case(x["name"]))
            t = t + " (magia)" if t in item_titles else t
            rows += ["|-", f"| [[{t}|{bm.title_case(x['name'])}]] || ''{x.get('words', '')}'' || {x.get('level', '')} || {x.get('mana', '')} || {'sim' if str(x.get('isPremium')).lower() == 'true' else ''}"]
        rows.append("|}")
        dump.add(f"Categoria:Magias de {voc}", f"Magias que um {voc} pode usar, em ordem de level.\n\n" + "\n".join(rows) + "\n\n[[Categoria:Magias]]")
    for cat in set(by_cat):
        dump.add(f"Categoria:{cat}", f"{cat} do VinOT.\n\n[[Categoria:Magias]]")
    dump.add("Categoria:Magias", "Todas as magias e runas do VinOT. Veja também as listas por vocação: "
             + " · ".join(f"[[:Categoria:Magias de {v}|{v}]]" for v in ("Sorcerer", "Druid", "Paladin", "Knight", "Monk")))

    # ---------------- NPCs
    people = npcs()
    looks = {}
    for n in people:
        o = n.get("outfit") or {}
        lt = int(wiki._num(o.get("lookType")))
        if lt:
            looks[n["slug"]] = (lt, [int(wiki._num(o.get(k))) for k in ("lookHead", "lookBody", "lookLegs", "lookFeet")], int(wiki._num(o.get("lookAddons"))))
    npc_imgs = render_looktypes(looks, img_dir, "NPC")
    npcs_by_town = {}
    creature_titles = {bm.clean(c["name"]) for c in wiki.data()["creatures"]}
    for n in people:
        title = bm.clean(n["name"])
        if title in item_titles or title in creature_titles:
            title += " (NPC)"
        n["title"] = title
        town = town_of(n.get("pos"))
        pos = n.get("pos")
        rows = [("Cidade", f"[[{town['name']}]]" if town else ""),
                ("Posição", f"{pos[0]}, {pos[1]}, {pos[2]}" if pos else ""),
                ("Compra", str(sum(1 for r in n["shop"] if r["sell"]))), ("Vende", str(sum(1 for r in n["shop"] if r["buy"])))]
        box = bm.infobox(n["name"], npc_imgs.get(n["slug"], ""), 64, rows)
        body = [box, "", f"'''{n['name']}''' é um NPC" + (f" de [[{town['name']}]]." if town else ".")]
        if n["voices"]:
            body += ["", "== Frases ==", *[f"* ''\"{v}\"''" for v in n["voices"]]]
        sells = [r for r in n["shop"] if r["buy"]]
        buys = [r for r in n["shop"] if r["sell"]]
        if sells:
            body += ["", "== Vende ==", '{| class="wikitable sortable"', "! Item !! Preço"]
            for r in sells:
                body += ["|-", f"| {item_link(r['item'])} || data-sort-value=\"{r['buy']}\" | {wiki.fmt_int(r['buy'])} gp"]
            body.append("|}")
        if buys:
            body += ["", "== Compra ==", '{| class="wikitable sortable"', "! Item !! Paga"]
            for r in buys:
                body += ["|-", f"| {item_link(r['item'])} || data-sort-value=\"{r['sell']}\" | {wiki.fmt_int(r['sell'])} gp"]
            body.append("|}")
        cats = ["NPCs"] + ([f"NPCs de {town['name']}"] if town else []) + (["Comerciantes"] if n["shop"] else [])
        body += [""] + [f"[[Categoria:{c}]]" for c in cats]
        dump.add(title, "\n".join(body))
        if town:
            npcs_by_town.setdefault(town["name"], []).append(n)
    dump.add("Categoria:NPCs", "Todos os NPCs do VinOT. Veja também os [[:Categoria:Comerciantes|comerciantes]].")
    dump.add("Categoria:Comerciantes", "NPCs que compram ou vendem itens.\n\n[[Categoria:NPCs]]")
    # who buys each item for the most: a page like TibiaWiki's "loot value"
    best = {}
    for n in people:
        for r in n["shop"]:
            if r["sell"] and r["sell"] > best.get(r["item"].lower(), (0,))[0]:
                best[r["item"].lower()] = (r["sell"], n["title"], r["item"])
    rows = ['{| class="wikitable sortable"', "! Item !! Melhor preço !! NPC"]
    for key, (price, who, item) in sorted(best.items(), key=lambda kv: -kv[1][0]):
        rows += ["|-", f"| {item_link(item)} || data-sort-value=\"{price}\" | {wiki.fmt_int(price)} gp || [[{who}]]"]
    rows.append("|}")
    dump.add("Onde vender", "Quem paga mais por cada item, direto das lojas dos NPCs.\n\n" + "\n".join(rows) + "\n\n[[Categoria:NPCs]]")

    # ---------------- quests
    qs = quests()
    for q in qs:
        title = bm.clean(q["name"])
        if title in item_titles or title in creature_titles:
            title += " (quest)"
        body = [f"'''{q['name']}''' é uma quest do VinOT"
                + (f" com {len(q['missions'])} missões." if q["missions"] else "."), ""]
        if q["missions"]:
            body += ["== Missões ==", '{| class="wikitable"', "! # !! Missão !! O que diz o registro de quests"]
            for i, m in enumerate(q["missions"], 1):
                body += ["|-", f"| {i} || {m['name']} || {m['description'] or '—'}"]
            body.append("|}")
        body += ["", "[[Categoria:Quests]]"]
        dump.add(title, "\n".join(body))
    dump.add("Categoria:Quests", f"As {len(qs)} quests do registro de quests do VinOT, com as missões de cada uma.")

    # ---------------- mounts and outfits
    mounts = []
    for m in ET.parse(os.path.join(G, "data", "XML", "mounts.xml")).getroot():
        mounts.append({k: m.get(k) for k in ("id", "clientid", "name", "speed", "premium", "type")})
    mount_imgs = render_looktypes({m["id"]: (int(m["clientid"]), [0, 0, 0, 0], 0) for m in mounts}, img_dir, "Montaria")
    rows = ['{| class="wikitable sortable vinot-loot"', "! !! Montaria !! Velocidade !! Premium !! Como conseguir"]
    for m in sorted(mounts, key=lambda m: m["name"]):
        img = f"[[Arquivo:{mount_imgs[m['id']]}|64px]]" if m["id"] in mount_imgs else ""
        how = {"quest": "Quest", "store": "Loja", "tame": "Domar", "achievement": "Conquista"}.get((m.get("type") or "").lower(), m.get("type") or "")
        rows += ["|-", f"| {img} || {m['name']} || +{m['speed']} || {'sim' if m['premium'] == 'yes' else 'não'} || {how}"]
    rows.append("|}")
    dump.add("Montarias", f"As {len(mounts)} montarias do VinOT.\n\n" + "\n".join(rows) + "\n\n[[Categoria:Montarias e outfits]]")
    outfits = [o.attrib for o in ET.parse(os.path.join(G, "data", "XML", "outfits.xml")).getroot() if o.tag == "outfit" and o.get("enabled", "yes") == "yes"]
    look = {f"{o['looktype']}": (int(o["looktype"]), [78, 69, 58, 76], 3) for o in outfits}
    outfit_imgs = render_looktypes(look, img_dir, "Outfit")
    for sex, label in (("1", "Masculinos"), ("0", "Femininos")):
        rows = ['{| class="wikitable sortable vinot-loot"', "! !! Outfit !! Premium !! Liberado no início"]
        for o in sorted((o for o in outfits if o.get("type") == sex), key=lambda o: o["name"]):
            img = f"[[Arquivo:{outfit_imgs[o['looktype']]}|64px]]" if o["looktype"] in outfit_imgs else ""
            rows += ["|-", f"| {img} || {o['name']} || {'sim' if o.get('premium') == 'yes' else 'não'} || {'sim' if o.get('unlocked') == 'yes' else 'não'}"]
        rows.append("|}")
        dump.add(f"Outfits {label.lower()}", f"Outfits {label.lower()} do VinOT, com os dois addons.\n\n" + "\n".join(rows) + "\n\n[[Categoria:Montarias e outfits]]")
    dump.add("Categoria:Montarias e outfits", "[[Montarias]] · [[Outfits masculinos]] · [[Outfits femininos]]")

    # ---------------- maps
    x0, y0 = bounds["x0"], bounds["y0"]
    floors = sorted(int(f[6:8]) for f in os.listdir(map_dir) if f.startswith("floor-"))
    surface = Image.open(os.path.join(map_dir, "floor-07.png")).convert("RGB")
    world = surface.copy()
    world.thumbnail((1600, 1600), Image.NEAREST)
    world.save(os.path.join(img_dir, "Mapa-mundo.png"), optimize=True)
    for z in floors:
        im = Image.open(os.path.join(map_dir, f"floor-{z:02d}.png")).convert("RGB")
        im.save(os.path.join(img_dir, f"Mapa-andar-{z:02d}.png"), optimize=True)
    town_rows = []
    for t in sorted(main_towns, key=lambda t: t["name"]):
        cx, cy = t["x"] - x0, t["y"] - y0
        box = (max(0, cx - 160), max(0, cy - 120), cx + 160, cy + 120)
        crop = surface.crop(box).resize((640, 480), Image.NEAREST)
        # temple marker
        px, py = (cx - box[0]) * 2, (cy - box[1]) * 2
        for dx in range(-4, 5):
            for dy in (-1, 0, 1):
                for x, y in ((px + dx, py + dy), (px + dy, py + dx)):
                    if 0 <= x < 640 and 0 <= y < 480:
                        crop.putpixel((x, y), (255, 255, 255))
        fname = f"Mapa-{wiki.slugify(t['name'])}.png"
        crop.save(os.path.join(img_dir, fname), optimize=True)
        people_here = sorted(npcs_by_town.get(t["name"], []), key=lambda n: n["name"])
        body = [f"'''{t['name']}''' é uma cidade do VinOT. O templo fica em {t['x']}, {t['y']}, {t['z']} (a cruz branca no mapa).", "",
                f"[[Arquivo:{fname}|640px|Mapa de {t['name']}]]", ""]
        if people_here:
            body += ["== NPCs ==", '{| class="wikitable sortable"', "! NPC !! Vende !! Compra"]
            for n in people_here:
                body += ["|-", f"| [[{n['title']}|{n['name']}]] || {sum(1 for r in n['shop'] if r['buy']) or ''} || {sum(1 for r in n['shop'] if r['sell']) or ''}"]
            body.append("|}")
        body += ["", "[[Categoria:Cidades]]"]
        dump.add(t["name"], "\n".join(body))
        dump.add(f"Categoria:NPCs de {t['name']}", f"NPCs de [[{t['name']}]].\n\n[[Categoria:NPCs]]")
        town_rows.append(f"[[{t['name']}]]")
    dump.add("Categoria:Cidades", "As cidades do VinOT, cada uma com mapa e NPCs.")
    floor_links = " · ".join(f"[[Arquivo:Mapa-andar-{z:02d}.png|andar {z - 7:+d}]]" if z != 7 else "[[Arquivo:Mapa-andar-07.png|superfície]]" for z in floors)
    dump.add("Mapa", "O mapa do VinOT desenhado direto do mapa do servidor, com as cores do automap do jogo.\n\n"
             "[[Arquivo:Mapa-mundo.png|1100px|Mapa do mundo]]\n\n"
             f"== Andares em tamanho real ==\nUm pixel por quadrado do jogo. {floor_links}\n\n"
             "== Cidades ==\n" + " · ".join(town_rows) + "\n\n[[Categoria:Cidades]]")

    dump.write(os.path.join(out, "pages-more.xml"))
    print(f"{len(dump.pages)} more pages: {len(sp)} spells/runes, {len(people)} NPCs, {len(qs)} quests, "
          f"{len(mounts)} mounts, {len(outfits)} outfits, {len(main_towns)} towns")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

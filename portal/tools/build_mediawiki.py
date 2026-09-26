"""Write the VinOT Wiki (MediaWiki) from the game files: one page per creature and per item, category
pages, templates and the main page, as a MediaWiki XML dump, plus the pictures named for the wiki.

    python tools/build_mediawiki.py OUT_DIR

OUT_DIR gets pages.xml (for maintenance/importDump.php), images/ (for maintenance/importImages.php)
and extra_items.txt (item ids without a picture yet, for build_wiki_sprites.py --extra-items).
Everything comes from the same data the portal wiki reads (app/wiki.py), so no page is written by hand.
"""

import datetime as dt
import os
import re
import shutil
import sys
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from app import wiki  # noqa: E402

SPRITES = os.path.join(HERE, "..", "app", "static", "wiki")

# primarytype in items.xml -> (category, group on the main page)
ITEM_CATS = {
    "sword weapons": ("Espadas", "Armas"), "axe weapons": ("Machados", "Armas"), "club weapons": ("Clavas", "Armas"),
    "distance weapons": ("Armas de distância", "Armas"), "ammunition": ("Munição", "Armas"), "quivers": ("Aljavas", "Armas"),
    "wands": ("Varinhas", "Armas"), "rods": ("Cajados", "Armas"), "exercise weapons": ("Armas de treino", "Armas"),
    "helmets": ("Capacetes", "Equipamentos"), "armors": ("Armaduras", "Equipamentos"), "legs": ("Calças", "Equipamentos"),
    "boots": ("Botas", "Equipamentos"), "shields": ("Escudos", "Equipamentos"), "spellbooks": ("Livros de magia", "Equipamentos"),
    "amulets and necklaces": ("Amuletos e colares", "Equipamentos"), "rings": ("Anéis", "Equipamentos"),
    "attack runes": ("Runas de ataque", "Consumíveis"), "healing runes": ("Runas de cura", "Consumíveis"),
    "support runes": ("Runas de suporte", "Consumíveis"), "liquids": ("Poções e líquidos", "Consumíveis"),
    "food": ("Comida", "Consumíveis"),
    "creature products": ("Produtos de criaturas", "Outros"), "valuables": ("Valiosos", "Outros"),
    "tools": ("Ferramentas", "Outros"), "containers": ("Recipientes", "Outros"), "light sources": ("Fontes de luz", "Outros"),
    "taming items": ("Itens de domar", "Outros"), "keys": ("Chaves", "Outros"), "magical items": ("Itens mágicos", "Outros"),
    "quest items": ("Itens de quest", "Outros"),
}
GROUPS = ["Armas", "Equipamentos", "Consumíveis", "Outros"]
SLOT_PT = {"two-handed": "Duas mãos", "right-hand": "Mão direita"}
SKILLS = [("skillsword", "espada"), ("skillaxe", "machado"), ("skillclub", "clava"), ("skilldist", "distância"),
          ("skillshield", "escudo"), ("skillfist", "punhos"), ("magiclevelpoints", "magic level")]
ABSORB = [("physical", "físico"), ("fire", "fogo"), ("ice", "gelo"), ("energy", "energia"), ("earth", "terra"),
          ("holy", "sagrado"), ("death", "morte"), ("drown", "afogamento"), ("lifedrain", "roubo de vida"), ("manadrain", "roubo de mana")]
IMMUNITY_PT = {"physical": "físico", "fire": "fogo", "ice": "gelo", "energy": "energia", "earth": "terra", "holy": "sagrado",
               "death": "morte", "drown": "afogamento", "lifedrain": "roubo de vida", "manadrain": "roubo de mana",
               "paralyze": "paralisia", "invisible": "invisibilidade", "outfit": "troca de roupa", "drunk": "embriaguez", "bleed": "sangramento"}
BAD_TITLE = re.compile(r"[#<>\[\]|{}_]")


def clean(title):
    t = BAD_TITLE.sub(" ", title).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:1].upper() + t[1:]


SMALL_WORDS = {"of", "the", "a", "an", "and", "in", "on", "to", "with", "from", "for", "at", "by"}


def title_case(name):
    """Item names in TibiaWiki style: "giant sword" -> "Giant Sword", "ring of healing" -> "Ring of Healing"."""
    return " ".join(w if (i and w.lower() in SMALL_WORDS) else w[:1].upper() + w[1:] for i, w in enumerate(name.split(" ")))


def infobox(name, img, size, rows, sub=None, subrows=None, banner=None):
    """The side box of a page, with only the rows that have a value."""
    out = ['<div class="vinot-infobox">', f'<div class="vinot-infobox-title">{name}</div>']
    if img:
        out.append(f'<div class="vinot-infobox-art">[[Arquivo:{img}|{size}px|link=]]</div>')
    if banner:
        out.append(f'<div class="vinot-boss">{banner}</div>')
    for head, table in ((None, rows), (sub, subrows or [])):
        table = [(k, v) for k, v in table if v not in (None, "", 0, "0")]
        if not table:
            continue
        if head:
            out.append(f'<div class="vinot-infobox-sub">{head}</div>')
        out.append('{| class="vinot-infobox-table"')
        for i, (k, v) in enumerate(table):
            if i:
                out.append("|-")
            out += [f"! {k}", f"| {v}"]
        out.append("|}")
    out.append("</div>")
    return "\n".join(out)


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def cell(v):
    return str(v).replace("|", "&#124;").replace("\n", " ")


class Dump:
    def __init__(self):
        self.pages = {}

    def add(self, title, text):
        self.pages[title] = text

    def write(self, path):
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11" xml:lang="pt-br">\n')
            for title, text in self.pages.items():
                css = title.endswith(".css")
                model, fmt = ("css", "text/css") if css else ("wikitext", "text/x-wiki")
                f.write(f"<page><title>{escape(title)}</title><revision><timestamp>{ts}</timestamp>"
                        f"<contributor><username>VinOT Bot</username></contributor><comment>Gerado dos arquivos do jogo</comment>"
                        f"<model>{model}</model><format>{fmt}</format>"
                        f'<text xml:space="preserve">{escape(text)}</text></revision></page>\n')
            f.write("</mediawiki>\n")


def main(out):
    d = wiki.data()
    items, creatures, drops = d["items"], d["creatures"], d["drops"]
    os.makedirs(os.path.join(out, "images"), exist_ok=True)
    dump = Dump()

    # ------------------------------------------------------------ which items get a page
    chosen = {}  # title -> item dict (first id wins; dropped ids first so loot links hit the right one)
    ordered = sorted(items.values(), key=lambda it: (it["id"] not in drops, it["id"]))
    for it in ordered:
        ptype = (it["attrs"].get("primarytype") or "").lower()
        if ptype not in ITEM_CATS and it["id"] not in drops:
            continue
        title = clean(title_case(it["name"]))
        if len(title) < 2:
            continue
        if title in chosen:
            chosen[title].setdefault("_other_ids", []).append(it["id"])
            continue
        chosen[title] = dict(it, _type=ptype, _label=title_case(it["name"]))
    creature_titles = {clean(c["name"]) for c in creatures}
    item_title = {}
    for title, it in list(chosen.items()):
        final = f"{title} (item)" if title in creature_titles else title
        item_title[it["id"]] = final
        for other in it.get("_other_ids", []):
            item_title[other] = final
        it["_title"] = final

    def item_link(iid, name=None):
        t = item_title.get(iid)
        label = title_case(name or (items[iid]["name"] if iid in items else f"item {iid}"))
        return f"[[{t}|{label}]]" if t else label

    def item_icon(iid):
        return f"[[Arquivo:Item-{iid}.png|32px|link={item_title.get(iid, '')}]]" if os.path.exists(os.path.join(SPRITES, "i", f"{iid}.png")) else ""

    # ------------------------------------------------------------ pictures
    for c in creatures:
        src = os.path.join(SPRITES, "c", c["slug"] + ".png")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(out, "images", f"Criatura-{c['slug']}.png"))
    missing = []
    for it in chosen.values():
        src = os.path.join(SPRITES, "i", f"{it['id']}.png")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(out, "images", f"Item-{it['id']}.png"))
        else:
            missing.append(it["id"])
    with open(os.path.join(out, "extra_items.txt"), "w") as f:
        f.write("\n".join(str(i) for i in sorted(missing)))

    # ------------------------------------------------------------ creature pages
    by_class = {}
    for c in creatures:
        title = clean(c["name"])
        el = c["elements"]
        img = f"Criatura-{c['slug']}.png" if os.path.exists(os.path.join(SPRITES, "c", c["slug"] + ".png")) else ""
        rows = [("Vida", wiki.fmt_int(c["health"])), ("Experiência", wiki.fmt_int(c["experience"])), ("Velocidade", c["speed"]),
                ("Armadura", c["armor"]), ("Defesa", c["defense"]),
                ("Classe", f"[[:Categoria:{c['class_pt']}|{c['class_pt']}]]" if c["class_pt"] else ""),
                ("Bestiário", f"{c['stars']} ★ · {wiki.fmt_int(c['to_kill'])} kills · {c['charms']} charms" if c["stars"] else ""),
                ("Paralisa?", "não" if c["paralyze_immune"] else "sim"),
                ("Invocável", f"{c['summon_cost']} mana" if c["summonable"] else ""),
                ("Convencível", f"{c['summon_cost']} mana" if c["convinceable"] else "")]
        dmg = [(pt, f"{100 - el.get(k, 0)}%") for k, pt in (("physical", "Físico"), ("fire", "Fogo"), ("ice", "Gelo"),
                                                            ("energy", "Energia"), ("earth", "Terra"), ("holy", "Sagrado"), ("death", "Morte"))]
        box = infobox(c["name"], img, 96, rows, "Dano recebido", dmg, banner="Boss" if c["boss"] else None)
        body = [box, "",
                f"'''{c['name']}''' é {'um boss' if c['boss'] else 'uma criatura'}"
                + (f" da classe [[:Categoria:{c['class_pt']}|{c['class_pt']}]]" if c["class_pt"] and not c["boss"] else "")
                + f" com {wiki.fmt_int(c['health'])} de vida que dá {wiki.fmt_int(c['experience'])} de experiência."]
        if c["voices"]:
            body += ["", "== Frases ==", *[f"* ''\"{v}\"''" for v in c["voices"]]]
        if c["melee"] or c["attacks"]:
            body += ["", "== Ataques =="]
            if c["melee"]:
                body.append(f"* Corpo a corpo: até '''{c['melee']}''' de dano.")
            for a in c["attacks"]:
                kind = a["element_pt"] or "Ataque"
                shape = " em área" if a["area"] else (" à distância" if a["range"] else "")
                body.append(f"* {kind}{shape}: de {a['min']} a '''{a['max']}''' de dano.")
        if c["immunities"]:
            body += ["", "== Imunidades ==", ", ".join(sorted({IMMUNITY_PT.get(i, i) for i in c["immunities"]})) + "."]
        if c["summons"]:
            body += ["", "== Invoca ==", ", ".join(f"[[{clean(s)}]]" for s in c["summons"]) + "."]
        if c["locations"]:
            body += ["", "== Onde encontrar ==", c["locations"], "", "''Nomes dos lugares como estão nos arquivos do jogo.''"]
        if c["loot"]:
            body += ["", "== Loot ==", '{| class="wikitable sortable vinot-loot"', "! !! Item !! Chance !! Quantidade"]
            for it in c["loot"]:
                qty = f"até {it['max']}" if it["max"] > 1 else "1"
                body += ["|-", f"| {item_icon(it['id'])} || {item_link(it['id'], it['name'])} || data-sort-value=\"{it['chance']}\" | {it['chance_pt']} ({wiki.RARITY_PT.get(it['rarity'], it['rarity'])}) || {qty}"]
            body.append("|}")
        cats = ["Criaturas"] + (["Bosses"] if c["boss"] else ([c["class_pt"]] if c["class_pt"] else []))
        body += [""] + [f"[[Categoria:{x}]]" for x in cats]
        dump.add(title, "\n".join(body))
        if not c["boss"] and c["class_pt"]:
            by_class[c["class_pt"]] = by_class.get(c["class_pt"], 0) + 1

    # ------------------------------------------------------------ item pages
    cat_count = {}
    for title, it in chosen.items():
        a = {k.lower(): v for k, v in it["attrs"].items()}
        cat, group = ITEM_CATS.get(it["_type"], ("Outros itens", "Outros"))
        cat_count[cat] = cat_count.get(cat, 0) + 1
        img = f"Item-{it['id']}.png" if os.path.exists(os.path.join(SPRITES, "i", f"{it['id']}.png")) else ""
        weight = num(a.get("weight"))
        bonus = [f"{pt} +{a[k]}" for k, pt in SKILLS if a.get(k)]
        prot = [f"{pt} {a['absorbpercent' + k]}%" for k, pt in ABSORB if a.get("absorbpercent" + k)]
        rows = [("Categoria", f"[[:Categoria:{cat}|{cat}]]"), ("Ataque", a.get("attack")),
                ("Defesa", (a.get("defense") or "") + (f" +{a['extradef']}" if a.get("extradef") else "")),
                ("Armadura", a.get("armor")), ("Alcance", a.get("range")), ("Empunhadura", SLOT_PT.get(a.get("slottype", ""), "")),
                ("Bônus", ", ".join(bonus)), ("Proteção", ", ".join(prot)), ("Imbuement", "sim" if a.get("imbuementslot") else ""),
                ("Capacidade", f"{a['containersize']} espaços" if a.get("containersize") else ""), ("Cargas", a.get("charges")),
                ("Peso", f"{weight / 100:.2f} oz".replace(".", ",") if weight else ""),
                ("ID", ", ".join(str(i) for i in [it["id"]] + it.get("_other_ids", [])))]
        box = infobox(it["_label"], img, 64, rows)
        body = [box, "", f"'''{it['_label']}''' é um item da categoria [[:Categoria:{cat}|{cat}]]."]
        if a.get("description"):
            body += ["", f"''{a['description']}''"]
        who = drops.get(it["id"], [])
        if who:
            body += ["", "== Dropado por ==", '{| class="wikitable sortable"', "! Criatura !! Chance !! Quantidade"]
            for slug, chance, mx in who:
                c = d["by_slug"][slug]
                body += ["|-", f"| [[{clean(c['name'])}]] || data-sort-value=\"{chance}\" | {wiki.fmt_chance(chance)} || {'até ' + str(mx) if mx > 1 else '1'}"]
            body.append("|}")
        body += ["", "[[Categoria:Itens]]", f"[[Categoria:{cat}]]"]
        dump.add(it["_title"], "\n".join(body))

    # ------------------------------------------------------------ categories
    for cls, n in by_class.items():
        dump.add(f"Categoria:{cls}", f"Criaturas da classe {cls} no VinOT.\n\n[[Categoria:Criaturas]]")
    dump.add("Categoria:Bosses", "Bosses do VinOT.\n\n[[Categoria:Criaturas]]")
    dump.add("Categoria:Criaturas", "Todas as criaturas do VinOT, com vida, experiência, fraquezas e loot.")
    dump.add("Categoria:Itens", "Todos os itens do VinOT que importam pra quem joga.")
    for key, (cat, group) in list(ITEM_CATS.items()) + [("", ("Outros itens", "Outros"))]:
        dump.add(f"Categoria:{cat}", f"{cat} do VinOT ({group.lower()}).\n\n[[Categoria:Itens]]")

    # ------------------------------------------------------------ templates and style
    dump.add("MediaWiki:Common.css", COMMON_CSS)
    dump.add("MediaWiki:Sidebar", SIDEBAR)

    # ------------------------------------------------------------ main page
    rows = []
    for group in GROUPS:
        cats = sorted({c for c, g in ITEM_CATS.values() if g == group and cat_count.get(c)})
        if group == "Outros" and cat_count.get("Outros itens"):
            cats.append("Outros itens")
        links = " · ".join(f"[[:Categoria:{c}|{c}]] ({cat_count[c]})" for c in cats)
        rows.append(f"=== {group} ===\n{links}")
    classes = " · ".join(f"[[:Categoria:{c}|{c}]] ({n})" for c, n in sorted(by_class.items()))
    main_page = MAIN_PAGE.format(creatures=len(creatures), items=len(chosen), classes=classes, items_rows="\n\n".join(rows),
                                 bosses=sum(1 for c in creatures if c["boss"]))
    dump.add("Página principal", main_page)

    dump.write(os.path.join(out, "pages.xml"))
    print(f"{len(dump.pages)} pages ({len(creatures)} creatures, {len(chosen)} items), "
          f"{len(os.listdir(os.path.join(out, 'images')))} pictures, {len(missing)} items without a picture")


COMMON_CSS = """/* VinOT Wiki */
:root { --vinot-gold: #c9962f; --vinot-red: #8c2a1f; }
.vinot-infobox { float: right; clear: right; width: 290px; margin: 0 0 1em 1.4em; border: 1px solid #c8ccd1; border-radius: 10px; background: #f8f9fa; overflow: hidden; font-size: 90%; }
.vinot-infobox-title { background: linear-gradient(90deg, var(--vinot-red), #5c1a12); color: #fff; font-weight: bold; text-align: center; padding: 8px; font-size: 115%; }
.vinot-infobox-art { text-align: center; padding: 12px; background: radial-gradient(closest-side, rgba(201,150,47,.25), transparent); }
.vinot-infobox-art img { image-rendering: pixelated; }
.vinot-infobox-sub { background: #eaecf0; font-weight: bold; text-align: center; padding: 4px; }
.vinot-infobox-table { width: 100%; border-collapse: collapse; }
.vinot-infobox-table th, .vinot-infobox-table td { padding: 4px 10px; border-top: 1px solid #eaecf0; text-align: left; }
.vinot-infobox-table th { width: 45%; color: #54595d; font-weight: 600; }
.vinot-boss { text-align: center; background: var(--vinot-red); color: #fff; font-weight: bold; padding: 3px; letter-spacing: .08em; }
.vinot-loot img, .mw-body img[src*="Item-"], .mw-body img[src*="Criatura-"] { image-rendering: pixelated; }
.vinot-home { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
.vinot-home > div { border: 1px solid #c8ccd1; border-radius: 10px; padding: 12px 16px; background: #f8f9fa; }
.vinot-home h2 { margin-top: 0; border-bottom: 2px solid var(--vinot-gold); }
@media screen { html.skin-theme-clientpref-night .vinot-infobox, html.skin-theme-clientpref-night .vinot-home > div { background: #202122; border-color: #54595d; } }
@media (max-width: 720px) { .vinot-infobox { float: none; width: auto; margin: 0 0 1em; } }
"""

SIDEBAR = """* navigation
** mainpage|Página principal
** Categoria:Criaturas|Criaturas
** Categoria:Bosses|Bosses
** Categoria:Itens|Itens
** randompage-url|Página aleatória
* Armas
** Categoria:Espadas|Espadas
** Categoria:Machados|Machados
** Categoria:Clavas|Clavas
** Categoria:Armas de distância|Distância
** Categoria:Varinhas|Varinhas
** Categoria:Cajados|Cajados
* Equipamentos
** Categoria:Capacetes|Capacetes
** Categoria:Armaduras|Armaduras
** Categoria:Calças|Calças
** Categoria:Botas|Botas
** Categoria:Escudos|Escudos
** Categoria:Amuletos e colares|Amuletos
** Categoria:Anéis|Anéis
* VinOT
** http://100.70.92.116:8091|Site do VinOT
** http://100.70.92.116:8091/baixar|Baixar o cliente
"""

MAIN_PAGE = """__NOTOC__
<div style="text-align:center; margin-bottom:1em">
[[Arquivo:Criatura-dragon.png|96px|link=Dragon]]
<div style="font-size:180%; font-weight:bold">Bem-vindo à Wiki do VinOT</div>
Tudo direto dos arquivos do servidor: {creatures} criaturas ({bosses} bosses) e {items} itens.
<inputbox>
type=search
width=40
buttonlabel=Buscar
placeholder=Buscar criatura ou item…
</inputbox>
</div>
<div class="vinot-home">
<div>
== Criaturas ==
[[:Categoria:Criaturas|Todas as criaturas]] · [[:Categoria:Bosses|Bosses]]

{classes}
</div>
<div>
== Itens ==
{items_rows}
</div>
</div>
"""

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mediawiki_out")
